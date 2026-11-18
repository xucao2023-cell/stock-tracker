#!/usr/bin/env python3
"""Tencent Q3 2026 revaluation. Monetary inputs: CNY million; shares: million.

Primary facts: source/revaluation_20261118/q3_official.pdf (pages in inputs).
All forecasts, multiples, valuation discounts and cash-flow recovery are assumptions.
No analyst price targets enter any valuation formula. No changes to old reports.
Run from any directory: python scripts/tencent_revaluation_20261118.py
"""
from pathlib import Path
from datetime import date, timedelta
import csv
import importlib.util
import json
import statistics

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "source/revaluation_20261118"
OUT = ROOT / "extracted/revaluation_20261118"
OUT.mkdir(exist_ok=True, parents=True)

FACTS = {
    "q3_revenue": 207336, "q3_revenue_prior": 192869,
    "q3_segments": [98326, 43049, 63655, 2306],
    "q3_gross_profit": 115911, "q3_segment_gp": [63017, 22578, 31551, -1235],
    "q3_nonifrs_op": 68073, "q3_nonifrs_ni": 66519,
    "q3_nonifrs_ni_prior": 70551, "q3_basic_shares": 9011,
    "q3_diluted_shares": 9125, "q3_nonifrs_diluted_eps": 7.227,
    "q3_ifrs_parent_profit": 63612, "q3_ifrs_diluted_profit": 63387,
    "q3_ifrs_diluted_eps": 6.947,
    "q3_op_ex_new_ai_rounded": 83300,
    "q3_sbc_op": 7115, "q3_sbc_parent_adjustment": 7834,
    "q3_acquisition_amort": 1621, "q3_donation_adjustment": 190,
    "q3_ifrs_op": 59147, "q3_other_gains": -543,
    "q3_da": 11995 + 1706 + 6121,
    "q3_interest_related": 3672, "q3_interest_income": 3992,
    "q3_associate_nonifrs": 8826,
    "nine_m_revenue": 608579, "nine_m_ni": 202839,
    "nine_m_ni_prior": 194932, "nine_m_sbc_parent": 22783,
    "nine_m_capex_accrual": 166153,
    "nine_m_cfo": 156713, "q3_capex_accrual": 81433,
    "q3_cfo_rounded": 2600, "q3_cash_capex_rounded": 65100,
    "q3_content_cash_rounded": 4600, "q3_lease_cash_rounded": 2000,
    "q3_fcf_rounded": -69100, "q3_fcf_ex_prepay_rounded": 16900,
    "q2_fcf_rounded": -13800, "q2_fcf_ex_prepay_rounded": 37600,
    "cash": 231717, "term_and_other_liquid": 294010,
    "borrowings": 380101, "notes": 159328,
    "q2_borrowings": 298942, "q2_notes": 154021,
    "net_cash": -13702, "listed_investments_attributable": 505400,
    "unlisted_investments_attributable": 397200,
    "nci_book": 86363,
    "deferred_rev": 129400 + 1994, "deferred_rev_dec2025": 110309 + 2210,
    "q3_buyback_hkd": 7032.25951704, "q3_buyback_shares": 15.8676,
    "issued_shares_oct": 9092.644829,
    "fy2025_revenue": 751766, "fy2025_nonifrs_ni": 259626,
    "fy2021_nonifrs_ni": 123788, "fy2022_nonifrs_ni": 115649,
    "h1_capital_commitments": 92729, "h1_other_commitments": 280147,
}

