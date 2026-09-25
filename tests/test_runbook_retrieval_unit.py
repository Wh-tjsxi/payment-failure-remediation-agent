"""Fast, offline tests for the non-LLM, non-DB parts of runbook retrieval
(docs/DESIGN.md Section 3, Sprint 4): the judge's prompt/tool shape and how
the judge's answer becomes a `RunbookEntry`. The real retrieval path
(pgvector + Claude) is covered by test_runbook_retrieval_golden_set.py.
"""

from typing import Any, cast

from payment_failure_remediation_agent.activities.runbook_retrieval import to_runbook_entry
from payment_failure_remediation_agent.runbook.corpus import CORPUS, CORPUS_BY_ID, CorpusEntry
from payment_failure_remediation_agent.runbook.judge import NONE, judge_tool, render_judge_message


def _tool_properties(candidates: list[CorpusEntry]) -> dict[str, Any]:
    # The SDK types `input_schema` as a bare `object`, so narrow it for indexing.
    schema = cast(dict[str, Any], judge_tool(candidates)["input_schema"])
    return cast(dict[str, Any], schema["properties"])


def test_judge_tool_offers_only_the_candidates_plus_none() -> None:
    candidates = CORPUS[:3]

    properties = _tool_properties(candidates)

    assert properties["entry_id"]["enum"] == [c.entry_id for c in candidates] + [NONE]


def test_judge_tool_asks_for_the_reason_before_the_choice() -> None:
    # Property order matters: the model writes `reason` first, so it thinks
    # before committing to an entry_id.
    assert list(_tool_properties(CORPUS[:3])) == ["reason", "entry_id"]


def test_judge_message_shows_each_candidate_situation_and_the_diagnosis() -> None:
    candidates = CORPUS[:2]

    message = render_judge_message("FUNDS_ISSUE: no backup card", candidates)

    for candidate in candidates:
        assert f"{candidate.entry_id}: {candidate.situation}" in message
    assert "FUNDS_ISSUE: no backup card" in message


def test_chosen_id_becomes_a_matching_runbook_entry() -> None:
    entry = to_runbook_entry("RB-0002", "backup card is on file")

    expected = CORPUS_BY_ID["RB-0002"]
    assert entry.match_found
    assert entry.entry_id == expected.entry_id
    assert entry.recommended_action == expected.recommended_action
    assert entry.reason == "backup card is on file"


def test_none_becomes_no_match_and_keeps_the_reason() -> None:
    entry = to_runbook_entry(None, "fraud: nothing applies")

    assert not entry.match_found
    assert entry.entry_id == ""
    assert entry.recommended_action == ""
    assert entry.reason == "fraud: nothing applies"
