"""CYPC Q3 update. CNY 100m, 100m ordinary shares, CNY/share; no FX/ADS.
Earlier files are read-only. Formula workbook has Python-computed caches.
"""
from pathlib import Path
import json,csv,datetime as dt,hashlib,math
import numpy as np
from scipy.optimize import brentq
import xlsxwriter
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'source/revaluation_20261120';OUT=ROOT/'extracted/revaluation_20261120'
OUT.mkdir(parents=True,exist_ok=True)
OLD=json.loads((ROOT/'extracted/revaluation_20261016/model_results.json').read_text())
ASOF=dt.date(2026,11,20)
I={
 'shares':244.68217716,'spot':31.62,'rf':.0165,'erp':.065,'r':.0575,'g':.0175,'payout':.70,
 'normal2027':355.,'normal2028':365.,'normal2029':372.,'normal2030':380.,
 'pe_low':18.5,'pe_high':21.,'yield_low':.035,'yield_high':.04,
 'revenue9m':630.5621486825,'np9m':263.4382852343,'core9m':263.6346287222,
 'npq3':115.8813374890,'coreq3':120.6943242818,
 'np25':345.0280917639,'np9m25':281.9287449495,'coreq425':52.3902824081,
 'interest25':95.0871871767,'interest9m25':72.5829900469,
 'interest9m26':62.1121888152,'interesth126':42.2907994089,
 'q4_volume_gain':10.,'after_tax_parent':.82,
 'consensus26':343.18,'consensus27':368.18,'consensus28':377.38,
 'cfo9m':403.4309106195,'capex9m':60.2811066149,'investment_cash9m':28.2032919796,
 'dividend25_paid':244.68217716,'div_interest_paid9m':308.0030411240,'minority_div_paid9m':.9554186404,
 'cash9m':94.5386086445,'short_debt9m':84.4373508529,'current_noncurrent9m':564.9712043753,
 'long_debt9m':1798.4365493045,'bonds9m':379.0991355254,'lease9m':5.2917166260,
 'scp_nominal':50.,'minority_equity9m':120.2188996994,'long_equity9m':760.8302503946,
}

def bridge():
 q4int25=I['interest25']-I['interest9m25']
 q4int26=I['interest9m26']-I['interesth126'] # Q3 run rate, not a company forecast.
 saving=(q4int25-q4int26)*I['after_tax_parent']
 q4core=I['coreq425']+I['q4_volume_gain']+saving
 core26=I['core9m']+q4core
 noncore9m=I['np9m']-I['core9m']
 return dict(q4int25=q4int25,q4int26=q4int26,q4_interest_saving=saving,q4core=q4core,core26=core26,noncore9m=noncore9m,np26=core26+noncore9m)
B=bridge()
PROFITS=[B['np26'],I['normal2027'],I['normal2028'],I['normal2029'],I['normal2030']]

def ddm(r=None,g=None,asof=None,profits=None):
 r=I['r'] if r is None else r;g=I['g'] if g is None else g;asof=ASOF if asof is None else asof
 profits=PROFITS if profits is None else profits
 if r-g<.02:raise ValueError('unstable terminal spread')
 rows=[]
 for y,p in zip(range(2026,2031),profits):
  d=p*I['payout']/I['shares'];t1=(dt.date(y+1,2,12)-asof).days/365.25;t2=(dt.date(y+1,7,17)-asof).days/365.25
  pv=d*(.21/(1+r)**t1+.79/(1+r)**t2)
  rows.append(dict(year=y,profit=p,dps=d,t1=t1,t2=t2,pv=pv))
 last=rows[-1];tv=last['dps']*(1+g)/(r-g)*(.21/(1+r)**last['t1']+.79/(1+r)**last['t2'])
 exp=sum(x['pv'] for x in rows)
 return dict(value=exp+tv,explicit=exp,terminal=tv,tv_share=tv/(exp+tv),rows=rows)

