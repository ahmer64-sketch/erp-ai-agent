"""
Chart layer — Plotly dashboard builders for the static analytics panels.
All functions read from erp_data (read-only) and return Plotly figures.
"""

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from erp_data import df, df_purchase, df_returns, N_MONTHS, ABC_MAP, KPI_CACHE, get_reorder_months, classify_stock


def build_revenue_chart():
    data = (
        df.groupby("Product")["Value"].sum()
        .reset_index()
        .rename(columns={"Value": "total_revenue"})
        .sort_values("total_revenue", ascending=False)
        .head(10)
    )
    fig = px.bar(
        data, x="total_revenue", y="Product", orientation="h",
        color="total_revenue", color_continuous_scale="Blues",
        labels={"total_revenue": "Revenue (₹)", "Product": ""},
    )
    fig.update_layout(
        title=dict(text="Top 10 Products by Revenue", font=dict(size=14)),
        height=360, plot_bgcolor="white", paper_bgcolor="white",
        coloraxis_showscale=False, margin=dict(l=10, r=20, t=40, b=10),
        yaxis=dict(autorange="reversed"),
    )
    return fig


def build_inventory_chart():
    summary = df.groupby("Product").agg(
        total_units_sold=("Quantity", "sum"),
        latest_balance=("Balance", "last"),
    ).reset_index()
    summary["monthly_demand"]      = summary["total_units_sold"] / N_MONTHS
    summary["months_of_stock_left"] = (summary["latest_balance"] / summary["monthly_demand"].replace(0, float("nan"))).round(2)
    summary = summary.dropna(subset=["months_of_stock_left"]).sort_values("months_of_stock_left").head(10)

    fig = px.bar(
        summary, x="months_of_stock_left", y="Product", orientation="h",
        color="months_of_stock_left", color_continuous_scale="RdYlGn",
        range_color=[0, 6], labels={"months_of_stock_left": "Months of Stock", "Product": ""},
    )
    fig.update_layout(
        title=dict(text="Inventory Risk (Months of Stock Left)", font=dict(size=14)),
        height=360, plot_bgcolor="white", paper_bgcolor="white",
        coloraxis_showscale=False, margin=dict(l=10, r=20, t=40, b=10),
        yaxis=dict(autorange="reversed"),
    )
    return fig


def build_reorder_alert_chart():
    summary = df.groupby("Product").agg(
        total_units_sold=("Quantity", "sum"),
        latest_balance=("Balance", "last"),
    ).reset_index()
    summary["monthly_demand"]       = summary["total_units_sold"] / N_MONTHS
    summary["months_of_stock_left"] = summary["latest_balance"] / summary["monthly_demand"].replace(0, float("nan"))
    summary["reorder_point_months"] = summary["Product"].map(get_reorder_months)
    summary = summary.dropna(subset=["months_of_stock_left"])
    reorder_df = summary[summary["months_of_stock_left"] < summary["reorder_point_months"]].sort_values("months_of_stock_left")

    if reorder_df.empty:
        fig = px.bar(title="No products below safety stock reorder threshold")
        fig.update_layout(height=300, plot_bgcolor="white", paper_bgcolor="white")
        return fig, 0

    fig = px.bar(
        reorder_df, x="months_of_stock_left", y="Product", orientation="h",
        color="months_of_stock_left", color_continuous_scale="Reds_r",
        range_color=[0, reorder_df["reorder_point_months"].max()],
        labels={"months_of_stock_left": "Months of Stock Left", "Product": ""},
        custom_data=["reorder_point_months"],
    )
    fig.update_traces(hovertemplate="<b>%{y}</b><br>Stock Left: %{x:.1f}m<br>Reorder At: %{customdata[0]:.1f}m<extra></extra>")
    fig.update_layout(
        title=dict(text=f"Reorder Now — {len(reorder_df)} Products Below Safety Stock Threshold", font=dict(size=14)),
        height=max(300, len(reorder_df) * 32 + 80),
        plot_bgcolor="white", paper_bgcolor="white",
        coloraxis_showscale=False, margin=dict(l=10, r=20, t=50, b=10),
        yaxis=dict(autorange="reversed"),
    )
    return fig, len(reorder_df)


