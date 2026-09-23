-- Sprint 4: real runbook retrieval (pgvector similarity search).
--
-- Only the seeded canonical corpus lives here. Human-authored entries
-- from the HUMAN_RUNBOOK_AUTHORING signal stay in-memory only (the
-- workflow's self._runbook_authoring_entry), exactly as in every prior
-- sprint -- promoting a reviewed entry from provisional to canonical
-- (and re-embedding it into this table) is Sprint 10's job
-- ("Runbook Learning Loop"), not built yet.
--
-- No ANN index (ivfflat/hnsw): at the 10-or-so rows this corpus has,
-- exact KNN (`ORDER BY embedding <=> %s`) is trivially fast. Add one
-- only if the corpus or query volume actually grows -- see
-- docs/DESIGN.md's Tech Stack "growth path" column for the same pattern
-- applied to the vector store itself.
--
-- Applied manually for now (no migration framework yet), same as
-- 0001_init.sql:
--   psql "$DATABASE_URL" -f db/migrations/0002_runbook_entries.sql

CREATE TABLE IF NOT EXISTS runbook_entries (
    entry_id           TEXT PRIMARY KEY,
    title              TEXT NOT NULL,
    -- The full text embedded for similarity search -- richer than
    -- title alone so retrieval has real signal to work with (customer
    -- context, backup-card availability, etc.), not just a decline code.
    body               TEXT NOT NULL,
    -- Must name a real registered Temporal activity (see
    -- src/payment_failure_remediation_agent/actions/) -- the workflow
    -- dispatches EXECUTING to this string directly by activity name.
    recommended_action TEXT NOT NULL,
    -- BAAI/bge-small-en-v1.5 (config.EMBEDDING_MODEL) produces 384-dim
    -- vectors. Changing the embedding model requires re-seeding this
    -- table, since existing vectors would no longer be comparable.
    embedding          VECTOR(384) NOT NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
