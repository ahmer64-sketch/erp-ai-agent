"""
Full-history data layer — Marg ERP exports in ./reman (FY2017-18 onwards).

Loads once at startup and exposes read-only frames + caches:
  sales      — one row per sales bill   (date, bill, party, bill_amt, taxable, tax, is_cash, FY)
  purchases  — one row per purchase bill
  stock      — one row per product per FY (purchase / sale / closing units, from the annual stock statement)
  debtors    — receivable balance per customer   (snapshot, see BALANCE_AS_OF)
  creditors  — payable balance per supplier      (manufacturers + suppliers)

There is no product × month data in these exports — product-level monthly tools
still run on the FY2018-19 pilot dataset in erp_data.py.
"""

import os
import re
from pathlib import Path

import numpy as np
import pandas as pd

# Real Marg exports if present (or MARG_DATA_DIR), otherwise the synthetic sample in sample_data/reman
DATA_DIR = Path(os.getenv("MARG_DATA_DIR", Path(__file__).parent / "reman"))
if not DATA_DIR.exists():
    DATA_DIR = Path(__file__).parent / "sample_data" / "reman"


# ── Loaders ───────────────────────────────────────────────────────────────────

def _fy(dates: pd.Series) -> pd.Series:
    """Indian financial year label: Apr-2025..Mar-2026 → 'FY25-26'."""
    start = (dates - pd.DateOffset(months=3)).dt.year
    return "FY" + (start % 100).astype(str).str.zfill(2) + "-" + ((start + 1) % 100).astype(str).str.zfill(2)


def _load_book(folder: str) -> pd.DataFrame:
    """Sales / purchase book: header row starts with DATE, footer 'Total :' and a Marg advert line."""
    frames = []
    for path in sorted(DATA_DIR.glob(f"{folder}*/*")):
        if path.name.startswith((".", "~$")):
            continue
        raw = pd.read_excel(path, header=None)
        hdr = raw.index[raw[0].astype(str).str.strip().eq("DATE")][0]
        book = raw.iloc[hdr + 1:].copy()
        book.columns = [str(c).strip() for c in raw.iloc[hdr]]
        book["date"] = pd.to_datetime(book["DATE"], format="%d-%m-%Y", errors="coerce")
        frames.append(book.dropna(subset=["date"]))
    book = pd.concat(frames, ignore_index=True)
    out = pd.DataFrame({
        "date":     book["date"],
        "bill_no":  book["BILL NO."].astype(str).str.strip(),
        "party":    book["PARTY NAME"].astype(str).str.strip(),
        "bill_amt": pd.to_numeric(book["BILL AMT."], errors="coerce").fillna(0),
        "taxable":  pd.to_numeric(book["TAXABLE"],   errors="coerce").fillna(0),
        "tax":      pd.to_numeric(book["TAX"],       errors="coerce").fillna(0),
    })
    out["FY"]    = _fy(out["date"])
    out["month"] = out["date"].dt.to_period("M").dt.to_timestamp()
    return out.sort_values("date").reset_index(drop=True)


# Stock statement rows that are charges / office assets, not saleable products
_NON_PRODUCT = re.compile(
    r"CHARGE|CHG\.|CYLINDER|PACKING SECURITY|COMPUTER|CAMERA|FEVICOL|LUNCH|DINNER|SAMSUNG|"
    r"CALNDAR|CALENDAR|FABER|^FDCA$|PLATE|INSURANCE|COURIER|INNER$",
    re.IGNORECASE,
)
_STOCK_ROW = re.compile(
    r"^(?P<name>.*?)\s{2,}(?:(?P<pack>\S+(?: \S+)?)\s{2,})?"
    r"(?P<pur>-|-?[\d.]+)\s+(?P<sale>-|-?[\d.]+)\s+(?P<close>-|-?[\d.]+)$"
)
_SUFFIXES = [
    (r"\bCAPSULES?\b", "CAP"), (r"\bTABLETS?\b", "TAB"), (r"\bSYRUP\b", "SYP"),
    (r"\bSUSPENSION\b|\bSUS\b", "SUSP"), (r"\bINJECTION\b", "INJ"),
]


def product_key(name: str) -> str:
    """Normalise a product name so year-to-year spelling variants match ('RABICID - DSR' == 'RABICID DSR')."""
    n = name.upper()
    for pat, rep in _SUFFIXES:
        n = re.sub(pat, rep, n)
    return re.sub(r"[^A-Z0-9]", "", n)


