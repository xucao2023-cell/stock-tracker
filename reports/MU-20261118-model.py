"""Micron revaluation, 2026-11-18. USD billions; shares billions.

Primary: explicit cycle FCFF plus normalized NOPAT times an exit EV/NOPAT.
DCF uses the identical normalized operating profit; no analyst target prices.
All market inputs are saved snapshots. Run also writes an auditable workbook.
"""
from pathlib import Path
import csv
import datetime as dt
import json
import math
import statistics
from scipy.optimize import brentq
import xlsxwriter

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'source/revaluation_20261118'
OUT = ROOT / 'extracted/revaluation_20261118'
OUT.mkdir(exist_ok=True)
ASOF = dt.date(2026, 11, 18)
SHARES, TAX, RF, ERP = 1.15, .155, .04953, .045
load = lambda p: json.loads(p.read_text())
facts = load(SRC / 'sec_companyfacts.json')['facts']['us-gaap']

def fact(tag, year, instant=False, unit=None):
    units = facts[tag]['units']
    values = units[unit] if unit else next(iter(units.values()))
    frame = f'CY{year}' + ('Q3I' if instant else '')
    match = [v for v in values if v.get('frame') == frame]
    assert match, (tag, year)
    return match[-1]['val']

history = []
for y in range(2021, 2027):
    rev = fact('RevenueFromContractWithCustomerExcludingAssessedTax', y) / 1e9
    op = fact('OperatingIncomeLoss', y) / 1e9
    gp = fact('GrossProfit', y) / 1e9
    history.append(dict(year=y, revenue=rev, grossProfit=gp, ebit=op,
                        netIncome=fact('NetIncomeLoss', y)/1e9,
                        dilutedEPS=fact('EarningsPerShareDiluted', y, unit='USD/shares'),
                        grossMargin=gp/rev, operatingMargin=op/rev))
NORMAL_MARGIN = statistics.mean(v['operatingMargin'] for v in history[1:])
NORMAL_GM = statistics.mean(v['grossMargin'] for v in history[1:])
NORMAL_REVENUE = 240.0

def chart(name):
    return load(SRC / name)['chart']['result'][0]

series = {}
for sym in ['MU', 'SPY', 'SOXX']:
    c = chart(f'weekly_{sym}.json')
    series[sym] = {dt.datetime.fromtimestamp(t, dt.timezone.utc).date(): p
                   for t, p in zip(c['timestamp'], c['indicators']['adjclose'][0]['adjclose'])
                   if p and dt.datetime.fromtimestamp(t, dt.timezone.utc).date() <= dt.date(2026,11,9)}
dates = sorted(set.intersection(*(set(s) for s in series.values())))
returns = {sym: [s[b]/s[a]-1 for a,b in zip(dates, dates[1:])] for sym,s in series.items()}
betas = {}
for count in [104,156]:
    betas[str(count)] = {}
    for bench in ['SPY','SOXX']:
        x,y = returns[bench][-count:], returns['MU'][-count:]
        assert len(x) == len(y) == count
        cov = statistics.covariance(x,y)
        betas[str(count)][bench] = dict(beta=cov/statistics.variance(x),
            r2=cov**2/statistics.variance(x)/statistics.variance(y), n=count,
            firstReturnWeek=str(dates[-count]), lastCompleteWeek=str(dates[-1]))
BETA = betas['156']['SPY']['beta']
quote = chart('quote_MU.json')['meta']
PRICE = quote['regularMarketPrice']
fx = load(SRC/'fx_EURUSD.json')
FX = fx['rates']['USD']
assert fx['base']=='EUR' and quote['symbol']=='MU' and quote['currency']=='USD'
KE = RF+BETA*ERP
DEBT, KD = .491+4.688, .052
WACC_EXACT = (PRICE*SHARES*KE + DEBT*KD*(1-TAX))/(PRICE*SHARES+DEBT)
WACC = .171
TNX = chart('quote_TNX.json')['meta']
assert abs(TNX['regularMarketPrice']/100-RF)<.0025  # cache retained under rule

# Remove pre-existing taxes once; future NOPAT taxes only cover future income.
# Current amount is income AND other tax: conservative gross proxy, no maturity PV.
BRIDGE = dict(cash=38.364, shortInvestments=5.070, longInvestments=30.019,
              currentDebt=.491, longDebt=4.688, refundableCustomerDeposits=12.747,
              currentIncomeAndOtherTaxes=5.626, noncurrentIncomeTaxes=9.820)
