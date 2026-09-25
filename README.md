# Payment Failure Remediation Agent

An agentic system that investigates a failed payment, diagnoses the root cause (with LLM help), proposes a remediation drawn from a runbook knowledge base (RAG), checks it against policy/risk rules, waits for human approval, executes it, and verifies the payment issue is actually resolved — looping back to reinvestigate if it isn't, and feeding new learnings back into the runbook when it is.

Built as a personal project on entirely synthetic data (no real bank/payment data) — see [`docs/DESIGN.md`](docs/DESIGN.md) for the full solution design, workflow diagram, sprint plan, tech stack, and testing strategy.

## Status

Sprints 1-4 are complete — see `docs/DESIGN.md` Section 3 for the sprint plan. A fake `payment.failed` event runs end-to-end through Temporal to `CASE_CLOSED` (Sprint 1); evidence collection is real, driven by a scripted Payment Gateway Simulator with a decline-code taxonomy and proprietary customer-context fields (Sprint 2); diagnosis is a real Claude-driven activity that classifies each case and cites its evidence (Sprint 3); runbook retrieval is real RAG: local embeddings + pgvector propose the top 3 candidate entries and a Claude judge picks the one that applies, or none, in which case the case waits for a human to author a runbook entry (Sprint 4 — an offline eval showed a similarity threshold cannot make that call; details in `docs/DESIGN.md`).

Still stubs: the policy/risk engine (always approves), remediation proposals, the action catalog (no-op actions), verification, and resolution analysis. **Next: Sprint 5** — a deterministic policy engine (fraud hard block on the raw gateway decline code, action risk tiers, a $100 auto-approve limit, first-attempt-only autonomy) plus skipping the approval gate for low-risk cases.

## Quickstart

```bash
docker compose up
```

This brings up Temporal (workflow engine), Postgres (+ pgvector), and the observability stack (Jaeger, Prometheus, Grafana). See `docs/DESIGN.md` for architecture details.

## Project layout

```
src/
  payment_failure_remediation_agent/
    simulator/            # synthetic Payment Gateway Simulator — stands in for a real processor
    workflows/             # Temporal workflows (case lifecycle, runbook review)
    activities/
      evidence_connectors/ # pluggable evidence sources (gateway, observability, customer, case history)
    policy/                 # deterministic policy/risk rules engine
    actions/                # remediation action adapters (retry, refund, config change, ...)
    runbook/                # runbook corpus + the Claude judge that picks a matching entry
db/
  migrations/             # Postgres schema
scripts/                  # DB seeding, end-to-end verify script, offline retrieval evals
tests/                    # unit tests, Temporal workflow tests, integration golden sets
docs/
  DESIGN.md               # full solution design
```