def build_inventory_turnover_chart():
    summary = df.groupby("Product").agg(
        total_units_sold=("Quantity", "sum"),
        latest_balance=("Balance", "last"),
    ).reset_index()
    summary["inventory_turnover"] = (summary["total_units_sold"] / summary["latest_balance"].replace(0, float("nan"))).round(2)
    summary = summary.dropna(subset=["inventory_turnover"])

    def _bar(data, title, scale):
        fig = px.bar(
            data, x="inventory_turnover", y="Product", orientation="h",
            color="inventory_turnover", color_continuous_scale=scale,
            labels={"inventory_turnover": "Turnover Ratio", "Product": ""},
        )
        fig.update_layout(
            title=dict(text=title, font=dict(size=14)),
            height=360, plot_bgcolor="white", paper_bgcolor="white",
            coloraxis_showscale=False, margin=dict(l=10, r=20, t=40, b=10),
            yaxis=dict(autorange="reversed"),
        )
        return fig

    return (
        _bar(summary.nlargest(10, "inventory_turnover"),  "Top 10 Inventory Turnover (Fast Movers)", "Greens"),
        _bar(summary.nsmallest(10, "inventory_turnover"), "Bottom 10 Inventory Turnover (Slow Movers)", "Oranges_r"),
    )


def build_stock_status_chart():
    summary = df.groupby("Product").agg(
        total_units_sold=("Quantity", "sum"),
        latest_balance=("Balance", "last"),
    ).reset_index()
    summary["monthly_demand"]       = summary["total_units_sold"] / N_MONTHS
    summary["months_of_stock_left"] = summary["latest_balance"] / summary["monthly_demand"].replace(0, float("nan"))
    summary = summary.dropna(subset=["months_of_stock_left"])
    summary["stock_status"] = summary.apply(lambda r: classify_stock(r["months_of_stock_left"], r["Product"]), axis=1)

    counts    = summary["stock_status"].value_counts().reset_index()
    counts.columns = ["status", "count"]
    color_map = {"STOCKOUT RISK": "#D13438", "HEALTHY": "#107C10", "OVERSTOCK": "#FFB900"}

    fig = px.pie(counts, names="status", values="count", hole=0.55, color="status", color_discrete_map=color_map)
    fig.update_traces(textinfo="label+percent+value", textfont_size=12)
    fig.update_layout(
        title=dict(text="Stock Health Distribution", font=dict(size=14)),
        height=360, paper_bgcolor="white",
        legend=dict(orientation="v", x=1.0, y=0.5),
        margin=dict(l=10, r=10, t=40, b=10),
        annotations=[dict(text=f"{len(summary)}<br>Products", x=0.5, y=0.5, font_size=14, showarrow=False)],
    )
    return fig


def build_abc_charts():
    abc_counts = (
        pd.Series(ABC_MAP).rename("abc_class")
        .reset_index()
        .rename(columns={"index": "Product"})
        ["abc_class"].value_counts()
        .reset_index()
    )
    abc_counts.columns = ["class", "count"]
    color_map = {"A": "#0078D4", "B": "#FFB900", "C": "#D13438"}

    label_map = {
        "A": "A — Top 80% Revenue",
        "B": "B — Next 15% Revenue",
        "C": "C — Bottom 5% Revenue",
    }
    abc_counts["label"] = abc_counts["class"].map(label_map)

    fig_donut = px.pie(abc_counts, names="label", values="count", hole=0.55,
                       color="class", color_discrete_map=color_map)
    fig_donut.update_traces(textinfo="label+percent+value", textfont_size=11)
    fig_donut.update_layout(
        title=dict(text="ABC Class Distribution (Pareto 80/15/5)", font=dict(size=14)),
        height=360, paper_bgcolor="white",
        margin=dict(l=10, r=10, t=40, b=10),
        legend=dict(orientation="v", x=1.0, y=0.5, font=dict(size=11)),
        annotations=[dict(text="Products", x=0.5, y=0.5, font_size=13, showarrow=False)],
    )

    summary = df.groupby("Product").agg(
        total_units_sold=("Quantity", "sum"),
        latest_balance=("Balance", "last"),
    ).reset_index()
    summary["monthly_demand"]       = summary["total_units_sold"] / N_MONTHS
    summary["months_of_stock_left"] = summary["latest_balance"] / summary["monthly_demand"].replace(0, float("nan"))
    summary = summary.dropna(subset=["months_of_stock_left"])
    summary["abc_class"]   = summary["Product"].map(ABC_MAP)
    summary["stock_status"] = summary.apply(lambda r: classify_stock(r["months_of_stock_left"], r["Product"]), axis=1)

    matrix = summary.groupby(["abc_class", "stock_status"]).size().reset_index(name="count")
    status_colors = {"STOCKOUT RISK": "#D13438", "HEALTHY": "#107C10", "OVERSTOCK": "#FFB900"}
    fig_matrix = px.bar(
        matrix, x="abc_class", y="count", color="stock_status",
        barmode="group", color_discrete_map=status_colors,
        category_orders={"abc_class": ["A", "B", "C"]},
        labels={"abc_class": "ABC Class", "count": "Products", "stock_status": "Status"},
    )
    fig_matrix.update_layout(
        title=dict(text="ABC × Stock Status Matrix  (A=80% rev · B=15% · C=5%)", font=dict(size=14)),
        height=360, plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(l=10, r=10, t=40, b=10),
        legend=dict(orientation="h", y=-0.2),
    )
    return fig_donut, fig_matrix