NET_CASH = sum(BRIDGE[k] for k in ['cash','shortInvestments','longInvestments']) - sum(
    BRIDGE[k] for k in ['currentDebt','longDebt','refundableCustomerDeposits',
                        'currentIncomeAndOtherTaxes','noncurrentIncomeTaxes'])
# Trade NWC includes customer rebates, excludes capex creditors and all tax payable.
NWC0 = 36.197+10.372-3.518-4.447-.396-4.386
NWC_RATIO = NWC0/133.188
BASE = dict(revenue=[260,280,240,220,230,240],
            opm=[(260*.86-11)/260,(280*.82-14)/280,(240*.68-16)/240,.45,.32,NORMAL_MARGIN],
            da=[12,16,20,24,26,28], capex=[55,60,60,50,44,38])
GROWTH = dict(revenue=[260,280,280,280,270,260,250,240],
              opm=[BASE['opm'][0],BASE['opm'][1],.60,.50,.45,.40,.30,NORMAL_MARGIN],
              da=[12,16,20,24,26,28,30,32], capex=[55,60,65,60,55,50,44,40])

def calculate(path=BASE, multiple=12., r=WACC, dated=True, method='exit',
              normal_margin=NORMAL_MARGIN, normal_revenue=NORMAL_REVENUE,
              nwc=NWC_RATIO, net_cash=NET_CASH, g=.03, roic=.15):
    rows=[]; previous=133.188
    for i,(rev,margin,da,capex) in enumerate(zip(path['revenue'],path['opm'],path['da'],path['capex'])):
        y=2027+i
        end=dt.date(y,8,31)  # modelling fiscal-end proxy, NOT announced exact calendar
        t=(end-ASOF).days/365.25 if dated else i+1
        # The normalization year uses the same profit as the terminal model.
        if i==len(path['revenue'])-1:
            rev,margin=normal_revenue,normal_margin
        ebit=rev*margin; nopat=ebit*(1-TAX)
        dnwc=(rev-previous)*nwc
        fcff=nopat+da-capex-dnwc
        factor=(1+r)**(-t)
        rows.append(dict(year=y,endProxy=str(end),t=t,revenue=rev,operatingMargin=margin,
                         ebit=ebit,nopat=nopat,da=da,netCashCapex=capex,dnwc=dnwc,
                         fcff=fcff,discountFactor=factor,pv=fcff*factor))
        previous=rev
    normal_nopat=normal_revenue*normal_margin*(1-TAX)
    next_fcff=normal_nopat*(1+g)*(1-g/roic)
    tv=normal_nopat*multiple if method=='exit' else next_fcff/(r-g)
    pv_tv=tv*rows[-1]['discountFactor']
    pv_fcff=sum(x['pv'] for x in rows)
    ev=pv_fcff+pv_tv; equity=ev+net_cash; usd=equity/SHARES
    return dict(rows=rows,normalizedRevenue=normal_revenue,normalizedOperatingMargin=normal_margin,
                normalizedNOPAT=normal_nopat,normalizedCoreEPS=normal_nopat/SHARES,
                multiple=multiple if method=='exit' else None,method=method,r=r,g=g,incrementalROIC=roic,
                terminalFCFF=next_fcff,terminalValue=tv,pvExplicit=pv_fcff,pvTerminal=pv_tv,
                enterpriseValue=ev,netCash=net_cash,equityValue=equity,usdPerShare=usd,
                eurPerShare=usd/FX,terminalShare=pv_tv/ev)

# Historical EV/NOPAT snapshots. FY21 investments verified in FY22 10-K p53.
dc=chart('daily_MU.json')
daily={dt.datetime.fromtimestamp(t,dt.timezone.utc).date():p
       for t,p in zip(dc['timestamp'],dc['indicators']['quote'][0]['close']) if p}
hist_bal={2021:('2021-09-02',.870+1.765),2022:('2022-09-01',1.069+1.647),
          2023:('2023-08-31',1.017+.844),2024:('2024-08-29',1.065+1.046),
          2025:('2025-08-28',.665+1.629),2026:('2026-09-03',5.070+30.019)}