ASSUMPTIONS = {
    "price_hkd": 372.8, "price_time_hkt": "2026-11-18 16:08:10",
    "cny_per_hkd": 0.84961, "fx_date": "2026-11-17",
    "shares": 9125,  # latest reported quarter, includes existing awards/options
    "fy2026_revenue": 817000, "fy2026_nonifrs_parent_ni": 264000,
    "fy2027_revenue": 878000, "fy2027_nonifrs_parent_ni": 262000,
    "subsidiary_associate_dilution": 2300,
    "ongoing_attributable_sbc_aftertax": 26000,
    "associate_economic_earnings": 31000,
    "cash_interest_aftertax": 13000, "portfolio_dividends_aftertax": 2000,
    "debt_interest_aftertax": 14000, "nci_economic_profit": 6500,
    "listed_haircut_factor": .90, "unlisted_factor": .50,
    "q4_2026_cash_burn": 50000,
    "tax": .18, "rf_cny": .0165,
    "mature_erp_nov": .0441, "china_country_risk_july": .008727858397633674,
    "cost_debt": .03, "wacc": .08, "terminal_g": .025,
    "base_multiple_range": [14, 16], "pressure_multiple": 12,
    "growth_multiple": 18,
}
A, F = ASSUMPTIONS, FACTS
DENOM = A["shares"] * A["cny_per_hkd"]

def hkd(value):
    return value / DENOM

def quantile(xs, p):
    xs = sorted(xs)
    k = (len(xs)-1)*p
    i = int(k)
    return xs[i] + (xs[min(i+1, len(xs)-1)]-xs[i]) * (k-i)

def beta_and_history():
    series = {}
    for label, filename, symbol in [
        ("stock", "daily_kline", "hk00700"),
        ("hstech", "hstech_kline", "hkHSTECH"),
        ("hsi", "hsi_kline", "hkHSI"),
    ]:
        data = json.loads((SRC / (filename+".txt")).read_text())["data"][symbol]
        # Endpoint returned day, not adjusted day. Explicitly price-return beta.
        rows = data.get("qfqday", data.get("day"))
        series[label] = {date.fromisoformat(x[0]): float(x[2]) for x in rows}
    weekly = {}
    common = set.intersection(*(set(s) for s in series.values()))
    for d in sorted(common):
        friday = d + timedelta(days=(4-d.weekday()) % 7)
        if friday <= date(2026, 11, 13):
            weekly[friday] = {name: s[d] for name, s in series.items()}
    dates = sorted(weekly)
    returns = []
    for prev, now in zip(dates, dates[1:]):
        row = {"date": now.isoformat()}
        row.update({k: weekly[now][k]/weekly[prev][k]-1 for k in series})
        returns.append(row)
    betas = {}
    for years in (2, 3):
        rows = [x for x in returns if x["date"] >= date(2026-years,11,13).isoformat()]
        for index in ("hstech", "hsi"):
            x, y = [r[index] for r in rows], [r["stock"] for r in rows]
            betas[f"{years}y_{index}"] = {
                "beta": statistics.covariance(x, y)/statistics.variance(x),
                "correlation": statistics.correlation(x, y), "n": len(rows),
                "first": rows[0]["date"], "last": rows[-1]["date"],
            }
    with (OUT / "weekly_returns.csv").open("w") as f:
        writer = csv.DictWriter(f, ["date", "stock", "hstech", "hsi"])
        writer.writeheader(); writer.writerows(returns)
    prices = list(series["stock"].values())
    return betas, {"n": len(prices), "min": min(prices), "max": max(prices),
                    "quantiles": {str(p): quantile(prices,p) for p in [.05,.1,.25,.5,.75,.9,.95]}}

BETAS, HISTORY = beta_and_history()
ERP = A["mature_erp_nov"] + A["china_country_risk_july"]
MARKET_CAP = A["price_hkd"] * F["issued_shares_oct"] * A["cny_per_hkd"]
DEBT = F["borrowings"] + F["notes"]
DEBT_WEIGHT = DEBT / (DEBT + MARKET_CAP)
KE = A["rf_cny"] + BETAS["2y_hsi"]["beta"] * ERP
CAPM_WACC = KE*(1-DEBT_WEIGHT) + A["cost_debt"]*(1-A["tax"])*DEBT_WEIGHT

ECON_NI = A["fy2027_nonifrs_parent_ni"] - A["subsidiary_associate_dilution"] - A["ongoing_attributable_sbc_aftertax"]
OP_NOPAT = (ECON_NI - A["associate_economic_earnings"] - A["cash_interest_aftertax"]
            - A["portfolio_dividends_aftertax"] + A["debt_interest_aftertax"] + A["nci_economic_profit"])
