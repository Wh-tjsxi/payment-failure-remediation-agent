"""Shared shape for evidence connectors.

docs/DESIGN.md Section 2 calls for a "pluggable Connector interface" where
each evidence source (gateway, observability, customer data, case history)
fails independently without blocking the others. Sprint 2 implements the
real per-source logic against the Payment Gateway Simulator's scripted
scenarios (docs/DESIGN.md Section 3) -- `event_payload` is how a
connector finds out which scenario a case belongs to, since nothing is
persisted to a database that a connector could look the case up in yet
(see `simulator/scenarios.py`'s docstring).
"""

from typing import Protocol

from payment_failure_remediation_agent.models import Evidence


class Connector(Protocol):
    """One evidence source. `fetch` must never raise on a missing/unreachable
    source -- it returns Evidence(missing=True) instead, so one broken
    connector can't block the others (per DESIGN.md's independent-failure
    requirement)."""

    async def fetch(self, case_id: str, event_payload: dict[str, str]) -> Evidence: ...
