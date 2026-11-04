"""Q3 review: new actuals and bridge, retain the adopted normalized market anchor.

Amounts EUR million; shares million; EUR/share. Forecast and debt proxies are
explicit in source/q3_review_20261104.json. Never import the old executable model:
it writes historical outputs at import time. Read its frozen JSON output instead.
"""
import json
from datetime import date
from pathlib import Path
from scipy.optimize import brentq

ROOT=Path(__file__).resolve().parents[1]
S=json.loads((ROOT/'source/q3_review_20261104.json').read_text())
OLD=json.loads((ROOT/'extracted/converged_valuation_20261020.json').read_text())
ASOF=date(2026,11,4)
A=S['model_assumptions']; B=S['balance_20260930']; Q=S['q3']; Y=S['nine_months']; G=S['company_guidance']
N=B['shares']; EB=A['normal_ebitda']; R=A['discount_rate']
T=(date(2027,12,31)-ASOF).days/365.25
BRIDGE=B['net_financial_debt']+B['lease_long']+B['lease_short']+B['pension']+B['nci_book']
SF=A['supplier_finance_opening_2025']+Y['other_financial_liability_proceeds']-Y['other_financial_liability_repayments']
Q4_CASH=G['2025_company_net_cash_flow']-Y['company_net_cash_flow']
WC=A['wc_ratio_of_incremental_revenue']*(A['2027_revenue_forecast_carried']-G['2025_revenue_actual'])
CF=EB-A['2027_cash_tax_floor']-A['2027_cash_capex_proxy_carried']-WC

def value(multiple=7.6,rate=R,cf=CF,bridge=BRIDGE,transition=-Q4_CASH,supplier=SF,asof=ASOF,ebitda=EB):
    t=(date(2027,12,31)-asof).days/365.25
    df=(1+rate)**(-t)
    exit_ev=ebitda*multiple
    pv_cash=cf*df;pv_exit=exit_ev*df
    return dict(price=(pv_cash+pv_exit-bridge-transition-supplier)/N,
                multiple=multiple,rate=rate,ebitda=ebitda,fcff=cf,df=df,t=t,
                exit_ev=exit_ev,pv_cash=pv_cash,pv_exit=pv_exit,
                reported_bridge=bridge,q4_cash_debt_proxy=transition,
                supplier_finance_proxy=supplier,total_claims=bridge+transition+supplier,
                terminal_share=pv_exit/(pv_exit+pv_cash))

def dcf(rate=R,maintenance=200,g=.02):
    tax=max(EB-maintenance,0)*.25
    growth_wc=.1*1524*g
    next_cf=(EB-tax-maintenance-growth_wc)*(1+g)
    terminal=next_cf/(rate-g)
    df=(1+rate)**(-T)
    return dict(price=((CF+terminal)*df-BRIDGE+Q4_CASH-SF)/N,
                terminal_fcff=next_cf,terminal_ev=terminal,
                terminal_share=terminal/(terminal+CF),rate=rate,
                maintenance_capex=maintenance,growth=g)

def bull():
    c=json.loads((ROOT/'source/consensus_20261019.json').read_text())['annual']
    cash=0;rows=[]
    for y in (2027,2028):
        a=c[str(y)]; prev_rev=G['2025_revenue_actual'] if y==2027 else c[str(y-1)]['revenue']
        tax=max(15,max(a['ebit'],0)*.25)
        cf=a['ebitda']-tax-a['capex_vendor']-.1*(a['revenue']-prev_rev)
        df=(1+R)**(-((date(y,12,31)-ASOF).days/365.25))
        cash+=cf*df;rows.append(dict(year=y,fcff=cf,df=df))
    mult=OLD['history'][1]['multiple']
    tv=c['2028']['ebitda']*mult*rows[-1]['df']
    return dict(price=(cash+tv-BRIDGE+Q4_CASH-SF)/N,ebitda=c['2028']['ebitda'],multiple=mult,
                rows=rows,pv_cash=cash,pv_exit=tv)

base=value()
steps=[('old_20261020',OLD['base']['price']),
       ('date_only',value(cf=135.32,bridge=1116.3,transition=0,supplier=0)['price']),
       ('new_reported_bridge',value(cf=135.32,transition=0,supplier=0)['price']),
       ('2026_revenue_base_and_2027_wc',value(cf=135.32+19.8-WC,transition=0,supplier=0)['price']),
       ('cash_tax_floor_15',value(transition=0,supplier=0)['price']),
       ('q4_cash_burn_proxy',value(supplier=0)['price']),
       ('supplier_finance_correction',base['price'])]
