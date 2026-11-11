"""
Agent layer — Claude agentic loop (tool manager) + OpenAI summarizer.

Stateless per request: all intermediate state lives in local variables
inside dashboard_agent(), so concurrent Gradio sessions are safe.
dashboard_agent() is a generator — yields (history, table, debug, graph)
tuples so Gradio can stream status updates and the final summary.
"""

import os
import re
import json
import pickle
import time
import numpy as np
import anthropic
from openai import OpenAI
import pandas as pd

QUERY_LOG = "query_log.jsonl"

def _log_query(question, tools, total_cost, elapsed, critic_passed, iterations, data_quality):
    entry = {
        "timestamp":     time.strftime("%Y-%m-%dT%H:%M:%S"),
        "question":      question[:200],
        "tools":         tools,
        "cost_usd":      round(total_cost, 6),
        "elapsed_s":     round(elapsed, 1),
        "critic_passed": critic_passed,
        "iterations":    iterations,
        "data_quality":  data_quality,
    }
    try:
        with open(QUERY_LOG, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        print(f"[QueryLog] failed: {e}")

from config import (
    ANTHROPIC_API_KEY, OPENAI_API_KEY, COHERE_API_KEY, GROQ_API_KEY, GOOGLE_API_KEY,
    CLAUDE_INPUT_PRICE, CLAUDE_OUTPUT_PRICE,
    CLAUDE_CACHE_WRITE_PRICE, CLAUDE_CACHE_READ_PRICE,
    OPENAI_INPUT_PRICE, OPENAI_OUTPUT_PRICE,
    MAX_AGENT_ITERATIONS, MAX_TOOL_PAIRS, CLAUDE_MODEL,
    calculate_cost,
)
from erp_data import ABC_MAP
from erp_tools import run_tool, build_forecast_graph

# SDK defaults are 10 min × 3 attempts — one stalled request froze a chat reply for 35 min
claude_client  = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, timeout=60, max_retries=2)
openai_client  = OpenAI(timeout=60, max_retries=2)

if COHERE_API_KEY:
    import cohere as _cohere
    cohere_client = _cohere.ClientV2(api_key=COHERE_API_KEY, timeout=20)
    print("[Cohere] Rerank enabled")
else:
    cohere_client = None
    print("[Cohere] No API key — cosine similarity RAG active")

GROQ_ROUTER_MODEL = "openai/gpt-oss-20b"   # llama-3.1-8b-instant was retired by Groq

if GROQ_API_KEY:
    from groq import Groq as _Groq
    groq_client = _Groq(api_key=GROQ_API_KEY, timeout=10, max_retries=1)
    print(f"[Groq] Intent router enabled ({GROQ_ROUTER_MODEL})")
else:
    groq_client = None
    print("[Groq] No API key — Claude handles routing directly")

if GOOGLE_API_KEY:
    from google import genai as _genai
    gemini_client = _genai.Client(api_key=GOOGLE_API_KEY, http_options={"timeout": 60_000})   # ms
    print("[Gemini] Flash bulk analyst enabled")
else:
    gemini_client = None
    print("[Gemini] No API key — bulk analysis unavailable")


# ── Token-aware truncation ────────────────────────────────────────────────────

def _truncate_to_tokens(text: str, max_tokens: int = 3000) -> str:
    """
    Truncate text to at most max_tokens (estimated at 4 chars/token),
    always cutting at a newline so rows are never split mid-line.
    """
    char_budget = max_tokens * 4
    if len(text) <= char_budget:
        return text
    cut = text.rfind("\n", 0, char_budget)
    return text[: cut if cut > 0 else char_budget]


# ── Retry helper ──────────────────────────────────────────────────────────────

def _with_retry(fn, retries=3, base_delay=1.0, label="API"):
    """Call fn(); on exception retry up to `retries` times with exponential backoff."""
    for attempt in range(retries + 1):
        try:
            return fn()
        except Exception as e:
            if attempt == retries:
                raise
            delay = base_delay * (2 ** attempt)
            print(f"[{label}] attempt {attempt + 1} failed: {e} — retrying in {delay:.0f}s")
            time.sleep(delay)


# ── Groq intent router ───────────────────────────────────────────────────────

_ROUTER_SYSTEM = """You are an ERP query router. Classify the user's question into the single most relevant tool.

Tools:
- inventory_tool       : stock levels, stockout risk, months of supply, balance
- revenue_tool         : revenue rankings, top/bottom products, sales value, average price
- seasonality_tool     : seasonal trends, demand patterns, forecast, growing/declining
- product_detail_tool  : one named product's monthly detail in FY2018-19 only (use product_trend_tool for any other year)
- kpi_dashboard_tool   : business overview, KPI summary, overall performance, average selling price across all products
- safety_stock_tool    : safety stock, reorder point, buffer stock, lead time
- customer_tool        : which distributor buys a specific product (FY18-19 pilot data)
- procurement_tool     : product-level purchase vs sale, sell-through rate (FY18-19 pilot data)
- sales_growth_tool      : revenue growth YoY / MoM, sales by year or month, this year vs last year
- revenue_forecast_tool  : company revenue forecast, year-end projection, forecast accuracy
- sales_seasonality_tool : strongest / weakest months for the company
- cash_credit_tool       : cash vs credit sales
- customer_health_tool   : customers — active, new, retention, top, lost, churn, at risk
- receivables_tool       : dues, outstanding, receivables, collections, DSO, payables, what we owe
- supplier_tool          : suppliers, purchases, purchase vs sales, margin
- product_trend_tool     : product trends across years, dead stock, overstock, best sellers now

Prefer the full-history tools (sales_growth … product_trend) unless the question needs monthly product-level detail.

Respond with JSON only — no explanation, no markdown:
{"tool": "<tool_name>", "confidence": "high|medium|low", "multi_step": true|false}

multi_step = true when the question clearly needs 2+ tools (e.g. "find the worst product AND explain why")."""


