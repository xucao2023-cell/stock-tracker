"""Reproduce the user-selected old-path DCF correction. USD bn / bn shares.
No network. Standalone usage:
 python revalue_corrected_20261119.py --inputs old-model.json --fx valuation-fx.json --output corrected-model.json
"""
import argparse,json,math
from pathlib import Path

TAX=.155; SHARES=1.15; REVENUE0=133.188
NWC_RATIO=(36.197+10.372-3.518-4.447-.396-4.386)/REVENUE0
NET_CASH=38.364+5.070+30.019-.491-4.688-12.747-5.626-9.820

def calc(s,r=.11,g=None,gm_shift=0):
    g=s['g'] if g is None else g
    rows=[];prev=REVENUE0
    for i,rev in enumerate(s['revenue']):
        gm=s['gm'][i]+(gm_shift if i>=2 else 0)
        ebit=rev*gm-s['opex'][i];nopat=ebit*(1-TAX)
        dnwc=(rev-prev)*NWC_RATIO;fcff=nopat+s['da'][i]-s['capex'][i]-dnwc
        rows.append(dict(year=2027+i,revenue=rev,gm=gm,opex=s['opex'][i],ebit=ebit,nopat=nopat,
                         da=s['da'][i],capex=s['capex'][i],dnwc=dnwc,fcff=fcff,
                         discountFactor=1/(1+r)**(i+1),pv=fcff/(1+r)**(i+1)))
        prev=rev
    multiple=(1+g)*(1-g/s['roic'])/(r-g)
    terminal=rows[-1]['nopat']*multiple
    pvterminal=terminal/(1+r)**10;pv=sum(x['pv'] for x in rows);ev=pv+pvterminal
    return dict(rows=rows,wacc=r,g=g,roic=s['roic'],terminalNOPAT=rows[-1]['nopat'],
                terminalFCFF=rows[-1]['nopat']*(1+g)*(1-g/s['roic']),terminalMultiple=multiple,
                terminal=terminal,pvExplicit=pv,pvTerminal=pvterminal,ev=ev,netCash=NET_CASH,
                equity=ev+NET_CASH,shares=SHARES,usdPerShare=(ev+NET_CASH)/SHARES,terminalShare=pvterminal/ev)

def build_model(old,fx,market_price_usd=None):
    scenarios=old['scenarios'];results={k:calc(s) for k,s in scenarios.items()}
    sensitivity={str(r):calc(scenarios['Base'],r) for r in [.10,.11,.12,.1357,.1551,.171]}
    raw={'low1':sensitivity['0.12']['usdPerShare'],'high1':sensitivity['0.1']['usdPerShare'],
         'low2':results['Bear']['usdPerShare'],'high2':results['Bull']['usdPerShare'],
         'base':results['Base']['usdPerShare'],'dcf':results['Base']['usdPerShare']}
    assert abs(raw['base']-803.674934892217)<1e-9
    # Independently reconcile every scenario against the original cash-flow/tax bridge.
    bridges={}
    for k,s in scenarios.items():
        delta_nwc_pv=sum((row['revenue']-(REVENUE0 if i==0 else s['revenue'][i-1]))*
                         (NWC_RATIO-old['nwc_ratio'])/(1.11)**(i+1)
                         for i,row in enumerate(old['results'][k]['rows']))
        change=(-delta_nwc_pv-(5.626+9.820))/SHARES
        expected=old['results'][k]['per_share']+change
        assert math.isclose(expected,results[k]['usdPerShare'],abs_tol=1e-9)
        bridges[k]={'originalUSD':old['results'][k]['per_share'],'nwcCorrectionUSD':-delta_nwc_pv/SHARES,
                    'existingTaxCorrectionUSD':-(5.626+9.820)/SHARES,'correctedUSD':expected}
    rate=fx['rate'];eur={k:round(v/rate,2) for k,v in raw.items()}
    reverse=None
    if market_price_usd:
        lo,hi=.040001,.50
        for _ in range(100):
            mid=(lo+hi)/2
            if calc(scenarios['Base'],mid)['usdPerShare']>market_price_usd:lo=mid
            else:hi=mid
        implied=(lo+hi)/2;assert abs(calc(scenarios['Base'],implied)['usdPerShare']-market_price_usd)<1e-7
        target_ev=market_price_usd*SHARES-NET_CASH
        implied_terminal_fcff=(target_ev-results['Base']['pvExplicit'])*1.11**10*(.11-.03)
        implied_gm=(implied_terminal_fcff/((1+.03)*(1-.03/.15))/(1-TAX)+24)/300
        reverse={'marketPriceUSD':market_price_usd,'impliedWACC':implied,'impliedFY2036GMAt11pct':implied_gm,
                 'interpretation':'Conditional on the same original operating forecast and capital bridge; not observed market expected return'}
    return {'scope':'User-selected 803.674934892217 USD/share old-model correction; conditional reference',
            'modelVintage':'2026-10-15','correctionAuditDate':'2026-11-18','publicationDate':'2026-11-19',
            'units':'USD billion; shares billion; per common share; USD cash flows with USD WACC; EUR display only',
            'scenarios':scenarios,'taxRate':TAX,'sharesBillion':SHARES,'nwcRatio':NWC_RATIO,
            'capitalBridge':{'cash':38.364,'shortInvestments':5.070,'longInvestments':30.019,
                'currentDebt':.491,'longDebt':4.688,'customerDeposits':12.747,'currentIncomeAndOtherTax':5.626,
                'noncurrentIncomeTax':9.820,'netCash':NET_CASH},
            'results':results,'sensitivity':sensitivity,'usdPerShare':raw,'eurPerShare':eur,'valuationFx':fx,
            'HConstruction':'Base operating path at12% (low),11% (model center),10% (high) USD WACC. Conditional sensitivity band, not a statistical interval.',
            'ZConstruction':'Original Bear/Bull operating forecasts at11% WACC, with corrected NWC and existing taxes; original scenario g and ROIC unchanged.',
            'originalToCorrectedBridge':bridges,
            'rgSensitivityUSD':{str(r):{str(g):calc(scenarios['Base'],r,g)['usdPerShare'] for g in [.02,.03,.04]} for r in [.10,.11,.12]},
            'marginSensitivityUSD':{str(x):calc(scenarios['Base'],gm_shift=x)['usdPerShare'] for x in [-.05,0,.05]},
            'reverse':reverse,
            'checks':{'scenarioArithmeticReconciled':True,'originalAudit803_67Reconciled':True,'valuationChecklistFullyPassed':False},
            'limitations':['Unvalidated structural midcycle margins and memory-peer bottom-up beta',
                'Original11% WACC retained by selected model, not newly independently approved',
                'Historical same-basis multiples and historical scenario percentiles not established',
                'H defined transparently from single operating path sensitivity; original750–1050 judgment range not restored',
                'No new earnings forecast, no valuation-date cash roll, no analyst target price in formula']}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--inputs',required=True,type=Path);p.add_argument('--fx',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path);p.add_argument('--market-price-usd',type=float)
    a=p.parse_args();out=build_model(json.loads(a.inputs.read_text()),json.loads(a.fx.read_text()),a.market_price_usd)
    a.output.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(out['eurPerShare'],ensure_ascii=False))
