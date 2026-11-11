"""
Eval harness — golden questions covering all 16 ERP tools
(8 FY18-19 pilot product tools + 8 full-history Marg tools) plus small talk.

Checks three things per question:
  1. Tool check   — did the agent call the expected tool?
  2. Data check   — does the answer contain the expected value/name?
  3. Format check — does the answer contain Summary / Risks / Actions / Confidence?

Run:
    python eval_harness.py
    python eval_harness.py --verbose     # print full agent answers
    python eval_harness.py --question 3  # run a single question by index
"""

import argparse
import re
import sys
import time

import pandas as pd

from erp_agent import dashboard_agent

# ── Golden test set ───────────────────────────────────────────────────────────
# Each entry:
#   question     : str
#   expected_tool: str | list — at least one tool call must match (any of a list); None = no tool (small talk)
#   data_checks  : list — every check must pass. A check is either
#                  "text"       → substring, case-insensitive
#                  ["a", "b"]   → any one of these (same value written differently)
#                  "re:<regex>" → regex search on the raw answer (case-sensitive)
#   tool      : str  — human label for the tool being tested

GOLDEN = [
    # ── inventory_tool (2) ────────────────────────────────────────────────────
    {
        "question":      "Which product has the worst stockout risk?",
        "expected_tool": "inventory_tool",
        "data_checks":   ["RUBICAL"],
        "tool":          "inventory_tool",
    },
    {
        "question":      "How many months of stock do we have left for our top A-class products?",
        "expected_tool": "inventory_tool",
        "data_checks":   ["RUBICAL", "NEROFORCE GX"],
        "tool":          "inventory_tool",
    },

    # ── revenue_tool (3) ──────────────────────────────────────────────────────
    {
        "question":      "Which product generates the most revenue?",
        "expected_tool": "revenue_tool",
        "data_checks":   ["SOYA D3"],
        "tool":          "revenue_tool",
    },
    {
        "question":      "What are our lowest revenue products?",
        "expected_tool": "revenue_tool",
        "data_checks":   ["REMANKOF SYP 100ML", "ALLVIT CAP"],
        "tool":          "revenue_tool",
    },
    {
        "question":      "What is the average selling price across all products?",
        "expected_tool": "kpi_dashboard_tool",
        "data_checks":   ["117.48"],   # total revenue ÷ total units — not the top-10 average
        "tool":          "kpi_dashboard_tool",
    },

    # ── seasonality_tool (2) ─────────────────────────────────────────────────
    {
        "question":      "Which product has the most seasonal demand?",
        "expected_tool": "seasonality_tool",
        "data_checks":   ["seasonality"],
        "tool":          "seasonality_tool",
    },
    {
        "question":      "Which products are showing a growing demand trend?",
        "expected_tool": ["seasonality_tool", "product_trend_tool"],   # pilot monthly trend or multi-year units — both valid
        "data_checks":   [["Growing", "WIN FLEX GOLD", "RUBICAL"]],
        "tool":          "seasonality_tool",
    },

    # ── product_detail_tool (2) ───────────────────────────────────────────────
    {
        "question":      "Give me full details on NEROFORCE GX",
        "expected_tool": "product_detail_tool",
        "data_checks":   ["NEROFORCE GX"],
        "tool":          "product_detail_tool",
    },
    {
        "question":      "What is the inventory turnover for NUROCAL OD?",
        "expected_tool": "product_detail_tool",
        "data_checks":   ["NUROCAL OD"],
        "tool":          "product_detail_tool",
    },

    # ── kpi_dashboard_tool (2) ────────────────────────────────────────────────
    {
        "question":      "Give me a business overview",
        "expected_tool": "kpi_dashboard_tool",
        "data_checks":   ["APEX MEDICOS", ["188.5", "1.88 crore", "1.89 crore", "192.0", "1.92 crore"]],
        "tool":          "kpi_dashboard_tool",
    },
    {
        "question":      "How many products are at critical stock risk?",
        "expected_tool": "inventory_tool",
        "data_checks":   ["stockout risk"],
        "tool":          "inventory_tool or kpi_dashboard_tool",
    },

    # ── safety_stock_tool (2) ─────────────────────────────────────────────────
    {
        "question":      "Which products need to be reordered immediately?",
        "expected_tool": "safety_stock_tool",
        "data_checks":   ["reorder"],
        "tool":          "safety_stock_tool",
    },
    {
        "question":      "What is the safety stock for ALLVIT CAP?",
        "expected_tool": "safety_stock_tool",
        "data_checks":   ["ALLVIT CAP"],
        "tool":          "safety_stock_tool",
    },

    # ── customer_tool (3) ────────────────────────────────────────────────────
    {
        "question":      "Who is our top revenue distributor?",
        "expected_tool": "customer_tool",
        "data_checks":   ["APEX MEDICOS"],
        "tool":          "customer_tool",
    },
    {
        "question":      "Which distributors haven't placed an order in the last 3 months?",
        "expected_tool": "customer_tool",
        "data_checks":   ["inactiv", "order"],   # inactive / inactivity
        "tool":          "customer_tool",
    },
    {
        "question":      "Who buys NUROCAL OD the most?",
        "expected_tool": "customer_tool",
        "data_checks":   ["NUROCAL OD"],
        "tool":          "customer_tool",
    },

    # ── procurement_tool (2) ─────────────────────────────────────────────────
    {
        "question":      "Which product did we purchase the most units of?",
        "expected_tool": "procurement_tool",
        "data_checks":   ["SOYA D3"],
        "tool":          "procurement_tool",
    },
    {
        "question":      "Are we buying more than we are selling for RABICID LS CP?",
        "expected_tool": "procurement_tool",
        "data_checks":   ["RABICID LS CP"],
        "tool":          "procurement_tool",
    },

    # ── multi-tool chains (2) ─────────────────────────────────────────────────
    {
        "question":      "What is the safety stock for our top revenue product?",
        "expected_tool": "safety_stock_tool",
        "data_checks":   ["SOYA D3"],   # top revenue product in the pilot data
        "tool":          "multi-step (revenue → safety_stock)",
    },
    {
        "question":      "Which A-class product has the worst stockout risk and what is its forecast?",
        "expected_tool": "inventory_tool",
        "data_checks":   ["RUBICAL", "A"],
        "tool":          "multi-step (inventory → seasonality)",
    },

    # ══ Full-history tools (Marg exports FY17-18 → Sep 2026) ══════════════════
    # Expected values match the synthetic sample (sample_data/make_sample_data.py, seed 42).
    # On real data, rerun the tools and update these checks.

    # ── sales_growth_tool (3) ─────────────────────────────────────────────────
    {
        "question":      "What was our revenue in FY25-26?",
        "expected_tool": "sales_growth_tool",
        "data_checks":   [["188.5", "1.88 crore", "1.89 crore"]],
        "tool":          "sales_growth_tool",
    },
    {
        "question":      "How much has revenue grown this year compared to the same months last year?",
        "expected_tool": "sales_growth_tool",
        "data_checks":   ["4.7"],
        "tool":          "sales_growth_tool",
    },
    {
        "question":      "Which financial year had the highest revenue?",
        "expected_tool": "sales_growth_tool",
        "data_checks":   ["FY25-26", ["188.5", "1.88 crore", "1.89 crore"]],
        "tool":          "sales_growth_tool",
    },

    # ── revenue_forecast_tool (3) ─────────────────────────────────────────────
    {
        "question":      "What is the revenue forecast for next month?",
        "expected_tool": "revenue_forecast_tool",
        "data_checks":   ["16.1"],
        "tool":          "revenue_forecast_tool",
    },
    {
        "question":      "What will total revenue be for the full financial year FY26-27?",
        "expected_tool": "revenue_forecast_tool",
        "data_checks":   [["192.0", "192", "1.92 crore", "191.0", "1.91 crore"]],
        "tool":          "revenue_forecast_tool",
    },
    {
        "question":      "How accurate is our monthly revenue forecast?",
        "expected_tool": "revenue_forecast_tool",
        "data_checks":   ["10.4"],
        "tool":          "revenue_forecast_tool",
    },

    # ── sales_seasonality_tool (2) ────────────────────────────────────────────
    {
        "question":      "Which is our strongest month for sales?",
        "expected_tool": "sales_seasonality_tool",
        "data_checks":   ["november"],
        "tool":          "sales_seasonality_tool",
    },
    {
        "question":      "Which month has the weakest sales?",
        "expected_tool": "sales_seasonality_tool",
        "data_checks":   [r"re:\bMay\b"],
        "tool":          "sales_seasonality_tool",
    },

    # ── cash_credit_tool (1) ──────────────────────────────────────────────────
    {
        "question":      "What share of our sales was cash in FY24-25?",
        "expected_tool": "cash_credit_tool",
        "data_checks":   ["6.2"],
        "tool":          "cash_credit_tool",
    },

    # ── customer_health_tool (3) ──────────────────────────────────────────────
    {
        "question":      "Who is our top customer in the last 12 months?",
        "expected_tool": "customer_health_tool",
        "data_checks":   ["APEX MEDICOS"],
        "tool":          "customer_health_tool",
    },
    {
        "question":      "Which lost customer had the highest lifetime revenue?",
        "expected_tool": "customer_health_tool",
        "data_checks":   ["KIRAN MEDICAL HALL"],
        "tool":          "customer_health_tool",
    },
    {
        "question":      "How many active customers did we have in FY24-25?",
        "expected_tool": "customer_health_tool",
        "data_checks":   ["38"],
        "tool":          "customer_health_tool",
    },

    # ── receivables_tool (3) ──────────────────────────────────────────────────
    {
        "question":      "Who owes us the most money?",
        "expected_tool": "receivables_tool",
        "data_checks":   ["APEX MEDICOS", "16.3"],
        "tool":          "receivables_tool",
    },
    {
        "question":      "What are our total receivables outstanding?",
        "expected_tool": "receivables_tool",
        "data_checks":   [["96.8"]],
        "tool":          "receivables_tool",
    },
    {
        "question":      "Which supplier do we owe the most money to?",
        "expected_tool": "receivables_tool",
        "data_checks":   ["ALPHA FORMULATIONS"],
        "tool":          "receivables_tool",
    },

    # ── supplier_tool (1) ─────────────────────────────────────────────────────
    {
        "question":      "Who was our biggest supplier by purchases in the last 12 months?",
        "expected_tool": "supplier_tool",
        "data_checks":   ["ALPHA FORMULATIONS"],
        "tool":          "supplier_tool",
    },

    # ── product_trend_tool (3) ────────────────────────────────────────────────
    {
        "question":      "Which products are dead stock right now?",
        "expected_tool": "product_trend_tool",
        "data_checks":   ["REMAN-D AQUA"],
        "tool":          "product_trend_tool",
    },
    {
        "question":      "What was our best-selling product by units last financial year?",
        "expected_tool": "product_trend_tool",
        "data_checks":   ["SOYA D3"],
        "tool":          "product_trend_tool",
    },
    {
        "question":      "How many units of RABICID DSR did we sell in FY23-24?",
        "expected_tool": "product_trend_tool",
        "data_checks":   [["6,024", "6024"]],
        "tool":          "product_trend_tool",
    },

    # ── small talk (1) ────────────────────────────────────────────────────────
    {
        "question":      "hi",
        "expected_tool": None,
        "data_checks":   ["Reman ERP agent"],
        "tool":          "small talk (no tools)",
    },
]

