"""Diagnosis agent (docs/DESIGN.md Section 3, Sprint 3).

Real Claude-driven diagnosis: reasons over the case's `Evidence` and
produces a schema-validated `Diagnosis` via forced tool-use, never
parsed free text. Classifies the raw `decline_code` into a
`DeclineCategory` itself -- the category *definitions* are given as
instructions (this project's own triage policy, same as briefing a
human analyst on what each bucket means), but never the
`decline_code -> category` answer key from `simulator/taxonomy.py`,
which would turn "classification" into a lookup and defeat the point
of this sprint.
"""

from typing import Any, cast

from anthropic import AsyncAnthropic
from anthropic.types import MessageParam, ToolChoiceToolParam, ToolParam, ToolUseBlock
from temporalio import activity

from payment_failure_remediation_agent.config import ANTHROPIC_API_KEY, DIAGNOSIS_MODEL
from payment_failure_remediation_agent.models import DeclineCategory, Diagnosis, Evidence

SYSTEM_PROMPT = """You are the diagnosis agent in a payment-failure remediation system. \
Given evidence about one failed payment, classify it and explain the root cause.

Classify the failure's decline_category into exactly one of:
- HARD_DECLINE: the payment instrument itself is unusable (stolen/fraudulent card) or \
permanently invalid (expired card). Never safe to blind-retry; fraud cases must never be \
auto-remediated regardless of the customer's value or history.
- SOFT_DECLINE: a transient issuer/processor-side problem. Safe to retry with backoff.
- FUNDS_ISSUE: the cardholder's account lacks funds right now. Retry-eligible, but the \
right response depends on customer context (tier, backup payment method on file, prior \
remediation attempts), not just the code.

Use your own knowledge of real-world payment-processor decline codes (Stripe/Adyen-style) \
to classify the given decline_code -- you are not given a lookup table; this is a genuine \
classification judgment, not a recall task.

Write a concise root_cause explaining what happened, citing the specific evidence that \
supports it (including customer-context fields like tier or a missing backup payment \
method when they matter to understanding the case) -- but do not propose a remediation \
action; that is a later step in this system, not yours. Set confidence between 0 and 1 \
based on how much of the evidence is actually available (missing sources should lower \
it). List only the evidence sources you actually relied on in evidence_cited."""

_DIAGNOSIS_TOOL: ToolParam = {
    "name": "submit_diagnosis",
    "description": "Submit the structured diagnosis for this payment failure case.",
    "input_schema": {
        "type": "object",
        "properties": {
            "root_cause": {"type": "string"},
            "decline_category": {"type": "string", "enum": [c.value for c in DeclineCategory]},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "evidence_cited": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["root_cause", "decline_category", "confidence", "evidence_cited"],
    },
}


def _render_evidence(evidence: list[Evidence]) -> str:
    lines = []
    for item in evidence:
        if item.missing:
            lines.append(f"- {item.source}: UNAVAILABLE (connector failed)")
        else:
            lines.append(f"- {item.source}: {item.data}")
    return "\n".join(lines)


@activity.defn(name="diagnose")
async def diagnose(case_id: str, evidence: list[Evidence]) -> Diagnosis:
    client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    messages: list[MessageParam] = [
        {"role": "user", "content": f"Case {case_id} evidence:\n{_render_evidence(evidence)}"}
    ]
    tool_choice: ToolChoiceToolParam = {"type": "tool", "name": "submit_diagnosis"}
    response = await client.messages.create(
        model=DIAGNOSIS_MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=messages,
        tools=[_DIAGNOSIS_TOOL],
        tool_choice=tool_choice,
    )

    tool_use_block = None
    for block in response.content:
        if isinstance(block, ToolUseBlock):
            tool_use_block = block
            break
    assert tool_use_block is not None, "forced tool_choice did not return a tool_use block"

    result = cast(dict[str, Any], tool_use_block.input)
    return Diagnosis(
        root_cause=result["root_cause"],
        decline_category=DeclineCategory(result["decline_category"]),
        confidence=result["confidence"],
        evidence_cited=result["evidence_cited"],
    )