def _classify_intent(question: str) -> dict:
    """Classify query intent using Groq before the Claude agentic loop."""
    if groq_client is None:
        return {"tool": None, "confidence": "low", "multi_step": True}
    try:
        import json
        resp = groq_client.chat.completions.create(
            model=GROQ_ROUTER_MODEL,
            messages=[
                {"role": "system", "content": _ROUTER_SYSTEM},
                {"role": "user",   "content": question},
            ],
            max_tokens=400,          # gpt-oss reasons before answering — 60 tokens gets cut off
            reasoning_effort="low",
            temperature=0.0,
            timeout=10,
        )
        text  = resp.choices[0].message.content.strip()
        start = text.find("{")
        end   = text.rfind("}") + 1
        result = json.loads(text[start:end])
        print(f"[Groq Router] {result}")
        return result
    except Exception as e:
        print(f"[Groq Router] failed: {e}")
        return {"tool": None, "confidence": "low", "multi_step": True}


# ── Gemini Flash bulk analyst ─────────────────────────────────────────────────

def gemini_analyst(question: str) -> str | None:
    """
    Send the full transaction dataset to Gemini Flash for deep analytical questions
    that require scanning all rows rather than pre-aggregated tool summaries.
    Returns a plain-text answer, or None if Gemini is unavailable.
    """
    if gemini_client is None:
        return None

    from erp_data import df
    try:
        sample = df.tail(2000).to_csv(index=False)
        prompt = (
            f"You are an ERP data analyst. Answer this business question using the transaction data below.\n\n"
            f"Question: {question}\n\n"
            f"ERP Data (sales transactions — Quantity=units sold, Value=revenue in ₹, Balance=stock):\n{sample}\n\n"
            f"Give a concise, data-driven answer with specific numbers and product/distributor names. "
            f"Write all money in ₹ (Indian Rupees), never $."
        )
        from google.genai import types as _gtypes
        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=_gtypes.GenerateContentConfig(
                thinking_config=_gtypes.ThinkingConfig(thinking_budget=0),
            ),
        )
        result = response.text.strip()
        print(f"[Gemini] success ({len(result)} chars)")
        return result
    except Exception as e:
        print(f"[Gemini] failed: {e}")
        return None


# Gemini only scans the FY18-19 pilot transactions — multi-year / trend questions
# must reach the full-history tools instead, so keep this to raw-row requests.
_BULK_KEYWORDS = [
    "entire dataset", "raw transactions", "every transaction", "transaction level",
]


def _is_bulk_question(question: str) -> bool:
    q = question.lower()
    return any(k in q for k in _BULK_KEYWORDS)


# ── Semantic RAG ──────────────────────────────────────────────────────────────

_RAG_CHUNKS = []
_RAG_EMBEDDINGS = None   # np.ndarray once built


