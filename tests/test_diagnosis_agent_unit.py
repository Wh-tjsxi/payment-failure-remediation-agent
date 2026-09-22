"""Fast, offline unit tests for the diagnosis agent's non-LLM parts
(docs/DESIGN.md Section 3, Sprint 3). The actual Claude call is only
exercised by tests/test_diagnosis_golden_set.py (marked `integration`)
-- these cover the deterministic pieces so the default fast suite still
has real regression coverage of this module.
"""

from payment_failure_remediation_agent.activities.diagnosis_agent import (
    _DIAGNOSIS_TOOL,
    _render_evidence,
)
from payment_failure_remediation_agent.models import Evidence
from payment_failure_remediation_agent.simulator import DeclineCategory


def test_render_evidence_includes_present_source_data() -> None:
    rendered = _render_evidence([Evidence(source="gateway", data={"decline_code": "fraudulent"})])
    assert "gateway" in rendered
    assert "fraudulent" in rendered


def test_render_evidence_flags_missing_sources_without_fabricating_data() -> None:
    rendered = _render_evidence([Evidence(source="observability", data={}, missing=True)])
    assert "observability" in rendered
    assert "UNAVAILABLE" in rendered


def test_diagnosis_tool_schema_enum_matches_taxonomy() -> None:
    schema_categories = set(_DIAGNOSIS_TOOL["input_schema"]["properties"]["decline_category"]["enum"])
    assert schema_categories == {category.value for category in DeclineCategory}


def test_diagnosis_tool_requires_every_output_field() -> None:
    assert set(_DIAGNOSIS_TOOL["input_schema"]["required"]) == {
        "root_cause",
        "decline_category",
        "confidence",
        "evidence_cited",
    }