def build_flow_rate_charts():
    summary = df.groupby("Product").agg(
        total_units_sold=("Quantity", "sum"),
        latest_balance=("Balance", "last"),
    ).reset_index()
    summary["monthly_demand"] = summary["total_units_sold"] / N_MONTHS
    summary = summary[summary["latest_balance"] > 0]
    summary["flow_rate"] = (summary["monthly_demand"] / summary["latest_balance"]).round(3)
    summary = summary.dropna(subset=["flow_rate"])

    def _bar(data, title, scale):
        fig = px.bar(
            data, x="flow_rate", y="Product", orientation="h",
            color="flow_rate", color_continuous_scale=scale,
            labels={"flow_rate": "Flow Rate (demand/stock)", "Product": ""},
        )
        fig.update_layout(
            title=dict(text=title, font=dict(size=14)),
            height=300, plot_bgcolor="white", paper_bgcolor="white",
            coloraxis_showscale=False, margin=dict(l=10, r=20, t=40, b=10),
            yaxis=dict(autorange="reversed"),
        )
        return fig

    return (
        _bar(summary.nlargest(5,  "flow_rate"), "Top 5 Fastest Moving Stock",   "Reds"),
        _bar(summary.nsmallest(5, "flow_rate"), "Bottom 5 Slowest Moving Stock", "Blues"),
    )


def build_distributor_charts():
    dist_df = df.dropna(subset=["Description"]).copy()
    dist_df = dist_df[dist_df["Description"].str.strip().str.len() > 2]

    summary = dist_df.groupby("Description").agg(
        total_revenue=("Value", "sum"),
        total_units=("Quantity", "sum"),
        total_orders=("Quantity", "count"),
    ).reset_index().rename(columns={"Description": "Distributor"})

    total_rev = summary["total_revenue"].sum()
    summary["pct_of_sales"] = (summary["total_revenue"] / total_rev * 100).round(1)
    summary["pct_label"]    = summary["pct_of_sales"].apply(lambda x: f"{x}%")

    top10 = summary.nlargest(10, "total_revenue")
    bot5  = summary.nsmallest(5,  "total_revenue")

    # ── Top 10 with % labels ──────────────────────────────────────────────────
    fig_top = px.bar(
        top10, x="total_revenue", y="Distributor", orientation="h",
        color="total_revenue", color_continuous_scale="Blues",
        labels={"total_revenue": "Revenue (₹)", "Distributor": ""},
        custom_data=["total_units", "total_orders", "pct_of_sales", "pct_label"],
        text="pct_label",
    )
    fig_top.update_traces(
        textposition="outside",
        textfont=dict(size=11, color="#333"),
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Revenue: ₹%{x:,.0f}<br>"
            "% of Total Sales: %{customdata[2]}%<br>"
            "Units: %{customdata[0]:,.0f}<br>"
            "Orders: %{customdata[1]}<extra></extra>"
        ),
    )
    fig_top.update_layout(
        title=dict(text="Top 10 Distributors by Revenue (% of Total Sales)", font=dict(size=14)),
        height=360, plot_bgcolor="white", paper_bgcolor="white",
        coloraxis_showscale=False,
        margin=dict(l=10, r=60, t=40, b=10),
        yaxis=dict(autorange="reversed"),
    )

    # ── Bottom 5 ──────────────────────────────────────────────────────────────
    fig_bot = px.bar(
        bot5, x="total_revenue", y="Distributor", orientation="h",
        color="total_revenue", color_continuous_scale="Oranges_r",
        labels={"total_revenue": "Revenue (₹)", "Distributor": ""},
        custom_data=["total_units", "total_orders", "pct_of_sales"],
        text="pct_label",
    )
    fig_bot.update_traces(
        textposition="outside",
        textfont=dict(size=11, color="#333"),
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Revenue: ₹%{x:,.0f}<br>"
            "% of Total Sales: %{customdata[2]}%<br>"
            "Units: %{customdata[0]:,.0f}<br>"
            "Orders: %{customdata[1]}<extra></extra>"
        ),
    )
    fig_bot.update_layout(
        title=dict(text="Bottom 5 Distributors by Revenue (% of Total Sales)", font=dict(size=14)),
        height=360, plot_bgcolor="white", paper_bgcolor="white",
        coloraxis_showscale=False,
        margin=dict(l=10, r=60, t=40, b=10),
        yaxis=dict(autorange="reversed"),
    )

    return fig_top, fig_bot


