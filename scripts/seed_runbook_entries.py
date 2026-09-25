"""Idempotently seed `runbook_entries` with the Sprint 4 corpus.

One-shot setup script, same role as `scripts/verify_sprint1.sh` for its
own sprint. Computes each entry's embedding locally via `fastembed`
(config.EMBEDDING_MODEL) and upserts by `entry_id`, so re-running this
after editing the corpus re-embeds and updates in place rather than
duplicating rows.

The corpus itself lives in `runbook/corpus.py` (shared with the
retrieval eval). What gets embedded is each entry's `situation` -- when
the entry applies -- not its full `body`; see that module's docstring
for why. (fastembed's `passage_embed`/`query_embed` are identical to
plain `embed` for this model, so we use `embed`; a manual BGE query prefix
is being measured in the retrieval eval and would apply to queries only.)

Run after `db/migrations/0002_runbook_entries.sql` has been applied:
    .venv/bin/python scripts/seed_runbook_entries.py
"""

import asyncio

from fastembed import TextEmbedding
from pgvector.psycopg import register_vector_async

from payment_failure_remediation_agent.config import EMBEDDING_MODEL
from payment_failure_remediation_agent.db import get_connection
from payment_failure_remediation_agent.runbook.corpus import CORPUS


async def seed() -> None:
    embedding_model = TextEmbedding(model_name=EMBEDDING_MODEL)
    situations = [entry.situation for entry in CORPUS]
    embeddings = list(embedding_model.embed(situations))

    async with get_connection() as conn:
        await register_vector_async(conn)
        for entry, embedding in zip(CORPUS, embeddings, strict=True):
            await conn.execute(
                """
                INSERT INTO runbook_entries (entry_id, title, body, recommended_action, embedding)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (entry_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    body = EXCLUDED.body,
                    recommended_action = EXCLUDED.recommended_action,
                    embedding = EXCLUDED.embedding
                """,
                (entry.entry_id, entry.title, entry.body, entry.recommended_action, embedding),
            )
        await conn.commit()
    print(f"Seeded {len(CORPUS)} runbook entries using {EMBEDDING_MODEL}.")


if __name__ == "__main__":
    asyncio.run(seed())
