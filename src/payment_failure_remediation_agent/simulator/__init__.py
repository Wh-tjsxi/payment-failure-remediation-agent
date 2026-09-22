"""Payment Gateway Simulator (docs/DESIGN.md Sections 2-3, Sprint 2).

Stands in for a real processor/merchant data store -- no real bank or
customer data is ever used. Evidence connectors ask this package for a
named scenario's fixtures rather than calling out to anything external
or querying a database; see `scenarios.py` for why (Sprint 1's fast,
DB-free happy-path test is what forced that design).
"""

from payment_failure_remediation_agent.simulator.scenarios import (
    DEFAULT_SCENARIO_NAME,
    Scenario,
    get_scenario,
)
from payment_failure_remediation_agent.simulator.taxonomy import DeclineCategory, category_of

__all__ = [
    "DEFAULT_SCENARIO_NAME",
    "DeclineCategory",
    "Scenario",
    "category_of",
    "get_scenario",
]