def _load_stock() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Annual IN/OUT & closing statement — fixed-width text in column 0, '-' means zero."""
    rows, values = [], []
    num = lambda x: 0.0 if x == "-" else float(x)
    for path in sorted(DATA_DIR.glob("Stock/*")):
        m = re.search(r"(\d{4})-(\d{4})", path.name)
        if not m:
            continue
        fy = f"FY{m[1][2:]}-{m[2][2:]}"
        for line in pd.read_excel(path, header=None)[0].dropna().astype(str):
            line = line.replace("\xa0", " ").rstrip()
            r = _STOCK_ROW.match(line)
            if not r or r["name"].strip() in ("DESCRIPTION", "TOTAL"):
                continue
            name = r["name"].strip()
            if name == "VALUE":   # ₹ totals footer (not present every year)
                values.append({"FY": fy, "purchase_value": num(r["pur"]), "sale_value": num(r["sale"]), "closing_value": num(r["close"])})
                continue
            if _NON_PRODUCT.search(name):
                continue
            rows.append({
                "FY": fy, "product": name, "pack": r["pack"] or "",
                "units_bought": num(r["pur"]), "units_sold": num(r["sale"]), "closing_units": num(r["close"]),
            })
    stock = pd.DataFrame(rows)
    stock["product_key"] = stock["product"].map(product_key)
    # Display name per key = most recent spelling
    latest = stock.sort_values("FY").groupby("product_key")["product"].last()
    stock["product_name"] = stock["product_key"].map(latest)
    return stock, pd.DataFrame(values)


def _load_balances(pattern: str) -> pd.DataFrame:
    """Sundry debtors / creditors closing-balance list. Drops GRAND TOTAL and Marg's opening-difference plug."""
    frames = []
    for path in DATA_DIR.glob(pattern):
        raw = pd.read_excel(path, header=None)
        body = raw.iloc[9:]
        body = body[body[1].notna()]
        frames.append(pd.DataFrame({
            "party":  body[1].astype(str).str.strip(),
            "debit":  pd.to_numeric(body[5], errors="coerce").fillna(0),
            "credit": pd.to_numeric(body[6], errors="coerce").fillna(0),
            "source": path.stem,
        }))
    bal = pd.concat(frames, ignore_index=True)
    bal = bal[~bal["party"].str.contains(r"GRAND TOTAL|Difference in Opening", case=False)]
    return bal.reset_index(drop=True)


def _balance_date() -> str:
    path = next(DATA_DIR.glob("Buyer/*"), None)
    if path is None:
        return "unknown"
    text = " ".join(pd.read_excel(path, header=None).astype(str).values.ravel())
    m = re.search(r"UPTO (\d{2}-\d{2}-\d{4})", text)
    return m[1] if m else "unknown"


sales     = _load_book("Sales")
purchases = _load_book("Purchase")
stock, stock_values = _load_stock()
debtors   = _load_balances("Buyer/*")
creditors = _load_balances("Vender*/*")
BALANCE_AS_OF = _balance_date()

# Cash-counter bills are booked to parties named "CASH (<store>)"
sales["is_cash"] = sales["party"].str.contains(r"\bCASH\b", case=False)
# Bills raised by the company to itself (internal transfers) — excluded from customer metrics
_SELF = re.compile(r"REMAN LIFE ?CARE", re.IGNORECASE)
debtors = debtors[~debtors["party"].str.contains(_SELF)].reset_index(drop=True)


# ── Monthly revenue series & forecast ─────────────────────────────────────────

LAST_SALE_DATE: pd.Timestamp = sales["date"].max()

_monthly_all = sales.set_index("date")["taxable"].resample("MS").sum()
# The month of the last bill is partial unless the data runs to month-end
_last_full = LAST_SALE_DATE.to_period("M").to_timestamp()
if LAST_SALE_DATE.day < LAST_SALE_DATE.days_in_month - 2:
    _last_full -= pd.DateOffset(months=1)
# First full trading month (FY17-18 had only a few weeks of billing)
MONTHLY_REVENUE: pd.Series = _monthly_all[_monthly_all.index >= "2018-04-01"][:_last_full]
PARTIAL_MONTH = _monthly_all.index[-1] if _monthly_all.index[-1] > _last_full else None

FORECAST_WINDOW = 12   # trailing-average window — beat Holt-Winters / SARIMA / seasonal-naive in backtest


def _forecast(series: pd.Series, horizon: int) -> np.ndarray:
    return np.repeat(series.iloc[-FORECAST_WINDOW:].mean(), horizon)


def _backtest(series: pd.Series, n_origins: int = 34) -> dict:
    """Rolling-origin MAPE for next month / next quarter / next 12 months."""
    errs = {"month": [], "quarter": [], "year": []}
    for cut in range(len(series) - n_origins - 1, len(series) - 1):
        train, actual = series.iloc[:cut], series.iloc[cut:]
        f = _forecast(train, 12)
        errs["month"].append(abs(f[0] - actual.iloc[0]) / actual.iloc[0])
        if len(actual) >= 3:
            errs["quarter"].append(abs(f[:3].sum() - actual.iloc[:3].sum()) / actual.iloc[:3].sum())
        if len(actual) >= 12:
            errs["year"].append(abs(f[:12].sum() - actual.iloc[:12].sum()) / actual.iloc[:12].sum())
    return {k: round(float(np.mean(v)) * 100, 1) for k, v in errs.items() if v}


FORECAST_ACCURACY: dict = _backtest(MONTHLY_REVENUE)   # MAPE %, lower is better


def seasonality_index() -> pd.Series:
    """Ratio of each month to its centred 12-month moving average; median per calendar month, 100 = average."""
    s = MONTHLY_REVENUE
    ma = s.rolling(12, center=True).mean().rolling(2).mean().shift(-1)
    ratio = (s / ma).dropna()
    idx = ratio.groupby(ratio.index.month).median()
    return (idx / idx.mean() * 100).round(0)