def _build_rag_cache():
    global _RAG_CHUNKS, _RAG_EMBEDDINGS
    kb_path    = "knowledge_base/reman_gyni_clean.txt"
    cache_path = "knowledge_base/embeddings_cache.pkl"

    try:
        with open(kb_path, "r", encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        return

    chunks = [c.strip() for c in text.split("--------------------------------------------------") if len(c.strip()) > 20]
    if not chunks:
        return

    if os.path.exists(cache_path):
        try:
            kb_mtime    = os.path.getmtime(kb_path)
            cache_mtime = os.path.getmtime(cache_path)
            if cache_mtime >= kb_mtime:
                with open(cache_path, "rb") as f:
                    cached = pickle.load(f)
                _RAG_CHUNKS     = cached["chunks"]
                _RAG_EMBEDDINGS = cached["embeddings"]
                print(f"[RAG] Loaded {len(_RAG_CHUNKS)} embeddings from cache")
                return
        except Exception:
            pass

    print(f"[RAG] Building embeddings for {len(chunks)} chunks...")
    try:
        embeddings = []
        for i in range(0, len(chunks), 100):
            resp = openai_client.embeddings.create(
                model="text-embedding-3-small", input=chunks[i:i + 100]
            )
            embeddings.extend([e.embedding for e in resp.data])
        _RAG_CHUNKS = chunks
        _RAG_EMBEDDINGS = np.array(embeddings, dtype=np.float32)
        with open(cache_path, "wb") as f:
            pickle.dump({"chunks": chunks, "embeddings": _RAG_EMBEDDINGS}, f)
        print(f"[RAG] {len(chunks)} embeddings built and cached")
    except Exception as e:
        print(f"[RAG] Build failed: {e} — keyword fallback active")


_RAG_CACHE_LOADED = False


def _ensure_rag_cache():
    global _RAG_CACHE_LOADED
    if not _RAG_CACHE_LOADED:
        _build_rag_cache()
        _RAG_CACHE_LOADED = True


def _rag_keyword_fallback(question: str, important_products: list) -> str:
    kb_path = "knowledge_base/reman_gyni_clean.txt"
    try:
        with open(kb_path, "r", encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        return "No RAG knowledge base found."

    chunks = text.split("--------------------------------------------------")
    scored = []
    for product in important_products:
        words = str(product).lower().split()
        for chunk in chunks:
            cl = chunk.lower()
            score = sum(1 for w in words if len(w) > 3 and w in cl)
            if score > 0:
                scored.append((score + 5, chunk.strip()))

    if not important_products:
        for chunk in chunks:
            cl = chunk.lower()
            score = sum(1 for w in question.lower().split() if len(w) > 3 and w in cl)
            if score > 0:
                scored.append((score, chunk.strip()))

    scored.sort(reverse=True, key=lambda x: x[0])
    seen, unique = set(), []
    for _, chunk in scored:
        if chunk and chunk not in seen:
            unique.append(chunk)
            seen.add(chunk)
    return "\n\n".join(unique[:3]) if unique else "No relevant product knowledge found."


def _cosine_rag_search(query: str) -> str:
    """Cosine similarity fallback — used when Cohere is unavailable."""
    if _RAG_EMBEDDINGS is None or not _RAG_CHUNKS:
        return "No relevant product knowledge found."
    try:
        resp  = openai_client.embeddings.create(model="text-embedding-3-small", input=[query])
        q_emb = np.array(resp.data[0].embedding, dtype=np.float32)
        dot   = _RAG_EMBEDDINGS @ q_emb
        norms = np.linalg.norm(_RAG_EMBEDDINGS, axis=1) * np.linalg.norm(q_emb)
        sims  = dot / np.where(norms == 0, 1.0, norms)
        top   = np.argsort(sims)[::-1][:3]
        results = [_RAG_CHUNKS[i] for i in top if sims[i] > 0.15]
        return "\n\n".join(results) if results else "No relevant product knowledge found."
    except Exception as e:
        print(f"[RAG cosine] failed: {e}")
        return "No relevant product knowledge found."


def rag_search(question: str, important_products: list) -> str:
    _ensure_rag_cache()
    if not _RAG_CHUNKS:
        return _rag_keyword_fallback(question, important_products)

    query = (" ".join(str(p) for p in important_products[:3]) + " " + question).strip()

    # ── Cohere Rerank (preferred) ─────────────────────────────────────────────
    if cohere_client is not None:
        try:
            response = cohere_client.rerank(
                model="rerank-v3.5",
                query=query,
                documents=_RAG_CHUNKS,
                top_n=3,
            )
            results = [
                _RAG_CHUNKS[r.index]
                for r in response.results
                if r.relevance_score > 0.1
            ]
            print(f"[Cohere Rerank] top scores: {[round(r.relevance_score, 3) for r in response.results[:3]]}")
            return "\n\n".join(results) if results else "No relevant product knowledge found."
        except Exception as e:
            print(f"[Cohere Rerank] failed: {e} — falling back to cosine")

    # ── Cosine similarity fallback ────────────────────────────────────────────
    return _cosine_rag_search(query)


# ── Tool schemas (Anthropic format) ──────────────────────────────────────────

CLAUDE_TOOLS = [
    {
        "name": "inventory_tool",
        "description": "Stock levels, stockout risk, reorder needs, demand velocity, and months of supply. Use when question is about stock, not revenue.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "revenue_tool",
        "description": "Revenue and units sold ranked across all products. Use for top/low performers, average selling price, or demand by value — not for a single product.",
        "input_schema": {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["top", "low"],
                    "description": "top = highest revenue products, low = lowest revenue products.",
                }
            },
            "required": ["mode"],
        },
    },
    {
        "name": "seasonality_tool",
        "description": "Monthly demand patterns, volatility, trend (growing/declining/stable), and 3-month forecast. Use when question is about seasonal trends or future demand.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "product_detail_tool",
        "description": "FY2018-19 PILOT ONLY. All monthly metrics for one named product in FY18-19: sales, revenue in ₹, stock, pricing, demand. Do NOT use for any other year or for trends across years — use product_trend_tool for those.",
        "input_schema": {
            "type": "object",
            "properties": {
                "product_name": {
                    "type": "string",
                    "description": "Exact or partial product name, e.g. NUROCAL-OD.",
                }
            },
            "required": ["product_name"],
        },
    },
    {
        "name": "kpi_dashboard_tool",
        "description": "Business-wide summary: total revenue, critical stock count, top products, average price. Use for overview or performance snapshot — not for deep-dives.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "safety_stock_tool",
        "description": "Per-product safety stock and reorder points using statistical formula (avg demand × lead time + Z × std dev × √lead time). Use for reorder quantity, safety buffer, buffer stock, or dynamic stockout threshold questions.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "procurement_tool",
        "description": "Purchase vs sales analysis: what was bought, procurement quantity vs units sold, sell-through rate, procurement gap (overstock risk). Use for questions about purchasing, buying, procurement, supplier, or comparing purchases to sales.",
        "input_schema": {
            "type": "object",
            "properties": {
                "product_name": {
                    "type": "string",
                    "description": "Optional. Filter by product name.",
                }
            },
            "required": [],
        },
    },
    {
        "name": "customer_tool",
        "description": "Distributor and customer analysis. Use for ANY question about: who buys, which distributor, top customers, buyer ranking, inactive customers, customer revenue, who orders which product. This is the ONLY tool with distributor/customer data.",
        "input_schema": {
            "type": "object",
            "properties": {
                "product_name": {
                    "type": "string",
                    "description": "Optional. Filter by product name to see which distributors buy that product.",
                },
                "mode": {
                    "type": "string",
                    "enum": ["top_revenue", "inactive"],
                    "description": "top_revenue = rank distributors by total revenue. inactive = distributors with no orders in 3+ months.",
                },
            },
            "required": ["mode"],
        },
    },
    # ── Full-history company tools (Marg exports FY2017-18 → latest) ──────────
    {
        "name": "sales_growth_tool",
        "description": "FULL HISTORY (FY17-18 → today). Company revenue by financial year with YoY growth and a like-for-like YTD comparison, or month-by-month revenue with MoM and same-month YoY. Use for any revenue growth, trend over years, this year vs last year, or monthly sales question.",
        "input_schema": {
            "type": "object",
            "properties": {
                "period": {"type": "string", "enum": ["fy", "month"],
                           "description": "fy = by financial year + like-for-like YTD row — use for annual growth, 'this year vs last year', 'so far this year', YTD. month = last 13 months with MoM and same-month YoY — use only for month-by-month questions."},
            },
            "required": ["period"],
        },
    },
    {
        "name": "revenue_forecast_tool",
        "description": "FULL HISTORY. Company revenue forecast for next month, next quarter and the full financial year, with backtested accuracy (typical % error) and a current-pace scenario. Use for any company-level revenue forecast, projection, target or 'how will this year end' question.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "sales_seasonality_tool",
        "description": "FULL HISTORY. Company-wide monthly seasonality index (100 = average month) — strong and weak months, and how reliable each month's pattern is. Use for 'which months are strongest/weakest' at company level.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "cash_credit_tool",
        "description": "FULL HISTORY. Cash vs credit sales share by financial year — revenue, bill counts and average bill size for cash-counter vs credit customers.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "customer_health_tool",
        "description": "FULL HISTORY. Customer base health. summary = active/new customers, retention %, concentration per FY. top = biggest customers last 12 months with outstanding dues. lost = customers silent >1 year ranked by lifetime value. at_risk = customers silent 90-365 days. Default tool for customer questions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": ["summary", "top", "lost", "at_risk"]},
                "top_n": {"type": "integer", "description": "Rows to return for top/lost/at_risk (default 15)."},
            },
            "required": ["mode"],
        },
    },
    {
        "name": "receivables_tool",
        "description": "Outstanding balances snapshot. receivables = what customers owe us (debtors), DSO, top debtors and how long since they last bought. payables = what we owe suppliers (creditors), DPO. Use for collections, dues, outstanding, credit risk, cash tied up, working capital.",
        "input_schema": {
            "type": "object",
            "properties": {
                "side": {"type": "string", "enum": ["receivables", "payables"]},
                "top_n": {"type": "integer", "description": "Rows of top parties (default 15)."},
            },
            "required": ["side"],
        },
    },
    {
        "name": "supplier_tool",
        "description": "FULL HISTORY. Purchases. summary = purchases vs sales by FY with purchase-to-sales ratio and gross-margin proxy. top = supplier ranking by last-12-month and lifetime purchase value.",
        "input_schema": {
            "type": "object",
            "properties": {"mode": {"type": "string", "enum": ["summary", "top"]}, "top_n": {"type": "integer"}},
            "required": ["mode"],
        },
    },
    {
        "name": "product_trend_tool",
        "description": "FULL HISTORY, ANNUAL units only (from yearly stock statements — no monthly or ₹ per product). With product_name: units bought/sold/closing for every FY. Without: mode top = best sellers last full FY with YoY, dead = stock with almost no sales this FY, overstock = closing stock above 12 months of sales, summary = company stock build-up by FY. Use for product trends across years, dead/slow stock, overstock.",
        "input_schema": {
            "type": "object",
            "properties": {
                "product_name": {"type": "string", "description": "Optional partial product name, e.g. RABICID."},
                "mode": {"type": "string", "enum": ["top", "dead", "overstock", "summary"]},
            },
            "required": [],
        },
    },
]

