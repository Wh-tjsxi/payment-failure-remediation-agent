"""Sprint 1 stub for resolution analysis.

Real body (detect genuinely-new info vs. the existing runbook entry) lands
in Sprint 10. Always reports "nothing new" -- the new-info branch
(-> RUNBOOK_UPDATE_REVIEW child workflow) is exercised only via
`CaseInput.force_scenario` in branch tests.
"""

from temporalio import activity

from payment_failure_remediation_agent.models import ResolutionAnalysis, Verification


@activity.defn(name="analyze_resolution")
async def analyze_resolution(case_id: str, verification: Verification) -> ResolutionAnalysis:
    return ResolutionAnalysis(new_info_found=False, summary="Sprint 1 stub: nothing new")
