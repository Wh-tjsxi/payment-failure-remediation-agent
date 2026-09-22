"""Golden-set accuracy eval for the Sprint 3 diagnosis agent
(docs/DESIGN.md Section 3).

Marked `integration` -- unlike every other test in this suite, this one
makes real, paid calls to the Anthropic API, so it's excluded from the
default `pytest -m "not integration"` gate CI already runs. This is the
resolution to the open cost question docs/DESIGN.md/CLAUDE.md flagged
for this sprint: no ANTHROPIC_API_KEY secret or per-push API cost is
needed for the default CI gate, since `-m "not integration"` was
already the exact command CI has run since Sprint 0. Run explicitly
with `pytest -m integration` (requires ANTHROPIC_API_KEY set) when
actually evaluating diagnosis accuracy, e.g. after a prompt/model
change.

Correctness bar is kept simple on purpose: exact decline_category match
plus a non-empty evidence_cited, not a fuzzy grading rubric.
"""

import pytest

from payment_failure_remediation_agent.activities.diagnosis_agent import diagnose
from payment_failure_remediation_agent.activities.evidence_connectors.case_history import (
    CaseHistoryConnector,
)
from payment_failure_remediation_agent.activities.evidence_connectors.customer_data import (
    CustomerDataConnector,
)
from payment_failure_remediation_agent.activities.evidence_connectors.gateway import (
    GatewayConnector,
)
from payment_failure_remediation_agent.simulator.scenarios import SCENARIOS

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("scenario_name", list(SCENARIOS))
async def test_diagnosis_matches_expected_taxonomy_category(scenario_name: str) -> None:
    scenario = SCENARIOS[scenario_name]
    event_payload = {"scenario": scenario_name}
    evidence = [
        await GatewayConnector().fetch(scenario_name, event_payload),
        await CustomerDataConnector().fetch(scenario_name, event_payload),
        await CaseHistoryConnector().fetch(scenario_name, event_payload),
    ]

    diagnosis = await diagnose(scenario_name, evidence)

    assert diagnosis.decline_category == scenario.expected_taxonomy_category
    assert diagnosis.evidence_cited