hist_multiples=[]
for h in history:
    y=h['year']; date,invest=hist_bal[y]; price=daily[dt.date.fromisoformat(date)]
    shares=fact('CommonStockSharesOutstanding',y,True)/1e9
    cash=fact('CashAndCashEquivalentsAtCarryingValue',y,True)/1e9
    debt=(fact('DebtCurrent',y,True)+fact('LongTermDebtAndCapitalLeaseObligations',y,True))/1e9
    ev=price*shares+debt-cash-invest
    if y==2026: ev+=12.747+5.626+9.820 # current bridge comparable, historical other tax not added
    hist_multiples.append(dict(year=y,date=date,price=price,shares=shares,cash=cash,investments=invest,
        debt=debt,ev=ev,nopat=h['ebit']*(1-TAX),evNopat=ev/(h['ebit']*(1-TAX)) if h['ebit']>0 else None,
        role='ordinary positive-cycle reference' if y in [2021,2022,2025] else 'loss/trough/supercycle diagnostic'))
LOW_MULTIPLE=min(x['evNopat'] for x in hist_multiples if x['year'] in [2021,2022,2025])
HIGH_MULTIPLE=max(x['evNopat'] for x in hist_multiples if x['year'] in [2021,2022,2025])
hist_median=statistics.median(x['evNopat'] for x in hist_multiples if x['year'] in [2021,2022,2025])
results=dict(H_low=calculate(multiple=10),base=calculate(),H_high=calculate(multiple=14),
             Z_low=calculate(multiple=LOW_MULTIPLE),Z_high=calculate(GROWTH,multiple=HIGH_MULTIPLE),
             dcf=calculate(method='dcf'))

# A measured news stress, with unchanged exit multiple and long-run profitability.
news_path={k:list(v) for k,v in BASE.items()}
for i in [0,1]:
    rev=BASE['revenue'][i]; old_opex=rev*(1-BASE['opm'][i]) # derive GM separately below
    gm=[.86,.82][i]-.05; opex=[11,14][i]
    news_path['revenue'][i]=rev*.9
    news_path['opm'][i]=(rev*.9*gm-opex)/(rev*.9)
results['operating_stress']=calculate(news_path)
sens=[dict(r=r,multiple=m,usd=calculate(r=r,multiple=m)['usdPerShare'],
           eur=calculate(r=r,multiple=m)['eurPerShare'])
      for r in [.161,.171,.181] for m in [10,12,14]]
margin_sens=[dict(margin=m,usd=calculate(normal_margin=m)['usdPerShare'],
                  eur=calculate(normal_margin=m)['eurPerShare']) for m in
             [statistics.mean(h['operatingMargin'] for h in history[:5]),NORMAL_MARGIN,history[4]['operatingMargin']]]
revenue_sens=[dict(revenue=v,usd=calculate(normal_revenue=v)['usdPerShare']) for v in [160,200,240,280]]
reverse=dict(priceUSD=PRICE,priceEUR=PRICE/FX,
             requiredExitMultiple=brentq(lambda m:calculate(multiple=m)['usdPerShare']-PRICE,1,100),
             requiredNormalMargin=brentq(lambda m:calculate(normal_margin=m)['usdPerShare']-PRICE,.01,.9),
             impliedPrimaryR=brentq(lambda r:calculate(r=r)['usdPerShare']-PRICE,.031,.5),
             impliedDcfR=brentq(lambda r:calculate(r=r,method='dcf')['usdPerShare']-PRICE,.031,.5))

old=load(ROOT/'extracted/MU_重估计算_20261015.json')
oldpath=old['scenarios']['Base']
def old_calc(r=.11,nwc=old['nwc_ratio'],net=55.527):
    prev=133.188;pv=0
    for i in range(10):
        rev=oldpath['revenue'][i];nop=(rev*oldpath['gm'][i]-oldpath['opex'][i])*(1-TAX)
        fc=nop+oldpath['da'][i]-oldpath['capex'][i]-(rev-prev)*nwc
        pv+=fc/(1+r)**(i+1);prev=rev
    tv=nop*1.03*.8/(r-.03)/(1+r)**10
    return (pv+tv+net)/SHARES
