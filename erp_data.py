"""
Data layer — loads ERP data once at startup and exposes read-only caches.

df is never mutated after module load; all tool functions that need a working
copy must call df.copy() themselves.
"""

import os
from pathlib import Path

import numpy as np
import pandas as pd
from typing import Optional
from config import LEAD_TIME_MONTHS, Z_SCORE

# ── Load & clean ──────────────────────────────────────────────────────────────
# Real export if present (or ERP_DATA_FILE), otherwise the synthetic sample in sample_data/
DATA_FILE = Path(os.getenv("ERP_DATA_FILE", "cleaned_erp_data.xlsx"))
if not DATA_FILE.exists():
    DATA_FILE = Path(__file__).parent / "sample_data" / "cleaned_erp_data.xlsx"
_raw = pd.read_excel(DATA_FILE)

def _clean(frame):
    frame = frame.copy()
    frame["Date"]     = pd.to_datetime(frame["Date"],    errors="coerce", dayfirst=True)
    frame["Quantity"] = pd.to_numeric(frame["Quantity"], errors="coerce")
    frame["Value"]    = pd.to_numeric(frame["Value"],    errors="coerce")
    frame["Balance"]  = pd.to_numeric(frame["Balance"],  errors="coerce")
    frame = frame.dropna(subset=["Date", "Quantity", "Product"])
    frame["Product"] = frame["Product"].str.replace(r"\s+\d{4}-\d{2}$", "", regex=True).str.strip()
    return frame.sort_values("Date").reset_index(drop=True)

df           = _clean(_raw[_raw["Type"] == "Sale"])
df_returns   = _clean(_raw[_raw["Type"] == "Sale Return"])

# Purchase Returns must subtract from totals, not add — negate before combining.
_pur_raw = _raw[_raw["Type"].isin(["Purchase", "Purchase Return"])].copy()
_pur_raw.loc[_pur_raw["Type"] == "Purchase Return", ["Quantity", "Value"]] *= -1
df_purchase  = _clean(_pur_raw)

# ── Derived constants ─────────────────────────────────────────────────────────
N_MONTHS: float = max((df["Date"].max() - df["Date"].min()).days / 30.44, 1)

# ── ABC classification ────────────────────────────────────────────────────────
_abc = (
    df.groupby("Product")["Value"].sum()
    .reset_index()
    .sort_values("Value", ascending=False)
)
_abc["cumulative_pct"] = _abc["Value"].cumsum() / _abc["Value"].sum() * 100
_abc["abc_class"] = _abc["cumulative_pct"].apply(
    lambda p: "A" if p <= 80 else ("B" if p <= 95 else "C")
)
ABC_MAP: dict = dict(zip(_abc["Product"], _abc["abc_class"]))

# ── Per-product safety stock ──────────────────────────────────────────────────
_monthly = df.copy()
_monthly["YearMonth"] = _monthly["Date"].dt.to_period("M")
_monthly_demand = (
    _monthly.groupby(["Product", "YearMonth"])["Quantity"]
    .sum()
    .reset_index()
)

_ss = _monthly_demand.groupby("Product")["Quantity"].agg(
    avg_monthly_demand="mean",
    std_monthly_demand="std",
).reset_index()
_ss["std_monthly_demand"]   = _ss["std_monthly_demand"].fillna(0)
_ss["safety_stock_units"]   = (Z_SCORE * _ss["std_monthly_demand"] * np.sqrt(LEAD_TIME_MONTHS)).round(1)
_ss["reorder_point_units"]  = (_ss["avg_monthly_demand"] * LEAD_TIME_MONTHS + _ss["safety_stock_units"]).round(1)
_ss["reorder_point_months"] = (
    _ss["reorder_point_units"] / _ss["avg_monthly_demand"].replace(0, float("nan"))
).round(2).fillna(LEAD_TIME_MONTHS)

SAFETY_STOCK_MAP: dict = _ss.set_index("Product").to_dict("index")

# ── KPI cache ─────────────────────────────────────────────────────────────────
_kpi_inv = df.groupby("Product").agg(
    total_units_sold=("Quantity", "sum"),
    latest_balance=("Balance", "last"),
).reset_index()
_kpi_inv["monthly_demand"] = _kpi_inv["total_units_sold"] / N_MONTHS
_kpi_inv["months_left"]    = (
    _kpi_inv["latest_balance"] / _kpi_inv["monthly_demand"].replace(0, float("nan"))
).round(2)
_kpi_inv["reorder_pt"] = _kpi_inv["Product"].map(
    lambda p: SAFETY_STOCK_MAP.get(p, {}).get("reorder_point_months", LEAD_TIME_MONTHS)
)
_kpi_at_risk = _kpi_inv.dropna(subset=["months_left"])
_kpi_at_risk = _kpi_at_risk[_kpi_at_risk["months_left"] < _kpi_at_risk["reorder_pt"]]

_kpi_cv      = _monthly_demand.groupby("Product")["Quantity"].agg(["std", "mean"])
_kpi_cv["cv"] = (_kpi_cv["std"] / _kpi_cv["mean"]).fillna(0)

_dist = df.dropna(subset=["Description"]).copy()
_dist = _dist[_dist["Description"].str.strip().str.len() > 2]
_dist_revenue = _dist.groupby("Description")["Value"].sum()
_dist_units   = _dist.groupby("Description")["Quantity"].sum()

KPI_CACHE: dict = {
    "total_revenue":               round(df["Value"].sum(), 2),
    "total_units":                 round(df["Quantity"].sum(), 2),
    "total_products":              df["Product"].nunique(),
    "avg_selling_price":           round(df["Value"].sum() / df["Quantity"].sum(), 2),
    "top_revenue_product":         df.groupby("Product")["Value"].sum().idxmax(),
    "top_volume_product":          df.groupby("Product")["Quantity"].sum().idxmax(),
    "critical_stock_count":        len(_kpi_at_risk),
    "highest_stockout_product":    (
        _kpi_at_risk.sort_values("months_left").iloc[0]["Product"]
        if not _kpi_at_risk.empty else "N/A"
    ),
    "highest_seasonality_product": (
        _kpi_cv["cv"].idxmax() if not _kpi_cv["cv"].empty else "N/A"
    ),
    "total_distributors":          int(_dist_revenue.count()),
    "top_distributor":             _dist_revenue.idxmax() if not _dist_revenue.empty else "N/A",
    "top_distributor_revenue":     round(_dist_revenue.max(), 2) if not _dist_revenue.empty else 0,
    "top_distributor_units":       round(_dist_units.max(), 0) if not _dist_units.empty else 0,
}


# ── Helpers ───────────────────────────────────────────────────────────────────
def get_reorder_months(product: str) -> float:
    return SAFETY_STOCK_MAP.get(product, {}).get("reorder_point_months", LEAD_TIME_MONTHS)


def classify_stock(months: float, product: Optional[str] = None) -> str:
    threshold = get_reorder_months(product) if product else LEAD_TIME_MONTHS
    if months < threshold:
        return "STOCKOUT RISK"
    if months > 12:
        return "OVERSTOCK"
    return "HEALTHY"