INV = F["listed_investments_attributable"]*A["listed_haircut_factor"] + F["unlisted_investments_attributable"]*A["unlisted_factor"]
ASSET_ADJ = INV + F["net_cash"]
PARENT_OP_NOPAT = OP_NOPAT - A["nci_economic_profit"]
NCI_OPERATING_SHARE = A["nci_economic_profit"] / OP_NOPAT
PE = [hkd(ECON_NI*m) for m in A["base_multiple_range"]]
# Capitalise only parent-attributable operating earnings. Investment values are
# already attributable: do not subtract the entire consolidated NCI book again.
SOTP = [hkd(PARENT_OP_NOPAT*m + ASSET_ADJ - A["q4_2026_cash_burn"]) for m in A["base_multiple_range"]]
H = [max(PE[0], SOTP[0], HISTORY["quantiles"]["0.25"]), min(PE[1], SOTP[1], HISTORY["quantiles"]["0.75"])]
assert H[0] <= H[1], "No overlapping valuation band; must make an explicit choice."
CENTER = sum(H)/2
TTM_NONIFRS = F["fy2025_nonifrs_ni"] - F["nine_m_ni_prior"] + F["nine_m_ni"]
GROWTH_ECON_NI = TTM_NONIFRS - A["subsidiary_associate_dilution"] - A["ongoing_attributable_sbc_aftertax"]
GROWTH_NOPAT = GROWTH_ECON_NI - (ECON_NI - OP_NOPAT)
Z = [hkd(ECON_NI*A["pressure_multiple"]),
     max(hkd(GROWTH_ECON_NI*A["growth_multiple"]),
         hkd((GROWTH_NOPAT-A["nci_economic_profit"])*A["growth_multiple"]+ASSET_ADJ-A["q4_2026_cash_burn"]))]

# Cash-flow model: consolidate the operating pool, excluding investment earnings;
# keep SBC as an economic operating cost. D&A excludes acquisition amortisation
# already added back to operating profit. Cash capex is NET cash paid, not accrual
# additions. Extra prepayment is only FUTURE net increase, never the historic 86bn.
# Content and leases are paid in full; lease liabilities are not deducted again.
GROWTH = [.07,.07,.065,.06,.055,.05,.045,.04,.03]
MARGINS = [OP_NOPAT/(1-A["tax"])/A["fy2027_revenue"], .295,.30,.305,.31,.31,.31,.31,.31,.31]
DA = [80000,100000,120000,135000,145000,150000,160000,170000,180000,190000]
CAPEX = [270000,260000,240000,225000,220000,220000,225000,225000,225000,225000]
CONTENT_LEASE = [32000,34000,36000,38000,40000,42000,44000,46000,48000,50000]
PREPAY = [60000,30000,10000,0,0,0,0,0,0,0]
WC = [.005]*10  # incremental ordinary working capital / incremental revenues

def forecast(extra_cash_cost=0):
    revenue, prior = A["fy2027_revenue"], A["fy2026_revenue"]
    out = []
    for i in range(10):
        if i:
            prior, revenue = revenue, revenue*(1+GROWTH[i-1])
        ebit = revenue*MARGINS[i]
        nopat = ebit*(1-A["tax"])
        dwc = (revenue-prior)*WC[i]
        fcff = nopat+DA[i]-CAPEX[i]-CONTENT_LEASE[i]-PREPAY[i]-dwc-extra_cash_cost
        out.append({"year":2027+i, "revenue":revenue, "economic_ebit":ebit,
                    "nopat":nopat, "da":DA[i], "cash_it_capex":CAPEX[i],
                    "content_and_lease":CONTENT_LEASE[i], "extra_prepay":PREPAY[i],
                    "ordinary_dwc":dwc, "extra_cash_cost":extra_cash_cost, "fcff":fcff,
                    "t":i+1.25})
    return out