CLAUDE_SYSTEM = [{
    "type": "text",
    "text": """You are an ERP agentic manager. Your job is to answer business questions by calling ERP tools iteratively.

ERP meanings: Quantity = units sold | Value = revenue in Indian Rupees (₹, never $) | Balance = remaining stock inventory

ABC classification (Pareto-based, pre-computed on cumulative revenue):
- A = top 80% of revenue — highest-value products, prioritise stock coverage and reorder
- B = next 15% of revenue — medium-value, monitor closely
- C = bottom 5% of revenue — low-value, minimal safety stock needed

TWO DATASETS — pick the right one:
1. FULL HISTORY (Marg ERP, FY2017-18 → latest, company level): sales_growth_tool, revenue_forecast_tool,
   sales_seasonality_tool, cash_credit_tool, customer_health_tool, receivables_tool, supplier_tool, product_trend_tool.
   Bill-level sales/purchases (no product per bill), annual units per product, current debtor/creditor balances.
2. FY2018-19 PILOT (47 products, monthly, product × distributor): inventory_tool, revenue_tool, seasonality_tool,
   product_detail_tool, safety_stock_tool, procurement_tool, customer_tool.
Default to FULL HISTORY for anything about the business today, growth, years, forecasts, customers, dues or suppliers.
Use the PILOT tools only for monthly product-level detail (product revenue in ₹, product seasonality, safety stock,
reorder points, which distributor buys which product) — and say the figures are from FY2018-19.

Tool selection rules:
- revenue growth, YoY, MoM, this year vs last year, sales by year/month → sales_growth_tool
- company revenue forecast, projection, year-end estimate, forecast accuracy → revenue_forecast_tool
- strongest/weakest months, company seasonality → sales_seasonality_tool
- cash vs credit sales → cash_credit_tool
- customers: active, new, retention, top customers, lost, churn, silent, at risk → customer_health_tool
- dues, outstanding, receivables, collections, DSO, what we owe, payables, DPO → receivables_tool
- suppliers, purchases, purchase vs sales, margin → supplier_tool
- product trend over years, best sellers now, dead stock, slow moving, overstock, stock build-up → product_trend_tool
- a product's units in ANY financial year other than FY18-19 (e.g. "units of X in FY23-24") → product_trend_tool(product_name=X)
- "growth this year vs same months last year", "so far this year", YTD → sales_growth_tool(period=fy) and quote the YTD row
- overview, KPI, summary, business health → kpi_dashboard_tool (has both full-history and pilot KPIs)
- average selling price across all products → kpi_dashboard_tool (revenue_tool lists only 10 products — never average its rows)
- PILOT only: which distributor buys a product → customer_tool; product revenue ranking in ₹ / average price → revenue_tool;
  monthly stock, stockout, months of supply → inventory_tool; product monthly seasonality → seasonality_tool;
  one product's full monthly detail → product_detail_tool; safety stock, reorder point → safety_stock_tool;
  product purchase vs sale / sell-through → procurement_tool

Agent rules:
- Call tools one step at a time, using each result to decide the next call
- Chain calls when needed: e.g. find worst A-class product → then get its detail → then get its forecast
- Prioritise A-class stockout risks over B/C — flag them explicitly in your tool selections
- Stop when you have enough data — do NOT call unnecessary tools
- Maximum 5 tool calls per question
- You do NOT write the final answer — OpenAI will summarize. Just gather the right data.

---
EXAMPLES OF CORRECT TOOL CHAINS:

Q: "Which A-class product has the worst stockout risk?"
Step 1 → inventory_tool (get all products sorted by months of stock, check abc_class column)
Step 2 → product_detail_tool(product_name=worst A-class product found) (get full detail)
STOP — 2 calls sufficient.

Q: "Who buys NUROCAL OD the most?"
Step 1 → customer_tool(mode=top_revenue, product_name="NUROCAL OD")
STOP — 1 call sufficient.

Q: "Which distributors haven't ordered recently?"
Step 1 → customer_tool(mode=inactive)
STOP — 1 call sufficient.

Q: "What is the safety stock for our top revenue product?"
Step 1 → revenue_tool(mode=top) (find top revenue product)
Step 2 → safety_stock_tool (get reorder and buffer for all products, filter to top product)
STOP — 2 calls sufficient.

Q: "Are we buying more than we are selling for REMAN CEF?"
Step 1 → procurement_tool(product_name="REMAN CEF")
STOP — 1 call sufficient.

Q: "Give me a CEO overview with the worst risk product detail"
Step 1 → kpi_dashboard_tool (get overview and identify highest stockout risk product)
Step 2 → product_detail_tool(product_name=highest stockout risk product from KPI)
Step 3 → seasonality_tool (get forecast for context)
STOP — 3 calls sufficient.

Q: "Which products have seasonal demand and what is the forecast?"
Step 1 → seasonality_tool (get all seasonality scores and forecasts)
STOP — 1 call sufficient.
---""",
    "cache_control": {"type": "ephemeral"},
}]

