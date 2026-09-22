"""Decline-code taxonomy (docs/DESIGN.md Section 3, Sprint 2).

Maps Stripe/Adyen-style decline codes to a small set of categories
defined by remediation semantics, not payments-domain completeness --
kept to three on purpose, since this project is an MVP meant to
demonstrate judgment, not model the payments domain exhaustively.

This is internal simulator/reference data. It is never handed to the
diagnosis agent as ground truth -- the gateway connector only ever
surfaces the raw `decline_code` a real processor webhook would give;
classifying it into a category here is Sprint 3's (the diagnosis
agent's) job, not free information from Sprint 2.
"""

from enum import StrEnum


class DeclineCategory(StrEnum):
    # Never blind-retry. Fraud codes always escalate to a human, no
    # matter the customer; expired-card codes are only fixable via a
    # backup card.
    HARD_DECLINE = "HARD_DECLINE"
    # Safe to retry with backoff -- the "boring" bucket, included to
    # prove the system doesn't over-engineer every path.
    SOFT_DECLINE = "SOFT_DECLINE"
    # Retry-eligible, but *how* to retry depends on customer context --
    # the category the scripted scenarios lean on.
    FUNDS_ISSUE = "FUNDS_ISSUE"


_CATEGORY_BY_CODE: dict[str, DeclineCategory] = {
    "stolen_card": DeclineCategory.HARD_DECLINE,
    "fraudulent": DeclineCategory.HARD_DECLINE,
    "expired_card": DeclineCategory.HARD_DECLINE,
    "processing_error": DeclineCategory.SOFT_DECLINE,
    "try_again_later": DeclineCategory.SOFT_DECLINE,
    "insufficient_funds": DeclineCategory.FUNDS_ISSUE,
}


def category_of(decline_code: str) -> DeclineCategory:
    try:
        return _CATEGORY_BY_CODE[decline_code]
    except KeyError:
        raise ValueError(f"unknown decline code: {decline_code!r}") from None
