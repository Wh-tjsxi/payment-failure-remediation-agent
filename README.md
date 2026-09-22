# Payment Failure Remediation Agent

An agentic system that investigates a failed payment, diagnoses the root cause (with LLM help), proposes a remediation drawn from a runbook knowledge base (RAG), checks it against policy/risk rules, waits for human approval, executes it, and verifies the payment issue is actually resolved — looping back to reinvestigate if it isn't, and feeding new learnings back into the runbook when it is.

Built as a personal project on entirely synthetic data (no real bank/payment data) — see [`docs/DESIGN.md`](docs/DESIGN.md) for the full solution design, workflow diagram, sprint plan, tech stack, and testing strategy.

## Status

Sprints 1-3 are complete — see `docs/DESIGN.md` Section 3 for the sprint plan. A fake `payment.failed` event runs end-to-end through Temporal to `CASE_CLOSED` (Sprint 1); evidence collection is real, driven by a scripted Payment Gateway Simulator with a decline-code taxonomy and proprietary customer-context fields (Sprint 2); diagnosis is a real Claude-driven activity that classifies each case and cites its evidence (Sprint 3). Policy, runbook retrieval/RAG, remediation proposals, and the action catalog are still stubs. Currently starting Sprint 4 (Runbook KB + RAG).

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
db/
  migrations/             # Postgres schema
docs/
  DESIGN.md               # full solution design
```
