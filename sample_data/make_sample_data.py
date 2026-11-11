"""Generate the synthetic dataset the public repo runs on.

Every customer, supplier, quantity and amount here is made up. Product names come from the public
product catalogue in knowledge_base/. File layouts mimic Marg ERP exports so the real loaders run unchanged.

Writes:
  sample_data/cleaned_erp_data.xlsx          FY2018-19 product ledger (pilot tools, erp_data.py)
  sample_data/reman/Sales/*.xlsx             sales book per year          (marg_data.py)
  sample_data/reman/Purchase/*.xlsx          purchase book per year
  sample_data/reman/Stock/*.xlsx             annual stock IN/OUT statement
  sample_data/reman/Buyer/DEBTOR LIST.xlsx   receivables snapshot
  sample_data/reman/Vender/CREDITOR LIST.xlsx payables snapshot

Run: python sample_data/make_sample_data.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).parent
MARG = OUT / "reman"
rng = np.random.default_rng(42)

PRODUCTS = ["NEROFORCE GX", "TAMVIT OX", "NUROCAL OD", "RABICID LS CP", "ALLVIT CAP", "WIN FLEX GOLD",
            "REMAN DEC50", "RUBICAL", "RABICID DSR", "REMAN OVA", "SOYA D3", "RUBIFER XT SYP",
            "WINFLAM SP", "REMAN CV 625LB", "DEE 6", "ECET PLUS", "OLZ OZ LB", "REMANKOF SYP 100ML",
            "REMAN-D AQUA", "LORTIN LIV"]
PRICE = dict(zip(PRODUCTS, rng.uniform(40, 180, len(PRODUCTS)).round(2)))
WEIGHT = dict(zip(PRODUCTS, rng.lognormal(0, 0.8, len(PRODUCTS))))
WEIGHT["NEROFORCE GX"] *= 4          # clear top seller
WEIGHT["RUBICAL"] *= 3

CUSTOMERS = ["APEX MEDICOS", "BLUEBIRD PHARMA", "CITYCARE DISTRIBUTORS", "DELTA HEALTH AGENCIES", "EVERGREEN MEDICALS",
             "FIRSTAID TRADERS", "GOODLIFE PHARMACY", "HARMONY MEDICAL STORE", "INDUS DRUG HOUSE", "JASMINE CHEMISTS",
             "KIRAN MEDICAL HALL", "LOTUS PHARMA", "METRO DRUG AGENCY", "NOVA HEALTHCARE", "ORCHID MEDICOS",
             "PEARL PHARMACY", "QUALITY DRUG STORE", "RIVERSIDE MEDICALS", "SUNRISE CHEMISTS", "TRUST PHARMA",
             "UNITY MEDICAL AGENCY", "VISTA DRUG HOUSE", "WELLNESS POINT", "ZENITH PHARMACEUTICALS"]
CUSTOMERS += [f"{c} MEDICAL STORE" for c in ["AARAV", "BHARAT", "CHANDRA", "DEEPAK", "EKTA", "FALAK", "GANGA", "HIRA",
                                             "ISHAN", "JYOTI", "KAVYA", "LAKSHMI", "MANAS", "NEHA", "OM", "PRIYA"]]
LOST = {"KIRAN MEDICAL HALL", "QUALITY DRUG STORE", "EKTA MEDICAL STORE"}   # stop buying in 2024
CUST_W = rng.lognormal(0, 1.0, len(CUSTOMERS)); CUST_W[0] *= 6; CUST_W[CUSTOMERS.index("KIRAN MEDICAL HALL")] *= 4
CASH = "CASH (COUNTER SALES)"
SUPPLIERS = ["ALPHA FORMULATIONS PVT LTD", "BETA LIFESCIENCES", "CRESCENT LABS", "DYNAMIC PHARMA PACK", "EAST WIND HEALTHCARE"]
SUP_W = np.array([5, 3, 2, 1, 1.0])
SEASON = {1: 1.00, 2: 0.95, 3: 1.05, 4: 0.90, 5: 0.80, 6: 0.85, 7: 0.95, 8: 1.00, 9: 1.05, 10: 1.10, 11: 1.25, 12: 1.10}
HEADER = ["SAMPLE PHARMA DISTRIBUTORS (SYNTHETIC DATA)", "123 Example Road, Sample City", "Phone : 0000000000", "GSTIN : SAMPLE"]


def fy_label(d):
    y = d.year if d.month >= 4 else d.year - 1
    return y, y + 1


# ── 1. FY2018-19 product ledger (cleaned_erp_data.xlsx) ───────────────────────
rows = []
for prod in PRODUCTS[:18]:
    bal = int(rng.integers(800, 4000))
    rows.append({"Bill Number": f"{prod} 1*10", "Product": f"{prod} 2018-19"})
    rows.append({"Bill Number": "Opening Balance", "Date": "as on", "Type": "01-04-2018 STRP", "Balance": bal, "Product": f"{prod} 2018-19"})
    days = pd.date_range("2018-04-01", "2019-03-31")
    events = []
    for d in days:
        lam = 0.12 * WEIGHT[prod] * SEASON[d.month] ** 3
        for _ in range(rng.poisson(lam)):
            events.append((d, "Sale"))
        if rng.random() < 0.004:
            events.append((d, "Sale Return"))
        if d.day == 5 and rng.random() < 0.6:
            events.append((d, "Purchase"))
    for i, (d, typ) in enumerate(sorted(events)):
        if typ == "Purchase":
            q = int(rng.integers(200, 900) * max(WEIGHT[prod], 0.5)); bal += q; party = SUPPLIERS[int(rng.choice(len(SUPPLIERS), p=SUP_W / SUP_W.sum()))]
            val = round(q * PRICE[prod] * 0.55, 2)
        else:
            q = int(rng.integers(5, 120)); party = CUSTOMERS[int(rng.choice(len(CUSTOMERS), p=CUST_W / CUST_W.sum()))]
            if typ == "Sale":
                if bal <= 0:
                    continue
                q = min(q, bal); bal -= q
            else:
                q = int(rng.integers(1, 10)); bal += q
            val = round(q * PRICE[prod], 2)
        rows.append({"Bill Number": f"SM{i:04d}", "Date": d.strftime("%d-%m-%Y"), "Type": typ, "Description": party,
                     "Batch No": f"SMP-{rng.integers(100, 999)}", "Quantity": q, "Value": val, "Balance": bal,
                     "Product": f"{prod} 2018-19"})
ledger = pd.DataFrame(rows, columns=["Bill Number", "Date", "Type", "Description", "Batch No", "Quantity", "Value", "Balance", "Product"])
ledger.to_excel(OUT / "cleaned_erp_data.xlsx", index=False)


# ── 2. Sales / purchase books 2017-04 → 2026-10 ──────────────────────────────
def book(kind, parties, weights, start, end, bills_per_month, growth):
    out = []
    for m in pd.date_range(start, end, freq="MS"):
        years = (m - pd.Timestamp(start)).days / 365.25
        n = rng.poisson(bills_per_month * SEASON[m.month] * (1 + growth) ** years)
        last = (m + pd.offsets.MonthEnd(0)).day
        for _ in range(n):
            d = m + pd.Timedelta(days=int(rng.integers(0, last)))
            if d > pd.Timestamp(end):
                continue
            w = weights.copy()
            if kind == "sale" and d.year >= 2024:
                w = np.array([0 if p in LOST else x for p, x in zip(parties, w)])
            party = parties[int(rng.choice(len(parties), p=w / w.sum()))]
            taxable = round(float(rng.lognormal(9.2, 0.6)), 2)
            tax = round(taxable * 0.12, 2)
            out.append((d, party, taxable, tax))
    return sorted(out)


def write_book(folder, prefix, entries, by):
    (MARG / folder).mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(entries, columns=["date", "party", "taxable", "tax"])
    df["key"] = df["date"].map(lambda d: fy_label(d)[0]) if by == "fy" else df["date"].dt.year
    for k, g in df.groupby("key"):
        top = [[h] + [None] * 9 for h in HEADER] + [[None] * 10, [f"{prefix} REPORT"] + [None] * 9, [None] * 10]
        hdr = [["DATE", "BILL NO.", "PARTY NAME", "BILL AMT.", "TAXABLE", "TAX", "SUR.", "TAX FREE", "EXEMPTED", "R.OFF"]]
        body = [[r.date.strftime("%d-%m-%Y"), f"S{k % 100:02d}-{i:05d}", r.party, round(r.taxable + r.tax), r.taxable, r.tax, 0, 0, 0, 0]
                for i, r in enumerate(g.itertuples(), 1)]
        foot = [[g["date"].max().strftime("%d-%m-%Y"), f"Total : {len(g)}", "SYNTHETIC DATA"] + [None] * 7]
        name = f"{prefix} REPORT {k}-{k + 1}.xlsx" if by == "fy" else f"{prefix} REPORT {k}.xlsx"
        pd.DataFrame(top + hdr + body + foot).to_excel(MARG / folder / name, header=False, index=False)


custs = CUSTOMERS + [CASH]
cw = np.append(CUST_W, CUST_W.sum() * 0.06)
sales = book("sale", custs, cw, "2017-04-01", "2026-10-31", 70, 0.08)
write_book("Sales", "SALES", sales, by="year")
purch = book("purchase", SUPPLIERS, SUP_W, "2017-04-01", "2026-10-31", 9, 0.08)
write_book("Purchase", "PURCHASE", purch, by="fy")


# ── 3. Annual stock statements ────────────────────────────────────────────────
(MARG / "Stock").mkdir(parents=True, exist_ok=True)
stock_prods = [p for p in PRODUCTS if p != "LORTIN LIV"]
closing = {p: int(rng.integers(200, 3000)) for p in stock_prods}
for y in range(2017, 2026):
    lines = ["SAMPLE PHARMA DISTRIBUTORS (SYNTHETIC DATA)", f"IN/OUT STATEMENT 01-04-{y} - 31-03-{y + 1}",
             "DESCRIPTION          PACK        PURCHASE      SALE      C.STOCK"]
    tot = [0, 0, 0]
    for p in stock_prods:
        if p == "REMAN-D AQUA" and y >= 2023:            # dead stock: nothing bought or sold since FY23-24
            bought, sold = 0, 0
        else:
            base = WEIGHT[p] * 3000 * (1.08 ** (y - 2017))
            sold = int(base * rng.uniform(0.7, 1.3)); bought = int(sold * rng.uniform(0.85, 1.2))
            sold = min(sold, closing[p] + bought)
        closing[p] = closing[p] + bought - sold
        f = lambda v: "-" if v == 0 else str(v)
        lines.append(f"{p}          1*10          {f(bought)}      {f(sold)}      {f(closing[p])}")
        tot = [tot[0] + bought, tot[1] + sold, tot[2] + closing[p]]
    lines.append(f"TOTAL                                  {tot[0]}      {tot[1]}      {tot[2]}")
    pd.DataFrame({0: lines}).to_excel(MARG / "Stock" / f"STOCK REPORT {y}-{y + 1}.xlsx", header=False, index=False)


# ── 4. Debtor / creditor balance lists ────────────────────────────────────────
def balances(folder, fname, title, parties, weights):
    (MARG / folder).mkdir(parents=True, exist_ok=True)
    head = [[None] * 7 for _ in range(9)]
    head[1][1], head[2][1], head[5][1] = HEADER[0], HEADER[1], "FINANCIAL YEAR 2026-2027"
    head[6][1], head[6][5] = title, "UPTO 31-10-2026"
    head[7][1], head[7][5], head[8][5], head[8][6] = "PARTICULARS", "CLOSING BALANCE", "DEBIT", "CREDIT"
    body, deb, cre = [], 0.0, 0.0
    for p, w in zip(parties, weights):
        amt = round(float(w / weights.sum() * rng.uniform(8e6, 1.2e7)), 2)
        if title.endswith("DEBTORS"):
            body.append([None, p, None, None, None, amt, None]); deb += amt
        else:
            body.append([None, p, None, None, None, None, amt]); cre += amt
    body.append([None, "GRAND TOTAL", None, None, None, round(deb, 2) or None, round(cre, 2) or None])
    pd.DataFrame(head + body).to_excel(MARG / folder / fname, header=False, index=False)


active = [c for c in CUSTOMERS]
balances("Buyer", "DEBTOR LIST.xlsx", "SUNDRY DEBTORS", active, np.array(CUST_W))
balances("Vender", "CREDITOR LIST.xlsx", "SUNDRY CREDITORS", SUPPLIERS, SUP_W)
print("synthetic data written to", OUT)