def history():
 allrows=[]
 for p in [1,2,3]:allrows+=json.loads((SRC/f'valuation_{p}.json').read_text())['result']['data']
 data=sorted({x['TRADE_DATE']:x for x in allrows}.values(),key=lambda x:x['TRADE_DATE'])
 ttm=I['np9m']+I['np25']-I['np9m25'];current_pe=I['spot']*I['shares']/ttm
 summary={}
 for tag,start in [('3y','2023-11-20'),('5y','2021-11-20')]:
  a=[x for x in data if start<=x['TRADE_DATE'][:10]<='2026-11-19'];v=np.array([x['PE_TTM'] for x in a]);ps=[1,5,10,25,50,75,85,90]
  summary[tag]=dict(n=len(a),first=a[0]['TRADE_DATE'][:10],last=a[-1]['TRADE_DATE'][:10],percentiles=dict(zip(map(str,ps),np.percentile(v,ps).tolist())),current_pe_percentile=float(np.mean(v<=current_pe)))
 with (OUT/'historical_valuation.csv').open('w') as f:
  keys=['TRADE_DATE','CLOSE_PRICE','PE_TTM','PE_LAR','PB_MRQ','TOTAL_SHARES'];w=csv.DictWriter(f,fieldnames=keys,extrasaction='ignore');w.writeheader();w.writerows(data)
 return summary,data,ttm,current_pe

H,HROWS,TTM,CURRENT_PE=history()
def beta():
 a=json.loads((SRC/'yahoo_600900.SS.json').read_text())['chart']['result'][0]
 stock={dt.datetime.fromtimestamp(t,dt.timezone(dt.timedelta(hours=8))).date().isoformat():v for t,v in zip(a['timestamp'],a['indicators']['adjclose'][0]['adjclose']) if v is not None}
 def weekly(series):
  w={}
  for d,v in sorted(series.items()):
   if d>='2026-11-16':continue # series stops at Nov 19, so omit the incomplete week.
   w[dt.date.fromisoformat(d).isocalendar()[:2]]=(d,float(v))
  return w
 b={};exports=[]
 for sym in ['sh000995','sh000300']:
  a=json.loads((SRC/f'tencent_{sym}.json').read_text())['data'][sym]['day']
  s,m=weekly(stock),weekly({x[0]:x[2] for x in a});keys=sorted(s.keys()&m.keys())
  x=np.array([s[k][1] for k in keys]);y=np.array([m[k][1] for k in keys]);rs=x[1:]/x[:-1]-1;rm=y[1:]/y[:-1]-1
  v=float(np.cov(rs,rm,ddof=1)[0,1]/np.var(rm,ddof=1));r2=float(np.corrcoef(rs,rm)[0,1]**2)
  b[sym]=dict(beta=v,r2=r2,n=len(rs),first=s[keys[0]][0],last=s[keys[-1]][0],mechanical_capm=I['rf']+v*I['erp'])
  exports.extend(dict(index=sym,date=s[k][0],stock_return=float(sx),index_return=float(mx)) for k,sx,mx in zip(keys[1:],rs,rm))
 with (OUT/'beta_weekly.csv').open('w') as f:
  w=csv.DictWriter(f,fieldnames=list(exports[0]));w.writeheader();w.writerows(exports)
 return b
BETAS=beta()
EPS=I['normal2027']/I['shares'];DPS=EPS*I['payout']
PE=[EPS*I['pe_low'],EPS*I['pe_high']];YIELD=[DPS/I['yield_high'],DPS/I['yield_low']]
FAIR=[max(PE[0],YIELD[0]),min(PE[1],YIELD[1])]
D=ddm()
REVERSE_R=brentq(lambda r:ddm(r,.0175)['value']-I['spot'],.04,.09)
REVERSE_G=brentq(lambda g:ddm(.0575,g)['value']-I['spot'],0,.035)
SENS=[dict(r=r,values=[ddm(r,g)['value'] for g in [.01,.0175,.025]]) for r in [.0475,.0525,.0575,.0625,.0675]]
# Scenario rules: bear uses historical low multiples only; bull uses realized peak NI,
# rather than assuming an unachieved 385 profit. Base remains forward normalized 355.
SCENARIOS={
 'bear':dict(profit=355.,pe=[H['5y']['percentiles']['1'],H['5y']['percentiles']['10']],reason='五年PE P1至P10，盈利保持355，仅压倍数'),
 'base':dict(profit=355.,pe=[18.5,21.],reason='同一正常化355，PE与要求股息率的交集'),
 'bull':dict(profit=I['np25'],pe=[H['5y']['percentiles']['75'],H['5y']['percentiles']['90']],reason='不超过已实现报表归母峰值345.03，PE P75至P90；溢价情景'),
}
for tag,x in SCENARIOS.items():
 x['eps']=x['profit']/I['shares'];x['dps']=x['eps']*I['payout'];x['values']=[x['eps']*p for p in x['pe']]
 if tag=='base':x['values']=FAIR
 x['implied_yields']=[x['dps']/v for v in reversed(x['values'])]
