# Stories — MVP (Shipped ✅) + Phase 1 (In Progress 🔄)
**BMAD Role: Scrum Master**

> **Note:** MVP = 1-year sample data, all tools working locally.
> Phase 1 = Real Data Migration (7-year Marg ERP dataset → Databricks). Currently blocked on dataset delivery.

---

## STORY-001 | Natural Language Query Interface
**As an** operations manager,
**I want to** ask inventory questions in plain English,
**So that** I can get answers without opening spreadsheets.

**Acceptance Criteria:**
- [x] Gradio UI accepts free-text queries
- [x] Response returned in < 5 seconds
- [x] Answer includes specific product names and numbers

**Status: DONE** — `app.py` + `erp_agent.py`

---

## STORY-002 | 5-LLM Orchestration Pipeline
**As a** system,
**I want to** route queries through the optimal LLM for each task,
**So that** speed, cost, and quality are all optimized.

**Acceptance Criteria:**
- [x] Groq routes intent in < 1 second
- [x] Claude orchestrates tool selection
- [x] OpenAI writes the final structured answer
- [x] Cohere reranks RAG results
- [x] Gemini Flash available as supplemental

**Status: DONE** — `erp_agent.py`

---

## STORY-003 | 8 Analytical Tools
**As an** analyst,
**I want to** query inventory, KPIs, safety stock, seasonality, customers, procurement, ABC, and forecasts,
**So that** every supply chain question has a dedicated data tool.

**Acceptance Criteria:**
- [x] All 6 local tools return correct data on eval harness
- [x] ABC classification: 47 products (A:18, B:13, C:16)
- [x] Inventory turnover tracked (4x → 6x improvement)

**Status: DONE** — `erp_tools.py`

---

## STORY-004 | Critic LLM Quality Gate
**As a** user,
**I want** every answer validated before I see it,
**So that** I can trust the output without second-guessing it.

**Acceptance Criteria:**
- [x] Critic checks: 4 sections present, specific products named, confidence matches data, < 160 words
- [x] FAIL triggers one retry with critic feedback
- [x] Debug line shows `Critic: PASS` or `Critic: FAIL→IMPROVED`
- [x] Cost: < $0.0002 extra per query

**Status: DONE** — `erp_agent.py`

---

## STORY-005 | Autonomous Daily Alerts
**As a** managing director,
**I want** a daily briefing at 8:00am with stockout risks and reorder alerts,
**So that** I can start the day with full operational awareness.

**Acceptance Criteria:**
- [x] Cron fires at 08:00 daily
- [x] Email: HTML format with stockout + reorder + agent health sections
- [x] WhatsApp: text summary via Twilio sandbox
- [x] Runs without any manual input

**Status: DONE** — `daily_alert.py`

---

## STORY-006 | LLMOps Drift Detection
**As a** product owner,
**I want** the agent to monitor its own health daily,
**So that** degradation is caught before users notice.

**Acceptance Criteria:**
- [x] 4 signals monitored: critic fail rate, cost spike, slow responses, tool miss rate
- [x] Drift report included in daily alert email
- [x] Green "Agent Health OK" or orange/red "DRIFT DETECTED" section

**Status: DONE** — `drift_check.py`

---

## STORY-007 | Evaluation Harness
**As a** QA engineer,
**I want** a repeatable test suite of 20 golden questions,
**So that** I can measure quality before and after every major change.

**Acceptance Criteria:**
- [x] 20 questions across 8 tools
- [x] 3 check types: tool called, data correct, format correct
- [x] Re-runnable after 7-year dataset migration

**Status: DONE** — `eval_harness.py`

---

## PHASE 1 — Real Data Migration (🔄 In Progress)

## STORY-P1-001 | Load 7-Year Dataset into Databricks
**As a** system,
**I want** the full 7-year Marg ERP dataset loaded into Databricks SQL,
**So that** all tools run on real production data.

**Acceptance Criteria:**
- [ ] All historical sales, inventory, procurement data loaded
- [ ] Schema matches current `cleaned_erp_data.xlsx` structure
- [ ] `erp_data.py` ETL pipeline updated to query Databricks
- [ ] No data loss validated vs source

**Blocked by:** 7-year dataset delivery from Marg ERP

---

## STORY-P1-002 | Migrate 8 Tools from Excel → Databricks SQL
**As a** developer,
**I want** all 8 tools querying Databricks instead of local Excel,
**So that** data is always current and scalable.

**Acceptance Criteria:**
- [ ] All 8 tools in `erp_tools.py` use Databricks SQL connector
- [ ] Response time stays < 5 seconds
- [ ] Local Excel fallback retained for dev/testing

---

## STORY-P1-003 | Rebuild Knowledge Base Embeddings
**As a** system,
**I want** the RAG knowledge base rebuilt with the full product catalog,
**So that** semantic search covers all 7 years of product history.

**Acceptance Criteria:**
- [ ] All product SKUs from full dataset embedded
- [ ] Embedding count grows from 13 → full catalog
- [ ] RAG retrieval accuracy re-validated

---

## STORY-P1-004 | Re-run Eval Harness & Fix Failures
**As a** QA engineer,
**I want** the full 20-question eval harness re-run on real data,
**So that** quality is validated end-to-end on production data.

**Acceptance Criteria:**
- [ ] All 20 questions re-run on Databricks-connected tools
- [ ] Pass rate ≥ 85%
- [ ] All failures triaged and fixed

---

## STORY-P1-005 | Upgrade Claude Model
**As a** system,
**I want** to upgrade from `claude-haiku-4-5` → `claude-sonnet-4-6`,
**So that** orchestration quality improves with real data complexity.

**Acceptance Criteria:**
- [ ] Model swapped in `config.py`
- [ ] Eval harness re-run post-upgrade
- [ ] Cost per query still < $0.01
