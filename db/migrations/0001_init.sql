-- Sprint 1 walking-skeleton schema.
--
-- The full data model (docs/DESIGN.md Section 2) names 9 entities: Case,
-- Evidence, Diagnosis, RemediationProposal, Action, Approval, RunbookEntry,
-- Verification, AuditEvent. Sprint 1 only creates the two tables real code
-- actually writes to this sprint -- everything else (evidence, diagnoses,
-- proposals, actions, approvals, runbook entries, verifications) stays as
-- Temporal workflow/activity history until the sprint that gives it a real
-- reason to be queried directly from SQL. See docs/DESIGN.md "Database
-- Schema" section for the human-readable version of this file.
--
-- Applied manually for now (no migration framework yet):
--   psql "$DATABASE_URL" -f db/migrations/0001_init.sql

CREATE TABLE IF NOT EXISTS cases (
    id              TEXT PRIMARY KEY,
    -- Dedupes retried/duplicate payment.failed webhooks so a second
    -- delivery of the same event never starts a second workflow.
    idempotency_key TEXT UNIQUE NOT NULL,
    -- Mirrors payment_failure_remediation_agent.models.CaseStatus values;
    -- kept as free text rather than a Postgres ENUM so new states don't
    -- require a migration, since this sprint's state list will keep growing.
    status          TEXT NOT NULL,
    -- The raw fake payment.failed payload the case was created from.
    event_payload   JSONB NOT NULL,
    -- Temporal workflow id (e.g. "case-<id>") -- lets a human jump straight
    -- from a DB row to the matching run in the Temporal UI.
    workflow_id     TEXT NOT NULL,
    -- REINVESTIGATION loop counter; workflow escalates once this exceeds 3.
    attempt_count   INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_events (
    id          BIGSERIAL PRIMARY KEY,
    case_id     TEXT NOT NULL REFERENCES cases(id),
    from_status TEXT,  -- NULL on the very first "case created" event
    to_status   TEXT NOT NULL,
    -- Free-form context for the transition (e.g. which policy rule fired,
    -- which approval decision was signaled). No PII by design -- see
    -- docs/DESIGN.md's "Evidence stores pointers ... not inline PII" note.
    detail      JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- append_audit_event activities only ever INSERT here, never UPDATE/DELETE --
-- this index just makes "give me a case's full timeline in order" cheap.
CREATE INDEX IF NOT EXISTS audit_events_case_id_created_at_idx
    ON audit_events (case_id, created_at);
