"""Contract tests for Sprint 2 evidence connectors and the Payment
Gateway Simulator's decline-code taxonomy + scripted scenarios
(docs/DESIGN.md Section 3).

No Temporal environment needed -- a connector's `fetch` is a plain
async method that doesn't touch Temporal or a real DB, so it's called
directly. These tests only assert evidence fidelity (does the right
data come back for a given scenario), never remediation correctness --
there's no diagnosis/policy/remediation logic yet to be correct about.
"""

import pytest

from payment_failure_remediation_agent.activities.evidence_connectors.case_history import (
    CaseHistoryConnector,
)
from payment_failure_remediation_agent.activities.evidence_connectors.customer_data import (
    CustomerDataConnector,
)
from payment_failure_remediation_agent.activities.evidence_connectors.gateway import (
    GatewayConnector,
)
from payment_failure_remediation_agent.simulator import DeclineCategory, category_of, get_scenario
from payment_failure_remediation_agent.simulator.scenarios import SCENARIOS


async def test_missing_scenario_key_falls_back_to_standard_customer() -> None:
    """Every Sprint 1 test passes event_payload with no "scenario" key --
    this is the fallback that keeps them working unchanged."""
    evidence = await GatewayConnector().fetch("case-1", {})
    assert evidence.data["decline_code"] == "insufficient_funds"
    assert evidence.missing is False


def test_unknown_scenario_name_raises_instead_of_silently_defaulting() -> None:
    with pytest.raises(ValueError):
        get_scenario("not_a_real_scenario")


@pytest.mark.parametrize("scenario_name", list(SCENARIOS))
async def test_connectors_surface_the_named_scenarios_evidence(scenario_name: str) -> None:
    event_payload = {"scenario": scenario_name}
    scenario = SCENARIOS[scenario_name]

    gateway_evidence = await GatewayConnector().fetch("case-1", event_payload)
    customer_evidence = await CustomerDataConnector().fetch("case-1", event_payload)
    history_evidence = await CaseHistoryConnector().fetch("case-1", event_payload)

    assert gateway_evidence.data == scenario.gateway
    assert customer_evidence.data == scenario.customer_data
    assert history_evidence.data == scenario.case_history


def test_high_value_and_standard_customer_share_a_decline_code_but_differ_in_tier() -> None:
    """The flagship proof this isn't naive code->action mapping: same
    decline code, different customer_tier."""
    high_value = SCENARIOS["insufficient_funds_high_value_customer"]
    standard = SCENARIOS["insufficient_funds_standard_customer"]
    assert high_value.gateway["decline_code"] == standard.gateway["decline_code"]
    assert high_value.customer_data["customer_tier"] != standard.customer_data["customer_tier"]


def test_fraud_hold_is_hard_decline_even_for_a_high_value_customer() -> None:
    fraud = SCENARIOS["fraud_hold_stolen_card"]
    assert fraud.expected_taxonomy_category == DeclineCategory.HARD_DECLINE
    assert fraud.customer_data["customer_tier"] == "high_value"


def test_taxonomy_categorizes_known_codes() -> None:
    assert category_of("stolen_card") == DeclineCategory.HARD_DECLINE
    assert category_of("processing_error") == DeclineCategory.SOFT_DECLINE
    assert category_of("insufficient_funds") == DeclineCategory.FUNDS_ISSUE


def test_taxonomy_rejects_unknown_code() -> None:
    with pytest.raises(ValueError):
        category_of("not_a_real_code")