# ── Format tokens every answer must contain ───────────────────────────────────
FORMAT_TOKENS = ["**Summary**", "**Risks**", "**Actions**", "**Confidence**"]


# ── Runner ────────────────────────────────────────────────────────────────────

def _check_passes(check, answer: str) -> bool:
    if isinstance(check, list):
        return any(_check_passes(c, answer) for c in check)
    if check.startswith("re:"):
        return re.search(check[3:], answer) is not None
    return check.lower() in answer.lower()


def _run_one(entry: dict, verbose: bool = False) -> dict:
    question  = entry["question"]
    exp_tool  = entry["expected_tool"]
    data_chks = entry["data_checks"]

    tools_called = []
    final_answer = ""
    elapsed      = 0.0

    t0 = time.time()
    try:
        for history, _table, _debug, _graph in dashboard_agent(question, []):
            if history:
                last = history[-1]
                if isinstance(last, dict) and last.get("role") == "assistant":
                    final_answer = str(last.get("content", ""))
            if _debug:
                # parse tool names from debug string: Tools: ['inventory_tool{}', ...]
                found = re.findall(r"'?(\w+_tool)'?", _debug)
                tools_called = list(dict.fromkeys(found))
    except Exception as e:
        final_answer = f"[AGENT ERROR: {e}]"
    elapsed = time.time() - t0

    if exp_tool is None:
        tool_ok = not tools_called
    elif isinstance(exp_tool, list):
        tool_ok = any(t in tools_called for t in exp_tool)
    else:
        tool_ok = exp_tool in tools_called
    data_ok   = all(_check_passes(chk, final_answer) for chk in data_chks)
    fmt_ok    = all(tok in final_answer for tok in FORMAT_TOKENS)
    if exp_tool is None:   # small-talk reply is a help message, not a report
        fmt_ok = True

    # Gemini bulk path skips ERP tools and format tokens — both are valid
    is_gemini = final_answer.startswith("**Gemini Flash Analysis**")
    if is_gemini:
        fmt_ok  = True
        tool_ok = True

    result = {
        "question":    question,
        "tool":        entry["tool"],
        "tools_called": tools_called,
        "tool_ok":     tool_ok,
        "data_ok":     data_ok,
        "fmt_ok":      fmt_ok,
        "elapsed":     round(elapsed, 1),
        "answer":      final_answer,
    }

    if verbose:
        status = "✅" if (tool_ok and data_ok and fmt_ok) else "❌"
        print(f"\n{status} Q: {question}")
        print(f"   Tools called : {tools_called}")
        print(f"   Tool ✅/❌  : {'✅' if tool_ok else '❌'}  (expected: {exp_tool})")
        print(f"   Data ✅/❌  : {'✅' if data_ok else '❌'}  (checks: {data_chks})")
        print(f"   Format ✅/❌: {'✅' if fmt_ok else '❌'}")
        print(f"   Time        : {elapsed:.1f}s")
        print(f"   Answer      : {final_answer[:300]}{'...' if len(final_answer)>300 else ''}")

    return result


