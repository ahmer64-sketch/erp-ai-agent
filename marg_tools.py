"""
Full-history tools — company-level analysis on the Marg ERP exports (marg_data.py).

Each tool returns (DataFrame, figure | None), same contract as erp_tools.py.
Money columns are in ₹ lakh (_L) unless the column name says otherwise.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go

import marg_data as md
from marg_data import sales, purchases, stock, stock_values, debtors, creditors

_L = 1e5   # ₹ per lakh
_MONTHS = ["Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar"]
_MONTH_NO = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def _pct(new, old):
    return round((new / old - 1) * 100, 1) if old else None


def _latest_fy() -> str:
    return sales["FY"].max()


def _ytd_cut() -> pd.Timestamp:
    """End of the last full month — YTD comparisons stop here so a partial month doesn't skew them."""
    return md.MONTHLY_REVENUE.index[-1] + pd.offsets.MonthBegin()


# ── 1. Sales growth ───────────────────────────────────────────────────────────

def sales_growth_tool(period: str = "fy"):
    """period = fy (year-on-year by financial year) | month (MoM + same-month YoY, last 13 months)."""
    if period == "month":
        s = md.MONTHLY_REVENUE
        out = pd.DataFrame({
            "Month":       s.index.strftime("%b-%y"),
            "revenue_L":   (s / _L).round(1),
            "MoM_pct":     (s.pct_change() * 100).round(1),
            "YoY_pct":     (s.pct_change(12) * 100).round(1),
        }).tail(13).reset_index(drop=True)
        if md.PARTIAL_MONTH is not None:
            part = sales[sales["month"] == md.PARTIAL_MONTH]["taxable"].sum()
            partial = pd.DataFrame([{"Month": f"{md.PARTIAL_MONTH:%b-%y} (partial, to {md.LAST_SALE_DATE:%d %b})",
                                     "revenue_L": round(part / _L, 1)}])
            out = pd.concat([out, partial], ignore_index=True)
        return out, _bar_line(out.iloc[:13], "Month", "revenue_L", "Monthly revenue (₹ lakh, taxable)")

    fy = sales.groupby("FY")["taxable"].sum()
    out = pd.DataFrame({"FY": fy.index, "revenue_L": (fy / _L).round(1).values})
    out["YoY_pct"] = [None] + [_pct(fy.iloc[i], fy.iloc[i - 1]) for i in range(1, len(fy))]
    out["note"] = ""
    out.loc[out["FY"] == "FY17-18", "note"] = "first ~2 months of trading only"
    out.loc[out["FY"] == "FY18-19", ["YoY_pct", "note"]] = [None, "first full year — no comparable prior year"]
    # The current FY is incomplete — it is represented only by the like-for-like YTD row below
    latest = _latest_fy()
    out = out[out["FY"] != latest].reset_index(drop=True)

    # Like-for-like YTD: same months this year vs last year
    cut = _ytd_cut()
    start = pd.Timestamp(f"{cut.year if cut.month > 4 else cut.year - 1}-04-01")
    ytd  = sales[(sales["date"] >= start) & (sales["date"] < cut)]["taxable"].sum()
    prev = sales[(sales["date"] >= start - pd.DateOffset(years=1)) & (sales["date"] < cut - pd.DateOffset(years=1))]["taxable"].sum()
    label = f"{latest} YTD Apr–{(cut - pd.DateOffset(days=1)):%b} vs same months last year"
    out.loc[len(out)] = [label, round(ytd / _L, 1), _pct(ytd, prev), f"current year, in progress; last year same months ₹{prev / _L:.1f}L"]
    return out, _bar_line(out.iloc[:-1], "FY", "revenue_L", "Revenue by financial year (₹ lakh, taxable)")


# ── 2. Revenue forecast + accuracy ────────────────────────────────────────────

