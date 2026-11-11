"""
Entry point — Gradio UI with optional basic auth.

Run:  python app.py

Auth: set APP_USERNAME and APP_PASSWORD in .env to enable login.
      Leave both blank to run without auth (local dev).
"""

import pandas as pd
import gradio as gr

from config import APP_USERNAME, APP_PASSWORD
from erp_data import df, N_MONTHS, ABC_MAP, classify_stock
from erp_agent import dashboard_agent
from erp_charts import (
    build_revenue_chart, build_inventory_chart, build_reorder_alert_chart,
    build_inventory_turnover_chart, build_stock_status_chart,
    build_abc_charts, build_flow_rate_charts, build_distributor_charts,
    build_distributor_product_heatmap, build_procurement_chart,
    build_monthly_trend_chart, build_price_volume_scatter,
    build_pareto_curve, build_return_rate_charts, kpi_html, CSS,
)
import marg_charts as mc

# ── Pre-build static charts once at startup ───────────────────────────────────
_abc_donut, _abc_matrix         = build_abc_charts()
_top_flow,  _bottom_flow        = build_flow_rate_charts()
_turnover_top, _turnover_bottom = build_inventory_turnover_chart()
_reorder_fig, _                 = build_reorder_alert_chart()
_dist_top, _dist_bottom         = build_distributor_charts()
_return_prod, _return_dist      = build_return_rate_charts()

# ── Shared base for filter (avoids recomputing groupby on every filter change) ─
_filter_base = df.groupby("Product").agg(
    total_units_sold=("Quantity", "sum"),
    total_revenue=("Value", "sum"),
    latest_balance=("Balance", "last"),
).reset_index()
_filter_base["monthly_demand"]       = _filter_base["total_units_sold"] / N_MONTHS
_filter_base["months_of_stock_left"] = (
    _filter_base["latest_balance"] / _filter_base["monthly_demand"].replace(0, float("nan"))
).round(1)
_filter_base["inventory_turnover"]   = (
    _filter_base["total_units_sold"] / _filter_base["latest_balance"].replace(0, float("nan"))
).round(2)
_filter_base["abc_class"]   = _filter_base["Product"].map(ABC_MAP)
_filter_base["stock_status"] = _filter_base.apply(
    lambda r: classify_stock(r["months_of_stock_left"], r["Product"]), axis=1
)

# ── Gradio UI ─────────────────────────────────────────────────────────────────

def _section(title: str) -> str:
    return f"<div style='font-size:15px;font-weight:700;color:#323130;margin:18px 0 4px 4px'>{title}</div>"


def _pilot_tab():
    gr.HTML(value=kpi_html())

    gr.Plot(value=build_monthly_trend_chart(), label="")

    with gr.Row():
        gr.Plot(value=build_revenue_chart(),      label="")
        gr.Plot(value=build_inventory_chart(),    label="")

    with gr.Row():
        gr.Plot(value=_dist_top,    label="")
        gr.Plot(value=_dist_bottom, label="")

    with gr.Row():
        gr.Plot(value=_abc_donut,               label="")
        gr.Plot(value=_abc_matrix,              label="")

    gr.Plot(value=build_pareto_curve(),         label="")
    gr.Plot(value=build_price_volume_scatter(), label="")

    gr.HTML("<div style='font-size:13px;font-weight:600;color:#323130;margin:12px 0 6px 0'>Filter Products by Class & Status</div>")
    with gr.Row():
        abc_filter    = gr.Radio(choices=["All", "A", "B", "C"],                           value="All", label="ABC Class")
        status_filter = gr.Radio(choices=["All", "STOCKOUT RISK", "HEALTHY", "OVERSTOCK"], value="All", label="Stock Status")
    filtered_table = gr.Dataframe(label="Filtered Product List")

    gr.Plot(value=build_distributor_product_heatmap(), label="")

    with gr.Row():
        gr.Plot(value=build_procurement_chart(), label="")

    with gr.Row():
        gr.Plot(value=_return_prod, label="")
        gr.Plot(value=_return_dist, label="")

    with gr.Row():
        gr.Plot(value=_top_flow,    label="")
        gr.Plot(value=_bottom_flow, label="")

    with gr.Row():
        gr.Plot(value=_reorder_fig,               label="")
        gr.Plot(value=build_stock_status_chart(),  label="")

    with gr.Row():
        gr.Plot(value=_turnover_top,    label="")
        gr.Plot(value=_turnover_bottom, label="")

    return abc_filter, status_filter, filtered_table