_TOOL_LABELS = {
    "inventory_tool":      "inventory data",
    "revenue_tool":        "revenue data",
    "seasonality_tool":    "seasonality data",
    "product_detail_tool": "product details",
    "kpi_dashboard_tool":  "KPI dashboard",
    "safety_stock_tool":   "safety stock data",
    "customer_tool":       "customer/distributor data",
    "procurement_tool":    "procurement data",
    "sales_growth_tool":      "revenue growth",
    "revenue_forecast_tool":  "revenue forecast",
    "sales_seasonality_tool": "seasonality index",
    "cash_credit_tool":       "cash vs credit sales",
    "customer_health_tool":   "customer health",
    "receivables_tool":       "outstanding balances",
    "supplier_tool":          "supplier & purchase data",
    "product_trend_tool":     "product trends",
}


# ── Internal helpers ──────────────────────────────────────────────────────────

def _collect_tool_result(tool_name, args, selected_tools, important_products):
    table, graph = run_tool(tool_name, args)
    selected_tools.append(f"{tool_name}{args}")

    if "Product" in table.columns:
        important_products.extend(table["Product"].head(3).tolist())
    elif tool_name == "kpi_dashboard_tool":
        kpi_rows = table[table["KPI"].str.startswith(("Top Revenue Product", "Top Volume Product", "Best-selling product"))]
        important_products.extend(kpi_rows["Value"].tolist())

    enriched = table.copy()
    if "Product" in enriched.columns and "abc_class" not in enriched.columns:
        enriched["abc_class"] = enriched["Product"].map(ABC_MAP)

    table_text = f"\n=== {tool_name} {args} ===\n{enriched.to_string(index=False)}\n"
    return table, graph, table_text, enriched


_SMALL_TALK = re.compile(
    r"^(hi+|hello|hey|hii+|namaste|good (morning|afternoon|evening)|thanks?( you)?|thank you|ok(ay)?|"
    r"how are you\??|who are you\??|what can you do\??|help)[\s!.?]*$",
    re.IGNORECASE,
)

_HELP_TEXT = (
    "Ask me about your business (Marg data FY17-18 to date):\n\n"
    "- **Revenue** — \"How has revenue grown year on year?\", \"What is the forecast for this year?\"\n"
    "- **Customers** — \"Which customers are at risk?\", \"Which big customers have we lost?\"\n"
    "- **Cash** — \"Who owes us the most money?\", \"What do we owe suppliers?\"\n"
    "- **Products & stock** — \"Which products are dead stock?\", \"How has RABICID sold over the years?\"\n"
    "- **Overview** — \"Give me a business overview\"\n\n"
    "Product-level monthly detail (safety stock, reorder points, who buys a product) uses the FY2018-19 pilot data."
)


