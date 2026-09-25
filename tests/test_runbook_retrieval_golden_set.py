"""Golden-set eval of the real runbook retrieval (docs/DESIGN.md Section 3,
Sprint 4): pgvector top-3 candidates, then the Claude judge.

Marked `integration` like the diagnosis golden set: it needs the
docker-compose Postgres with `runbook_entries` seeded
(scripts/seed_runbook_entries.py) and makes real Anthropic calls, so
CI's `pytest -m "not integration"` skips it. Run with `pytest -m integration`.

Inputs are the frozen real diagnoses in tests/fixtures/ (captured once by
scripts/capture_diagnosis_fixtures.py), so this pays only for the judge,
not for re-diagnosing every scenario.

The bar is the action, not the entry id. Scenarios expected to have NO
match include both fraud scenarios, so passing also proves fraud never
gets a "switch to the backup card" recommendation. The `_wordy_live_run`
scenario is a real diagnosis from an end-to-end run that mentions an extra
observability timeout: the tidier fixtures alone hid a judge failure.
"""

import json
from pathlib import Path

import pytest

from payment_failure_remediation_agent.activities.runbook_retrieval import retrieve_runbook_entry
from payment_failure_remediation_agent.models import DeclineCategory, Diagnosis

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).parent / "fixtures"
DIAGNOSES = json.loads((FIXTURES / "diagnoses_captured.json").read_text())["diagnoses"]
LABELS = json.loads((FIXTURES / "retrieval_queries_authored.json").read_text())["captured_labels"]


@pytest.mark.parametrize("captured", DIAGNOSES, ids=[d["scenario"] for d in DIAGNOSES])
async def test_retrieval_picks_the_expected_action_or_no_match(captured: dict) -> None:
    diagnosis = Diagnosis(
        root_cause=captured["root_cause"],
        decline_category=DeclineCategory(captured["decline_category"]),
        confidence=captured["confidence"],
        evidence_cited=captured["evidence_cited"],
    )
    label = LABELS[captured["scenario"]]

    entry = await retrieve_runbook_entry(captured["scenario"], diagnosis)

    if label["expected_entry_ids"]:
        assert entry.match_found, entry.reason
        assert entry.recommended_action == label["expected_action"], entry.reason
    else:
        assert not entry.match_found, f"expected no match, got {entry.entry_id}: {entry.reason}"