with gr.Blocks(title="Reman ERP Executive Dashboard") as demo:

    gr.HTML("""
        <div style="background:#0078D4;padding:18px 28px;border-radius:10px;margin-bottom:16px">
            <h1 style="color:white;margin:0;font-size:22px;font-weight:700">Reman ERP Executive Dashboard</h1>
            <p style="color:#cce4f7;margin:4px 0 0 0;font-size:12px">Reman LifeCare · Marg ERP data FY2017-18 to date · Claude · OpenAI · RAG</p>
        </div>
    """)

    with gr.Tab("Business — FY17-18 to today"):
        gr.HTML(value=mc.business_kpi_html())

        gr.HTML(_section("Revenue"))
        gr.Plot(value=mc.build_forecast_chart(), label="")
        with gr.Row():
            gr.Plot(value=mc.build_fy_revenue_chart(),  label="")
            gr.Plot(value=mc.build_seasonality_chart(), label="")

        gr.HTML(_section("Customers"))
        gr.Plot(value=mc.build_customer_base_chart(), label="")
        with gr.Row():
            gr.Plot(value=mc.build_top_customers_chart(), label="")
            gr.Plot(value=mc.build_cash_credit_chart(),   label="")
        with gr.Row():
            gr.Dataframe(value=mc.at_risk_customers_table(), label="At-risk customers — silent 90–365 days (₹ lakh)")
            gr.Dataframe(value=mc.lost_customers_table(),    label="Lost customers — silent > 1 year, by lifetime revenue (₹ lakh)")

        gr.HTML(_section("Cash — receivables & payables"))
        with gr.Row():
            gr.Plot(value=mc.build_debtors_chart(),   label="")
            gr.Plot(value=mc.build_creditors_chart(), label="")

        gr.HTML(_section("Purchases & stock (annual units per product)"))
        with gr.Row():
            gr.Plot(value=mc.build_purchase_vs_sales_chart(), label="")
            gr.Plot(value=mc.build_stock_flow_chart(),        label="")
        gr.Dataframe(value=mc.top_products_table(), label="Best-selling products — last full FY (units)")
        with gr.Row():
            gr.Dataframe(value=mc.overstock_table(),  label="Overstock — closing stock > 12 months of sales")
            gr.Dataframe(value=mc.dead_stock_table(), label="Dead stock — this FY, almost no sales")

    with gr.Tab("Products — FY18-19 pilot"):
        gr.HTML("<div style='background:#FFF4CE;border-left:4px solid #FF8C00;padding:10px 16px;border-radius:6px;"
                "font-size:13px;color:#323130;margin-bottom:10px'>These product-level charts use the <b>FY2018-19 pilot "
                "dataset</b> (47 products, monthly). Monthly product data for later years needs the item-wise sales export from Marg.</div>")
        abc_filter, status_filter, filtered_table = _pilot_tab()

    gr.HTML("""
        <div style="background:linear-gradient(135deg,#1a1f36 0%,#0d1117 100%);border-radius:14px;padding:20px 28px 8px 28px;margin-top:16px;box-shadow:0 4px 24px rgba(0,0,0,0.18)">
            <div style="font-size:16px;font-weight:700;color:#90cdf4;letter-spacing:0.4px;margin-bottom:4px">Ask the ERP Agent</div>
            <div style="font-size:12px;color:#718096">Powered by Claude · OpenAI · Databricks · RAG</div>
        </div>
    """)

    with gr.Group(elem_classes="agent-section"):
        chatbot = gr.Chatbot(label="ERP Agent Conversation", height=420)

        with gr.Row():
            query_input = gr.Textbox(
                label="Your Question",
                placeholder="e.g. Which products have seasonal demand and what is the forecast?",
                scale=5,
            )
            submit_btn = gr.Button("Submit", variant="primary", scale=1)
            clear_btn  = gr.Button("Clear Chat", scale=1)

        with gr.Row():
            with gr.Column(scale=1):
                result_table = gr.Dataframe(label="Analytics Result")
                export_btn   = gr.Button("Download Table as Excel", variant="secondary", size="sm")
                export_file  = gr.File(label="", visible=False)
            with gr.Column(scale=1):
                result_graph = gr.Plot(label="Forecast / Seasonality Graph")

        debug_box = gr.Textbox(label="Cost Tracking", lines=2, interactive=False)

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def filter_products(abc_class, stock_status):
        out = _filter_base.copy()
        if abc_class    != "All":
            out = out[out["abc_class"]    == abc_class]
        if stock_status != "All":
            out = out[out["stock_status"] == stock_status]
        return mc.pretty_columns(
            out[["Product", "abc_class", "stock_status", "months_of_stock_left", "inventory_turnover", "total_revenue"]]
            .sort_values("total_revenue", ascending=False)
            .reset_index(drop=True)
        )

    def export_table(table):
        import tempfile, os
        if table is None or (hasattr(table, "empty") and table.empty):
            return gr.update(visible=False)
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            path = f.name
        pd.DataFrame(table).to_excel(path, index=False)
        # Schedule cleanup: remove the file after a short delay so Gradio
        # can serve the download before the file disappears.
        import threading
        def _cleanup(p, delay=60):
            import time
            time.sleep(delay)
            try:
                os.remove(p)
            except OSError:
                pass
        threading.Thread(target=_cleanup, args=(path,), daemon=True).start()
        return gr.update(value=path, visible=True)

    def submit(question, history):
        base = list(history or []) + [{"role": "user", "content": question}]
        try:
            for chatbot_state, table, debug, graph in dashboard_agent(question, history):
                yield "", chatbot_state, mc.pretty_columns(table), debug, graph
        except Exception as e:
            error_msg = (
                f"Something went wrong — please try rephrasing your question.\n\n"
                f"_(Error: {type(e).__name__}: {e})_"
            )
            yield "", base + [{"role": "assistant", "content": error_msg}], pd.DataFrame(), "", None

    abc_filter.change(fn=filter_products,    inputs=[abc_filter, status_filter], outputs=filtered_table)
    status_filter.change(fn=filter_products, inputs=[abc_filter, status_filter], outputs=filtered_table)
    export_btn.click(fn=export_table, inputs=[result_table], outputs=[export_file])

    _outputs = [query_input, chatbot, result_table, debug_box, result_graph]
    submit_btn.click(fn=submit, inputs=[query_input, chatbot], outputs=_outputs)
    query_input.submit(fn=submit, inputs=[query_input, chatbot], outputs=_outputs)
    clear_btn.click(fn=lambda: ([], pd.DataFrame(), "", None), outputs=[chatbot, result_table, debug_box, result_graph])


# ── Launch ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    auth = (APP_USERNAME, APP_PASSWORD) if APP_USERNAME and APP_PASSWORD else None
    if auth:
        print(f"[Auth] Login required — username: {APP_USERNAME}")
    else:
        print("[Auth] No auth configured — running open (set APP_USERNAME + APP_PASSWORD in .env to enable)")
    # Local only — bound to this machine, no public gradio.live link
    demo.launch(auth=auth, css=CSS, share=False, server_name="127.0.0.1", server_port=7860)
