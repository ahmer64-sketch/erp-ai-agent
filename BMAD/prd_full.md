# Product Requirements Document (PRD)
**Product:** Reman ERP Intelligence Agent
**Version:** 1.0
**Date:** May 28, 2026
**PM:** Ahmer Rizvi
**Status:** Phase 1 In Progress

---

## 1. Executive Summary
Reman ERP Intelligence Agent is a 5-LLM agentic AI system that transforms raw ERP data into instant, validated operational intelligence for supply chain teams. Operators ask questions in plain English — *"Which products will stock out this week?"* — and receive structured, critic-validated answers in under 5 seconds at under $0.01/query. The product also fires autonomous daily alerts via email and WhatsApp every morning at 8:00am. Built in 20 days by Ahmer Rizvi, the MVP is live on 1-year sample data. Phase 1 is in progress pending the 7-year Marg ERP dataset. Definition of success: operations managers stop opening Excel in the morning.

---

## 2. Problem Statement (JTBD)

**When** I start my workday as an operations head at a nutraceutical distribution company,
**I want to** instantly know which products need attention today,
**So I can** make reorder and procurement decisions in minutes — not hours.

**Problem scope:**
- Mid-sized Indian distributors (50–500 employees) collect years of ERP data but cannot extract insights without a data analyst
- Operations teams spend 2–3 hours daily on manual Excel reports
- Stockouts and dead stock are discovered reactively — after financial damage is done
- Marg ERP and Tally have no conversational interface — data is exported to Excel and analyzed manually
- Hiring a data analyst costs ₹6–12L/year — out of reach for most SME distributors

**Why now:**
- LLM APIs now cost under $0.01/query — making AI accessible at SME scale
- Marg ERP export format is standardized — one integration covers thousands of potential clients
- Ahmer's 7-year operations background means domain-specific tools can be built that generic BI tools can't replicate

---

## 3. Goals & Success Metrics

**North Star Metric:** Validated queries answered correctly per day (quality × volume)

| Metric | Target | Current |
|---|---|---|
| Query response time | < 5 seconds | ~3 seconds ✅ |
| Cost per query | < $0.01 | ~$0.008 ✅ |
| Eval harness pass rate | ≥ 85% | Measured on 20 Qs |
| Daily alert uptime | 100% | ✅ Cron live |
| Critic pass rate | > 90% | Monitored daily |
| Inventory turnover improvement | 4x → 6x | ✅ Validated on sample data |

**Guardrail metrics (must NOT break):**
- Cost per query must not exceed $0.01
- Critic fail rate must stay < 10%
- Response time must stay < 8 seconds

**Business goals (Phase 5):**
- First paying client by Q4 2026
- MRR of $5,000+ within 12 months of Phase 5 launch
- Gross margin > 90% (current unit economics support this)

---

## 4. User Personas

**Persona 1 — Ahmer (MD / Builder)**
- Role: Managing Director, strategic oversight
- Age: 35 | Industry: Nutraceutical distribution | Tech level: High
- Goals: Instant operational summary, proof-of-concept for investors, exception-based management
- Frustrations: "I have 7 years of data and I still make decisions based on gut feel because pulling the numbers takes too long"
- Quote: *"I want to know what's on fire before 9am without opening a single spreadsheet."*

**Persona 2 — Operations Manager**
- Role: Day-to-day supply chain execution
- Age: 30–45 | Tech level: Medium
- Goals: Daily reorder decisions, stockout prevention, distributor accountability
- Frustrations: Manual inventory checks, reactive replenishment, no early warning system
- Quote: *"By the time I know we're out of stock, the orders are already delayed."*

**Persona 3 — Procurement Head**
- Role: Purchasing, supplier management
- Age: 35–50 | Tech level: Low-Medium
- Goals: Optimal reorder quantities, lead time visibility, supplier performance
- Frustrations: Reordering by instinct, over-purchasing slow SKUs, under-purchasing fast ones

---

## 5. User Stories (MoSCoW)

### Must Have (MVP — Done ✅)
- As an ops manager, I want to ask inventory questions in plain English so I can get answers without Excel
- As an MD, I want a daily 8:00am alert with stockout risks so I can act before the workday starts
- As a user, I want every answer validated by a second AI before I see it so I can trust the output
- As a QA engineer, I want a 20-question eval harness so I can measure quality after every change
- As an ops team, I want ABC classification of all SKUs so I can prioritize attention on A-class products

### Should Have (Phase 1 — In Progress 🔄)
- As a system, I want all 8 tools querying Databricks SQL so data is always current
- As an MD, I want the agent upgraded to Claude Sonnet so answer quality improves on complex queries
- As a QA engineer, I want the eval harness re-run on 7-year data so quality is validated on production data