def _pick_display_table(question, tool_tables, focus_products):
    q = question.lower()

    if focus_products and "product_detail_tool" in tool_tables:
        return tool_tables["product_detail_tool"]

    keyword_map = [
        (["forecast", "projection", "year end", "year-end"], "revenue_forecast_tool"),
        (["growth", "yoy", "mom", "last year", "by year", "by month"], "sales_growth_tool"),
        (["strongest month", "weakest month", "seasonality index"], "sales_seasonality_tool"),
        (["cash"], "cash_credit_tool"),
        (["outstanding", "receivable", "dues", "owe", "payable", "dso", "dpo", "collection"], "receivables_tool"),
        (["customer", "lost", "churn", "retention", "at risk"], "customer_health_tool"),
        (["supplier", "purchase", "margin"], "supplier_tool"),
        (["dead stock", "overstock", "slow", "trend", "best seller", "build-up"], "product_trend_tool"),
        (["procurement", "purchase", "supplier", "sell-through", "buying"], "procurement_tool"),
        (["customer", "distributor", "buyer", "who buys", "who orders", "inactive"], "customer_tool"),
        (["safety stock", "reorder point", "buffer stock", "lead time"], "safety_stock_tool"),
        (["stock", "inventory", "stockout", "balance", "months of supply", "supply"], "inventory_tool"),
        (["season", "forecast", "trend", "monthly demand", "volatile", "demand pattern"], "seasonality_tool"),
        (["revenue", "sales", "top product", "bottom product", "low performer", "high performer", "price", "earning"], "revenue_tool"),
        (["kpi", "overview", "summary", "dashboard", "overall", "business health"], "kpi_dashboard_tool"),
    ]
    for keywords, tool in keyword_map:
        if any(k in q for k in keywords) and tool in tool_tables:
            t = tool_tables[tool]
            if not t.empty:
                return t

    for tool in ["product_detail_tool", "safety_stock_tool", "inventory_tool", "seasonality_tool", "revenue_tool", "kpi_dashboard_tool"]:
        if tool in tool_tables and not tool_tables[tool].empty:
            return tool_tables[tool]

    # Otherwise show the last table the agent fetched
    for t in reversed(list(tool_tables.values())):
        if not t.empty:
            return t
    return pd.DataFrame()


# ── Main agent entry point (streaming generator) ──────────────────────────────