def revenue_forecast_tool():
    s = md.MONTHLY_REVENUE
    acc = md.FORECAST_ACCURACY
    next_months = pd.date_range(s.index[-1] + pd.offsets.MonthBegin(), periods=7, freq="MS")
    base = md._forecast(s, len(next_months))[0]

    # Remaining months of the current FY
    fy_end = pd.Timestamp(f"{next_months[0].year + (1 if next_months[0].month > 3 else 0)}-03-01")
    remaining = pd.date_range(next_months[0], fy_end, freq="MS")
    fy_start = pd.Timestamp(f"{fy_end.year - 1}-04-01")
    fy_actual = s[s.index >= fy_start].sum()
    pace = s[s.index >= fy_start].mean() if (s.index >= fy_start).any() else base

    first = next_months[0]
    nxt_q = pd.date_range(first, periods=3, freq="MS")
    rows = [
        ["Model", f"Average of last {md.FORECAST_WINDOW} full months (won backtest vs Holt-Winters, SARIMA, seasonal-naive)", ""],
        ["Data through", f"{s.index[-1]:%b-%Y} (full months)", ""],
        [f"Forecast {first:%b-%y} (next month)", f"₹{base / _L:.1f}L", f"typical error ±{acc.get('month')}%"],
        [f"Forecast {nxt_q[0]:%b}–{nxt_q[-1]:%b-%y} (next quarter)", f"₹{base * 3 / _L:.1f}L", f"typical error ±{acc.get('quarter')}%"],
        [f"Forecast full FY{fy_start.year % 100}-{fy_end.year % 100} — base", f"₹{(fy_actual + base * len(remaining)) / _L:.1f}L",
         f"₹{fy_actual / _L:.1f}L actual + {len(remaining)} months × ₹{base / _L:.1f}L; 12-month error ±{acc.get('year')}%"],
        [f"Forecast full FY{fy_start.year % 100}-{fy_end.year % 100} — current pace", f"₹{(fy_actual + pace * len(remaining)) / _L:.1f}L",
         f"if this year's ₹{pace / _L:.1f}L/month average continues"],
    ]
    if md.PARTIAL_MONTH is not None:
        part = sales[sales["month"] == md.PARTIAL_MONTH]["taxable"].sum()
        rows.append([f"{md.PARTIAL_MONTH:%b-%y} so far (to {md.LAST_SALE_DATE:%d %b})", f"₹{part / _L:.1f}L", "partial month, not used in model"])
    out = pd.DataFrame(rows, columns=["Metric", "Value", "Note"])

    fig = go.Figure()
    hist = s[-36:]
    fig.add_trace(go.Scatter(x=hist.index, y=hist / _L, name="Actual", mode="lines+markers", line=dict(color="#0078D4")))
    fig.add_trace(go.Scatter(x=hist.index, y=hist.rolling(12).mean() / _L, name="12-month average", line=dict(color="#888", dash="dot")))
    band = acc.get("month", 0) / 100
    fig.add_trace(go.Scatter(x=list(next_months) + list(next_months[::-1]),
                             y=[base * (1 + band) / _L] * 7 + [base * (1 - band) / _L] * 7,
                             fill="toself", fillcolor="rgba(255,140,0,0.15)", mode="lines", line=dict(width=0), name=f"±{acc.get('month')}% typical error"))
    fig.add_trace(go.Scatter(x=next_months, y=[base / _L] * 7, name="Forecast", mode="lines+markers", line=dict(color="#FF8C00", dash="dash")))
    fig.update_layout(title="Monthly revenue — actual vs forecast (₹ lakh)", template="plotly_white", height=420,
                      hovermode="x unified", yaxis_title="₹ lakh")
    return out, fig


# ── 3. Seasonality ────────────────────────────────────────────────────────────