### Could Have (Phase 2 — Planned ⏳)
- As a finance manager, I want customer ledger and invoice aging tools so I can manage collections
- As an MD, I want payment overdue alerts in my daily brief so collections is part of my morning view
- As a system, I want a CrewAI collections crew so complex payment queries are handled by specialist agents

### Won't Have (This Version)
- Multi-tenant architecture (Phase 5)
- Next.js frontend (Phase 5)
- Stripe billing (Phase 5)
- Autonomous sub-goal planning (Phase 4)

---

## 6. UX Requirements

**Design principles:**
1. Plain English in, plain English out — no technical jargon in responses
2. Every answer must include specific product names and numbers — no vague summaries
3. Confidence level always stated — user knows how much to trust the answer
4. Under 160 words per answer — concise, scannable, actionable

**Key flows:**
- **Query flow:** User types → Groq routes → tools execute → OpenAI writes → Critic validates → answer displayed
- **Alert flow:** Cron fires at 08:00 → data pulled → stockout + reorder + drift analyzed → HTML email + WhatsApp sent
- **Error flow:** If critic fails twice → answer flagged as LOW CONFIDENCE, still delivered with caveat

**Accessibility:** Gradio default (web-based, keyboard navigable)

**Current UI:** Gradio chat interface
**Future UI (Phase 5):** Next.js enterprise dashboard

---

## 7. Technical Requirements

| Requirement | Detail |
|---|---|
| LLM stack | Groq Llama (router), Claude Sonnet (orchestrator + critic), OpenAI GPT-4o (writer), Cohere (reranker), Gemini Flash (supplemental) |
| Data source | Excel/CSV (Phase MVP), Databricks SQL (Phase 1+) |
| RAG | OpenAI embeddings, 13 docs (grows with full dataset) |
| UI | Gradio (replace with Next.js at Phase 5) |
| Alerts | Gmail SMTP (HTML) + Twilio WhatsApp |
| Scheduling | Unix cron (08:00 daily) |
| Orchestration | Custom Python agentic loop (Phase MVP), CrewAI (Phase 2 collections) |
| Performance | < 5s response, < $0.01/query, > 90% critic pass rate |
| Security | API keys in `.env`, not committed to Git |
| Hosting | Local machine (Phase MVP), AWS/GCP (Phase 5) |

---

## 8. Constraints & Risks

**Constraints:**
- 7-year dataset not yet received — Phase 1 blocked
- Single developer (Ahmer) — no parallel workstreams
- Budget: bootstrapped — must stay under $0.01/query

**Risks:**

| Risk | Impact | Mitigation |
|---|---|---|
| Sample data doesn't reflect real patterns | High | Eval harness re-run when real data arrives |
| LLM hallucination on financial data | High | Critic LLM validates every answer |
| Model drift over time | Medium | Daily drift_check.py monitors 4 signals |
| CrewAI latency > 5s threshold | Medium | Spike test before Phase 2 build |
| API cost spike | Medium | Cost tracked per query, guardrail alert built |
| Marg ERP export format change | Low | ETL pipeline in `erp_data.py` is modular |

**Assumptions:**
- 7-year dataset arrives in same format as 1-year sample
- First client is willing to export Marg ERP data as Excel/CSV
- Groq remains the fastest/cheapest routing option

---

## 9. Timeline & Milestones

| Milestone | Target | Status |
|---|---|---|
| MVP — 5 LLMs, 8 tools, critic, drift, eval, alerts | May 2026 | ✅ Done |
| Phase 1 — 7-year dataset + Databricks + eval re-run + model upgrade | TBD | 🔄 Blocked on data |
| Phase 2 — Payment & Collections (4 tools + CrewAI crew) | After Phase 1 | ⏳ Planned |
| Phase 3 — Session memory + monitoring dashboard | After Phase 2 | ⏳ Deferred |
| Phase 4 — Weekly summaries + proactive alerts | After Phase 3 | ⏳ Deferred |
| Phase 5 — Multi-tenant SaaS (Auth + Next.js + Stripe + AWS) | Long-term (~2 months after first client) | ⏳ Long-term |

---

## 10. Open Questions

| Question | Owner | Target Resolution |
|---|---|---|
| When does 7-year Marg ERP dataset arrive? | Ahmer | ASAP — Phase 1 blocked |
| Does CrewAI add latency > 5s on collections queries? | Engineering | Spike test before Phase 2 |
| Auto-block vs notify-first for credit block tool? | Ahmer | Decided: notify-first (see alignment doc) |
| Which company is the first paying client? | Sales | Target: after Phase 1 validation |
| Next.js vs Streamlit for Phase 5 frontend? | Engineering | Evaluate at Phase 4 |
