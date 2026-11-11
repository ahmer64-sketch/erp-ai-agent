# 04 — Alignment Checklist
**BMAD Role: Product Owner**
**Date: May 28, 2026**

---

## Purpose
Resolve conflicts between Brief, PRD, and Architecture before development begins on Phase 2.

---

## Phase 1 — Retrospective Alignment ✅

| Check | Status | Notes |
|---|---|---|
| Brief problem matches PRD JTBD | ✅ | Consistent — operational visibility gap |
| PRD features match architecture tools | ✅ | 8 tools cover all Must Have features |
| Cost guardrail ($0.01) achievable with 5-LLM stack | ✅ | Confirmed at ~$0.008/query |
| Eval harness covers PRD success metrics | ✅ | 20 questions × 3 checks |
| Daily alert covers all PRD alert requirements | ✅ | Email + WhatsApp + drift section |
| Critic LLM wired into main agent loop | ✅ | PASS/FAIL→IMPROVED confirmed |
| Session memory deferred consistently across docs | ✅ | Deferred in Brief, PRD, and Architecture |

**Phase 1 Verdict: Fully aligned — no conflicts.**

---

## Phase 2 — Pre-Build Alignment

| Check | Status | Notes |
|---|---|---|
| CrewAI latency acceptable (< 5s target)? | ⚠️ OPEN | Must spike test before full build |
| Payment data format confirmed from Marg ERP? | ⚠️ OPEN | Need to confirm ledger export format |
| Collections crew fits existing router architecture? | ✅ | New route added — no conflict |
| Phase 2 eval questions drafted (target: 40 total)? | ❌ TODO | Add 20 payment questions to harness |
| Credit block logic has approval workflow? | ⚠️ OPEN | Auto-block vs notify-first needs decision |
| WhatsApp alert for payment overdue scoped? | ✅ | Consistent across PRD and Architecture |

---

## Open Decisions — Need Resolution Before Phase 2 Build

### 1. CrewAI Latency Risk
**Issue:** CrewAI sequential process may push response time > 5 seconds for complex collections queries.
**Options:**
- A) Spike test CrewAI with mock data — measure latency
- B) Use direct tool calls instead of CrewAI for Phase 2
- **Recommendation:** Spike test first (1 day). Use direct calls if > 4s.

### 2. Auto-block vs Notify-First
**Issue:** `credit_block_tool` — should it auto-block 90-day overdue buyers or just alert?
**Options:**
- A) Auto-block immediately (aggressive, could damage relationships)
- B) Alert MD first, block on confirmation (safer)
- **Recommendation:** Notify-first with 1-click confirm. Block is irreversible.

### 3. Payment Data Source
**Issue:** No customer ledger file exists yet.
**Action:** Ahmer to export from Marg ERP or create mock ledger for Phase 2 development.

---

## Single Source of Truth

| Artifact | Location | Owner |
|---|---|---|
| Project Brief | `BMAD/01_brief.md` | Analyst |
| PRD | `BMAD/02_prd.md` | PM |
| Architecture | `BMAD/03_architecture.md` | Architect |
| This checklist | `BMAD/04_alignment.md` | Product Owner |
| Stories | `BMAD/stories/` | Scrum Master |
| Code | Root of repo | Developer |
| Quality | `eval_harness.py` | QA |