def build_monthly_trend_chart():
    monthly = df.copy()
    monthly["YearMonth"] = monthly["Date"].dt.to_period("M")
    trend = monthly.groupby("YearMonth").agg(
        revenue=("Value",   "sum"),
        units=("Quantity",  "sum"),
        orders=("Quantity", "count"),
    ).reset_index().sort_values("YearMonth")

    # ── Trend + seasonal forecast ─────────────────────────────────────────────
    x         = np.arange(len(trend))
    y         = trend["revenue"].values
    slope, intercept = np.polyfit(x, y, 1)

    seasonal_idx = monthly.groupby(monthly["Date"].dt.month)["Value"].sum()
    seasonal_idx = seasonal_idx / seasonal_idx.mean()

    last_period = trend["YearMonth"].iloc[-1]
    forecast_labels, forecast_vals = [], []
    for i in range(1, 7):
        future_t      = len(trend) - 1 + i
        future_period = last_period + i
        trend_val     = intercept + slope * future_t
        s_idx         = float(seasonal_idx.get(future_period.month, 1.0) or 1.0)
        forecast_labels.append(str(future_period))
        forecast_vals.append(max(0, trend_val * s_idx))

    x_labels = trend["YearMonth"].astype(str).tolist()

    fig = go.Figure()

    # Actual revenue
    fig.add_trace(go.Scatter(
        x=x_labels, y=y.tolist(),
        mode="lines+markers", name="Actual Revenue",
        line=dict(color="#0078D4", width=2.5),
        fill="tozeroy", fillcolor="rgba(0,120,212,0.08)",
        customdata=trend[["units", "orders"]].values,
        hovertemplate="<b>%{x}</b><br>Revenue: ₹%{y:,.0f}<br>Units: %{customdata[0]:,.0f}<br>Orders: %{customdata[1]}<extra></extra>",
    ))

    # Trend line
    fig.add_trace(go.Scatter(
        x=x_labels, y=(intercept + slope * x).tolist(),
        mode="lines", name="Trend",
        line=dict(color="#888", dash="dot", width=1.5),
        hoverinfo="skip",
    ))

    # 6-month forecast
    forecast_x = [x_labels[-1]] + forecast_labels
    forecast_y = [float(y[-1])] + forecast_vals
    fig.add_trace(go.Scatter(
        x=forecast_x, y=forecast_y,
        mode="lines+markers", name="Forecast (6m)",
        line=dict(color="#D13438", dash="dash", width=2),
        marker=dict(symbol="diamond", size=7),
        hovertemplate="<b>%{x}</b><br>Forecast: ₹%{y:,.0f}<extra></extra>",
    ))

    fig.update_layout(
        title=dict(text="Monthly Revenue Trend + 6-Month Forecast", font=dict(size=14)),
        height=360, plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(l=10, r=10, t=40, b=60),
        xaxis=dict(tickangle=45, tickfont=dict(size=10)),
        yaxis=dict(title="Revenue (₹)", gridcolor="#f0f0f0"),
        hovermode="x unified",
        legend=dict(orientation="h", y=1.12),
    )
    return fig