waterfall=[dict(step=k,price=v,delta=0 if i==0 else v-steps[i-1][1]) for i,(k,v) in enumerate(steps)]
quote=S['quote']['price']
metrics=dict(revenue_qoq=Q['revenue']/321.6-1,revenue_yoy=Q['revenue']/300.3-1,
    ebitda_qoq=Q['ebitda']/69.4-1,ebitda_yoy=Q['ebitda']/65.7-1,
    revenue_vs_old_consensus=Q['revenue']/335-1,ebitda_vs_old_consensus=Q['ebitda']/73.69-1,
    q3_margin=Q['ebitda']/Q['revenue'],nine_month_margin=Y['ebitda']/Y['revenue'],
    inventory_qoq=B['inventory']/342.7-1,
    inventory_change=B['inventory']-342.7,
    bs_nwc=B['inventory']+B['trade_receivables']+B['contract_assets']-B['trade_payables'],
    cfo_provision_adjustment_share=28.7/100.8,
    q3_other_finance_net=75.7-49.5,
    quote_change=quote/S['quote']['previous_close']-1,
    guidance_ebitda_low=G['2025_revenue_actual']*.22,
    guidance_ebitda_high=G['2025_revenue_actual']*.24,
    guidance_ebitda_mid=G['2025_revenue_actual']*.23,
    guidance_ebitda_mid_vs_old_consensus=(G['2025_revenue_actual']*.23)/300.9-1,
    implied_q4_ebitda_low=G['2025_revenue_actual']*.22-Y['ebitda'],
    implied_q4_ebitda_high=G['2025_revenue_actual']*.24-Y['ebitda'],
    bvps=B['parent_equity']/N,
    old_current_other_financial_total=59.0+.3,
    new_other_financial_total=B['other_financial_liabilities_long']+B['other_financial_liabilities_short'],
    q2_fcf=S['q2_cashflow_from_h1_statement_p21']['cfo']-S['q2_cashflow_from_h1_statement_p21']['net_cash_investment'])
result=dict(asof=str(ASOF),units=S['units'],source='source/q3_review_20261104.json',
    method='normalized EBITDA x historical mid-cycle multiple; dated recovery adjustment',
    base=base,working_range=[60,70],normal_ebitda=EB,metrics=metrics,
    raw_band=[value(7.25)['price'],value(8)['price']],waterfall=waterfall,
    sensitivities={str(r):{str(m):value(m,r)['price'] for m in (7.25,7.6,8)}
                  for r in (.085,.095,.105)},
    debt_sensitivity=dict(no_supplier_proxy=value(supplier=0)['price'],
        all_other_financial_liabilities=value(supplier=95.2)['price'],
        no_q4_burn=value(transition=0)['price'],
        claims_plus100=base['price']-100/N),
    dcf={str(r):dcf(r) for r in (.085,.095,.105)},
    reverse=dict(multiple=((quote*N+base['total_claims'])/base['df']-CF)/EB,
        rate=brentq(lambda r:value(rate=r)['price']-quote,.001,.3),
        dcf_rate=brentq(lambda r:dcf(rate=r)['price']-quote,.021,.3)),
    scenarios=dict(bear=value(OLD['history'][2]['multiple']),base=base,bull=bull()),
    quote=S['quote'],center_return=base['price']/quote-1,
    limitation='Targeted quarterly review. Rate, historical multiple and normal earnings carried; weekly beta and contemporaneous peer validation remain incomplete.')
# Report figures are rounded; 9M and sum of standalone quarters differ by EUR0.1m.
assert abs(Q['revenue']+321.6+306.5-Y['revenue'])<.11
assert abs(Q['ebitda']+69.4+65.1-Y['ebitda'])<.11
assert abs(Y['ebitda']-362.4-Y['ebit'])<.01
assert abs(Q['parent_net_income']/N-Q['eps'])<.01
assert abs(100.8-(45.4-.3-1.3)-57.0)<1e-8
assert abs(BRIDGE-1038.3)<1e-8
assert abs(SF-71.1)<1e-8
assert abs(CF-129.89)<1e-8
assert abs(metrics['q2_fcf']-(-28.3))<1e-8
assert abs(-373.1-360.7+2.9+1350.8-B['net_financial_debt'])<1e-8
assert value(8)['price']>base['price']>value(7.25)['price']
assert base['price']>value(rate=.105)['price']
(ROOT/'extracted/q3_review_20261104.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:result[k] for k in ('base','metrics','raw_band','waterfall','debt_sensitivity','dcf','reverse','scenarios')},ensure_ascii=False,indent=2))
