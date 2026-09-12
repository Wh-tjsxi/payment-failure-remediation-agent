"""Worker entrypoint: `python -m payment_failure_remediation_agent.worker`

Connects to Temporal and registers every workflow and activity on
`TASK_QUEUE`, then polls until interrupted.
"""

import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

from payment_failure_remediation_agent.actions import (
    issue_refund,
    retry_payment,
    toggle_feature_flag,
)
from payment_failure_remediation_agent.activities import (
    diagnosis_agent,
    persistence,
    remediation_proposal_agent,
    resolution_analysis,
    runbook_retrieval,
    verification,
)
from payment_failure_remediation_agent.activities.evidence_connectors import (
    case_history,
    customer_data,
    gateway,
    observability,
)
from payment_failure_remediation_agent.config import (
    TASK_QUEUE,
    TEMPORAL_ADDRESS,
    TEMPORAL_NAMESPACE,
)
from payment_failure_remediation_agent.policy import rules_engine
from payment_failure_remediation_agent.workflows.payment_failure_case_workflow import (
    PaymentFailureCaseWorkflow,
)
from payment_failure_remediation_agent.workflows.runbook_update_review_workflow import (
    RunbookUpdateReviewWorkflow,
)


async def main() -> None:
    client = await Client.connect(TEMPORAL_ADDRESS, namespace=TEMPORAL_NAMESPACE)
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[PaymentFailureCaseWorkflow, RunbookUpdateReviewWorkflow],
        activities=[
            gateway.fetch_gateway_evidence,
            observability.fetch_observability_evidence,
            customer_data.fetch_customer_data_evidence,
            case_history.fetch_case_history_evidence,
            diagnosis_agent.diagnose,
            runbook_retrieval.retrieve_runbook_entry,
            rules_engine.evaluate_policy,
            remediation_proposal_agent.propose_remediation,
            retry_payment.retry_payment,
            issue_refund.issue_refund,
            toggle_feature_flag.toggle_feature_flag,
            verification.verify_resolution,
            resolution_analysis.analyze_resolution,
            persistence.persist_case_status,
            persistence.append_audit_event,
        ],
    )
    print(f"Worker connected to {TEMPORAL_ADDRESS}, polling task queue {TASK_QUEUE!r} ...")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
