"""Runbook retrieval (docs/DESIGN.md Section 3, Sprint 4).

Two stages, fully encapsulated here -- the workflow only ever sees one
`RunbookEntry` (match_found=False means "nothing applies"):
  1. Vector search (pgvector) proposes the top few candidate entries.
  2. A Claude judge decides which one applies, or NONE.
Similarity alone can't do stage 2: scores for right and wrong matches
overlap completely (debugged_log.md sections 4-5).
"""

from anthropic import AsyncAnthropic
from fastembed import TextEmbedding
from pgvector.psycopg import register_vector_async
from temporalio import activity

from payment_failure_remediation_agent.config import ANTHROPIC_API_KEY, EMBEDDING_MODEL
from payment_failure_remediation_agent.db import get_connection
from payment_failure_remediation_agent.models import Diagnosis, RunbookEntry
from payment_failure_remediation_agent.runbook.corpus import CORPUS_BY_ID
from payment_failure_remediation_agent.runbook.judge import pick_entry

# recall@3 was ~100% in the retrieval eval, so 3 candidates is enough for
# the judge to always see the right entry.
CANDIDATE_COUNT = 3

# Loaded once per worker process: loading the ONNX model has real cost and
# this activity runs on every case.
_embedding_model: TextEmbedding | None = None


def _get_embedding_model() -> TextEmbedding:
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = TextEmbedding(model_name=EMBEDDING_MODEL)
    return _embedding_model


def to_runbook_entry(chosen_id: str | None, reason: str) -> RunbookEntry:
    """Turn the judge's answer (an entry id, or None for NONE) into a RunbookEntry."""
    if chosen_id is None:
        return RunbookEntry(
            entry_id="", title="", recommended_action="", match_found=False, reason=reason
        )
    entry = CORPUS_BY_ID[chosen_id]
    return RunbookEntry(
        entry_id=entry.entry_id,
        title=entry.title,
        recommended_action=entry.recommended_action,
        match_found=True,
        reason=reason,
    )


@activity.defn(name="retrieve_runbook_entry")
async def retrieve_runbook_entry(case_id: str, diagnosis: Diagnosis) -> RunbookEntry:
    # Stage 1: embed the diagnosis. Same "CATEGORY: text" shape the corpus
    # `situation` texts use, so the vectors compare like with like.
    query_text = f"{diagnosis.decline_category.value}: {diagnosis.root_cause}"
    query_vector = next(iter(_get_embedding_model().embed([query_text])))

    async with get_connection() as conn:
        # Teaches psycopg to send numpy vectors as pgvector's `vector` type.
        await register_vector_async(conn)
        # `<=>` is cosine distance, so ascending order = most similar first.
        # Exact scan (no ANN index): fine at ~7 rows, see the migration.
        cursor = await conn.execute(
            "SELECT entry_id FROM runbook_entries ORDER BY embedding <=> %s LIMIT %s",
            (query_vector, CANDIDATE_COUNT),
        )
        rows = await cursor.fetchall()

    if not rows:  # a forgotten seed step, not a hypothetical
        return to_runbook_entry(None, "runbook_entries is empty; run scripts/seed_runbook_entries.py")

    # Stage 2: the judge. The DB holds each entry's vector and full body, but
    # the judge was measured on the short `situation` text, which lives only
    # in the shared corpus -- so look candidates up there by id. (When entries
    # can be authored outside corpus.py, e.g. Sprint 10, store `situation` in
    # the DB instead; that's a schema change.)
    candidates = [CORPUS_BY_ID[entry_id] for (entry_id,) in rows]
    client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    chosen_id, reason = await pick_entry(client, query_text, candidates)
    return to_runbook_entry(chosen_id, reason)
