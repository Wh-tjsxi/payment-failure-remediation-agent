"""Freeze real `diagnose` outputs for every simulator scenario.

The retrieval eval (scripts/eval_runbook_retrieval.py) uses these as its
"real query" examples so it can run offline and deterministically -- no
per-run LLM cost or nondeterminism. Re-run this only when the diagnosis
prompt/model changes and you want the fixtures to reflect the new output
style (that's also exactly when retrieval quality can shift).

Makes one real Anthropic call per scenario (needs ANTHROPIC_API_KEY):
    .venv/bin/python scripts/capture_diagnosis_fixtures.py
"""

import asyncio
import json
from pathlib import Path

from payment_failure_remediation_agent.activities.diagnosis_agent import diagnose
from payment_failure_remediation_agent.activities.evidence_connectors.case_history import (
    CaseHistoryConnector,
)
from payment_failure_remediation_agent.activities.evidence_connectors.customer_data import (
    CustomerDataConnector,
)
from payment_failure_remediation_agent.activities.evidence_connectors.gateway import (
    GatewayConnector,
)
from payment_failure_remediation_agent.config import DIAGNOSIS_MODEL
from payment_failure_remediation_agent.simulator.scenarios import SCENARIOS

OUTPUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "diagnoses_captured.json"


async def capture() -> None:
    captured = []
    for name in SCENARIOS:
        payload = {"scenario": name}
        evidence = [
            await GatewayConnector().fetch(name, payload),
            await CustomerDataConnector().fetch(name, payload),
            await CaseHistoryConnector().fetch(name, payload),
        ]
        diagnosis = await diagnose(name, evidence)
        captured.append(
            {
                "scenario": name,
                "decline_category": diagnosis.decline_category.value,
                "root_cause": diagnosis.root_cause,
                "confidence": diagnosis.confidence,
                "evidence_cited": diagnosis.evidence_cited,
            }
        )
        print(f"captured {name}: {diagnosis.decline_category.value}")
    OUTPUT.write_text(
        json.dumps({"model": DIAGNOSIS_MODEL, "diagnoses": captured}, indent=2) + "\n"
    )
    print(f"wrote {OUTPUT}")


if __name__ == "__main__":
    asyncio.run(capture())
