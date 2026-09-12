"""Shared shape for remediation actions.

docs/DESIGN.md Section 2 calls for a generic `Action` abstraction with a
risk tier, executed only after a human approval signal. Sprint 1's
concrete actions (`retry_payment`, `issue_refund`, `toggle_feature_flag`)
are no-op stubs -- the real per-action side effects against the Payment
Gateway Simulator land in Sprints 7-8. The `execute`/idempotency-key
*shape* is real now so nothing has to change when the stub bodies are
swapped out.

Each concrete action module also exports a Temporal `@activity.defn`
wrapping its `execute`, registered under the action's own name (e.g.
"retry_payment") -- `RemediationProposal.action_name` is that same string,
so the workflow dispatches to the right action activity by name without a
branching if/elif per action.
"""

from typing import Protocol

from payment_failure_remediation_agent.models import ActionResult


class Action(Protocol):
    """One remediation action. `execute` must be safe to call twice with the
    same idempotency_key (per DESIGN.md's idempotent-execution requirement)
    -- real adapters dedupe on it, stubs just accept and ignore it."""

    async def execute(self, case_id: str, idempotency_key: str) -> ActionResult: ...
