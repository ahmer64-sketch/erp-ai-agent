"""
Business dashboard charts — full Marg history (marg_data.py), FY2017-18 onwards.

Same style as erp_charts.py: plotly white, ₹ lakh on money axes.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import marg_data as md
import marg_tools as mt

BLUE, RED, GREEN, PURPLE, ORANGE, GREY = "#0078D4", "#D13438", "#107C10", "#5C2D91", "#FF8C00", "#8A8886"
_L = 1e5


def _layout(fig, title, height=400, **kw):
    kw = {"margin": dict(l=10, r=10, t=60, b=40), "legend": dict(orientation="h", y=1.12), **kw}
    fig.update_layout(title=title, title_font_size=14, height=height, plot_bgcolor="white", paper_bgcolor="white", **kw)
    return fig


# ── Revenue ───────────────────────────────────────────────────────────────────

def build_fy_revenue_chart():
    growth, _ = mt.sales_growth_tool("fy")
    full, ytd = growth.iloc[:-1], growth.iloc[-1]
    colors = [GREY if fy == "FY17-18" else BLUE for fy in full["FY"]]
    labels = [f"{v:+.0f}%" if pd.notna(v) else "" for v in full["YoY_pct"]]
    fig = go.Figure(go.Bar(x=full["FY"], y=full["revenue_L"], marker_color=colors, text=labels, textposition="outside",
                           hovertemplate="%{x}<br>₹%{y:,.1f} lakh<extra></extra>", name="Full year"))
    # Like-for-like YTD pair for the year in progress
    prev = float(ytd["note"].split("₹")[-1].rstrip("L"))
    fy_now = ytd["FY"].split()[0]
    fig.add_trace(go.Bar(x=[f"{fy_now} YTD"], y=[ytd["revenue_L"]], marker_color=GREEN, name=f"{fy_now} YTD",
                         text=[f"{ytd['YoY_pct']:+.0f}%"], textposition="outside",
                         hovertemplate="%{x}<br>₹%{y:,.1f} lakh<extra></extra>"))
    fig.add_trace(go.Bar(x=["Same months last year"], y=[prev], marker_color="#A6C8EA", name="Same months last year",
                         hovertemplate="₹%{y:,.1f} lakh<extra></extra>"))
    return _layout(fig, "Revenue by financial year (₹ lakh, taxable) — label = YoY growth", yaxis_title="₹ lakh",
                   showlegend=False)


def build_forecast_chart():
    _, fig = mt.revenue_forecast_tool()
    return _layout(fig, f"Monthly revenue — actual vs forecast (₹ lakh) · model error ±{md.FORECAST_ACCURACY.get('month')}%/month",
                   height=420)


def build_seasonality_chart():
    _, fig = mt.sales_seasonality_tool()
    return _layout(fig, "Seasonality index — 100 = average month (green strong, red weak)", height=380)


def build_cash_credit_chart():
    cc, _ = mt.cash_credit_tool()
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(x=cc["FY"], y=cc["credit_revenue_L"], name="Credit sales", marker_color=BLUE), secondary_y=False)
    fig.add_trace(go.Bar(x=cc["FY"], y=cc["cash_revenue_L"], name="Cash sales", marker_color=ORANGE), secondary_y=False)
    fig.add_trace(go.Scatter(x=cc["FY"], y=cc["cash_share_pct"], name="Cash share %", mode="lines+markers",
                             line=dict(color=RED)), secondary_y=True)
    fig.update_layout(barmode="stack")
    fig.update_yaxes(title_text="₹ lakh", secondary_y=False)
    fig.update_yaxes(title_text="cash share %", secondary_y=True, rangemode="tozero")
    return _layout(fig, "Cash vs credit sales by FY", height=380)


# ── Customers ─────────────────────────────────────────────────────────────────

def build_customer_base_chart():
    cs, _ = mt.customer_health_tool("summary")
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(x=cs["FY"], y=cs["active_customers"], name="Active customers", marker_color=BLUE), secondary_y=False)
    fig.add_trace(go.Bar(x=cs["FY"], y=cs["new_customers"], name="New customers", marker_color=GREEN), secondary_y=False)
    fig.add_trace(go.Scatter(x=cs["FY"], y=cs["retained_from_last_year_pct"], name="Retained from last year %",
                             mode="lines+markers", line=dict(color=PURPLE)), secondary_y=True)
    fig.update_yaxes(title_text="customers", secondary_y=False)
    fig.update_yaxes(title_text="retention %", range=[0, 100], secondary_y=True)
    note = " (current FY is year-to-date)"
    return _layout(fig, "Customer base by FY — active, new, retention" + note, height=400, barmode="group")


def build_top_customers_chart(n=10):
    top, _ = mt.customer_health_tool("top", n)
    top = top.iloc[::-1]
    fig = go.Figure(go.Bar(x=top["last_12m_revenue_L"], y=top["Customer"], orientation="h", marker_color=BLUE,
                           customdata=top[["outstanding_L", "days_since_last_bill"]],
                           hovertemplate="<b>%{y}</b><br>Last 12m: ₹%{x:,.1f} lakh<br>Outstanding: ₹%{customdata[0]:,.1f} lakh"
                                         "<br>Last bill %{customdata[1]} days ago<extra></extra>"))
    return _layout(fig, "Top customers — last 12 months revenue (₹ lakh)", height=420, xaxis_title="₹ lakh")


def build_debtors_chart(n=12):
    rec, _ = mt.receivables_tool("receivables", n)
    top = rec[rec["rank"] > 0].iloc[::-1]
    days = top["days_since_last_bill"].fillna(9999)
    colors = np.where(days > 365, RED, np.where(days > 90, ORANGE, GREEN))
    fig = go.Figure(go.Bar(x=top["owes_us_L"], y=top["Customer"], orientation="h", marker_color=colors,
                           customdata=top[["last_bill", "days_since_last_bill"]],
                           hovertemplate="<b>%{y}</b><br>Owes ₹%{x:,.1f} lakh<br>Last bill %{customdata[0]} "
                                         "(%{customdata[1]} days ago)<extra></extra>"))
    total = rec.iloc[0]["owes_us_L"]
    return _layout(fig, f"Who owes us — top debtors (₹ lakh) · total ₹{total:.1f}L as of {md.BALANCE_AS_OF}"
                        "<br><sup>green = bought in last 90 days · orange = 90–365 days · red = silent > 1 year</sup>",
                   height=440, xaxis_title="₹ lakh")


def build_creditors_chart(n=10):
    pay, _ = mt.receivables_tool("payables", n)
    top = pay[pay["rank"] > 0].iloc[::-1]
    fig = go.Figure(go.Bar(x=top["we_owe_L"], y=top["Supplier"], orientation="h", marker_color=PURPLE,
                           hovertemplate="<b>%{y}</b><br>We owe ₹%{x:,.1f} lakh<extra></extra>"))
    total = pay.iloc[0]["we_owe_L"]
    return _layout(fig, f"What we owe — top suppliers (₹ lakh) · total ₹{total:.1f}L", height=440, xaxis_title="₹ lakh")


# ── Purchases & stock ─────────────────────────────────────────────────────────

def build_purchase_vs_sales_chart():
    sp, _ = mt.supplier_tool("summary")
    sp = sp[sp["FY"] != "FY17-18"]   # partial first year distorts the margin axis
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(x=sp["FY"], y=sp["sales_L"], name="Sales", marker_color=BLUE), secondary_y=False)
    fig.add_trace(go.Bar(x=sp["FY"], y=sp["purchases_L"], name="Purchases", marker_color=PURPLE), secondary_y=False)
    fig.add_trace(go.Scatter(x=sp["FY"], y=sp["gross_margin_proxy_pct"], name="Margin proxy % (1 − purchases/sales)",
                             mode="lines+markers", line=dict(color=GREEN)), secondary_y=True)
    fig.update_yaxes(title_text="₹ lakh", secondary_y=False)
    fig.update_yaxes(title_text="margin proxy %", rangemode="tozero", secondary_y=True)
    return _layout(fig, "Purchases vs sales by FY (₹ lakh)", height=400, barmode="group")


def build_stock_flow_chart():
    st, _ = mt.product_trend_tool(mode="summary")
    fig = go.Figure()
    fig.add_trace(go.Bar(x=st["FY"], y=st["units_bought"], name="Units bought", marker_color=PURPLE))
    fig.add_trace(go.Bar(x=st["FY"], y=st["units_sold"], name="Units sold", marker_color=BLUE))
    fig.add_trace(go.Scatter(x=st["FY"], y=st["closing_units"], name="Closing stock", mode="lines+markers",
                             line=dict(color=RED, width=3)))
    return _layout(fig, "Stock flow by FY (units, all products) — rising red line = stock building up", height=400,
                   barmode="group", yaxis_title="units")


# ── Display column names ──────────────────────────────────────────────────────

_WORDS = {"yoy": "YoY", "mom": "MoM", "abc": "ABC", "dso": "DSO", "dpo": "DPO", "fy": "FY", "ytd": "YTD", "12m": "12 months"}
_UNITS = [("_L", " (₹ lakh)"), ("_k", " (₹ thousand)"), ("_pct", " (%)"), ("_pts", " (pts)"), ("_usd", " ($)")]


def pretty_column(col: str) -> str:
    """'lifetime_revenue_L' → 'Lifetime revenue (₹ lakh)', 'YoY_pct' → 'YoY (%)'. Display only — tools keep raw names."""
    name, unit = str(col), ""
    for suffix, label in _UNITS:
        if name.endswith(suffix):
            name, unit = name[: -len(suffix)], label
            break
    words = [_WORDS.get(w.lower(), w) for w in name.replace("_", " ").split()]
    if not words:
        return str(col)
    words[0] = words[0] if words[0][:1].isupper() else words[0].capitalize()
    return " ".join(words) + unit


def pretty_columns(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or not hasattr(frame, "rename"):
        return frame
    return frame.rename(columns=pretty_column)


# ── Tables ────────────────────────────────────────────────────────────────────

def lost_customers_table(n=12):
    t, _ = mt.customer_health_tool("lost", n)
    return pretty_columns(t[["Customer", "lifetime_revenue_L", "last_bill", "days_since_last_bill", "outstanding_L"]])


def at_risk_customers_table(n=12):
    t, _ = mt.customer_health_tool("at_risk", n)
    return pretty_columns(t[["Customer", "lifetime_revenue_L", "last_12m_revenue_L", "last_bill", "days_since_last_bill", "outstanding_L"]])


def dead_stock_table():
    t, _ = mt.product_trend_tool(mode="dead")
    return pretty_columns(t.drop(columns="FY"))


def overstock_table(n=15):
    t, _ = mt.product_trend_tool(mode="overstock")
    return pretty_columns(t.drop(columns="FY").head(n))


def top_products_table(n=15):
    t, _ = mt.product_trend_tool(mode="top")
    return pretty_columns(t.head(n))


# ── KPI cards ─────────────────────────────────────────────────────────────────

def business_kpi_html() -> str:
    def card(label, value, color=BLUE, sub=None):
        sub_html = f'<div style="font-size:10px;color:#aaa;margin-top:4px">{sub}</div>' if sub else ""
        return f"""
        <div style="background:white;border-radius:10px;padding:16px 18px;box-shadow:0 2px 8px rgba(0,0,0,0.08);text-align:center;flex:1;min-width:150px;margin:6px">
            <div style="font-size:11px;color:#888;text-transform:uppercase;letter-spacing:0.8px;margin-bottom:6px">{label}</div>
            <div style="font-size:22px;font-weight:700;color:{color}">{value}</div>
            {sub_html}
        </div>"""

    k = dict(mt.company_kpis())
    get = lambda prefix: next(v for key, v in k.items() if key.startswith(prefix))
    fy_full = next(key for key in k if key.startswith("Revenue") and "full year" in key).split()[1]
    fy_now = next(key for key in k if key.startswith("Revenue") and "YTD" in key).split()[1]
    ytd = get(f"Revenue {fy_now} YTD")
    ytd_val, ytd_growth = ytd.split(" (")[0], ytd.split("(")[1].split("%")[0] + "%"
    full = get(f"Revenue {fy_full}")
    full_val, full_growth = full.split(" (")[0], full.split("(")[1].split(" ")[0]
    top_cust = get("Top customer")
    debtor = get("Largest debtor")
    growth_color = GREEN if not ytd_growth.startswith("-") else RED

    as_of = (f"Sales to {md.LAST_SALE_DATE:%d %b %Y} · purchases to {md.purchases['date'].max():%d %b %Y} · "
             f"balances as of {md.BALANCE_AS_OF} · source: Marg ERP exports in reman/")
    return f"""
    <div style="display:flex;flex-wrap:wrap;margin-bottom:4px">
        {card(f"Revenue {fy_now} YTD", ytd_val, growth_color, f"{ytd_growth} vs same months last year")}
        {card(f"Forecast full {fy_now}", get("Forecast full").split(" (")[0].replace("₹", "₹ ").replace("L", " lakh"), BLUE, "±" + get("Forecast full").split("±")[1].rstrip(")") + " typical error")}
        {card(f"Revenue {fy_full}", full_val, BLUE, f"{full_growth} YoY")}
        {card("Next month forecast", get("Next-month").split(" (")[0], BLUE, "±" + get("Next-month").split("±")[1].rstrip(")"))}
    </div>
    <div style="display:flex;flex-wrap:wrap;margin-bottom:4px">
        {card("Active customers (12m)", get("Active customers"), GREEN, f"top: {top_cust}")}
        {card("Customers at risk", get("Customers at risk"), ORANGE, "silent 90–365 days")}
        {card("Big customers lost", get("Lost customers with"), RED, "≥ ₹10 lakh lifetime, silent > 1 year")}
        {card("Receivables", get("Receivables outstanding"), RED, f"largest: {debtor}")}
        {card("Dead-stock products", get("Dead-stock"), PURPLE, f"{fy_now} YTD")}
    </div>
    <div style="font-size:11px;color:#888;margin:2px 8px 10px 8px">{as_of}</div>"""
