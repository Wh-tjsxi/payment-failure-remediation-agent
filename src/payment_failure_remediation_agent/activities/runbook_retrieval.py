"""Sprint 1 stub for runbook retrieval (RAG lookup).

Real body (pgvector similarity search over a seeded runbook corpus) lands
in Sprint 4. Always returns a match against a hardcoded entry -- the
"no adequate match" branch (-> HUMAN_RUNBOOK_AUTHORING) is exercised only
via `CaseInput.force_scenario` in branch tests, not by this stub's logic.
"""

from temporalio import activity

from payment_failure_remediation_agent.models import Diagnosis, RunbookEntry


@activity.defn(name="retrieve_runbook_entry")
async def retrieve_runbook_entry(case_id: str, diagnosis: Diagnosis) -> RunbookEntry:
    return RunbookEntry(
        entry_id="RB-0001",
        title="Card declined for insufficient funds -- retry after 24h",
        recommended_action="retry_payment",
        match_found=True,
    )
