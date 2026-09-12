"""CLI approval endpoint: `python -m payment_failure_remediation_agent.cli <subcommand> ...`

Sends real Temporal signals to a running `PaymentFailureCaseWorkflow`
(id `case-<id>`) -- this is a first-party argparse script, not the
vendor `temporal` CLI (not installed here) and not a fake. Stands in for
the real approval-queue dashboard (Sprint 6) for a solo dev in the
meantime.
"""

import argparse
import asyncio

from temporalio.client import Client

from payment_failure_remediation_agent.config import TEMPORAL_ADDRESS, TEMPORAL_NAMESPACE
from payment_failure_remediation_agent.models import ApprovalDecision, RunbookEntry


def _workflow_id(case_id: str) -> str:
    return f"case-{case_id}"


async def _signal_approval(case_id: str, decision: ApprovalDecision) -> None:
    client = await Client.connect(TEMPORAL_ADDRESS, namespace=TEMPORAL_NAMESPACE)
    handle = client.get_workflow_handle(_workflow_id(case_id))
    await handle.signal("submit_approval", decision)


async def _signal_author_runbook(case_id: str, entry: RunbookEntry) -> None:
    client = await Client.connect(TEMPORAL_ADDRESS, namespace=TEMPORAL_NAMESPACE)
    handle = client.get_workflow_handle(_workflow_id(case_id))
    await handle.signal("author_runbook", entry)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Send a human decision signal to a running case workflow."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    approve = subparsers.add_parser("approve", help="Approve the proposed remediation.")
    approve.add_argument("case_id")
    approve.add_argument("--approver", default="cli-user")

    reject_try_different = subparsers.add_parser(
        "reject-try-different", help="Reject and ask for a different remediation."
    )
    reject_try_different.add_argument("case_id")
    reject_try_different.add_argument("--approver", default="cli-user")
    reject_try_different.add_argument("--reason", default="")

    reject_no_automation = subparsers.add_parser(
        "reject-no-automation", help="Reject and escalate -- no automation for this case."
    )
    reject_no_automation.add_argument("case_id")
    reject_no_automation.add_argument("--approver", default="cli-user")
    reject_no_automation.add_argument("--reason", default="")

    author_runbook = subparsers.add_parser(
        "author-runbook", help="Author a provisional runbook entry for a novel failure."
    )
    author_runbook.add_argument("case_id")
    author_runbook.add_argument("--entry-id", required=True)
    author_runbook.add_argument("--title", required=True)
    author_runbook.add_argument("--recommended-action", required=True)

    args = parser.parse_args()

    if args.command == "approve":
        asyncio.run(
            _signal_approval(
                args.case_id, ApprovalDecision(decision="approve", approver=args.approver)
            )
        )
    elif args.command == "reject-try-different":
        asyncio.run(
            _signal_approval(
                args.case_id,
                ApprovalDecision(
                    decision="reject_try_different",
                    approver=args.approver,
                    reason=args.reason,
                ),
            )
        )
    elif args.command == "reject-no-automation":
        asyncio.run(
            _signal_approval(
                args.case_id,
                ApprovalDecision(
                    decision="reject_no_automation",
                    approver=args.approver,
                    reason=args.reason,
                ),
            )
        )
    elif args.command == "author-runbook":
        asyncio.run(
            _signal_author_runbook(
                args.case_id,
                RunbookEntry(
                    entry_id=args.entry_id,
                    title=args.title,
                    recommended_action=args.recommended_action,
                    match_found=True,
                ),
            )
        )


if __name__ == "__main__":
    main()
