# Payment Failure Remediation Agent

An agentic system that investigates a failed payment, diagnoses the root cause (with LLM help), proposes a remediation drawn from a runbook knowledge base (RAG), checks it against policy/risk rules, waits for human approval, executes it, and verifies the payment issue is actually resolved — looping back to reinvestigate if it isn't, and feeding new learnings back into the runbook when it is.

Built as a personal project on entirely synthetic data (no real bank/payment data) — see [`docs/DESIGN.md`](docs/DESIGN.md) for the full solution design, workflow diagram, sprint plan, tech stack, and testing strategy.

## Status

Sprint 1 (Walking Skeleton) is complete — see `docs/DESIGN.md` Section 3 for the sprint plan. A fake `payment.failed` event runs end-to-end through Temporal to `CASE_CLOSED` with every step stubbed. Currently starting Sprint 2 (Payment Gateway Simulator + real evidence collection).

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
