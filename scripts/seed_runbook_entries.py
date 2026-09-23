"""Idempotently seed `runbook_entries` with the Sprint 4 corpus.

One-shot setup script, same role as `scripts/verify_sprint1.sh` for its
own sprint. Computes each entry's embedding locally via `fastembed`
(config.EMBEDDING_MODEL) and upserts by `entry_id`, so re-running this
after editing the corpus below re-embeds and updates in place rather
than duplicating rows.

Run after `db/migrations/0002_runbook_entries.sql` has been applied:
    .venv/bin/python scripts/seed_runbook_entries.py

Deliberately only 7 entries, not docs/DESIGN.md's original "10-15" --
see CLAUDE.md's Sprint 4 section for why (MVP-scope discipline: add
more only if the golden-set eval shows a real precision gap, not to
pad toward a round number). Three of the nine golden-set scenarios
(fraud_hold_stolen_card, fraudulent_charge_flagged,
insufficient_funds_high_value_customer) are deliberately left with no
matching entry here at all -- that's the point of the sprint, not a
gap: retrieval must report match_found=False for them.
"""

import asyncio

from fastembed import TextEmbedding
from pgvector.psycopg import register_vector_async

from payment_failure_remediation_agent.config import EMBEDDING_MODEL
from payment_failure_remediation_agent.db import get_connection

CORPUS: list[dict[str, str]] = [
    {
        "entry_id": "RB-0001",
        "title": "Insufficient funds, standard customer, no backup card",
        "body": (
            "FUNDS_ISSUE: the cardholder's account has insufficient funds to cover "
            "the charge right now. The customer is on the standard tier with no "
            "backup payment method on file and no prior remediation attempts for "
            "this case. Since the customer is not high-value and there is no backup "
            "card to switch to, the safest response is to retry the payment after a "
            "short delay (about 24 hours) to give the balance time to replenish."
        ),
        "recommended_action": "retry_payment",
    },
    {
        "entry_id": "RB-0002",
        "title": "Insufficient funds, backup payment method on file",
        "body": (
            "FUNDS_ISSUE: the cardholder's account currently lacks sufficient funds "
            "for this charge. The customer has a backup payment method on file. "
            "Rather than waiting and retrying the same failing card, the case should "
            "switch the charge to the customer's backup payment method to avoid delay."
        ),
        "recommended_action": "switch_backup_payment_method",
    },
    {
        "entry_id": "RB-0003",
        "title": "Card expired, backup payment method on file",
        "body": (
            "HARD_DECLINE: the card was expired at the time of the charge, making "
            "the instrument permanently unusable -- this is not a transient issue "
            "and must never be blind-retried. The customer has a backup payment "
            "method on file, so the case should switch the charge to that backup "
            "payment method instead of asking the customer to update their card."
        ),
        "recommended_action": "switch_backup_payment_method",
    },
    {
        "entry_id": "RB-0004",
        "title": "Card expired, no backup on file",
        "body": (
            "HARD_DECLINE: the card was expired at the time of the charge and is "
            "permanently unusable; retrying the same card will never succeed. No "
            "backup payment method is on file for this customer, so there is no "
            "fallback instrument to switch to. The customer must be asked to update "
            "their card on file before the payment can proceed."
        ),
        "recommended_action": "request_card_update",
    },
    {
        "entry_id": "RB-0005",
        "title": "Transient gateway processing error",
        "body": (
            "SOFT_DECLINE: the gateway reported a transient processing error on the "
            "issuer or processor side, not a problem with the card or the "
            "cardholder's funds. This kind of failure is safe to retry immediately, "
            "since the underlying instrument is fine and the error is expected to "
            "clear on its own."
        ),
        "recommended_action": "retry_payment",
    },
    {
        "entry_id": "RB-0006",
        "title": "Gateway rate-limited / try-again-later",
        "body": (
            "SOFT_DECLINE: the gateway returned a try-again-later / rate-limited "
            "response, indicating a temporary processor-side throttling condition "
            "rather than any problem with the card or the cardholder's account. The "
            "correct response is to retry the payment with backoff rather than "
            "escalating or asking the customer to take any action."
        ),
        "recommended_action": "retry_payment",
    },
    {
        "entry_id": "RB-0007",
        "title": "Insufficient balance decline, standard tier (alternate phrasing)",
        "body": (
            "FUNDS_ISSUE: the charge was declined because the cardholder's balance "
            "was too low to cover it at the time of the attempt. The customer is a "
            "standard-tier account with no backup card on file and no history of "
            "prior remediation for this case. Since there is no alternate payment "
            "instrument available and the customer is not a high-value account "
            "requiring white-glove handling, retrying the charge after a short wait "
            "is the appropriate next step."
        ),
        "recommended_action": "retry_payment",
    },
]


async def seed() -> None:
    embedding_model = TextEmbedding(model_name=EMBEDDING_MODEL)
    bodies = [entry["body"] for entry in CORPUS]
    embeddings = list(embedding_model.embed(bodies))

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
                (
                    entry["entry_id"],
                    entry["title"],
                    entry["body"],
                    entry["recommended_action"],
                    embedding,
                ),
            )
        await conn.commit()
    print(f"Seeded {len(CORPUS)} runbook entries using {EMBEDDING_MODEL}.")


if __name__ == "__main__":
    asyncio.run(seed())
