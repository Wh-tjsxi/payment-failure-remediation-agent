"""Scriptable payment-failure scenarios (docs/DESIGN.md Section 3, Sprint 2).

Each scenario bundles the gateway/customer_data/case_history evidence a
real case with that profile would surface, plus non-binding metadata
(`expected_taxonomy_category`, `expected_remediation_hint`) later
sprints can use as golden-set seeds. Sprint 2 itself only asserts
evidence fidelity (tests/test_evidence_connectors.py) -- never
remediation correctness, since diagnosis/proposal logic doesn't exist
yet.

The first four scenarios (Sprint 2) are enough on their own to prove the
system reasons about customer context, not just error codes. Sprint 3
adds five more -- not to hit docs/DESIGN.md's original "15-20 item"
golden-set figure by padding with near-duplicates, but because a golden
set needs every taxonomy category actually represented, and the
original four only covered two of three (no SOFT_DECLINE example, and
only one HARD_DECLINE flavor). Nine distinct, purposeful scenarios beat
padding to an arbitrary count.
"""

from dataclasses import dataclass

from payment_failure_remediation_agent.models import EvidenceValue
from payment_failure_remediation_agent.simulator.taxonomy import DeclineCategory, category_of


@dataclass(frozen=True)
class Scenario:
    name: str
    expected_taxonomy_category: DeclineCategory
    expected_remediation_hint: str
    gateway: dict[str, EvidenceValue]
    customer_data: dict[str, EvidenceValue]
    case_history: dict[str, EvidenceValue]


def _funds_issue_scenario(
    name: str,
    *,
    amount: float,
    customer_tier: str,
    has_backup_payment_method: bool,
    remediation_hint: str,
) -> Scenario:
    return Scenario(
        name=name,
        expected_taxonomy_category=category_of("insufficient_funds"),
        expected_remediation_hint=remediation_hint,
        gateway={"decline_code": "insufficient_funds", "amount": amount, "currency": "usd"},
        customer_data={
            "customer_tier": customer_tier,
            "has_backup_payment_method": has_backup_payment_method,
        },
        case_history={"prior_remediation_attempted": False},
    )


_SCENARIO_LIST = [
    # The flagship pair: identical decline code, differing only in
    # customer_tier -> concierge escalation vs. automated retry.
    _funds_issue_scenario(
        "insufficient_funds_standard_customer",
        amount=49.00,
        customer_tier="standard",
        has_backup_payment_method=False,
        remediation_hint="auto_retry_with_backoff",
    ),
    _funds_issue_scenario(
        "insufficient_funds_high_value_customer",
        amount=249.00,
        customer_tier="high_value",
        has_backup_payment_method=False,
        remediation_hint="escalate_to_human_concierge",
    ),
    # Same code again, this time the deciding field is backup-card
    # availability rather than tier.
    _funds_issue_scenario(
        "insufficient_funds_with_backup_card",
        amount=79.00,
        customer_tier="standard",
        has_backup_payment_method=True,
        remediation_hint="switch_to_backup_payment_method",
    ),
    # Hard-stop path: proves the fraud override beats even a high-value
    # "be lenient" bias -- see docs/DESIGN.md Sprint 5's policy note.
    Scenario(
        name="fraud_hold_stolen_card",
        expected_taxonomy_category=category_of("stolen_card"),
        expected_remediation_hint="escalate_to_fraud_review",
        gateway={"decline_code": "stolen_card", "amount": 500.00, "currency": "usd"},
        customer_data={"customer_tier": "high_value", "has_backup_payment_method": True},
        case_history={"prior_remediation_attempted": False},
    ),
    # A second HARD_DECLINE flavor, distinct from fraud: an expired card
    # is a dead instrument, not a fraud signal -- proves HARD_DECLINE
    # isn't monolithic, and (paired below) that backup-card availability
    # still matters even within a "never blind-retry" category.
    Scenario(
        name="expired_card_no_backup",
        expected_taxonomy_category=category_of("expired_card"),
        expected_remediation_hint="request_customer_update_card",
        gateway={"decline_code": "expired_card", "amount": 99.00, "currency": "usd"},
        customer_data={"customer_tier": "standard", "has_backup_payment_method": False},
        case_history={"prior_remediation_attempted": False},
    ),
    Scenario(
        name="expired_card_with_backup",
        expected_taxonomy_category=category_of("expired_card"),
        expected_remediation_hint="switch_to_backup_payment_method",
        gateway={"decline_code": "expired_card", "amount": 99.00, "currency": "usd"},
        customer_data={"customer_tier": "standard", "has_backup_payment_method": True},
        case_history={"prior_remediation_attempted": False},
    ),
    # A second fraud example, deliberately at standard tier (not
    # high_value like the stolen-card scenario) -- confirms the
    # fraud-hard-stop generalizes across tiers, not just the one tested.
    Scenario(
        name="fraudulent_charge_flagged",
        expected_taxonomy_category=category_of("fraudulent"),
        expected_remediation_hint="escalate_to_fraud_review",
        gateway={"decline_code": "fraudulent", "amount": 650.00, "currency": "usd"},
        customer_data={"customer_tier": "standard", "has_backup_payment_method": False},
        case_history={"prior_remediation_attempted": False},
    ),
    # SOFT_DECLINE: the "boring" bucket -- no customer-context nuance
    # needed, just retry with backoff. Two examples so the golden set
    # doesn't have a single-item category.
    Scenario(
        name="processing_error_transient",
        expected_taxonomy_category=category_of("processing_error"),
        expected_remediation_hint="auto_retry_with_backoff",
        gateway={"decline_code": "processing_error", "amount": 59.00, "currency": "usd"},
        customer_data={"customer_tier": "standard", "has_backup_payment_method": False},
        case_history={"prior_remediation_attempted": False},
    ),
    Scenario(
        name="try_again_later_transient",
        expected_taxonomy_category=category_of("try_again_later"),
        expected_remediation_hint="auto_retry_with_backoff",
        gateway={"decline_code": "try_again_later", "amount": 39.00, "currency": "usd"},
        customer_data={"customer_tier": "standard", "has_backup_payment_method": False},
        case_history={"prior_remediation_attempted": False},
    ),
]

SCENARIOS: dict[str, Scenario] = {s.name: s for s in _SCENARIO_LIST}

DEFAULT_SCENARIO_NAME = "insufficient_funds_standard_customer"


def get_scenario(name: str | None) -> Scenario:
    """Look up a named scenario. Falls back to the default (standard
    customer, insufficient funds, no complications) only when no name is
    given at all -- e.g. `event_payload` with no "scenario" key, which
    is what every Sprint 1 test still passes. An explicitly-named but
    unknown scenario raises rather than silently defaulting, so a typo'd
    scenario name fails loudly instead of quietly demo-ing the wrong
    case.
    """
    resolved_name = name or DEFAULT_SCENARIO_NAME
    try:
        return SCENARIOS[resolved_name]
    except KeyError:
        raise ValueError(f"unknown scenario: {resolved_name!r}") from None