bridge=[dict(step='2026-10-15 base DCF',usd=old_calc()),
        dict(step='Recomputed beta / WACC only',usd=old_calc(r=WACC)),
        dict(step='Operating NWC only',usd=old_calc(r=WACC,nwc=NWC_RATIO)),
        dict(step='Existing tax liabilities only',usd=old_calc(r=WACC,nwc=NWC_RATIO,net=NET_CASH)),
        dict(step='Six-year cycle / normalized earnings / capex, DCF',usd=calculate(method='dcf',dated=False)['usdPerShare']),
        dict(step='Primary normalized-profit exit at 12x',usd=calculate(dated=False)['usdPerShare']),
        dict(step='Discount dates to 2026-11-18',usd=results['base']['usdPerShare'])]
for i,x in enumerate(bridge):x['deltaUSD']=x['usd']-bridge[i-1]['usd'] if i else 0
old_site=dict(H_USD=[750,1050],Z_USD=[448.2149788074846,1611.7027347191943],
              centerUSD=900,fx=1.1172,H_EUR=[671.32,939.85],Z_EUR=[401,1442.89])
data=dict(version='2026-11-18',units='USD billions; shares billions; USD/EUR per ordinary share',
    valuationDate=str(ASOF),latestFinancialPeriod='FY2026 ended 2026-09-03; released 2026-09-30; 10-K 2026-10-09',
    shares=SHARES,tax=TAX,rf=RF,rfCacheDate='2026-10-22',newTnx=TNX,
    erp=ERP,erpReference=.0441,erpReferenceDate='2026-11-01',betas=betas,ke=KE,waccExact=WACC_EXACT,wacc=WACC,
    quote=quote,fx=fx,bridgeInputs=BRIDGE,netCash=NET_CASH,nwc0=NWC0,nwcRatio=NWC_RATIO,
    historicalFinancials=history,historicalMultiples=hist_multiples,historicalReferenceMedian=hist_median,
    normalMargin=NORMAL_MARGIN,normalGrossMargin=NORMAL_GM,normalRevenue=NORMAL_REVENUE,
    basePath=BASE,growthPath=GROWTH,results=results,sensitivity=sens,normalMarginSensitivity=margin_sens,
    normalRevenueSensitivity=revenue_sens,reverse=reverse,oldNewBridge=bridge,oldSite=old_site,
    operatingNewsStress='FY27/28 revenue -10%, gross margin -5 percentage points; same capex/exit/normal profitability',
    legalCashSensitivity=[dict(lossUSD_billion=l,deltaUSD_perShare=l/(1+WACC)/SHARES) for l in [1,5,10]],
    lowConfidence=['Normalized USD240bn revenue; not a verified bit-volume/ASP model',
      'Five-year mean includes FY26 supercycle and FY23 inventory write-down; regime shift unresolved',
      'Sparse fiscal-end historical EV/NOPAT observations, no continuous forward-multiple percentile',
      'Post-FY28 capex ramp-down unconfirmed; deposits/tax gross liability deductions and mature timing approximate',
      'SCA segment margins / floor prices / quarterly cash-flow conversion not public',
      'BIS full rule / Micron customer exposure and litigation loss range not yet quantified',
      'No calibrated 12-month win probability; historical beta not constant business beta'],
    checklistFullyPassed=False)