def build_return_rate_charts():
    if df_returns.empty:
        empty = go.Figure().update_layout(
            title="No Sale Return data available",
            height=320, plot_bgcolor="white", paper_bgcolor="white",
        )
        return empty, empty

    # ── By Product ────────────────────────────────────────────────────────────
    sold    = df.groupby("Product")["Quantity"].sum().rename("sold")
    returns = df_returns.groupby("Product")["Quantity"].sum().rename("returned")
    prod_df = pd.concat([sold, returns], axis=1).fillna(0).reset_index()
    prod_df = prod_df[prod_df["sold"] > 0].copy()
    prod_df["return_rate"] = (prod_df["returned"] / prod_df["sold"] * 100).round(2)
    prod_df["abc_class"]   = prod_df["Product"].map(ABC_MAP)
    prod_df = prod_df[prod_df["return_rate"] > 0].sort_values("return_rate", ascending=False).head(15)

    color_map = {"A": "#0078D4", "B": "#FFB900", "C": "#D13438"}
    prod_colors = prod_df["abc_class"].map(color_map).fillna("#aaa").tolist()

    fig_prod = go.Figure(go.Bar(
        x=prod_df["return_rate"], y=prod_df["Product"],
        orientation="h",
        marker_color=prod_colors,
        text=prod_df["return_rate"].apply(lambda x: f"{x}%"),
        textposition="outside",
        customdata=prod_df[["returned", "sold", "abc_class"]].values,
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Return Rate: %{x:.2f}%<br>"
            "Returned: %{customdata[0]:,.0f} units<br>"
            "Sold: %{customdata[1]:,.0f} units<br>"
            "Class: %{customdata[2]}<extra></extra>"
        ),
    ))
    fig_prod.update_layout(
        title=dict(text="Return Rate by Product (% of Units Sold)", font=dict(size=14)),
        height=400, plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(l=10, r=60, t=40, b=10),
        xaxis=dict(title="Return Rate (%)", gridcolor="#f0f0f0"),
        yaxis=dict(autorange="reversed"),
    )

    # ── By Distributor ────────────────────────────────────────────────────────
    dist_returns = df_returns.dropna(subset=["Description"]).copy()
    dist_returns = dist_returns[dist_returns["Description"].str.strip().str.len() > 2]
    dist_sales   = df.dropna(subset=["Description"]).copy()
    dist_sales   = dist_sales[dist_sales["Description"].str.strip().str.len() > 2]

    d_sold    = dist_sales.groupby("Description")["Quantity"].sum().rename("sold")
    d_returns = dist_returns.groupby("Description")["Quantity"].sum().rename("returned")
    dist_df   = pd.concat([d_sold, d_returns], axis=1).fillna(0).reset_index()
    dist_df.columns = ["Distributor", "sold", "returned"]
    dist_df   = dist_df[dist_df["sold"] > 0].copy()
    dist_df["return_rate"] = (dist_df["returned"] / dist_df["sold"] * 100).round(2)
    dist_df   = dist_df[dist_df["return_rate"] > 0].sort_values("return_rate", ascending=False).head(10)

    fig_dist = go.Figure(go.Bar(
        x=dist_df["return_rate"], y=dist_df["Distributor"],
        orientation="h",
        marker_color="#D13438",
        opacity=0.8,
        text=dist_df["return_rate"].apply(lambda x: f"{x}%"),
        textposition="outside",
        customdata=dist_df[["returned", "sold"]].values,
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Return Rate: %{x:.2f}%<br>"
            "Returned: %{customdata[0]:,.0f} units<br>"
            "Sold: %{customdata[1]:,.0f} units<extra></extra>"
        ),
    ))
    fig_dist.update_layout(
        title=dict(text="Return Rate by Distributor (% of Units Sold)", font=dict(size=14)),
        height=400, plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(l=10, r=60, t=40, b=10),
        xaxis=dict(title="Return Rate (%)", gridcolor="#f0f0f0"),
        yaxis=dict(autorange="reversed"),
    )

    return fig_prod, fig_dist


