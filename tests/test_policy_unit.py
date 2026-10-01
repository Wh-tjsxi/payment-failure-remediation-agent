"""Offline, table-driven tests for `policy.rules_engine.decide` (Sprint 5).

Pure function, no Temporal/DB/LLM -- every case constructs `RunbookEntry`
and `Evidence` fixtures directly and asserts the resulting `PolicyDecision`.
"""

from payment_failure_remediation_agent.models import Evidence, RunbookEntry
from payment_failure_remediation_agent.policy.rules_engine import decide

LOW_RISK_ENTRY = RunbookEntry(
    entry_id="RB-TEST", title="test", recommended_action="retry_payment", match_found=True
)
HIGH_RISK_ENTRY = RunbookEntry(
    entry_id="RB-TEST",
    title="test",
    recommended_action="switch_backup_payment_method",
    match_found=True,
)
UNKNOWN_ACTION_ENTRY = RunbookEntry(
    entry_id="RB-TEST", title="test", recommended_action="some_future_action", match_found=True
)


def _gateway(decline_code: str, amount: float, *, missing: bool = False) -> Evidence:
    if missing:
        return Evidence(source="fetch_gateway_evidence", data={}, missing=True)
    return Evidence(source="gateway", data={"decline_code": decline_code, "amount": amount})


def _case_history(prior_attempted: object, *, missing: bool = False) -> Evidence:
    if missing:
        return Evidence(source="fetch_case_history_evidence", data={}, missing=True)
    return Evidence(source="case_history", data={"prior_remediation_attempted": prior_attempted})


def _evidence(gateway: Evidence, case_history: Evidence) -> list[Evidence]:
    return [gateway, case_history]


def test_fraud_beats_low_amount_low_risk_first_attempt() -> None:
    decision = decide(
        LOW_RISK_ENTRY,
        _evidence(_gateway("stolen_card", 49.00), _case_history(False)),
    )
    assert decision.approved is False
    assert decision.rule_fired == "fraud_hard_block"


def test_amount_just_under_threshold_auto_approves() -> None:
    decision = decide(
        LOW_RISK_ENTRY,
        _evidence(_gateway("insufficient_funds", 99.99), _case_history(False)),
    )
    assert decision.approved is True
    assert decision.requires_approval is False
    assert decision.rule_fired == "auto_approve_low_risk_first_attempt"


def test_amount_at_threshold_requires_approval() -> None:
    decision = decide(
        LOW_RISK_ENTRY,
        _evidence(_gateway("insufficient_funds", 100.00), _case_history(False)),
    )
    assert decision.requires_approval is True
    assert decision.rule_fired == "amount_at_or_above_threshold"


def test_high_risk_action_requires_approval_even_at_low_amount() -> None:
    decision = decide(
        HIGH_RISK_ENTRY,
        _evidence(_gateway("insufficient_funds", 49.00), _case_history(False)),
    )
    assert decision.requires_approval is True
    assert decision.rule_fired == "high_risk_action"


def test_unknown_action_requires_approval() -> None:
    decision = decide(
        UNKNOWN_ACTION_ENTRY,
        _evidence(_gateway("insufficient_funds", 49.00), _case_history(False)),
    )
    assert decision.requires_approval is True
    assert decision.rule_fired == "high_risk_action"


def test_prior_attempt_true_requires_approval() -> None:
    decision = decide(
        LOW_RISK_ENTRY,
        _evidence(_gateway("insufficient_funds", 49.00), _case_history(True)),
    )
    assert decision.requires_approval is True
    assert decision.rule_fired == "not_first_attempt_or_unknown_history"


def test_prior_attempt_as_serialized_one_requires_approval() -> None:
    """Temporal's data converter can round-trip a bool as 0/1 -- `1` must
    read as truthy, not as some non-bool value that falls through."""
    decision = decide(
        LOW_RISK_ENTRY,
        _evidence(_gateway("insufficient_funds", 49.00), _case_history(1)),
    )
    assert decision.requires_approval is True
    assert decision.rule_fired == "not_first_attempt_or_unknown_history"


def test_prior_attempt_absent_requires_approval() -> None:
    decision = decide(
        LOW_RISK_ENTRY,
        _evidence(_gateway("insufficient_funds", 49.00), Evidence(source="case_history", data={})),
    )
    assert decision.requires_approval is True
    assert decision.rule_fired == "not_first_attempt_or_unknown_history"


def test_prior_attempt_zero_auto_approves() -> None:
    """A real `prior_remediation_attempted=0` (serialized False) must read
    as "first attempt", not fall into the "unknown" branch."""
    decision = decide(
        LOW_RISK_ENTRY,
        _evidence(_gateway("insufficient_funds", 49.00), _case_history(0)),
    )
    assert decision.requires_approval is False
    assert decision.rule_fired == "auto_approve_low_risk_first_attempt"


def test_gateway_evidence_present_but_amount_missing_requires_approval() -> None:
    decision = decide(
        LOW_RISK_ENTRY,
        _evidence(
            Evidence(source="gateway", data={"decline_code": "insufficient_funds"}),
            _case_history(False),
        ),
    )
    assert decision.approved is True
    assert decision.requires_approval is True
    assert decision.rule_fired == "evidence_missing_fail_safe"


def test_gateway_evidence_missing_requires_approval_not_hard_block() -> None:
    decision = decide(
        LOW_RISK_ENTRY,
        _evidence(_gateway("", 0, missing=True), _case_history(False)),
    )
    assert decision.approved is True
    assert decision.requires_approval is True
    assert decision.rule_fired == "evidence_missing_fail_safe"


def test_case_history_missing_requires_approval() -> None:
    decision = decide(
        LOW_RISK_ENTRY,
        _evidence(_gateway("insufficient_funds", 49.00), _case_history("", missing=True)),
    )
    assert decision.requires_approval is True
    assert decision.rule_fired == "not_first_attempt_or_unknown_history"


def test_otherwise_auto_approves() -> None:
    decision = decide(
        LOW_RISK_ENTRY,
        _evidence(_gateway("insufficient_funds", 49.00), _case_history(False)),
    )
    assert decision.approved is True
    assert decision.requires_approval is False
    assert decision.rule_fired == "auto_approve_low_risk_first_attempt"