def sales_seasonality_tool():
    idx = md.seasonality_index()
    s = md.MONTHLY_REVENUE
    ma = s.rolling(12, center=True).mean().rolling(2).mean().shift(-1)
    ratio = (s / ma).dropna()
    spread = ratio.groupby(ratio.index.month).agg(lambda r: (r.quantile(.75) - r.quantile(.25)) * 100)

    out = pd.DataFrame({"Month": _MONTHS})
    out["seasonality_index"] = out["Month"].map(lambda m: int(idx[_MONTH_NO[m]]))
    out["vs_average_pct"]    = out["seasonality_index"] - 100
    out["year_to_year_spread_pts"] = out["Month"].map(lambda m: round(spread[_MONTH_NO[m]]))
    out["reading"] = np.select(
        [out["seasonality_index"] >= 110, out["seasonality_index"] <= 90],
        ["STRONG month", "WEAK month"], "normal (within ±10%)",
    )
    out.loc[out["year_to_year_spread_pts"] > 35, "reading"] += " — unreliable, varies a lot by year"
    fig = go.Figure(go.Bar(x=out["Month"], y=out["seasonality_index"],
                           marker_color=np.where(out["seasonality_index"] >= 110, "#2E8B57",
                                                 np.where(out["seasonality_index"] <= 90, "#D9534F", "#0078D4"))))
    fig.add_hline(y=100, line_dash="dot", line_color="#888")
    fig.update_layout(title="Sales seasonality index (100 = average month, FY18-19 onwards)", template="plotly_white", height=380)
    return out, fig


# ── 4. Cash vs credit ─────────────────────────────────────────────────────────

def cash_credit_tool():
    g = sales.groupby("FY")
    out = pd.DataFrame({
        "cash_revenue_L":    g.apply(lambda x: x.loc[x["is_cash"], "taxable"].sum()) / _L,
        "credit_revenue_L":  g.apply(lambda x: x.loc[~x["is_cash"], "taxable"].sum()) / _L,
        "cash_share_pct":    g.apply(lambda x: x.loc[x["is_cash"], "taxable"].sum() / x["taxable"].sum() * 100),
        "cash_bills":        g["is_cash"].sum(),
        "credit_bills":      g.apply(lambda x: (~x["is_cash"]).sum()),
        "avg_cash_bill_k":   g.apply(lambda x: x.loc[x["is_cash"], "taxable"].mean()) / 1e3,
        "avg_credit_bill_k": g.apply(lambda x: x.loc[~x["is_cash"], "taxable"].mean()) / 1e3,
    }).round(1).reset_index()
    return out, None


# ── 5. Customers ──────────────────────────────────────────────────────────────

def _customer_sales() -> pd.DataFrame:
    return sales[~sales["is_cash"]]


def customer_health_tool(mode: str = "summary", top_n: int = 15):
    """mode = summary | top | lost | at_risk"""
    cs = _customer_sales()
    as_of = md.LAST_SALE_DATE

    if mode == "summary":
        by_fy = cs.groupby("FY")["party"].apply(set)
        first_fy = cs.groupby("party")["FY"].min()
        rows = []
        prev = None
        for fy, parties in by_fy.items():
            fy_sales = cs[cs["FY"] == fy]
            top2 = fy_sales.groupby("party")["taxable"].sum().nlargest(2).sum() / fy_sales["taxable"].sum() * 100
            rows.append({
                "FY": fy, "active_customers": len(parties),
                "new_customers": int((first_fy == fy).sum()),
                "retained_from_last_year_pct": round(len(parties & prev) / len(prev) * 100, 1) if prev else None,
                "avg_bill_k": round(fy_sales["taxable"].mean() / 1e3, 1),
                "top2_customer_share_pct": round(top2, 1),
            })
            prev = parties
        return pd.DataFrame(rows), None

    last = cs.groupby("party").agg(
        lifetime_revenue_L=("taxable", "sum"), bills=("bill_no", "count"),
        first_bill=("date", "min"), last_bill=("date", "max"),
    )
    last["days_since_last_bill"] = (as_of - last["last_bill"]).dt.days
    last["lifetime_revenue_L"] = (last["lifetime_revenue_L"] / _L).round(1)
    recent_12m = cs[cs["date"] > as_of - pd.DateOffset(months=12)].groupby("party")["taxable"].sum() / _L
    last["last_12m_revenue_L"] = recent_12m.reindex(last.index).fillna(0).round(1)
    owed = debtors.groupby("party")["debit"].sum() / _L
    last["outstanding_L"] = owed.reindex(last.index).fillna(0).round(1)
    last = last.reset_index().rename(columns={"party": "Customer"})
    for c in ("first_bill", "last_bill"):
        last[c] = last[c].dt.strftime("%d-%b-%Y")

    if mode == "top":
        return last.sort_values("last_12m_revenue_L", ascending=False).head(top_n).reset_index(drop=True), None

    # Prior 3 years' buying, used to rank how much a silent customer matters
    prior = cs[(cs["date"] > as_of - pd.DateOffset(years=4)) & (cs["date"] <= as_of - pd.DateOffset(years=1))]
    last["prior_3y_revenue_L"] = (prior.groupby("party")["taxable"].sum() / _L).reindex(last["Customer"]).fillna(0).round(1).values
    if mode == "lost":
        lost = last[last["days_since_last_bill"] > 365].drop(columns=["prior_3y_revenue_L", "last_12m_revenue_L"])
        return lost.sort_values("lifetime_revenue_L", ascending=False).head(top_n).reset_index(drop=True), None
    # at_risk: bought in the last 2 years, silent for 90–365 days
    risk = last[last["days_since_last_bill"].between(90, 365) & (last["last_12m_revenue_L"] + last["prior_3y_revenue_L"] > 0)]
    return risk.sort_values("lifetime_revenue_L", ascending=False).head(top_n).reset_index(drop=True), None