def build_pareto_curve():
    summary = df.groupby("Product")["Value"].sum().reset_index()
    summary.columns = ["Product", "revenue"]
    summary = summary.sort_values("revenue", ascending=False).reset_index(drop=True)

    total = summary["revenue"].sum()
    summary["cumulative_pct"] = (summary["revenue"].cumsum() / total * 100).round(2)
    summary["abc_class"]      = summary["Product"].map(ABC_MAP)

    color_map = {"A": "#0078D4", "B": "#FFB900", "C": "#D13438"}
    bar_colors = summary["abc_class"].map(color_map).tolist()

    fig = go.Figure()

    # Shaded ABC zones
    a_cutoff = summary[summary["cumulative_pct"] <= 80].index.max() + 1 if not summary[summary["cumulative_pct"] <= 80].empty else 0
    b_cutoff = summary[summary["cumulative_pct"] <= 95].index.max() + 1 if not summary[summary["cumulative_pct"] <= 95].empty else 0
    n        = len(summary)

    for x0, x1, color, label in [
        (-0.5, a_cutoff - 0.5, "rgba(0,120,212,0.07)",  "A — 80%"),
        (a_cutoff - 0.5, b_cutoff - 0.5, "rgba(255,185,0,0.1)",  "B — 15%"),
        (b_cutoff - 0.5, n - 0.5,        "rgba(209,52,56,0.07)", "C — 5%"),
    ]:
        fig.add_vrect(x0=x0, x1=x1, fillcolor=color, line_width=0,
                      annotation_text=label, annotation_position="top left",
                      annotation_font=dict(size=10, color="#666"))

    # Revenue bars
    fig.add_trace(go.Bar(
        x=summary["Product"], y=summary["revenue"],
        name="Revenue", marker_color=bar_colors,
        opacity=0.85, yaxis="y1",
        hovertemplate="<b>%{x}</b><br>Revenue: ₹%{y:,.0f}<extra></extra>",
    ))

    # Cumulative % line
    fig.add_trace(go.Scatter(
        x=summary["Product"], y=summary["cumulative_pct"],
        name="Cumulative %", mode="lines+markers",
        line=dict(color="#333", width=2),
        marker=dict(size=4),
        yaxis="y2",
        hovertemplate="<b>%{x}</b><br>Cumulative: %{y:.1f}%<extra></extra>",
    ))

    # 80% and 95% reference lines
    for level, color in [(80, "#0078D4"), (95, "#FFB900")]:
        fig.add_hline(y=level, line=dict(color=color, dash="dot", width=1),
                      yref="y2", annotation_text=f"{level}%",
                      annotation_position="right",
                      annotation_font=dict(size=10, color=color))

    fig.update_layout(
        title=dict(text="Pareto Revenue Curve — ABC Concentration Analysis", font=dict(size=14)),
        height=460, plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(l=10, r=60, t=40, b=120),
        xaxis=dict(tickangle=45, tickfont=dict(size=9)),
        yaxis=dict(title="Revenue (₹)", gridcolor="#f0f0f0"),
        yaxis2=dict(title="Cumulative %", overlaying="y", side="right",
                    range=[0, 105], gridcolor="rgba(0,0,0,0)"),
        legend=dict(orientation="h", y=1.1),
        bargap=0.15,
    )
    return fig