def dcf(wacc=.08, g=.025, extra_cash_cost=0, inv=INV):
    assert wacc>g
    rows = forecast(extra_cash_cost)
    stub = -A["q4_2026_cash_burn"]/(1+wacc)**.25
    for row in rows:
        row["discount_factor"] = (1+wacc)**-row["t"]
        row["pv"] = row["fcff"]*row["discount_factor"]
    pv_explicit = stub + sum(x["pv"] for x in rows)
    terminal_fcf = rows[-1]["fcff"]*(1+g)
    tv = terminal_fcf/(wacc-g)
    pv_tv = tv/(1+wacc)**rows[-1]["t"]
    ev = pv_explicit+pv_tv
    # NCI is a forecast cash-flow claim, not a book-value subtraction. The share
    # is an assumption from normalised operating profit, not an observed legal
    # ownership percentage. It applies only to operating EV; portfolio values
    # are already attributable to Tencent. Net debt conservatively all to parent.
    nci_value = ev*NCI_OPERATING_SHARE
    equity = ev+inv+F["net_cash"]-nci_value
    reinvest = rows[-1]["nopat"]-rows[-1]["fcff"]
    return {"wacc":wacc,"g":g,"stub_pv":stub,"pv_explicit":pv_explicit,
            "terminal_fcf":terminal_fcf,"terminal_value":tv,"pv_terminal":pv_tv,
            "terminal_share_ev":pv_tv/ev,"terminal_share_equity":pv_tv/equity,
            "ev":ev,"nci_value":nci_value,"equity":equity,"hkd":hkd(equity),
            "implied_terminal_roic":g/(reinvest/rows[-1]["nopat"]),"rows":rows}

def solve(target, kind):
    lo,hi = (.04,.25) if kind=="wacc" else (-.10,.079)
    def value(x):
        return dcf(wacc=x)["hkd"] if kind=="wacc" else dcf(g=x)["hkd"]
    vlo,vhi=value(lo),value(hi)
    assert min(vlo,vhi)<=target<=max(vlo,vhi)
    for _ in range(100):
        mid=(lo+hi)/2
        if (value(mid)>target)==(vlo>vhi):lo=mid
        else:hi=mid
    return (lo+hi)/2

BASE = dcf()
SENS = {f"{r:.1%}":{f"{g:.1%}":dcf(r,g)["hkd"] for g in [.015,.025,.035]} for r in [.07,.08,.09]}
PE_SENS = {f"{ni:.0f}":{str(pe):hkd((ni-28300)*pe) for pe in [12,14,15,16,18]} for ni in [240000,262000,280000]}
REVERSE_R = solve(A["price_hkd"],"wacc")
REVERSE_G = solve(A["price_hkd"],"g")

# Reproduce old DCF and then make a sequential, auditable parameter bridge.
spec = importlib.util.spec_from_file_location("old_tencent", ROOT/"scripts/tencent_valuation.py")
old = importlib.util.module_from_spec(spec); spec.loader.exec_module(old)
old_result = old.run_dcf(old.BASE,.08,.035,old.ROIC,old.INV_BASE)
old_rate = old.run_dcf(old.BASE,.08,.025,old.ROIC,old.INV_BASE)
bridge_dcf = [
    {"stage":"old_exact_model", "hkd":old_result["hkd"]},
    {"stage":"old_cashflows_new_terminal_g_2.5pct", "hkd":old_rate["hkd"]},
    {"stage":"new_cashflow_schedule_old_assets_shares_fx", "hkd":(BASE["ev"]+old.INV_BASE+old.NET_CASH-old.MINORITY)/old.SHARES/old.FX},
    {"stage":"new_cashflows_and_assets_old_shares_fx", "hkd":BASE["equity"]/old.SHARES/old.FX},
    {"stage":"new_shares_old_fx", "hkd":BASE["equity"]/A["shares"]/old.FX},
    {"stage":"new_fx_final", "hkd":BASE["hkd"]},
]
for i,x in enumerate(bridge_dcf):
    x["change"] = 0 if i==0 else x["hkd"]-bridge_dcf[i-1]["hkd"]

