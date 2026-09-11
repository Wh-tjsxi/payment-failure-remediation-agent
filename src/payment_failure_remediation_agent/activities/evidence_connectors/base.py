"""Shared shape for evidence connectors.

docs/DESIGN.md Section 2 calls for a "pluggable Connector interface" where
each evidence source (gateway, observability, customer data, case history)
fails independently without blocking the others. In Sprint 1 every
connector below is a stub that returns fixed fixture data -- the real
per-source logic (Sprint 2) will implement `Connector.fetch`, but the
*shape* callers depend on (Evidence, missing_source flag) is real now so
nothing has to change when Sprint 2 swaps the stub bodies out.
"""

from typing import Protocol

from payment_failure_remediation_agent.models import Evidence


class Connector(Protocol):
    """One evidence source. `fetch` must never raise on a missing/unreachable
    source -- it returns Evidence(missing=True) instead, so one broken
    connector can't block the others (per DESIGN.md's independent-failure
    requirement)."""

    async def fetch(self, case_id: str) -> Evidence: ...