def build_price_volume_scatter():
    summary = df.groupby("Product").agg(
        total_units=("Quantity", "sum"),
        total_revenue=("Value",  "sum"),
    ).reset_index()
    summary["avg_price"]  = (summary["total_revenue"] / summary["total_units"]).round(2)
    summary["abc_class"]  = summary["Product"].map(ABC_MAP)
    summary["size_scaled"] = (summary["total_revenue"] / summary["total_revenue"].max() * 40 + 8).round(0)

    color_map = {"A": "#0078D4", "B": "#FFB900", "C": "#D13438"}

    fig = go.Figure()
    for cls in ["A", "B", "C"]:
        grp = summary[summary["abc_class"] == cls]
        fig.add_trace(go.Scatter(
            x=grp["total_units"],
            y=grp["avg_price"],
            mode="markers",
            name=f"Class {cls}",
            marker=dict(
                size=grp["size_scaled"].tolist(),
                color=color_map[cls],
                opacity=0.75,
                line=dict(width=1, color="white"),
            ),
            text=grp["Product"],
            customdata=grp[["total_revenue", "abc_class"]].values,
            hovertemplate=(
                "<b>%{text}</b><br>"
                "Units Sold: %{x:,.0f}<br>"
                "Avg Price: ₹%{y:,.2f}<br>"
                "Revenue: ₹%{customdata[0]:,.0f}<br>"
                "Class: %{customdata[1]}<extra></extra>"
            ),
        ))

    # Quadrant lines at medians
    med_units = summary["total_units"].median()
    med_price = summary["avg_price"].median()
    line_style = dict(color="rgba(150,150,150,0.4)", width=1, dash="dash")
    fig.add_vline(x=med_units, line=line_style)
    fig.add_hline(y=med_price, line=line_style)

    # Quadrant labels
    x_max = summary["total_units"].max()
    y_max = summary["avg_price"].max()
    for text, x, y, anchor in [
        ("High Price / Low Volume",  med_units * 0.05, y_max * 0.97,  "left"),
        ("High Price / High Volume", x_max * 0.97,    y_max * 0.97,  "right"),
        ("Low Price / Low Volume",   med_units * 0.05, med_price * 0.6, "left"),
        ("Low Price / High Volume",  x_max * 0.97,    med_price * 0.6, "right"),
    ]:
        fig.add_annotation(
            x=x, y=y, text=text, showarrow=False,
            font=dict(size=9, color="#aaa"),
            xanchor=anchor,
        )

    fig.update_layout(
        title=dict(text="Price × Volume Matrix (bubble size = revenue)", font=dict(size=14)),
        height=460, plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(l=10, r=10, t=40, b=10),
        xaxis=dict(title="Total Units Sold", gridcolor="#f0f0f0"),
        yaxis=dict(title="Avg Selling Price (₹)", gridcolor="#f0f0f0"),
        legend=dict(orientation="h", y=1.1),
    )
    return fig


def build_distributor_product_heatmap():
    dist_df = df.dropna(subset=["Description"]).copy()
    dist_df = dist_df[dist_df["Description"].str.strip().str.len() > 2]

    top_dists = dist_df.groupby("Description")["Value"].sum().nlargest(10).index.tolist()
    top_prods = dist_df.groupby("Product")["Value"].sum().nlargest(10).index.tolist()

    filtered = dist_df[dist_df["Description"].isin(top_dists) & dist_df["Product"].isin(top_prods)]
    pivot    = filtered.pivot_table(index="Description", columns="Product", values="Value", aggfunc="sum", fill_value=0)
    pivot    = pivot.reindex(index=top_dists, columns=top_prods, fill_value=0)

    # Truncate long distributor names
    pivot.index = [n[:22] + "…" if len(n) > 22 else n for n in pivot.index]

    fig = px.imshow(
        pivot,
        labels=dict(x="Product", y="Distributor", color="Revenue (₹)"),
        color_continuous_scale="Blues",
        aspect="auto",
        text_auto=".0f",
    )
    fig.update_traces(textfont=dict(size=9))
    fig.update_layout(
        title=dict(text="Distributor × Product Revenue Heatmap (Top 10 each)", font=dict(size=14)),
        height=460, paper_bgcolor="white",
        margin=dict(l=10, r=10, t=40, b=120),
        xaxis=dict(tickangle=40, tickfont=dict(size=10)),
        yaxis=dict(tickfont=dict(size=10)),
        coloraxis_colorbar=dict(title="₹"),
    )
    return fig


def build_procurement_chart():
    if df_purchase.empty:
        fig = px.bar(title="No purchase data available")
        fig.update_layout(height=360, plot_bgcolor="white", paper_bgcolor="white")
        return fig

    sales     = df.groupby("Product")["Quantity"].sum().rename("sold")
    purchased = df_purchase.groupby("Product")["Quantity"].sum().rename("purchased")

    combined = pd.concat([sales, purchased], axis=1).fillna(0).reset_index()
    combined["gap"] = combined["purchased"] - combined["sold"]
    combined = combined[combined["purchased"] > 0].sort_values("purchased", ascending=False).head(15)

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Purchased", x=combined["Product"], y=combined["purchased"],
        marker_color="#0078D4",
    ))
    fig.add_trace(go.Bar(
        name="Sold", x=combined["Product"], y=combined["sold"],
        marker_color="#00B294",
    ))
    fig.update_layout(
        barmode="group",
        title=dict(text="Procurement vs Sales by Product (Units)", font=dict(size=14)),
        height=400, plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(l=10, r=10, t=40, b=120),
        xaxis=dict(tickangle=40, tickfont=dict(size=10)),
        legend=dict(orientation="h", y=1.1),
    )
    return fig


