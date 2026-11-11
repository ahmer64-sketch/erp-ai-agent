# 02 — Product Requirements Document
**BMAD Role: Product Manager**
**Date: May 28, 2026 | Version: 1.1**

---

## Executive Summary
Reman ERP Intelligence Agent is a 5-LLM agentic AI system that lets supply chain operators query their ERP data in plain English and receive validated, structured answers — with autonomous daily alerts and built-in LLMOps monitoring. Phase 1 is shipped. This PRD covers Phase 1 (as-built) and Phase 2 (Payment & Collections).

---

## Problem Statement (JTBD)

> *When I start my workday as an operations manager, I want to instantly know which products need attention today, so I can make reorder and procurement decisions without spending 2 hours in spreadsheets.*

---

## Goals & Success Metrics

| Metric | Target | Current |
|---|---|---|
| Query response time | < 5 seconds | ~3 seconds ✅ |
| Cost per query | < $0.01 | ~$0.008 ✅ |
| Eval harness pass rate | ≥ 85% | Measured on 20 Qs |
| Daily alert uptime | 100% | Cron + Gmail + WhatsApp ✅ |
| Critic pass rate | > 90% | Monitored via drift_check ✅ |

**North Star Metric:** Queries answered correctly per day (quality × volume)

**Guardrail Metrics:** Cost per query must not exceed $0.01 | Critic fail rate must stay < 10%

---

## User Personas

**Primary: Ahmer (MD / Builder)**
- Needs: Strategic summary, exception alerts, proof-of-concept for investors
- Tech level: High
- Quote: "I want to know what's on fire before 9am without opening a single spreadsheet."

**Secondary: Operations Manager**
- Needs: Daily reorder decisions, stockout risks
- Tech level: Medium
- Quote: "Tell me what I need to order today and how much."

---

## Phase 1 — Feature Set (Shipped ✅)

### Must Have
- [x] Natural language query interface (Gradio UI)
- [x] 5-LLM orchestration (Groq router → Claude → OpenAI → Cohere reranker → Gemini Flash)
- [x] 8 analytical tools (inventory status, KPI dashboard, safety stock, seasonality, customer analysis, procurement, ABC classification, demand forecast)
- [x] RAG knowledge base (13 embeddings from product catalog + SOPs)
- [x] Critic LLM — validates answer quality before delivery
- [x] Daily autonomous alerts — email (Gmail SMTP) + WhatsApp (Twilio)
- [x] Drift detection — monitors critic fail rate, cost, latency, tool miss rate
- [x] Eval harness — 20 golden questions, 3 check types (tool, data, format)

### Should Have
- [x] ABC classification (A:18, B:13, C:16 products)
- [x] Inventory turnover from 4x → 6x tracking
- [x] Error logging (`error_log.md`)

### Deferred to Phase 3
- [ ] Long-term conversation memory (`session_store.py` built, not wired)
- [ ] Real-time Databricks SQL connection
- [ ] Monitoring dashboard tab in Gradio

---

## Phase 2 — Payment & Collections (Next Sprint)

### Must Have
- [ ] `ledger_tool` — full ledger per customer (debit/credit/balance)
- [ ] `aging_tool` — invoice buckets: 0-30 / 31-60 / 61-90 / 90+ days
- [ ] `payment_behavior_tool` — identify chronic late payers
- [ ] `credit_block_tool` — auto-block buyers with 90-day overdue invoices
- [ ] CrewAI crew: Manager → Collections Agent → Credit Risk Agent → Finance Agent
- [ ] Wire payment tools into main agent router

### Should Have
- [ ] Payment overdue alerts in daily email/WhatsApp
- [ ] Expand eval harness to 40 questions (cover payment tools)

### Won't Have (Phase 2)
- Multi-tenant architecture
- Stripe billing
- Next.js frontend

---

## Technical Requirements

| Requirement | Detail |
|---|---|
| LLM stack | Groq (Llama), Claude Sonnet, OpenAI GPT-4o, Cohere, Gemini Flash |
| Data source | Excel (Phase 1), Databricks SQL (Phase 3+) |
| UI | Gradio (replace with Next.js in Phase 5) |
| Alerts | Gmail SMTP + Twilio WhatsApp |
| Orchestration | Custom Python (Phase 1), CrewAI (Phase 2 collections) |
| Hosting | Local (Phase 1), AWS/GCP (Phase 5) |
| Cost target | < $0.01/query |

---

## Open Questions

| Question | Owner | Target |
|---|---|---|
| When does 7-year Marg ERP dataset arrive? | Ahmer | TBD |
| Does CrewAI add latency beyond acceptable threshold? | Engineering | Before Phase 2 build |
| Which customer first for multi-tenant? | Sales | Phase 5 planning |
