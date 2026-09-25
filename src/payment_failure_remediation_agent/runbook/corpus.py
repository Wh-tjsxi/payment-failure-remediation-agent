"""The seeded runbook corpus (docs/DESIGN.md Section 3, Sprint 4).

Lives in the package (not in scripts/seed_runbook_entries.py) so the
seed script, the retrieval eval, and the tests all read one source of
truth.

Each entry carries two texts on purpose:
- `body`: the full human-readable runbook prose, including what to do.
- `situation`: only *when the entry applies* -- this is what gets
  embedded. The query (a diagnosis) is explicitly forbidden from
  proposing a remediation, so embedding the action prose in the
  document side would add noise that can never match anything in the
  query. See CLAUDE.md's Sprint 4 section / the retrieval eval for the
  measured effect.

Deliberately 6 entries, not docs/DESIGN.md's original "10-15": add more
only if the eval shows a real precision gap. Never add two entries that
fit the same situation: the judge sees a tie and answers NONE (an
RB-0007 duplicate of RB-0001 did exactly that -- debugged_log.md section 6). Three golden-set scenarios
(fraud_hold_stolen_card, fraudulent_charge_flagged,
insufficient_funds_high_value_customer) have no entry here at all --
retrieval must report no match for them.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CorpusEntry:
    entry_id: str
    title: str
    category: str  # DeclineCategory value; used as a hard pre-filter at retrieval
    situation: str
    body: str
    recommended_action: str


CORPUS: list[CorpusEntry] = [
    CorpusEntry(
        entry_id="RB-0001",
        title="Insufficient funds, standard customer, no backup card",
        category="FUNDS_ISSUE",
        situation=(
            "FUNDS_ISSUE: insufficient funds decline. Standard-tier customer with no "
            "backup payment method on file and no prior remediation attempts."
        ),
        body=(
            "FUNDS_ISSUE: the cardholder's account has insufficient funds to cover "
            "the charge right now. The customer is on the standard tier with no "
            "backup payment method on file and no prior remediation attempts for "
            "this case. Since the customer is not high-value and there is no backup "
            "card to switch to, the safest response is to retry the payment after a "
            "short delay (about 24 hours) to give the balance time to replenish."
        ),
        recommended_action="retry_payment",
    ),
    CorpusEntry(
        entry_id="RB-0002",
        title="Insufficient funds, backup payment method on file",
        category="FUNDS_ISSUE",
        situation=(
            "FUNDS_ISSUE: insufficient funds decline. The customer has a backup "
            "payment method on file."
        ),
        body=(
            "FUNDS_ISSUE: the cardholder's account currently lacks sufficient funds "
            "for this charge. The customer has a backup payment method on file. "
            "Rather than waiting and retrying the same failing card, the case should "
            "switch the charge to the customer's backup payment method to avoid delay."
        ),
        recommended_action="switch_backup_payment_method",
    ),
    CorpusEntry(
        entry_id="RB-0003",
        title="Card expired, backup payment method on file",
        category="HARD_DECLINE",
        situation=(
            "HARD_DECLINE: the card was expired at the time of the charge, a "
            "permanent instrument-level failure. The customer has a backup payment "
            "method on file."
        ),
        body=(
            "HARD_DECLINE: the card was expired at the time of the charge, making "
            "the instrument permanently unusable -- this is not a transient issue "
            "and must never be blind-retried. The customer has a backup payment "
            "method on file, so the case should switch the charge to that backup "
            "payment method instead of asking the customer to update their card."
        ),
        recommended_action="switch_backup_payment_method",
    ),
    CorpusEntry(
        entry_id="RB-0004",
        title="Card expired, no backup on file",
        category="HARD_DECLINE",
        situation=(
            "HARD_DECLINE: the card was expired at the time of the charge, a "
            "permanent instrument-level failure. No backup payment method is on "
            "file for the customer."
        ),
        body=(
            "HARD_DECLINE: the card was expired at the time of the charge and is "
            "permanently unusable; retrying the same card will never succeed. No "
            "backup payment method is on file for this customer, so there is no "
            "fallback instrument to switch to. The customer must be asked to update "
            "their card on file before the payment can proceed."
        ),
        recommended_action="request_card_update",
    ),
    CorpusEntry(
        entry_id="RB-0005",
        title="Transient gateway processing error",
        category="SOFT_DECLINE",
        situation=(
            "SOFT_DECLINE: the gateway reported a transient processing error on the "
            "issuer or processor side, not a problem with the card or the "
            "cardholder's funds."
        ),
        body=(
            "SOFT_DECLINE: the gateway reported a transient processing error on the "
            "issuer or processor side, not a problem with the card or the "
            "cardholder's funds. This kind of failure is safe to retry immediately, "
            "since the underlying instrument is fine and the error is expected to "
            "clear on its own."
        ),
        recommended_action="retry_payment",
    ),
    CorpusEntry(
        entry_id="RB-0006",
        title="Gateway rate-limited / try-again-later",
        category="SOFT_DECLINE",
        situation=(
            "SOFT_DECLINE: the gateway returned a try-again-later / rate-limited "
            "response, a temporary processor-side throttling condition, not a "
            "problem with the card or the cardholder's account."
        ),
        body=(
            "SOFT_DECLINE: the gateway returned a try-again-later / rate-limited "
            "response, indicating a temporary processor-side throttling condition "
            "rather than any problem with the card or the cardholder's account. The "
            "correct response is to retry the payment with backoff rather than "
            "escalating or asking the customer to take any action."
        ),
        recommended_action="retry_payment",
    ),
]

CORPUS_BY_ID = {entry.entry_id: entry for entry in CORPUS}