def dashboard_agent(question: str, history: list):
    """
    Generator — yields (new_history, display_table, debug_info, graph) tuples.
    First yields are status updates (table/debug empty).
    Final yield has complete data + streamed OpenAI summary.
    """
    selected_tools     = []
    all_tables_text    = ""
    final_graph        = None
    tool_tables        = {}
    important_products = []
    focus_products     = []
    data_tools_hit     = 0   # tools that returned non-empty data
    data_tools_miss    = 0   # tools that returned empty
    _query_start       = time.time()

    loop_messages = []
    for msg in (history or [])[-10:]:
        if isinstance(msg, dict) and msg.get("content"):
            loop_messages.append({"role": msg["role"], "content": msg["content"]})
    loop_messages.append({"role": "user", "content": question})

    _initial_msg_count = len(loop_messages)

    claude_input_total   = 0
    claude_output_total  = 0
    cache_creation_total = 0
    cache_read_total     = 0
    iterations           = 0

    base = list(history or []) + [{"role": "user", "content": question}]

    # ── Status: thinking ──
    # Greetings / thanks need no tools or LLM calls
    if _SMALL_TALK.match(question.strip()):
        yield base + [{"role": "assistant", "content": "Hi! I'm the Reman ERP agent. " + _HELP_TEXT}], pd.DataFrame(), "Small talk — no tools or LLM calls", None
        return

    yield base + [{"role": "assistant", "content": "Analyzing your question..."}], pd.DataFrame(), "", None

    # ── Gemini bulk analysis (deep/historical questions) ─────────────────────
    if _is_bulk_question(question) and gemini_client is not None:
        yield base + [{"role": "assistant", "content": "Running deep analysis with Gemini Flash..."}], pd.DataFrame(), "", None
        gemini_answer = gemini_analyst(question)
        if gemini_answer:
            final = f"**Gemini Flash Analysis**\n\n{gemini_answer}"
            debug = "Routed to Gemini Flash (bulk/historical query) | Claude + tools skipped"
            yield base + [{"role": "assistant", "content": final}], pd.DataFrame(), debug, None
            return

    # ── Groq intent routing ───────────────────────────────────────────────────
    intent = _classify_intent(question)
    # Only inject hint for clearly single-tool questions — multi-step questions
    # need Claude to chain tools freely without a premature hint locking it in.
    _is_multi = intent.get("multi_step", False) or any(
        w in question.lower() for w in ("top ", "best ", "worst ", "highest ", "lowest ")
        if " and " in question.lower() or " for our " in question.lower() or " of our " in question.lower()
    )
    if intent.get("tool") and intent.get("confidence") in ("high", "medium") and not _is_multi:
        hint = f"\n[Routing hint: start with {intent['tool']}. Multi-step: False]"
        loop_messages[-1] = {"role": "user", "content": question + hint}

    # ── Claude agentic loop ───────────────────────────────────────────────────
    for _ in range(MAX_AGENT_ITERATIONS):
        tool_msgs = loop_messages[_initial_msg_count:]
        if len(tool_msgs) > MAX_TOOL_PAIRS * 2:
            loop_messages = loop_messages[:_initial_msg_count] + tool_msgs[-(MAX_TOOL_PAIRS * 2):]

        try:
            response = _with_retry(
                lambda: claude_client.messages.create(
                    model=CLAUDE_MODEL,
                    max_tokens=1024,
                    system=CLAUDE_SYSTEM,
                    tools=CLAUDE_TOOLS,
                    messages=loop_messages,
                ),
                label="Claude",
            )
        except Exception as e:
            print(f"[Claude] failed after retries: {e}")
            break

        claude_input_total   += response.usage.input_tokens
        claude_output_total  += response.usage.output_tokens
        cache_creation_total += getattr(response.usage, "cache_creation_input_tokens", 0) or 0
        cache_read_total     += getattr(response.usage, "cache_read_input_tokens", 0) or 0
        iterations += 1

        if response.stop_reason == "tool_use":
            tool_names = [b.name for b in response.content if b.type == "tool_use"]
            labels     = ", ".join(_TOOL_LABELS.get(n, n) for n in tool_names)
            yield base + [{"role": "assistant", "content": f"Fetching {labels}..."}], pd.DataFrame(), "", None

            tool_results_content = []
            for block in response.content:
                if block.type == "tool_use":
                    args = block.input or {}
                    table, graph, table_text, enriched = _collect_tool_result(
                        block.name, args, selected_tools, important_products
                    )
                    all_tables_text += table_text
                    if not table.empty and "Message" not in table.columns:
                        tool_tables[block.name] = table
                    if graph is not None:
                        final_graph = graph

                    if block.name == "product_detail_tool":
                        if not table.empty and "Product" in table.columns:
                            focus_products.extend(table["Product"].tolist())
                        elif args.get("product_name"):
                            focus_products.append(args["product_name"])

                    if not enriched.empty and "Message" not in enriched.columns:
                        data_tools_hit += 1
                        result_text = enriched.to_string(index=False)
                    else:
                        data_tools_miss += 1
                        result_text = (
                            "No data returned. This tool found no results for the given query. "
                            "Try a different tool or a broader/different product name."
                        )

                    tool_results_content.append({
                        "type":        "tool_result",
                        "tool_use_id": block.id,
                        "content":     result_text,
                    })

            loop_messages.append({"role": "assistant", "content": response.content})
            loop_messages.append({"role": "user",      "content": tool_results_content})
        else:
            break

    # ── No tools called ───────────────────────────────────────────────────────
    if not selected_tools:
        msg = "I couldn't match that to the ERP data. " + _HELP_TEXT
        yield base + [{"role": "assistant", "content": msg}], pd.DataFrame(), "", None
        return

    # ── Graph resolution ──────────────────────────────────────────────────────
    important_products = list(dict.fromkeys(important_products))
    if focus_products:
        specific = build_forecast_graph(list(dict.fromkeys(focus_products)))
        if specific:
            final_graph = specific
    if final_graph is None and important_products:
        final_graph = build_forecast_graph(important_products[:3])

    # ── RAG ───────────────────────────────────────────────────────────────────
    rag_context = rag_search(question, important_products)
    has_rag     = rag_context not in ("No RAG knowledge base found.", "No relevant product knowledge found.")

    # ── Build OpenAI prompt ───────────────────────────────────────────────────
    truncated_data = _truncate_to_tokens(all_tables_text, max_tokens=3000)
    rag_snippet    = rag_context[:600] if has_rag else ""
    data_quality   = (
        "high"    if data_tools_hit >= 1 and data_tools_miss == 0 else
        "medium"  if data_tools_hit >= 1 else
        "low"
    )
    summary_prompt = (
        f"Question: {question}\n\n"
        f"Data quality: {data_quality} ({data_tools_hit} tools returned data, {data_tools_miss} returned empty)\n\n"
        f"ERP Data:\n{truncated_data}"
        + (f"\n\nProduct Notes:\n{rag_snippet}" if rag_snippet else "")
        + "\n\nWrite a concise executive summary."
    )
    openai_messages = [
        {"role": "system", "content": (
            "You are an ERP executive assistant. Answer in this exact format:\n\n"
            "**Summary**\n"
            "[2-3 sentences. Always name specific products, distributors, or values from the data — never say 'a product' or 'a distributor' when you have the actual name.]\n\n"
            "**Risks**\n"
            "- [risk 1 — include specific names/numbers where available]\n"
            "- [risk 2]\n\n"
            "**Actions**\n"
            "- [action 1 — include specific names/numbers where available]\n"
            "- [action 2]\n\n"
            "**Confidence**: [High / Medium / Low]\n"
            "Set it from the Data quality line: high → High, medium → Medium, low → Low. "
            "High = every tool called returned data. Medium = some tools returned empty. "
            "Low = tools returned empty or minimal data.\n\n"
            "Total under 160 words. ERP: Quantity=units sold, Value=revenue in Indian Rupees, Balance=stock.\n"
            "All money is INR — write it as ₹ (e.g. ₹3,73,227 or ₹3.7 lakh). Never use $ or USD.\n"
            "Columns ending _L are already in ₹ lakh (130.1 → ₹130.1 lakh = ₹1.30 crore); _k = ₹ thousand.\n"
            "If figures come from the FY2018-19 pilot tools, say so; full-history tools cover FY2017-18 to date."
        )}
    ]
    for msg in (history or [])[-2:]:
        if isinstance(msg, dict) and msg.get("content"):
            openai_messages.append({"role": msg["role"], "content": str(msg["content"])[:300]})
    openai_messages.append({"role": "user", "content": summary_prompt})

    display_table = _pick_display_table(question, tool_tables, focus_products)

    # ── Cost calculation ──────────────────────────────────────────────────────
    claude_total  = claude_input_total + claude_output_total
    regular_input = max(0, claude_input_total - cache_creation_total - cache_read_total)
    claude_cost   = (
        regular_input        * CLAUDE_INPUT_PRICE
        + cache_creation_total * CLAUDE_CACHE_WRITE_PRICE
        + cache_read_total     * CLAUDE_CACHE_READ_PRICE
        + claude_output_total  * CLAUDE_OUTPUT_PRICE
    )
    cache_status = (
        f"CACHE HIT ({cache_read_total})"       if cache_read_total   > 0 else
        f"CACHE WRITE ({cache_creation_total})" if cache_creation_total > 0 else
        "no cache"
    )

    # ── Stream OpenAI response ────────────────────────────────────────────────
    try:
        stream = _with_retry(
            lambda: openai_client.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=250,
                messages=openai_messages,
                stream=True,
                stream_options={"include_usage": True},
            ),
            label="OpenAI",
        )

        partial   = ""
        oai_usage = None

        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                partial += chunk.choices[0].delta.content
                yield base + [{"role": "assistant", "content": partial}], display_table, "", final_graph
            if getattr(chunk, "usage", None):
                oai_usage = chunk.usage

        oai_in_tok    = oai_usage.prompt_tokens     if oai_usage else 0
        oai_out_tok   = oai_usage.completion_tokens if oai_usage else 0
        oai_total_tok = oai_in_tok + oai_out_tok
        oai_cost      = calculate_cost(oai_in_tok, oai_out_tok, OPENAI_INPUT_PRICE, OPENAI_OUTPUT_PRICE)
        final_answer  = partial

    except Exception as e:
        print(f"[OpenAI] API error: {e}")
        oai_in_tok = oai_out_tok = oai_total_tok = 0
        oai_cost     = 0.0
        final_answer = f"Summary unavailable ({type(e).__name__}: {e}). Raw data:\n{_truncate_to_tokens(all_tables_text, max_tokens=500)}"

    # ── Feedback loop — critic checks answer quality ──────────────────────────
    def _critic_check(answer: str, data_quality: str) -> tuple[bool, str]:
        """Claude Haiku critic — checks format AND facts against the tool data. Returns (passed, feedback)."""
        critic_prompt = (
            f"You are a strict ERP report critic.\n\nQuestion: {question}\n\n"
            f"Tool data the answer must be based on:\n{_truncate_to_tokens(all_tables_text, max_tokens=2500)}\n\n"
            f"Answer to evaluate:\n\n{answer}\n\n"
            f"Data quality was: {data_quality}\n\n"
            "Check ALL of these:\n"
            "0. FACTS: every number, name, ranking and financial-year label matches the tool data exactly "
            "(e.g. 'owes the most' must be the rank-1 / largest row; FY labels must not be shifted). "
            "List each wrong fact with the correct value.\n"
            "1. Has all 4 sections: **Summary**, **Risks**, **Actions**, **Confidence**?\n"
            "2. Names specific products/distributors (not 'a product' or 'a distributor')?\n"
            "3. Confidence level matches data quality (High only if data_quality=high)?\n"
            "4. Under 160 words?\n"
            "5. All money written in ₹ (Indian Rupees) — FAIL if any $ or USD amount appears?\n\n"
            "Reply in exactly this format:\n"
            "PASS or FAIL\n"
            "ISSUES: [list issues if FAIL, else 'none']"
        )
        try:
            resp = claude_client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=300,
                messages=[{"role": "user", "content": critic_prompt}],
            )
            text   = resp.content[0].text.strip()
            passed = text.startswith("PASS")
            issues = text.split("ISSUES:")[-1].strip() if "ISSUES:" in text else ""
            print(f"[Critic] {'PASS' if passed else 'FAIL'} — {issues[:80]}")
            return passed, issues
        except Exception as e:
            print(f"[Critic] failed: {e} — skipping")
            return True, ""

    critic_passed, critic_issues = _critic_check(final_answer, data_quality)

    if not critic_passed and critic_issues:
        yield base + [{"role": "assistant", "content": "Improving answer quality..."}], display_table, "", final_graph
        retry_messages = openai_messages + [
            {"role": "assistant", "content": final_answer},
            {"role": "user",      "content": f"Your answer failed quality check. Issues: {critic_issues}\nRewrite fixing these issues. Keep same format."},
        ]
        try:
            retry_resp = _with_retry(
                lambda: openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    max_tokens=300,
                    messages=retry_messages,
                ),
                label="OpenAI-retry",
            )
            final_answer  = retry_resp.choices[0].message.content
            oai_in_tok   += retry_resp.usage.prompt_tokens
            oai_out_tok  += retry_resp.usage.completion_tokens
            oai_total_tok = oai_in_tok + oai_out_tok
            oai_cost      = calculate_cost(oai_in_tok, oai_out_tok, OPENAI_INPUT_PRICE, OPENAI_OUTPUT_PRICE)
            print(f"[Critic] Answer improved.")
        except Exception as e:
            print(f"[OpenAI-retry] failed: {e}")

    # All ERP values are INR — catch any "$1,234" the LLM still slips in
    final_answer = re.sub(r"(?:US)?\$\s?(?=\d)|\bUSD\s?(?=\d)", "₹", final_answer or "")

    _log_query(
        question     = question,
        tools        = selected_tools,
        total_cost   = oai_cost + claude_cost,
        elapsed      = time.time() - _query_start,
        critic_passed= critic_passed,
        iterations   = iterations,
        data_quality = data_quality,
    )

    print(f"[Agent] iter={iterations} claude={claude_total}tok ${claude_cost:.6f} [{cache_status}] | openai={oai_total_tok}tok ${oai_cost:.6f}")

    critic_status = "PASS" if critic_passed else "FAIL→IMPROVED"
    debug_info = (
        f"Tools: {selected_tools} | Agent iterations: {iterations} | Critic: {critic_status}\n"
        f"Claude (agent): {claude_total} tok (${claude_cost:.6f}) [{cache_status}]  |  "
        f"OpenAI (summary): {oai_total_tok} tok (${oai_cost:.6f})  |  "
        f"Total: ${oai_cost + claude_cost:.6f}"
    )

    yield (
        base + [{"role": "assistant", "content": final_answer}],
        display_table, debug_info, final_graph,
    )