def kpi_html() -> str:
    def card(label, value, color="#0078D4", sub=None):
        sub_html = f'<div style="font-size:10px;color:#aaa;margin-top:4px">{sub}</div>' if sub else ""
        return f"""
        <div style="background:white;border-radius:10px;padding:18px 20px;box-shadow:0 2px 8px rgba(0,0,0,0.08);text-align:center;flex:1;margin:0 6px">
            <div style="font-size:11px;color:#888;text-transform:uppercase;letter-spacing:0.8px;margin-bottom:6px">{label}</div>
            <div style="font-size:24px;font-weight:700;color:{color}">{value}</div>
            {sub_html}
        </div>"""

    top_dist      = KPI_CACHE["top_distributor"]
    top_dist_rev  = KPI_CACHE["top_distributor_revenue"]
    top_dist_units = int(KPI_CACHE["top_distributor_units"])

    return f"""
    <div style="display:flex;flex-direction:row;gap:0;margin-bottom:8px">
        {card("Total Revenue",        f"₹ {round(KPI_CACHE['total_revenue']):,}")}
        {card("Units Sold",           f"{round(KPI_CACHE['total_units']):,}")}
        {card("Products",             KPI_CACHE['total_products'])}
        {card("Critical Stock Alerts",KPI_CACHE['critical_stock_count'], "#D13438")}
        {card("Avg Selling Price",    f"₹ {KPI_CACHE['avg_selling_price']:,}")}
    </div>
    <div style="display:flex;flex-direction:row;gap:0;margin-bottom:4px">
        {card("Total Distributors",   KPI_CACHE['total_distributors'], "#107C10")}
        {card("Top Distributor",      top_dist, "#0078D4", f"₹ {round(top_dist_rev):,} revenue")}
        {card("Top Distributor Units",f"{top_dist_units:,}", "#5C2D91", top_dist)}
    </div>"""


CSS = """
body, .gradio-container { background: #F3F2F1 !important; }
footer { display: none !important; }
.agent-section {
    background: linear-gradient(135deg, #1a1f36 0%, #0d1117 100%);
    border-radius: 14px;
    padding: 24px 28px 28px 28px;
    margin-top: 8px;
    box-shadow: 0 4px 24px rgba(0,0,0,0.18);
}
.agent-section label, .agent-section .label-wrap span {
    color: #a0aec0 !important;
    font-size: 12px !important;
    text-transform: uppercase;
    letter-spacing: 0.6px;
}
.agent-section input, .agent-section textarea {
    background: #2d3348 !important;
    border: 1px solid #3d4464 !important;
    color: #e2e8f0 !important;
    border-radius: 8px !important;
}
.agent-section input::placeholder, .agent-section textarea::placeholder { color: #718096 !important; }
.agent-section .gr-button {
    background: #0078D4 !important;
    border: none !important;
    color: white !important;
    font-weight: 600 !important;
    border-radius: 8px !important;
}
.agent-section table { border-collapse: collapse !important; width: 100% !important; border-radius: 8px !important; overflow: hidden !important; }
.agent-section table thead tr th {
    background: #0078D4 !important;
    color: #ffffff !important;
    font-weight: 700 !important;
    font-size: 12px !important;
    text-transform: uppercase !important;
    letter-spacing: 0.6px !important;
    padding: 10px 14px !important;
    border: none !important;
}
.agent-section table tbody tr:nth-child(odd)  td { background: #2d3348 !important; color: #e2e8f0 !important; padding: 8px 14px !important; border: none !important; }
.agent-section table tbody tr:nth-child(even) td { background: #242840 !important; color: #e2e8f0 !important; padding: 8px 14px !important; border: none !important; }
.agent-section table tbody tr:hover td { background: #3a4060 !important; }
"""