# ── 6. Receivables / payables ─────────────────────────────────────────────────

def receivables_tool(side: str = "receivables", top_n: int = 15):
    """side = receivables (debtors, DSO) | payables (creditors, DPO)."""
    as_of = pd.to_datetime(md.BALANCE_AS_OF, format="%d-%m-%Y", errors="coerce")
    as_of = as_of if pd.notna(as_of) else md.LAST_SALE_DATE
    if side == "payables":
        bal = creditors.assign(balance=creditors["credit"] - creditors["debit"])
        flow = purchases[purchases["date"] > purchases["date"].max() - pd.DateOffset(months=12)]["bill_amt"].sum()
        days_label, who = "DPO_days", "Supplier"
    else:
        bal = debtors.assign(balance=debtors["debit"] - debtors["credit"])
        flow = sales[sales["date"] > md.LAST_SALE_DATE - pd.DateOffset(months=12)]["bill_amt"].sum()
        days_label, who = "DSO_days", "Customer"

    total = bal["balance"].sum()
    amount_col = "owes_us_L" if side == "receivables" else "we_owe_L"
    days = round(total / flow * 365) if flow else None
    advance = bal["balance"] < 0
    total_row = {
        "rank": 0,
        who: (f"TOTAL as of {md.BALANCE_AS_OF}: {days_label}={days}, {int((bal['balance'] > 0).sum())} parties with balance, "
              f"{int(advance.sum())} in advance (₹{-bal.loc[advance, 'balance'].sum() / _L:.1f}L), "
              f"last-12-month {'sales' if side == 'receivables' else 'purchases'} ₹{flow / _L:.1f}L"),
        amount_col: round(total / _L, 1), "share_pct": 100.0,
    }

    top = bal.sort_values("balance", ascending=False).head(top_n)
    top = pd.DataFrame({"rank": range(1, len(top) + 1), who: top["party"].values,
                        amount_col: (top["balance"] / _L).round(1).values,
                        "share_pct": (top["balance"] / total * 100).round(1).values})
    if side == "receivables":
        last_bill = sales.groupby("party")["date"].max()
        top["last_bill"] = top[who].map(last_bill).dt.strftime("%d-%b-%Y").fillna("—")
        top["days_since_last_bill"] = (as_of - top[who].map(last_bill)).dt.days
    else:
        top["source"] = bal.loc[bal.sort_values("balance", ascending=False).head(top_n).index, "source"].str.replace("CREDITOR LIST ", "").values
    # Snapshot only — no bill-wise ageing in this export; very old balances may be legacy / uncollectable
    return pd.concat([pd.DataFrame([total_row]), top], ignore_index=True), None


# ── 7. Suppliers / purchases ──────────────────────────────────────────────────