# Old 500 was rounded and internally inconsistent in share count. Reconstruct
# its stated inputs, then change only one input at a time, keeping 15x throughout.
old_reconstructed = 277000/9100*1.098*15
bridge_pe = [
    {"stage":"old_rounded_headline", "hkd":500},
    {"stage":"old_stated_2770yi_91yi_1.098_15x", "hkd":old_reconstructed},
    {"stage":"new_2027_ni_2620yi", "hkd":262000/9100*1.098*15},
    {"stage":"new_sbc_and_subsidiary_dilution", "hkd":ECON_NI/9100*1.098*15},
    {"stage":"new_shares", "hkd":ECON_NI/A["shares"]*1.098*15},
    {"stage":"new_fx", "hkd":hkd(ECON_NI*15)},
    {"stage":"sotp_pe_history_overlap_midpoint", "hkd":CENTER},
]
for i,x in enumerate(bridge_pe):
    x["change"] = 0 if i==0 else x["hkd"]-bridge_pe[i-1]["hkd"]

CHECKS = {
    "segment_revenue_sum": sum(F["q3_segments"]) == F["q3_revenue"],
    "segment_gross_profit_sum": sum(F["q3_segment_gp"]) == F["q3_gross_profit"],
    "net_cash_reconciliation": F["cash"]+F["term_and_other_liquid"]-DEBT == F["net_cash"],
    "ifrs_to_nonifrs_op": 59147+7115+1621+190 == 68073,
    "ifrs_diluted_eps_rounding": abs(F["q3_ifrs_diluted_profit"]/A["shares"]-F["q3_ifrs_diluted_eps"])<.00051,
    "fcf_rounding": abs(F["q3_cfo_rounded"]-F["q3_cash_capex_rounded"]-F["q3_content_cash_rounded"]-F["q3_lease_cash_rounded"]-F["q3_fcf_rounded"])<=100,
    "sotp_excludes_equity_accounted_investment_income": True,
    "no_lease_liability_double_deduction": True,
    "no_historic_compute_prepayment_addback_in_value": True,
    "no_nci_book_subtraction_from_attributable_investments": True,
}
assert all(CHECKS.values()), CHECKS

