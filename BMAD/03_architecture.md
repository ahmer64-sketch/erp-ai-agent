# 03 — Architecture Document
**BMAD Role: Architect**
**Date: May 28, 2026**

---

## System Overview

```
User Query (Gradio UI)
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│                   ORCHESTRATION LAYER                    │
│                                                         │
│  1. Groq (Llama) ──► Intent & Tool Routing (fast)      │
│  2. Claude Sonnet ──► Orchestrator + Critic LLM        │
│  3. Cohere ──────────► Reranker (RAG results)          │
│  4. OpenAI GPT-4o ──► Answer Writer                    │
│  5. Gemini Flash ───► Supplemental / Fallback          │
└─────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│                     TOOL LAYER (8 tools)                │
│                                                         │
│  inventory_tool       → stockout risk, current stock   │
│  kpi_tool             → turnover, fill rate, COGS      │
│  safety_stock_tool    → reorder points per SKU         │
│  seasonality_tool     → demand patterns, peaks         │
│  customer_tool        → distributor performance        │
│  procurement_tool     → reorder qty, lead times        │
│  abc_tool             → A/B/C classification           │
│  forecast_tool        → demand forecast                │
└─────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│                      DATA LAYER                         │
│                                                         │
│  cleaned_erp_data.xlsx  ← erp_data.py (ETL pipeline)  │
│  knowledge_base/        ← RAG embeddings (13 docs)     │
│  query_log.jsonl        ← every query logged           │
└─────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│                    QUALITY LAYER                        │
│                                                         │
│  Critic LLM (Claude Haiku)                             │
│  ├── Validates: 4 sections, specific products          │
│  ├── Validates: confidence matches data quality        │
│  ├── Validates: under 160 words                        │
│  └── If FAIL → OpenAI retries once with feedback      │
│                                                         │
│  eval_harness.py                                       │
│  └── 20 golden questions × 3 checks = 60 assertions   │
└─────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│                   LLMOPS LAYER                          │
│                                                         │
│  drift_check.py (daily)                                │
│  ├── Critic fail rate (threshold: 10%)                 │
│  ├── Cost spike (threshold: 2x baseline)               │
│  ├── Slow responses (threshold: 8s)                    │
│  └── Tool miss rate (threshold: 15%)                   │
│                                                         │
│  daily_alert.py (cron 08:00 daily)                     │
│  ├── Stockout risk section                             │
│  ├── Reorder now section                               │
│  └── Agent Health / Drift section                      │
│       → Gmail SMTP (HTML email)                        │
│       → Twilio WhatsApp                                │
└─────────────────────────────────────────────────────────┘
```

---

## Phase 2 Architecture Addition — Payment & Collections

```
Existing Agent Router
        │
        ▼ (new route: payment/collections queries)
┌─────────────────────────────────────────────────────────┐
│              CREWAI COLLECTIONS CREW                    │
│                                                         │
│  Manager Agent                                         │
│  ├── Collections Agent  → ledger_tool, aging_tool      │
│  ├── Credit Risk Agent  → payment_behavior_tool        │
│  └── Finance Agent      → credit_block_tool            │
└─────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│              PAYMENT DATA LAYER (new)                   │
│                                                         │
│  customer_ledger.xlsx   → debit/credit/balance         │
│  invoice_aging.xlsx     → 0-30/31-60/61-90/90+ days   │
└─────────────────────────────────────────────────────────┘
```

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| Groq for routing | Fastest inference — sub-second tool selection |
| Claude as orchestrator | Best instruction following + critic reliability |
| OpenAI for answer writing | Most consistent structured output |
| Cohere for reranking | RAG precision improvement |
| Excel data source | Matches current Marg ERP export format |
| Gradio UI | Fastest to ship — replace with Next.js at Phase 5 |
| CrewAI for Phase 2 | Sequential + hierarchical process fits collections workflow |

---

## File Structure

```
Reman-Erp-Agent/
├── app.py                 # Gradio UI entry point
├── erp_agent.py           # Main orchestration loop
├── erp_tools.py           # 8 tool implementations
├── erp_data.py            # ETL — cleans ERP Excel
├── erp_charts.py          # Visualizations
├── config.py              # API keys, model names
├── daily_alert.py         # Autonomous alert system
├── drift_check.py         # LLMOps drift monitoring
├── eval_harness.py        # 20-question eval suite
├── session_store.py       # Session memory (not wired)
├── knowledge_base/        # RAG embeddings
├── Data/                  # Raw + cleaned ERP data
├── query_log.jsonl        # All query logs
├── dev_log.md             # Engineering decisions
├── error_log.md           # Bug/mistake tracker
└── BMAD/                  # This folder — product artifacts
```