def supplier_tool(mode: str = "summary", top_n: int = 15):
    """mode = summary (purchases vs sales by FY) | top (supplier ranking, last 12 months vs lifetime)."""
    if mode == "top":
        last12 = purchases[purchases["date"] > purchases["date"].max() - pd.DateOffset(months=12)]
        g = purchases.groupby("party").agg(lifetime_L=("taxable", "sum"), bills=("bill_no", "count"), last_bill=("date", "max"))
        g["last_12m_L"] = (last12.groupby("party")["taxable"].sum()).reindex(g.index).fillna(0)
        g[["lifetime_L", "last_12m_L"]] = (g[["lifetime_L", "last_12m_L"]] / _L).round(1)
        g["share_last_12m_pct"] = (g["last_12m_L"] / g["last_12m_L"].sum() * 100).round(1)
        g["last_bill"] = g["last_bill"].dt.strftime("%d-%b-%Y")
        return g.sort_values("last_12m_L", ascending=False).head(top_n).reset_index().rename(columns={"party": "Supplier"}), None

    p = purchases.groupby("FY").agg(purchases_L=("taxable", "sum"), purchase_bills=("bill_no", "count"), suppliers=("party", "nunique"))
    p["sales_L"] = sales.groupby("FY")["taxable"].sum()
    p[["purchases_L", "sales_L"]] = (p[["purchases_L", "sales_L"]] / _L).round(1)
    p["purchase_to_sales_pct"] = (p["purchases_L"] / p["sales_L"] * 100).round(1)
    p["gross_margin_proxy_pct"] = (100 - p["purchase_to_sales_pct"]).round(1)
    p["note"] = "margin proxy ignores stock change — rising stock pushes it down"
    return p.reset_index(), None


# ── 8. Product trends (annual stock statement) ────────────────────────────────

def product_trend_tool(product_name: str = "", mode: str = "top"):
    """
    product_name given → that product's bought/sold/closing units for every FY.
    mode (no product)  = top (best sellers latest full FY) | dead (closing stock, ~no sales) |
                         overstock (closing > 1 year of sales) | summary (company stock by FY)
    """
    if product_name:
        key = md.product_key(product_name)
        hit = stock[stock["product_key"].str.contains(key, regex=False) | stock["product"].str.contains(product_name, case=False, regex=False)]
        if hit.empty:
            return pd.DataFrame({"Message": [f"No product matching '{product_name}' in stock statements."]}), None
        out = hit.sort_values(["product_name", "FY"])[["FY", "product", "pack", "units_bought", "units_sold", "closing_units"]]
        return out.reset_index(drop=True), None

    if mode == "summary":
        g = stock.groupby("FY").agg(products=("product_key", "nunique"), units_bought=("units_bought", "sum"),
                                    units_sold=("units_sold", "sum"), closing_units=("closing_units", "sum")).astype(int)
        g["build_up_units"] = g["units_bought"] - g["units_sold"]
        v = stock_values.set_index("FY")[["closing_value"]] / _L
        g["closing_value_L"] = v["closing_value"].round(1).reindex(g.index)
        return g.reset_index(), None

    # One row per product per FY — spelling variants / extra packs of the same product are summed
    agg = stock.groupby(["FY", "product_key"]).agg(
        product_name=("product_name", "first"), pack=("pack", "first"),
        units_bought=("units_bought", "sum"), units_sold=("units_sold", "sum"), closing_units=("closing_units", "sum"),
    ).reset_index()
    fys = sorted(agg["FY"].unique())
    latest_full, latest = fys[-2], fys[-1]   # last FY in the data is year-to-date
    cur = agg[agg["FY"] == latest].set_index("product_key")
    full = agg[agg["FY"] == latest_full].set_index("product_key")
    prev = agg[agg["FY"] == fys[-3]].set_index("product_key")

    if mode == "dead":
        d = cur[(cur["closing_units"] > 0) & (cur["units_sold"] <= cur["closing_units"] * 0.05)]
        out = d[["product_name", "pack", "units_bought", "units_sold", "closing_units"]].sort_values("closing_units", ascending=False)
        return out.reset_index(drop=True).assign(FY=f"{latest} (YTD)"), None
    if mode == "overstock":
        f = full.copy()
        f["months_of_stock"] = (f["closing_units"] / (f["units_sold"] / 12).replace(0, np.nan)).round(1)
        o = f[(f["closing_units"] > 0) & ((f["months_of_stock"] > 12) | f["months_of_stock"].isna())]
        out = o[["product_name", "pack", "units_bought", "units_sold", "closing_units", "months_of_stock"]].sort_values("closing_units", ascending=False)
        return out.reset_index(drop=True).assign(FY=latest_full), None

    t = full[["product_name", "pack", "units_sold", "closing_units"]].copy()
    t["units_sold_prev_FY"] = prev["units_sold"].reindex(t.index).fillna(0)
    t["YoY_pct"] = ((t["units_sold"] / t["units_sold_prev_FY"].replace(0, np.nan) - 1) * 100).round(1)
    t["units_sold_this_FY_ytd"] = cur["units_sold"].reindex(t.index).fillna(0)
    out = t.sort_values("units_sold", ascending=False).head(20).reset_index(drop=True)
    return out.rename(columns={"units_sold": f"units_sold_{latest_full}"}), None