RESULTS = {
    "facts":F,"assumptions":A,"checks":CHECKS,"beta":BETAS,"price_history":HISTORY,
    "capital_cost":{"erp":ERP,"ke":KE,"debt_weight":DEBT_WEIGHT,"capm_wacc":CAPM_WACC,
                    "q3_annualised_debt_cost":F["q3_interest_related"]*4/((DEBT+F["q2_borrowings"]+F["q2_notes"])/2)},
    "profit_bridge":{"economic_ni":ECON_NI,"operating_nopat":OP_NOPAT,"operating_ebit":OP_NOPAT/(1-A["tax"]),
                    "parent_operating_nopat":PARENT_OP_NOPAT,"nci_operating_share":NCI_OPERATING_SHARE,
                    "investment_value":INV,"asset_adjustment":ASSET_ADJ,"ttm_nonifrs_ni":TTM_NONIFRS},
    "valuation":{"pe_band":PE,"sotp_band":SOTP,"H":H,"center":CENTER,"Z":Z,
                "growth_economic_ni":GROWTH_ECON_NI,"growth_nopat":GROWTH_NOPAT,
                "pressure_pe":Z[0],"growth_pe":hkd(GROWTH_ECON_NI*18),
                "growth_sotp":hkd((GROWTH_NOPAT-A["nci_economic_profit"])*18+ASSET_ADJ-A["q4_2026_cash_burn"]),
                "center_upside":CENTER/A["price_hkd"]-1,
                "price_discount_to_center":1-A["price_hkd"]/CENTER,
                "actual_price_economic_pe":A["price_hkd"]/(ECON_NI/DENOM),
                "old_500_change_pct":CENTER/500-1},
    "dcf":BASE,"dcf_sensitivity":SENS,"pe_sensitivity":PE_SENS,
    "reverse":{"implied_wacc":REVERSE_R,"implied_terminal_g":REVERSE_G},
    "cash_tail":{"extra_annual_spend_80000":dcf(extra_cash_cost=80000)["hkd"],
                 "extra_annual_spend_40000":dcf(extra_cash_cost=40000)["hkd"]},
    "bridge_old_dcf":bridge_dcf,"bridge_old_500":bridge_pe,
    "fact_derived":{
        "q3_revenue_growth":F["q3_revenue"]/F["q3_revenue_prior"]-1,
        "q3_ni_growth":F["q3_nonifrs_ni"]/F["q3_nonifrs_ni_prior"]-1,
        "q3_new_ai_op_drag_rounded":F["q3_op_ex_new_ai_rounded"]-F["q3_nonifrs_op"],
        "q3_compute_prepay_rounded":F["q3_fcf_ex_prepay_rounded"]-F["q3_fcf_rounded"],
        "q2_compute_prepay_rounded":F["q2_fcf_ex_prepay_rounded"]-F["q2_fcf_rounded"],
        "fy2026_q4_ni":A["fy2026_nonifrs_parent_ni"]-F["nine_m_ni"],
        "fy2025_q4_ni":F["fy2025_nonifrs_ni"]-F["nine_m_ni_prior"],
        "fy2026_q4_ni_growth":(A["fy2026_nonifrs_parent_ni"]-F["nine_m_ni"])/(F["fy2025_nonifrs_ni"]-F["nine_m_ni_prior"])-1,
        "fy2027_ni_growth":A["fy2027_nonifrs_parent_ni"]/A["fy2026_nonifrs_parent_ni"]-1,
        "fy2026_q4_revenue":A["fy2026_revenue"]-F["nine_m_revenue"],
        "fy2026_revenue_growth":A["fy2026_revenue"]/F["fy2025_revenue"]-1,
        "fy2027_revenue_growth":A["fy2027_revenue"]/A["fy2026_revenue"]-1,
        "historical_2021_2022_nonifrs_decline":1-F["fy2022_nonifrs_ni"]/F["fy2021_nonifrs_ni"],
        "deferred_revenue_change_since_dec":F["deferred_rev"]/F["deferred_rev_dec2025"]-1,
        "deferred_revenue_annual_coverage":F["deferred_rev"]/A["fy2026_revenue"],
        "economic_eps_cny":ECON_NI/A["shares"],"economic_eps_hkd":ECON_NI/DENOM,
        "cashburn_per_10bn_cny_hkd":hkd(10000),
        "sbc_aftertax_q3_parent_annual_proxy":F["q3_sbc_parent_adjustment"]*4*(1-A["tax"]),
        "subsidiary_dilution_q3_annual_inferred":(F["q3_nonifrs_ni"]-F["q3_nonifrs_diluted_eps"]*A["shares"])*4,
        "economic_pe_to_nonifrs_pe_range":[m*ECON_NI/A["fy2027_nonifrs_parent_ni"] for m in A["base_multiple_range"]],
        "old_dcf_terminal_share_ev":old_result["tv"]/(1.08**10)/old_result["core_ev"],
        "old_dcf_change_pct":BASE["hkd"]/old_result["hkd"]-1,
        "fy2025_effective_tax":47448/277249,
        "nine_m2026_effective_tax":35342/217850,
        "normalized_ebit_margin":OP_NOPAT/(1-A["tax"])/A["fy2027_revenue"],
        "q3_fcf_ex_prepay_qoq":16900/37600-1,
    }
}
(OUT/"model_results.json").write_text(json.dumps(RESULTS,ensure_ascii=False,indent=2))
with (OUT/"dcf_cashflows.csv").open("w") as f:
    writer=csv.DictWriter(f,list(BASE["rows"][0]));writer.writeheader();writer.writerows(BASE["rows"])
if __name__ == "__main__":
    for k in ["capital_cost","profit_bridge","valuation","reverse","cash_tail","bridge_old_dcf","bridge_old_500","fact_derived"]:
        print(k, json.dumps(RESULTS[k],ensure_ascii=False,indent=2))
    print("DCF",json.dumps({k:v for k,v in BASE.items() if k!="rows"},indent=2))
    print("SENSITIVITY",json.dumps(SENS,indent=2))
    for row in BASE["rows"]:
        print(row["year"],*(round(row[k]/100,2) for k in ["revenue","nopat","da","cash_it_capex","content_and_lease","extra_prepay","ordinary_dwc","fcff","pv"]))
