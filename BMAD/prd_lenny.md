# Product 1-Pager PRD — Reman ERP Intelligence Agent
**Format: Lenny's 1-Pager PRD**
**Date: May 28, 2026 | PM: Ahmer Rizvi**

---

## Project Title
**Reman ERP Intelligence Agent** — Plain English AI for Supply Chain Operations

---

## Description — What is it?
A 5-LLM agentic AI system that lets supply chain operators query their ERP data in plain English and receive validated, structured answers in under 5 seconds — with autonomous daily alerts and built-in quality monitoring. No dashboards, no data analysts, no spreadsheets.

---

## Problem — What problem is this solving?
Mid-sized nutraceutical and FMCG distributors collect years of ERP data but can't use it. Operations managers spend 2–3 hours daily pulling manual reports, stockouts are discovered after the damage is done, and hiring a data analyst costs more than the insight is worth. The ERP sits full of answers nobody can access.

---

## Why — How do we know this is a real problem and worth solving?
- Ahmer ran Reman Lifecare for 7 years as Managing Director — lived this problem daily across 6 states and 100+ distributors
- Inventory turnover was stuck at 4x annually until manual KPI tracking was introduced — jumping to 6x only after deliberate data discipline
- Marg ERP (used by thousands of Indian distributors) has no conversational interface — users export to Excel and do analysis manually
- No direct competitor offers a plain-English, critic-validated, sub-$0.01 query interface for SME supply chain operators

---

## Success — How do we know if we've solved this problem?
- Eval harness pass rate ≥ 85% on 20 golden questions (tool check + data check + format check)
- Query response time < 5 seconds
- Cost per query < $0.01
- Daily alert fires at 8:00am with zero manual input — 100% uptime
- Critic LLM pass rate > 90% (answers validated before delivery)
- **Ultimate signal:** Operations manager stops opening Excel in the morning

---

## Audience — Who are we building for?
**Primary:** Managing Directors and Operations Heads of nutraceutical/FMCG distribution companies (50–500 employees) running on Marg ERP or Tally — technically non-coder but data-hungry

**Secondary:** Procurement and warehouse teams who need instant answers on reorder quantities, stockout risks, and supplier performance

**Early adopter profile:** MD who already uses WhatsApp for business, has 100+ SKUs, multi-state operations, and is frustrated that their ERP "has all the data but gives none of the answers"

---

## What — Roughly, what does this look like in the product?
- **Chat UI (Gradio):** Type any supply chain question → get a structured answer with specific product names, numbers, and confidence level
- **Daily Alert (Email + WhatsApp):** Every morning at 8:00am — stockout risks, reorder recommendations, agent health status
- **8 Specialized Tools:** Inventory status, KPI dashboard, safety stock, seasonality, customer analysis, procurement, ABC classification, demand forecast
- **Critic Validation:** Every answer checked by a second LLM before the user sees it — shows PASS or FAIL→IMPROVED
- **Drift Monitoring:** Agent monitors its own quality daily — flags degradation before users notice

---

## How — What is the experiment plan?
- **MVP (done):** 1-year sample dataset, all 8 tools working, eval harness passing, daily alerts firing
- **Phase 1 (current):** Load 7-year Marg ERP dataset → migrate tools to Databricks SQL → re-run eval harness → upgrade model to Claude Sonnet
- **Validation approach:** Re-run 20-question eval harness after every major change. Critic pass rate monitored daily. First real client onboarded as a live pilot — measure time-to-first-value and query accuracy on real operations data
- **NOTE (from MOR-530 prof):** For tech products, develop an MVP prototype and put it in front of users to directly observe behavior, usability, and utility — already done with Gradio UI

---

## When — When does it ship and what are the milestones?

| Milestone | Target | Status |
|---|---|---|
| MVP — core agent, 8 tools, alerts, eval | May 2026 | ✅ Done |
| Phase 1 — 7-year dataset + Databricks migration | TBD (awaiting data) | 🔄 In Progress |
| Phase 2 — Payment & Collections module (CrewAI) | After Phase 1 | ⏳ Planned |
| Phase 3 — Long-term memory + monitoring dashboard | After Phase 2 | ⏳ Deferred |
| Phase 4 — Autonomy upgrades (weekly summaries) | After Phase 3 | ⏳ Deferred |
| Phase 5 — Multi-tenant Supply Chain SaaS | Long-term | ⏳ Long-term |

**First paying client target:** After Phase 1 validation on real data