(OUT/'valuation_model.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
with (OUT/'cashflows.csv').open('w',newline='') as f:
    fields=['scenario']+list(results['base']['rows'][0]);w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
    for name,res in results.items():
        for row in res['rows']:w.writerow(dict(scenario=name,**row))

# A compact formula workbook with Python-checked cached values.
book=xlsxwriter.Workbook(ROOT/'美光_重新估值模型_20261118.xlsx')
head=book.add_format({'bold':True,'bg_color':'#16324f','font_color':'white'})
num=book.add_format({'num_format':'0.000'});pct=book.add_format({'num_format':'0.00%'})
inp=book.add_format({'font_color':'#1767a4','num_format':'0.000'})
ws=book.add_worksheet('Inputs');ws.set_column('A:A',40);ws.set_column('B:B',20);ws.set_column('C:C',85)
ws.write_row(0,0,['Input: USD bn / shares bn','Value','Source / meaning'],head)
inputs=[('Valuation date serial',float((ASOF-dt.date(1899,12,30)).days),'2026-11-18'),
        ('Shares',SHARES,'Q4 FY26 deck: FQ1 FY27 guided diluted shares'),('Tax',TAX,'FY27 guidance'),
        ('WACC',WACC,'156 complete weekly returns vs SPY; USD CAPM'),('USD per EUR',FX,'ECB/Frankfurter '+fx['date']),
        ('NWC ratio',NWC_RATIO,'Trade NWC; exclude tax and equipment creditors'),('Opening revenue',133.188,'FY26 10-K p67'),
        ('Net cash after taxes/deposits',NET_CASH,'Bridge in JSON/report'),('Normalized revenue',NORMAL_REVENUE,'Self forecast'),
        ('Normalized operating margin',NORMAL_MARGIN,'FY22-FY26 simple annual mean'),('Terminal growth',.03,'DCF only, assumption'),
        ('Terminal incremental ROIC',.15,'DCF only, assumption')]
for i,(label,value,source) in enumerate(inputs,1):ws.write(i,0,label);ws.write_number(i,1,value,inp);ws.write(i,2,source)
for name,res in results.items():
    sh=book.add_worksheet(name[:31]);sh.set_column('A:M',16)
    sh.write_row(0,0,['Fiscal year','Revenue','EBIT margin','EBIT','NOPAT','D&A','Cash capex','Delta NWC','FCFF','t (years)','PV FCFF','Date serial'],head)
    for i,row in enumerate(res['rows'],1):
        k=i+1;sh.write_number(i,0,row['year']);sh.write_number(i,1,row['revenue'],inp);sh.write_number(i,2,row['operatingMargin'],pct)
        for col,formula,value in [(3,f'=B{k}*C{k}',row['ebit']),(4,f'=D{k}*(1-Inputs!$B$4)',row['nopat']),
           (7,f'=(B{k}-'+('Inputs!$B$8' if i==1 else f'B{k-1}')+')*Inputs!$B$7',row['dnwc']),
           (8,f'=E{k}+F{k}-G{k}-H{k}',row['fcff']),
           (9,f'=(L{k}-Inputs!$B$2)/365.25',row['t']),
           (10,f'=I{k}/(1+Inputs!$B$5)^J{k}',row['pv'])]:sh.write_formula(i,col,formula,num,value)
        sh.write_number(i,5,row['da'],inp);sh.write_number(i,6,row['netCashCapex'],inp)
        sh.write_number(i,11,float((dt.date.fromisoformat(row['endProxy'])-dt.date(1899,12,30)).days))
    n=len(res['rows']);sh.write('A12','Exit multiple');sh.write_number('B12',res['multiple'] or 0,inp)
    sh.write('A13','Normalized NOPAT');sh.write_formula('B13','=Inputs!B10*Inputs!B11*(1-Inputs!B4)',num,res['normalizedNOPAT'])
    sh.write('A14','PV explicit');sh.write_formula('B14',f'=SUM(K2:K{n+1})',num,res['pvExplicit'])
    sh.write('A15','PV terminal')
    tv_formula='B13*B12' if res['method']=='exit' else 'B13*(1+Inputs!B12)*(1-Inputs!B12/Inputs!B13)/(Inputs!B5-Inputs!B12)'
    sh.write_formula('B15',f'=({tv_formula})/(1+Inputs!B5)^J{n+1}',num,res['pvTerminal'])
    for cell,label,formula,key in [('B16','Equity','=B14+B15+Inputs!B9','equityValue'),
       ('B17','USD/share','=B16/Inputs!B3','usdPerShare'),('B18','EUR/share','=B17/Inputs!B6','eurPerShare'),
       ('B19','Terminal share','=B15/(B14+B15)','terminalShare')]:
        sh.write('A'+cell[1:],label);sh.write_formula(cell,formula,pct if key=='terminalShare' else num,res[key])
    sh.freeze_panes(1,1)
book.close()
assert math.isclose(bridge[0]['usd'],825.1009977393221,rel_tol=1e-12)
assert results['Z_low']['eurPerShare'] < results['H_low']['eurPerShare'] < results['base']['eurPerShare'] < results['H_high']['eurPerShare'] < results['Z_high']['eurPerShare']
assert results['base']['normalizedCoreEPS'] < history[-1]['dilutedEPS']
print(json.dumps({'results':{k:{a:v[a] for a in ['usdPerShare','eurPerShare','pvExplicit','pvTerminal','terminalShare']} for k,v in results.items()},
                  'normalMargin':NORMAL_MARGIN,'netCash':NET_CASH,'waccExact':WACC_EXACT,
                  'reverse':reverse,'bridge':bridge},ensure_ascii=False,indent=2))