# ── Company snapshot (feeds the KPI dashboard) ────────────────────────────────

def company_kpis() -> list[tuple[str, str]]:
    fy = sales.groupby("FY")["taxable"].sum()
    fys = list(fy.index)
    growth, _ = sales_growth_tool("fy")
    ytd_row = growth.iloc[-1]
    rec = (debtors["debit"] - debtors["credit"]).sum()
    s = md.MONTHLY_REVENUE
    fc, _ = revenue_forecast_tool()
    fy_base = fc.loc[fc["Metric"].str.contains("— base"), "Value"].iloc[0]
    top_cust, _ = customer_health_tool("top", 1)
    top_debtor, _ = receivables_tool("receivables", 1)
    best, _ = product_trend_tool(mode="top")
    dead, _ = product_trend_tool(mode="dead")
    lost, _ = customer_health_tool("lost", 1000)
    risk, _ = customer_health_tool("at_risk", 1000)
    return [
        (f"Revenue {fys[-2]} (full year)", f"₹ {fy.iloc[-2] / _L:.1f} lakh ({_pct(fy.iloc[-2], fy.iloc[-3]):+.1f}% YoY)"),
        (f"Revenue {fys[-1]} YTD", f"₹ {ytd_row['revenue_L']} lakh ({ytd_row['YoY_pct']:+.1f}% vs same months last year)"),
        (f"Forecast full {fys[-1]}", f"{fy_base} (±{md.FORECAST_ACCURACY.get('year')}%)"),
        ("Next-month revenue forecast", f"₹ {md._forecast(s, 1)[0] / _L:.1f} lakh (±{md.FORECAST_ACCURACY.get('month')}%)"),
        ("Active customers last 12 months", int(sales[(sales["date"] > md.LAST_SALE_DATE - pd.DateOffset(months=12)) & ~sales["is_cash"]]["party"].nunique())),
        ("Top customer last 12 months", f"{top_cust.iloc[0]['Customer']} (₹ {top_cust.iloc[0]['last_12m_revenue_L']} lakh)"),
        ("Customers at risk (silent 90–365 days)", len(risk)),
        ("Customers lost (silent > 1 year, incl. one-off buyers)", len(lost)),
        ("Lost customers with ≥ ₹10 lakh lifetime revenue", int((lost["lifetime_revenue_L"] >= 10).sum())),
        (f"Receivables outstanding ({md.BALANCE_AS_OF})", f"₹ {rec / _L:.1f} lakh"),
        ("Largest debtor", f"{top_debtor.iloc[1]['Customer']} (₹ {top_debtor.iloc[1]['owes_us_L']} lakh)"),
        (f"Best-selling product {fys[-2]} (units)", best.iloc[0]["product_name"]),
        (f"Dead-stock products {fys[-1]} YTD", len(dead)),
    ]


# ── Chart helper ──────────────────────────────────────────────────────────────

def _bar_line(frame: pd.DataFrame, x: str, y: str, title: str):
    fig = go.Figure(go.Bar(x=frame[x], y=frame[y], marker_color="#0078D4",
                           hovertemplate="%{x}<br>₹%{y:,.1f} lakh<extra></extra>"))
    fig.update_layout(title=title, template="plotly_white", height=380, yaxis_title="₹ lakh")
    return fig
