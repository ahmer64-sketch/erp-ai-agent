# 01 — Project Brief
**BMAD Role: Analyst**
**Date: May 28, 2026 | Project: Reman ERP Intelligence Agent**

---

## 1. Problem Statement

Reman Lifecare Pvt Ltd — a nutraceutical distributor operating across 6 states in India — manages inventory, procurement, and distributor relationships manually. The supply chain team lacks real-time visibility into:
- Which products are at risk of stockout
- Which SKUs are dead or slow-moving
- What reorder quantities are optimal
- How distributor performance is trending

The result: reactive decisions, expired stock, missed revenue, and high manual reporting effort for management.

---

## 2. Opportunity

Plain-English AI interfaces can replace complex ERP dashboards. A single query like *"Which products will stock out in the next 2 weeks?"* can trigger multi-step data analysis that previously took hours — in under 3 seconds, at under $0.01.

---

## 3. Target Users

| User | Role | Primary Need |
|---|---|---|
| Managing Director (Ahmer) | Strategic oversight | Daily operational summary, exceptions |
| Operations Manager | Day-to-day execution | Stockout alerts, reorder decisions |
| Procurement Team | Purchasing | Reorder quantities, lead times |
| Finance | Cost control | Inventory value, dead stock exposure |

---

## 4. Scope

**In scope (Phase 1 — shipped):**
- Natural language query interface over ERP data
- 8 analytical tools (inventory, KPI, safety stock, seasonality, customer, procurement, critic, drift)
- 5-LLM orchestration pipeline
- Autonomous daily alerts (email + WhatsApp)
- LLMOps drift detection
- Evaluation harness (20 golden questions)

**Out of scope (Phase 1):**
- Payment and collections tracking
- Long-term conversation memory
- Multi-tenant architecture
- Real-time database (uses Excel — 7-year dataset pending)

---

## 5. Constraints

- Budget: minimal — must run under $0.01/query
- Data: 1-year sample dataset (7-year dataset incoming from Marg ERP)
- Team: 1 builder (Ahmer Rizvi)
- Timeline: Phase 1 built in 20 days

---

## 6. Key Risks

| Risk | Mitigation |
|---|---|
| Sample data doesn't reflect real patterns | Eval harness re-run when 7-year data arrives |
| LLM hallucination on financial data | Critic LLM validates every answer before delivery |
| Model drift over time | Daily drift check monitors critic fail rate, cost, latency |
| Data quality from Marg ERP export | Cleaned via `erp_data.py` pipeline |

---

## 7. Success Definition

- Analyst can answer any inventory or KPI question in plain English in < 5 seconds
- Daily alerts fire at 8:00am with zero manual input
- Eval harness pass rate ≥ 85% on 20 golden questions
- Cost per query < $0.01
- Drift detection catches model degradation before users notice
