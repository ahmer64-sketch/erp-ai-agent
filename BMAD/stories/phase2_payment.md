# Stories — Phase 2: Payment & Collections (Next Sprint)
**BMAD Role: Scrum Master**
**Status: Ready to build — pending alignment items in 04_alignment.md**

---

## STORY-008 | Customer Ledger Tool
**As an** operations manager,
**I want to** ask "What is distributor X's current balance?",
**So that** I can see full debit/credit history per customer instantly.

**Acceptance Criteria:**
- [ ] `ledger_tool` returns: customer name, total debit, total credit, net balance
- [ ] Covers all active distributors in ERP data
- [ ] Response in < 3 seconds
- [ ] Passes 5 new eval harness questions

**Files to create/modify:** `erp_tools.py` (add `ledger_tool`), `customer_ledger.xlsx`
**Blocked by:** Customer ledger data export from Marg ERP

---

## STORY-009 | Invoice Aging Tool
**As a** finance manager,
**I want to** see which invoices are overdue and by how long,
**So that** I can prioritize collections calls.

**Acceptance Criteria:**
- [ ] `aging_tool` buckets invoices: 0-30 / 31-60 / 61-90 / 90+ days
- [ ] Returns: customer name, invoice number, amount, days overdue, bucket
- [ ] Sorted by oldest first
- [ ] Passes 5 new eval harness questions

**Files to create/modify:** `erp_tools.py` (add `aging_tool`), `invoice_aging.xlsx`

---

## STORY-010 | Payment Behavior Tool
**As a** collections manager,
**I want to** identify chronic late payers,
**So that** I can adjust credit terms proactively.

**Acceptance Criteria:**
- [ ] `payment_behavior_tool` returns: customer, avg days to pay, late payment frequency, risk label (Low/Medium/High)
- [ ] High risk = > 3 instances of 60+ day payments
- [ ] Passes 5 new eval harness questions

**Files to create/modify:** `erp_tools.py` (add `payment_behavior_tool`)

---

## STORY-011 | Credit Block Tool
**As a** managing director,
**I want to** be alerted when a distributor hits 90-day overdue,
**So that** I can authorize a credit block before further exposure.

**Acceptance Criteria:**
- [ ] `credit_block_tool` identifies all customers with any invoice > 90 days
- [ ] Returns: customer, invoice, amount, days overdue, recommended action
- [ ] Notify-first flow: alert MD, block only on explicit confirmation
- [ ] Passes 3 new eval harness questions

**Files to create/modify:** `erp_tools.py` (add `credit_block_tool`)
**Note:** Auto-block rejected — notify-first approved per alignment doc

---

## STORY-012 | CrewAI Collections Crew
**As a** system,
**I want** complex collections queries handled by a specialized multi-agent crew,
**So that** the analysis is thorough and cross-validated.

**Acceptance Criteria:**
- [ ] CrewAI crew: Manager → Collections Agent → Credit Risk Agent → Finance Agent
- [ ] Sequential process for standard queries, hierarchical for complex
- [ ] Crew response time < 5 seconds (validate in spike test first)
- [ ] Crew output routed back through critic LLM before delivery

**Files to create/modify:** New `collections_crew.py`
**Blocked by:** CrewAI latency spike test (see alignment doc)

---

## STORY-013 | Payment Alerts in Daily Brief
**As a** managing director,
**I want** payment overdue alerts included in my 8:00am brief,
**So that** collections is part of my daily operational view.

**Acceptance Criteria:**
- [ ] Daily email adds 4th section: "Payment Alerts"
- [ ] Lists all new 90-day breaches since yesterday
- [ ] WhatsApp message appends payment summary
- [ ] Zero manual input required

**Files to create/modify:** `daily_alert.py`

---

## STORY-014 | Expand Eval Harness to 40 Questions
**As a** QA engineer,
**I want** 20 new payment questions in the eval harness,
**So that** Phase 2 quality is measured as rigorously as Phase 1.

**Acceptance Criteria:**
- [ ] 20 new questions covering all 4 payment tools
- [ ] Same 3-check format: tool called, data correct, format correct
- [ ] Total harness: 40 questions, 120 assertions
- [ ] Pass rate target: ≥ 85%

**Files to create/modify:** `eval_harness.py`

---

## Sprint Order (Recommended)

1. STORY-008 — Ledger Tool (foundation for all others)
2. STORY-009 — Aging Tool
3. STORY-010 — Payment Behavior Tool
4. STORY-011 — Credit Block Tool
5. STORY-014 — Expand Eval Harness
6. STORY-013 — Payment Alerts
7. STORY-012 — CrewAI Crew (last — depends on spike test result)
