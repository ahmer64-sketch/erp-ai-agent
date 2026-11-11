"""
Tool layer — the ERP tools callable by the Claude agent (8 FY18-19 product tools + 8 full-history tools in marg_tools.py), plus graph builder.

Each tool returns (DataFrame, figure | None).
df is imported read-only; every tool that needs a working copy calls df.copy().
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from databricks import sql

from config import DATABRICKS_HOST, DATABRICKS_HTTP_PATH, DATABRICKS_TOKEN
from erp_data import df, df_purchase, N_MONTHS, ABC_MAP, SAFETY_STOCK_MAP, KPI_CACHE, get_reorder_months, classify_stock
import marg_tools


# ── Databricks helper ─────────────────────────────────────────────────────────

def run_databricks_query(query: str) -> pd.DataFrame:
    if not (DATABRICKS_HOST and DATABRICKS_TOKEN):   # not configured: callers fall back to local data
        return pd.DataFrame()
    try:
        connection = sql.connect(
            server_hostname=DATABRICKS_HOST,
            http_path=DATABRICKS_HTTP_PATH,
            access_token=DATABRICKS_TOKEN,
        )
    except Exception as e:
        print(f"[Databricks] connection failed: {e}")
        return pd.DataFrame()

    cursor = None
    try:
        cursor = connection.cursor()
        cursor.execute(query)
        rows    = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        result  = pd.DataFrame(rows, columns=columns)
        # Databricks returns Decimal for aggregates — convert to float for JSON serialization
        from decimal import Decimal
        for col in result.columns:
            if result[col].apply(lambda x: isinstance(x, Decimal)).any():
                result[col] = result[col].apply(lambda x: float(x) if isinstance(x, Decimal) else x)
        return result
    except Exception as e:
        print(f"[Databricks] query failed: {e}")
        return pd.DataFrame()
    finally:
        if cursor:
            cursor.close()
        connection.close()


# ── Forecast graph ────────────────────────────────────────────────────────────

def build_forecast_graph(products: list[str]):
    """Plotly seasonality + 3-month forecast for up to 3 products."""
    colors = ["steelblue", "seagreen", "darkorange"]

    valid = []
    for p in products:
        prod_df = df[df["Product"] == p]
        if prod_df.empty:
            continue
        monthly = prod_df.groupby(prod_df["Date"].dt.to_period("M"))["Quantity"].sum()
        if len(monthly) >= 2:
            valid.append(p)
        if len(valid) == 3:
            break

    if not valid:
        return None

    fig = make_subplots(rows=len(valid), cols=1, subplot_titles=valid, vertical_spacing=0.12)

    for row, (product, color) in enumerate(zip(valid, colors), start=1):
        prod_df = df[df["Product"] == product].copy()
        prod_df["YearMonth"] = prod_df["Date"].dt.to_period("M")
        monthly_series = prod_df.groupby("YearMonth")["Quantity"].sum().sort_index()

        x         = np.arange(len(monthly_series))
        slope, intercept = np.polyfit(x, monthly_series.values, 1)
        trend_line = np.maximum(0, intercept + slope * x)

        seasonal_idx = prod_df.groupby(prod_df["Date"].dt.month)["Quantity"].sum()
        seasonal_idx = seasonal_idx / seasonal_idx.mean()

        last_period = monthly_series.index[-1]
        forecast_labels, forecast_y = [], []
        for i in range(1, 4):
            future_t      = len(monthly_series) - 1 + i
            future_period = last_period + i
            trend_val     = intercept + slope * future_t
            s_idx         = float(seasonal_idx.get(future_period.month, 1.0) or 1.0)
            forecast_labels.append(str(future_period))
            forecast_y.append(max(0, trend_val * s_idx))

        x_labels    = [str(p) for p in monthly_series.index]
        show_legend = (row == 1)

        fig.add_trace(go.Scatter(
            x=x_labels, y=monthly_series.values.tolist(),
            mode="lines+markers", name="Actual",
            line=dict(color=color), showlegend=show_legend,
        ), row=row, col=1)

        fig.add_trace(go.Scatter(
            x=x_labels, y=trend_line.tolist(),
            mode="lines", name="Trend",
            line=dict(color="gray", dash="dash"), showlegend=show_legend,
        ), row=row, col=1)

        fig.add_trace(go.Scatter(
            x=[x_labels[-1]] + forecast_labels,
            y=[float(monthly_series.values[-1])] + forecast_y,
            mode="lines+markers", name="Forecast (3m)",
            line=dict(color="tomato", dash="dash"), showlegend=show_legend,
        ), row=row, col=1)

    title = valid[0] if len(valid) == 1 else f"Seasonality + Forecast: {', '.join(valid)}"
    fig.update_layout(title_text=title, title_font_size=14, height=420 * len(valid), template="plotly_white")
    fig.update_xaxes(tickangle=45)
    return fig


# ── Tools ─────────────────────────────────────────────────────────────────────

def inventory_tool():
    summary = df.groupby("Product").agg(
        total_units_sold=("Quantity", "sum"),
        total_revenue=("Value", "sum"),
        latest_balance=("Balance", "last"),
    ).reset_index()

    summary["estimated_monthly_demand_units"] = summary["total_units_sold"] / N_MONTHS
    summary["months_of_stock_left"]           = summary["latest_balance"] / summary["estimated_monthly_demand_units"].replace(0, float("nan"))
    summary["inventory_turnover"]             = (summary["total_units_sold"] / summary["latest_balance"].replace(0, float("nan"))).round(2)
    summary["reorder_point_months"]           = summary["Product"].map(get_reorder_months)
    summary["safety_stock_units"]             = summary["Product"].map(
        lambda p: int(SAFETY_STOCK_MAP.get(p, {}).get("safety_stock_units", 0))
    )
    summary["stock_status"] = summary.apply(
        lambda r: classify_stock(r["months_of_stock_left"], r["Product"]), axis=1
    )
    summary["abc_class"] = summary["Product"].map(ABC_MAP)

    return summary.sort_values("months_of_stock_left").head(10), None


def revenue_tool(mode: str = "top"):
    order = "DESC" if mode == "top" else "ASC"
    query = f"""
    SELECT
        Product,
        SUM(TRY_CAST(Quantity AS DOUBLE)) AS total_units_sold,
        SUM(TRY_CAST(Value AS DOUBLE))    AS total_revenue,
        COUNT(*)                          AS transactions,
        SUM(TRY_CAST(Value AS DOUBLE))
            / NULLIF(SUM(TRY_CAST(Quantity AS DOUBLE)), 0) AS average_selling_price
    FROM reman.erp.cleaned_erp_data
    WHERE Type = 'Sale'
    GROUP BY Product
    ORDER BY total_revenue {order}
    LIMIT 10
    """
    result = run_databricks_query(query)
    if result.empty:
        # Databricks unreachable (e.g. expired token) — same query on the local copy
        print("[revenue_tool] Databricks returned nothing — using local data")
        result = df.groupby("Product").agg(
            total_units_sold=("Quantity", "sum"),
            total_revenue=("Value", "sum"),
            transactions=("Value", "count"),
        ).reset_index()
        result["average_selling_price"] = result["total_revenue"] / result["total_units_sold"].replace(0, float("nan"))
        result = result.sort_values("total_revenue", ascending=(mode != "top")).head(10).reset_index(drop=True)
    return result, None


def seasonality_tool():
    # ── Vectorized pre-computation (single pass over df) ─────────────────────
    _df = df.copy()
    _df["YearMonth"] = _df["Date"].dt.to_period("M")
    _df["month"]     = _df["Date"].dt.month

    # Monthly totals for all products at once
    monthly_all = (
        _df.groupby(["Product", "YearMonth"])["Quantity"]
        .sum()
        .reset_index()
    )

    # Seasonal index per (Product, month) — computed once, looked up per product
    _seas = _df.groupby(["Product", "month"])["Quantity"].sum().reset_index()
    _seas_mean = _seas.groupby("Product")["Quantity"].transform("mean")
    _seas["idx"] = _seas["Quantity"] / _seas_mean.replace(0, float("nan"))
    seasonal_dict: dict = {
        product: grp.set_index("month")["idx"]
        for product, grp in _seas.groupby("Product")
    }

    # ── Per-product loop over pre-grouped data (no repeated df filtering) ────
    results = []
    for product, grp in monthly_all.groupby("Product"):
        monthly_series = grp.set_index("YearMonth")["Quantity"].sort_index()

        if len(monthly_series) < 3:
            continue

        avg_units = monthly_series.mean()
        std_units = monthly_series.std()
        if avg_units == 0:
            continue

        x = np.arange(len(monthly_series))
        slope, intercept = np.polyfit(x, monthly_series.values, 1)
        trend = "Growing" if slope > avg_units * 0.02 else (
            "Declining" if slope < -avg_units * 0.02 else "Stable"
        )

        prod_seasonal = seasonal_dict.get(product, pd.Series(dtype=float))
        last_period   = monthly_series.index[-1]
        forecasts     = []
        for i in range(1, 4):
            future_t     = len(monthly_series) - 1 + i
            future_month = (last_period + i).month
            trend_val    = intercept + slope * future_t
            s_idx        = float(prod_seasonal.get(future_month, 1.0) or 1.0)
            forecasts.append(max(0, round(trend_val * s_idx, 0)))

        results.append({
            "Product":              product,
            "avg_monthly_units":    round(avg_units, 0),
            "seasonality_score":    round(std_units / avg_units, 2),
            "trend":                trend,
            "forecast_next_month":  int(forecasts[0]),
            "forecast_3m_total":    int(sum(forecasts)),
        })

    result = pd.DataFrame(results).sort_values("seasonality_score", ascending=False).head(10)
    if result.empty:
        return result, None
    return result, build_forecast_graph(result.head(3)["Product"].tolist())


def product_detail_tool(product_name: str = ""):
    if not product_name or len(product_name.strip()) < 2:
        return pd.DataFrame({"Message": ["product_name is required. Provide a specific product name, e.g. NUROCAL-OD."]}), None

    # Normalize: treat hyphens and spaces as equivalent so "NUROCAL-OD" matches "NUROCAL OD 2018-19"
    normalized_search = product_name.strip().replace("-", " ")
    normalized_col    = df["Product"].str.replace("-", " ", regex=False)
    prod_df = df[normalized_col.str.contains(normalized_search, case=False, na=False, regex=False)]
    if prod_df.empty:
        return pd.DataFrame({"Message": [f"No matching product found for: {product_name}"]}), None

    summary = prod_df.groupby("Product").agg(
        total_units_sold=("Quantity", "sum"),
        total_revenue=("Value", "sum"),
        latest_balance=("Balance", "last"),
        transactions=("Quantity", "count"),
    ).reset_index()

    summary["average_selling_price"]         = (summary["total_revenue"] / summary["total_units_sold"].replace(0, float("nan"))).round(2)
    summary["estimated_monthly_demand_units"] = summary["total_units_sold"] / N_MONTHS
    summary["months_of_stock_left"]           = summary["latest_balance"] / summary["estimated_monthly_demand_units"].replace(0, float("nan"))
    summary["inventory_turnover"]             = (summary["total_units_sold"] / summary["latest_balance"].replace(0, float("nan"))).round(2)
    summary["reorder_point_months"]           = summary["Product"].map(get_reorder_months)
    summary["safety_stock_units"]             = summary["Product"].map(
        lambda p: int(SAFETY_STOCK_MAP.get(p, {}).get("safety_stock_units", 0))
    )
    summary["stock_status"] = summary.apply(
        lambda r: classify_stock(r["months_of_stock_left"], r["Product"]), axis=1
    )
    summary["abc_class"] = summary["Product"].map(ABC_MAP)

    return summary, None


def kpi_dashboard_tool():
    kpi_df = pd.DataFrame({
        "KPI": [
            "Total Revenue", "Total Units Sold", "Total Products",
            "Critical Stock Risks", "Top Revenue Product", "Top Volume Product",
            "Highest Stockout Risk Product", "Highest Seasonality Product", "Average Selling Price",
        ],
        "Value": [
            f"₹ {KPI_CACHE['total_revenue']}",
            KPI_CACHE["total_units"],
            KPI_CACHE["total_products"],
            KPI_CACHE["critical_stock_count"],
            KPI_CACHE["top_revenue_product"],
            KPI_CACHE["top_volume_product"],
            KPI_CACHE["highest_stockout_product"],
            KPI_CACHE["highest_seasonality_product"],
            f"₹ {KPI_CACHE['avg_selling_price']}",
        ],
    })
    # Overview = current business from full history; the FY18-19 pilot stock KPIs are years stale,
    # so only its product-mix facts are kept, clearly labelled.
    kpi_df = kpi_df[kpi_df["KPI"].isin(["Top Revenue Product", "Top Volume Product", "Average Selling Price"])]
    kpi_df["KPI"] = kpi_df["KPI"] + " (FY18-19 pilot data only)"
    company = pd.DataFrame(marg_tools.company_kpis(), columns=["KPI", "Value"])
    return pd.concat([company, kpi_df], ignore_index=True), None


def safety_stock_tool():
    rows = []
    for product, stats in SAFETY_STOCK_MAP.items():
        prod_df = df[df["Product"] == product]
        if prod_df.empty:
            continue
        latest_balance = int(prod_df["Balance"].iloc[-1] or 0)
        reorder_units  = stats["reorder_point_units"]
        rows.append({
            "Product":                 product,
            "Avg Monthly Demand":      round(stats["avg_monthly_demand"], 1),
            "Std Dev":                 round(stats["std_monthly_demand"], 1),
            "Safety Stock (units)":    int(stats["safety_stock_units"]),
            "Reorder Point (units)":   int(reorder_units),
            "Reorder Point (months)":  stats["reorder_point_months"],
            "Balance":                 latest_balance,
            "Status":                  "REORDER" if latest_balance < reorder_units else "OK",
        })
    return pd.DataFrame(rows).sort_values("Status", ascending=False).reset_index(drop=True), None


def procurement_tool(product_name: str = ""):
    if df_purchase.empty:
        return pd.DataFrame({"Message": ["No purchase data available."]}), None

    pur = df_purchase.copy()
    if product_name and len(product_name.strip()) >= 2:
        normalized = product_name.strip().replace("-", " ")
        pur = pur[pur["Product"].str.replace("-", " ", regex=False).str.contains(normalized, case=False, na=False, regex=False)]
        if pur.empty:
            return pd.DataFrame({"Message": [f"No purchase data found for: {product_name}"]}), None

    pur_summary = pur.groupby("Product").agg(
        total_purchased=("Quantity", "sum"),
        total_purchase_value=("Value", "sum"),
        purchase_orders=("Quantity", "count"),
        last_purchase_date=("Date", "max"),
    ).reset_index()

    sal_summary = df.groupby("Product")["Quantity"].sum().rename("total_sold").reset_index()

    merged = pur_summary.merge(sal_summary, on="Product", how="left").fillna({"total_sold": 0})
    merged["procurement_gap"]  = merged["total_purchased"] - merged["total_sold"]
    merged["sell_through_pct"] = (merged["total_sold"] / merged["total_purchased"].replace(0, float("nan")) * 100).round(1)
    merged["last_purchase_date"] = merged["last_purchase_date"].dt.strftime("%Y-%m-%d")

    merged = merged.sort_values("total_purchased", ascending=False)
    return merged.reset_index(drop=True), None


def customer_tool(product_name: str = "", mode: str = "top_revenue"):
    cust_df = df.dropna(subset=["Description"]).copy()
    cust_df = cust_df[cust_df["Description"].str.strip().str.len() > 2]

    if product_name and len(product_name.strip()) >= 2:
        normalized_search = product_name.strip().replace("-", " ")
        normalized_col    = cust_df["Product"].str.replace("-", " ", regex=False)
        cust_df = cust_df[normalized_col.str.contains(normalized_search, case=False, na=False, regex=False)]
        if cust_df.empty:
            return pd.DataFrame({"Message": [f"No customer orders found for: {product_name}"]}), None

    if mode == "inactive":
        last_order = cust_df.groupby("Description").agg(
            last_order_date=("Date", "max"),
            total_orders=("Quantity", "count"),
            total_revenue=("Value", "sum"),
        ).reset_index()
        last_order.columns = ["Distributor", "Last Order Date", "Total Orders", "Total Revenue"]
        cutoff  = df["Date"].max() - pd.DateOffset(months=3)
        last_order["Days Since Last Order"] = (df["Date"].max() - last_order["Last Order Date"]).dt.days
        inactive = last_order[last_order["Last Order Date"] < cutoff].sort_values("Days Since Last Order", ascending=False)
        if inactive.empty:
            return pd.DataFrame({"Message": ["All distributors ordered within the last 3 months."]}), None
        return inactive.reset_index(drop=True), None

    # top_revenue
    summary = cust_df.groupby("Description").agg(
        total_units_bought=("Quantity", "sum"),
        total_revenue=("Value", "sum"),
        total_orders=("Quantity", "count"),
        last_order_date=("Date", "max"),
        unique_products=("Product", "nunique"),
    ).reset_index()
    summary.columns = ["Distributor", "Units Bought", "Revenue", "Orders", "Last Order", "Products"]
    summary["Last Order"] = summary["Last Order"].dt.strftime("%Y-%m-%d")
    return summary.sort_values("Revenue", ascending=False).head(10).reset_index(drop=True), None


# ── Dispatcher ────────────────────────────────────────────────────────────────

def run_tool(tool_name: str, args: dict):
    dispatch = {
        "inventory_tool":      lambda: inventory_tool(),
        "revenue_tool":        lambda: revenue_tool(**args),
        "seasonality_tool":    lambda: seasonality_tool(),
        "product_detail_tool": lambda: product_detail_tool(**args),
        "kpi_dashboard_tool":  lambda: kpi_dashboard_tool(),
        "safety_stock_tool":   lambda: safety_stock_tool(),
        "customer_tool":       lambda: customer_tool(**args),
        "procurement_tool":    lambda: procurement_tool(**args),
        # Full-history company tools (Marg exports, FY2017-18 onwards)
        "sales_growth_tool":      lambda: marg_tools.sales_growth_tool(**args),
        "revenue_forecast_tool":  lambda: marg_tools.revenue_forecast_tool(),
        "sales_seasonality_tool": lambda: marg_tools.sales_seasonality_tool(),
        "cash_credit_tool":       lambda: marg_tools.cash_credit_tool(),
        "customer_health_tool":   lambda: marg_tools.customer_health_tool(**args),
        "receivables_tool":       lambda: marg_tools.receivables_tool(**args),
        "supplier_tool":          lambda: marg_tools.supplier_tool(**args),
        "product_trend_tool":     lambda: marg_tools.product_trend_tool(**args),
    }
    fn = dispatch.get(tool_name)
    return fn() if fn else (pd.DataFrame(), None)