def run_eval(verbose: bool = False, question_idx: int | None = None):
    questions = GOLDEN if question_idx is None else [GOLDEN[question_idx]]
    total     = len(questions)

    print(f"\n{'='*60}")
    print(f"  Reman ERP Agent — Eval Harness ({total} questions)")
    print(f"{'='*60}\n")

    results = []
    for i, entry in enumerate(questions):
        idx = question_idx if question_idx is not None else i
        print(f"[{idx+1:02d}/{len(GOLDEN):02d}] {entry['question'][:65]}...", end=" ", flush=True)
        r = _run_one(entry, verbose=verbose)
        results.append(r)
        status = "✅" if (r["tool_ok"] and r["data_ok"] and r["fmt_ok"]) else "❌"
        if not verbose:
            checks = f"tool={'✅' if r['tool_ok'] else '❌'} data={'✅' if r['data_ok'] else '❌'} fmt={'✅' if r['fmt_ok'] else '❌'}"
            print(f"{status}  {checks}  ({r['elapsed']}s)")

    # ── Summary ───────────────────────────────────────────────────────────────
    pass_all  = sum(1 for r in results if r["tool_ok"] and r["data_ok"] and r["fmt_ok"])
    pass_tool = sum(1 for r in results if r["tool_ok"])
    pass_data = sum(1 for r in results if r["data_ok"])
    pass_fmt  = sum(1 for r in results if r["fmt_ok"])

    print(f"\n{'='*60}")
    print(f"  RESULTS ({total} questions)")
    print(f"{'='*60}")
    print(f"  Overall pass (all 3 checks) : {pass_all}/{total}  ({100*pass_all//total}%)")
    print(f"  Tool routing accuracy        : {pass_tool}/{total}  ({100*pass_tool//total}%)")
    print(f"  Data accuracy                : {pass_data}/{total}  ({100*pass_data//total}%)")
    print(f"  Format compliance            : {pass_fmt}/{total}  ({100*pass_fmt//total}%)")
    avg_time = sum(r["elapsed"] for r in results) / len(results)
    print(f"  Avg response time            : {avg_time:.1f}s")
    print(f"{'='*60}\n")

    # ── Failures detail ───────────────────────────────────────────────────────
    failures = [r for r in results if not (r["tool_ok"] and r["data_ok"] and r["fmt_ok"])]
    if failures:
        print("FAILURES:")
        for r in failures:
            issues = []
            if not r["tool_ok"]: issues.append(f"wrong tool (got {r['tools_called']})")
            if not r["data_ok"]: issues.append("data check failed")
            if not r["fmt_ok"]:  issues.append("format missing")
            print(f"  ❌ {r['question'][:60]}")
            print(f"     Issues: {', '.join(issues)}")
        print()

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reman ERP Agent eval harness")
    parser.add_argument("--verbose",  action="store_true", help="Print full agent answers")
    parser.add_argument("--question", type=int, default=None, help="Run a single question by 0-based index")
    args = parser.parse_args()
    run_eval(verbose=args.verbose, question_idx=args.question)
