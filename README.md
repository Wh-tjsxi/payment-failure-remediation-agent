# Payment Failure Remediation Agent

An agentic system that investigates a failed payment, diagnoses the root cause (with LLM help), proposes a remediation drawn from a runbook knowledge base (RAG), checks it against policy/risk rules, waits for human approval, executes it, and verifies the payment issue is actually resolved — looping back to reinvestigate if it isn't, and feeding new learnings back into the runbook when it is.

Built as a personal project on entirely synthetic data (no real bank/payment data) — see [`docs/DESIGN.md`](docs/DESIGN.md) for the full solution design, workflow diagram, sprint plan, tech stack, and testing strategy.

## Status

Early scaffolding — see `docs/DESIGN.md` Section 3 for the sprint plan. Currently: Sprint 0 (foundations).

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