cash_interest=I['div_interest_paid9m']-I['dividend25_paid']-I['minority_div_paid9m']
CASH=dict(cash_interest=cash_interest,cfo_less_capex=I['cfo9m']-I['capex9m'],before_parent_div=I['cfo9m']-I['capex9m']+I['investment_cash9m']-cash_interest-I['minority_div_paid9m'])
CASH['after_parent_div']=CASH['before_parent_div']-I['dividend25_paid'];CASH['coverage']=CASH['before_parent_div']/I['dividend25_paid']
debt_four=sum(I[k] for k in ['short_debt9m','current_noncurrent9m','long_debt9m','bonds9m'])
DEBT=dict(four_categories=debt_four,net_four=debt_four-I['cash9m'],net_with_lease_scp=debt_four+I['lease9m']+I['scp_nominal']-I['cash9m'])
old_at_new_date=ddm(profits=[x['profit'] for x in OLD['ddm']['rows']])['value']
DRIFT=dict(old_ddm=OLD['ddm']['value'],date_effect=old_at_new_date-OLD['ddm']['value'],earnings_effect=D['value']-old_at_new_date,old_fair=OLD['fair'],new_fair=FAIR)
# Quotes agree on price; report close time comes from Yahoo, not capture time.
meta=json.loads((SRC/'yahoo_600900.SS.json').read_text())['chart']['result'][0]['meta']
tencent=(SRC/'quote_tencent.txt').read_bytes().decode('gbk').split('"')[1].split('~')
assert float(meta['regularMarketPrice'])==float(tencent[3])==I['spot']
QUOTE=dict(price=I['spot'],currency='CNY',security='600900.SH ordinary A share',market_time=dt.datetime.fromtimestamp(meta['regularMarketTime'],dt.timezone(dt.timedelta(hours=8))).isoformat(),tencent_time=tencent[30],type='regular session close',crosscheck='Yahoo chart metadata + Tencent')
(SRC/'market_snapshot.json').write_text(json.dumps(QUOTE,ensure_ascii=False,indent=2))
R=dict(asof=str(ASOF),inputs=I,bridge=B,eps=EPS,dps=DPS,fair=FAIR,center=sum(FAIR)/2,pe_range=PE,yield_range=YIELD,ddm=D,reverse_r=REVERSE_R,reverse_g=REVERSE_G,sensitivity=SENS,history=H,betas=BETAS,ttm_profit=TTM,current_pe=CURRENT_PE,scenarios=SCENARIOS,cash=CASH,debt=DEBT,drift=DRIFT,quote=QUOTE)
(OUT/'model_results.json').write_text(json.dumps(R,ensure_ascii=False,indent=2))
with (OUT/'dividends.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=list(D['rows'][0]));w.writeheader();w.writerows(D['rows'])

wb=xlsxwriter.Workbook(ROOT/'长江电力_估值更新模型_20261120.xlsx')
num=wb.add_format({'num_format':'0.0000'});pct=wb.add_format({'num_format':'0.00%'});blue=wb.add_format({'font_color':'#1466A4','num_format':'0.000000'});hdr=wb.add_format({'bold':True,'bg_color':'#E7DFCF'})
ws=wb.add_worksheet('说明');ws.set_column('A:A',25);ws.set_column('B:B',115)
for ri,content in enumerate([
 ['用途','2026Q3后更新；所有金额人民币亿元、股数亿股、每股人民币元。公式已缓存，输入可编辑。'],
 ['价格','600900.SH A股普通股；2026-11-20 15:00中国时间收盘人民币31.62元/股，Yahoo与腾讯交叉验证。'],
 ['主锚','2027前瞻正常化355；PE18.5至21倍与股息率3.5%至4.0%交集。参数沿用10月。'],
 ['DDM','r5.75%/g1.75%，2026利润改为三季报实际+Q4假设，未来年份保持旧路径。'],
 ['支付时间','未宣告年度股利21%次年2月12日、79%次年7月17日；只是假设，不是已确定方案。'],
 ['历史情景','熊：355×历史P1至P10；牛：已实现归母峰值×历史P75至P90。不得当作统计概率。'],
 ['限制','355未实现、未来来水/电价/税惠/再投资不确定；DDM终值依赖高；无获利概率。'],
 ['复算','scripts/revaluation_20261120.py；原文与来源见报告附录和source/revaluation_20261120/manifest.json'],
]):ws.write_row(ri,0,content)
ws=wb.add_worksheet('Inputs');ws.set_column('A:A',30);ws.set_column('B:B',22);ws.write_row(0,0,['输入参数','数值'],hdr);REF={}
for ri,(k,val) in enumerate(I.items(),2):ws.write(ri-1,0,k);ws.write_number(ri-1,1,val,blue);REF[k]=f'Inputs!$B${ri}'
def formula(ws,cell,s,value,fmt=num):ws.write_formula(cell,s,fmt,value)
ws=wb.add_worksheet('盈利桥');ws.set_column('A:A',40);ws.set_column('B:B',22);ws.write_row(0,0,['项目','人民币亿元'],hdr)
items=[
 ('2025Q4利息',f'={REF["interest25"]}-{REF["interest9m25"]}',B['q4int25']),
 ('2026Q4利息按Q3运行',f'={REF["interest9m26"]}-{REF["interesth126"]}',B['q4int26']),
 ('Q4税后归母利息增量',f'=(B2-B3)*{REF["after_tax_parent"]}',B['q4_interest_saving']),
 ('Q4持续归母预测',f'={REF["coreq425"]}+{REF["q4_volume_gain"]}+B4',B['q4core']),
 ('全年持续归母',f'={REF["core9m"]}+B5',B['core26']),
 ('已实现非经常净损益',f'={REF["np9m"]}-{REF["core9m"]}',B['noncore9m']),
 ('全年归母预测','=B6+B7',B['np26']),
]
for ri,(label,expr,value) in enumerate(items,2):ws.write(ri-1,0,label);formula(ws,f'B{ri}',expr,value)
ws=wb.add_worksheet('DDM');ws.set_column('A:F',22);ws.write_row(0,0,['利润年度','归母亿元','DPS元每股','中期支付年距','末期支付年距','现值元每股'],hdr)
refs=['盈利桥!B8',REF['normal2027'],REF['normal2028'],REF['normal2029'],REF['normal2030']]
for ri,(x,ref) in enumerate(zip(D['rows'],refs),2):
 ws.write(ri-1,0,x['year']);formula(ws,f'B{ri}','='+ref,x['profit']);formula(ws,f'C{ri}',f'=B{ri}*{REF["payout"]}/{REF["shares"]}',x['dps'])
 formula(ws,f'D{ri}',f'=(DATE(A{ri}+1,2,12)-DATE(2026,11,20))/365.25',x['t1']);formula(ws,f'E{ri}',f'=(DATE(A{ri}+1,7,17)-DATE(2026,11,20))/365.25',x['t2'])
 formula(ws,f'F{ri}',f'=C{ri}*(0.21/(1+{REF["r"]})^D{ri}+0.79/(1+{REF["r"]})^E{ri})',x['pv'])
ws.write('A9','显性现值');formula(ws,'B9','=SUM(F2:F6)',D['explicit'])
ws.write('A10','终值现值');formula(ws,'B10',f'=C6*(1+{REF["g"]})/({REF["r"]}-{REF["g"]})*(0.21/(1+{REF["r"]})^D6+0.79/(1+{REF["r"]})^E6)',D['terminal'])
ws.write('A11','DDM合计');formula(ws,'B11','=B9+B10',D['value']);ws.write('A12','终值占比');formula(ws,'B12','=B10/B11',D['tv_share'],pct)
ws=wb.add_worksheet('主锚');ws.set_column('A:A',35);ws.set_column('B:C',22);ws.write_row(0,0,['项目','下界/值','上界'],hdr)
ws.write('A2','正常化EPS');formula(ws,'B2',f'={REF["normal2027"]}/{REF["shares"]}',EPS)
ws.write('A3','正常化DPS');formula(ws,'B3',f'=B2*{REF["payout"]}',DPS)
ws.write('A4','PE估值');formula(ws,'B4',f'=B2*{REF["pe_low"]}',PE[0]);formula(ws,'C4',f'=B2*{REF["pe_high"]}',PE[1])
ws.write('A5','股息率估值');formula(ws,'B5',f'=B3/{REF["yield_high"]}',YIELD[0]);formula(ws,'C5',f'=B3/{REF["yield_low"]}',YIELD[1])
ws.write('A6','两法交集');formula(ws,'B6','=MAX(B4,B5)',FAIR[0]);formula(ws,'C6','=MIN(C4,C5)',FAIR[1])
ws.write('A7','中枢');formula(ws,'B7','=AVERAGE(B6:C6)',sum(FAIR)/2)
ws.write('A8','2026预测DPS');formula(ws,'B8',f'=盈利桥!B8*{REF["payout"]}/{REF["shares"]}',D['rows'][0]['dps'])
ws.write('A9','正常化股息率');formula(ws,'B9',f'=B3/{REF["spot"]}',DPS/I['spot'],pct)
ws.write('A10','中枢/现价-1');formula(ws,'B10',f'=B7/{REF["spot"]}-1',sum(FAIR)/2/I['spot']-1,pct)
ws=wb.add_worksheet('敏感性');ws.set_column('A:D',22);ws.write_row(0,0,['r / g',.01,.0175,.025],hdr)
for ri,x in enumerate(SENS,2):
 ws.write_number(ri-1,0,x['r'],pct)
 for ci,v in enumerate(x['values'],1):
  col=xlsxwriter.utility.xl_col_to_name(ci)
  expr=f'=SUMPRODUCT(DDM!C2:C6,0.21/(1+$A{ri})^DDM!D2:D6+0.79/(1+$A{ri})^DDM!E2:E6)+DDM!C6*(1+{col}$1)/($A{ri}-{col}$1)*(0.21/(1+$A{ri})^DDM!D6+0.79/(1+$A{ri})^DDM!E6)'
  formula(ws,f'{col}{ri}',expr,v)
ws=wb.add_worksheet('三档');ws.set_column('A:F',23);ws.write_row(0,0,['情景','归母亿元','PE低','PE高','每股低','每股高'],hdr)
for ri,(tag,x) in enumerate(SCENARIOS.items(),2):
 ws.write(ri-1,0,tag);ws.write_number(ri-1,1,x['profit']);ws.write_number(ri-1,2,x['pe'][0]);ws.write_number(ri-1,3,x['pe'][1])
 expr_low='=主锚!B6' if tag=='base' else f'=B{ri}/{REF["shares"]}*C{ri}'
 expr_high='=主锚!C6' if tag=='base' else f'=B{ri}/{REF["shares"]}*D{ri}'
 formula(ws,f'E{ri}',expr_low,x['values'][0]);formula(ws,f'F{ri}',expr_high,x['values'][1])
ws=wb.add_worksheet('现金流核对');ws.set_column('A:A',45);ws.set_column('B:B',23);ws.write_row(0,0,['项目','人民币亿元/倍'],hdr)
cashitems=[('推算现金付息',f'={REF["div_interest_paid9m"]}-{REF["dividend25_paid"]}-{REF["minority_div_paid9m"]}',CASH['cash_interest']),('CFO减现金capex',f'={REF["cfo9m"]}-{REF["capex9m"]}',CASH['cfo_less_capex']),('扣资本开支利息及少数股东分红后',f'=B3+{REF["investment_cash9m"]}-B2-{REF["minority_div_paid9m"]}',CASH['before_parent_div']),('再扣母公司已付股利',f'=B4-{REF["dividend25_paid"]}',CASH['after_parent_div']),('支付覆盖倍数',f'=B4/{REF["dividend25_paid"]}',CASH['coverage'])]
for ri,(label,expr,value) in enumerate(cashitems,2):ws.write(ri-1,0,label);formula(ws,f'B{ri}',expr,value)
ws=wb.add_worksheet('历史PE');ws.set_column('A:A',21);ws.set_column('B:D',18);ws.write_row(0,0,['日期','收盘元每股','PE TTM','PB MRQ'],hdr)
for ri,x in enumerate(HROWS,1):ws.write_row(ri,0,[x['TRADE_DATE'][:10],x['CLOSE_PRICE'],x['PE_TTM'],x['PB_MRQ']])
for ws in wb.worksheets():ws.freeze_panes(1,0)
wb.close()
print(json.dumps({k:R[k] for k in ['bridge','fair','center','ddm','drift','scenarios','cash','debt','quote','betas']},ensure_ascii=False,indent=2))
