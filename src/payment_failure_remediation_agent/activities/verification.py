"""Sprint 1 stub for post-execution verification.

Real body (re-query evidence sources to confirm actual resolution, not
just "API call succeeded") lands in Sprint 7. Always reports resolved --
the not-resolved branch (-> REINVESTIGATION) is exercised only via
`CaseInput.force_scenario` in branch tests.
"""

from temporalio import activity

from payment_failure_remediation_agent.models import ActionResult, Verification


@activity.defn(name="verify_resolution")
async def verify_resolution(case_id: str, action_result: ActionResult) -> Verification:
    return Verification(resolved=True, detail="Sprint 1 stub: always resolved")
