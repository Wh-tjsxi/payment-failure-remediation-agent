"""Decline-code -> category answer key (docs/DESIGN.md Section 3, Sprint 2).

`DeclineCategory` itself lives in `models.py` (it's a core domain
concept `Diagnosis` needs). What belongs here is `category_of`: the
mapping from a raw Stripe/Adyen-style decline code to its category,
used only to (a) build internally-consistent scripted scenarios and
(b) let tests grade the diagnosis agent's classification against a
known-correct answer.

This mapping is never read by the diagnosis agent itself -- the gateway
connector only ever surfaces the raw `decline_code` a real processor
webhook would give; classifying it into a category is the diagnosis
agent's own job (Sprint 3), done through real reasoning about what the
code means, not a lookup against this table. Importing this module from
`activities/diagnosis_agent.py` for anything other than the
`DeclineCategory` type itself would defeat that.
"""

from payment_failure_remediation_agent.models import DeclineCategory

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
