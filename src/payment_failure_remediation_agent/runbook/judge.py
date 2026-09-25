"""The Claude judge that picks one runbook entry for a diagnosis, or NONE.

Vector search only proposes candidates; deciding whether one actually
applies (backup card yes/no, customer tier, prior attempts, fraud) is a
judgment task that similarity scores measurably can't do -- see
debugged_log.md sections 4-5. The prompt and tool schema here are exactly
what scripts/eval_runbook_judges.py measured (18/18 right action, 12/12
correctly NONE), so change them only by re-running that eval.
"""

from typing import Any, cast

from anthropic import AsyncAnthropic
from anthropic.types import ToolChoiceToolParam, ToolParam, ToolUseBlock

from payment_failure_remediation_agent.config import RUNBOOK_JUDGE_MODEL
from payment_failure_remediation_agent.runbook.corpus import CorpusEntry

NONE = "NONE"

JUDGE_SYSTEM_PROMPT = """You match one failed-payment diagnosis to at most one runbook entry.

Pick an entry only if its situation fits EVERY detail the diagnosis states: the decline \
reason, whether a backup payment method is on file, the customer tier, and any prior \
remediation attempts. If no entry fits all of them, answer NONE. A near miss is NONE, \
not a best guess."""


def judge_tool(entries: list[CorpusEntry]) -> ToolParam:
    return {
        "name": "select_entry",
        "description": "Choose the one runbook entry that fits, or NONE.",
        "input_schema": {
            "type": "object",
            "properties": {
                # Reason comes first so the model thinks before it commits.
                "reason": {"type": "string"},
                "entry_id": {"type": "string", "enum": [e.entry_id for e in entries] + [NONE]},
            },
            "required": ["reason", "entry_id"],
        },
    }


def render_judge_message(query_text: str, entries: list[CorpusEntry]) -> str:
    listing = "\n".join(f"- {e.entry_id}: {e.situation}" for e in entries)
    return f"Runbook entries:\n{listing}\n\nDiagnosis:\n{query_text}"


async def pick_entry(
    client: AsyncAnthropic, query_text: str, entries: list[CorpusEntry]
) -> tuple[str | None, str]:
    """Returns (entry_id or None for NONE, the judge's stated reason)."""
    tool_choice: ToolChoiceToolParam = {"type": "tool", "name": "select_entry"}
    response = await client.messages.create(
        model=RUNBOOK_JUDGE_MODEL,
        max_tokens=512,
        system=JUDGE_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": render_judge_message(query_text, entries)}],
        tools=[judge_tool(entries)],
        tool_choice=tool_choice,
    )
    block = next(b for b in response.content if isinstance(b, ToolUseBlock))
    result = cast(dict[str, Any], block.input)
    chosen = result["entry_id"]
    return (None if chosen == NONE else chosen), result["reason"]
