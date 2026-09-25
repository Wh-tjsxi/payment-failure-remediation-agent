"""Second retrieval experiment: can something smarter than top-1 cosine decide?

scripts/eval_runbook_retrieval.py showed that vector search finds the right
entry within the top 3 almost every time (recall@3 ~100%) but cannot pick
between near-identical entries (backup card yes/no) or say "no match".
This script tries three ways to close that gap, on the SAME 30 queries:

  E  vector top-3 -> Claude picks one entry, or NONE
  F  no vectors: Claude sees the whole corpus and picks one, or NONE
  G  vector top-5 -> local cross-encoder reranker picks the top one
     (a reranker only scores; it cannot answer NONE, so we only look at
     whether its scores can separate right answers from should-not-match)

Scoring is by *action* (not entry id), and wrong
picks are broken down by how risky the wrongly chosen action is -- a wrong
low-risk pick is tolerable, a wrong "switch to the backup card" is not.

E and F make real Anthropic calls (about 60 in total, needs ANTHROPIC_API_KEY):
    .venv/bin/python scripts/eval_runbook_judges.py
"""

from typing import Any, cast

from anthropic import Anthropic
from anthropic.types import ToolChoiceToolParam, ToolUseBlock
from eval_runbook_retrieval import VARIANTS, Query, load_queries, rank_all
from fastembed import TextEmbedding
from fastembed.rerank.cross_encoder import TextCrossEncoder

from payment_failure_remediation_agent.config import (
    ANTHROPIC_API_KEY,
    EMBEDDING_MODEL,
    RUNBOOK_JUDGE_MODEL,
)
from payment_failure_remediation_agent.runbook.corpus import CORPUS, CORPUS_BY_ID, CorpusEntry
from payment_failure_remediation_agent.runbook.judge import (
    JUDGE_SYSTEM_PROMPT,
    NONE,
    judge_tool,
    render_judge_message,
)

RERANKER_MODEL = "Xenova/ms-marco-MiniLM-L-6-v2"

# PROVISIONAL risk labels, only used to grade this experiment. The real
# per-action risk tiers belong to the Sprint 5 policy engine.
ACTION_RISK = {
    "retry_payment": "low",
    "request_card_update": "low",  # customer-facing message, no money moves
    "switch_backup_payment_method": "high",  # charges a different instrument
}

ENTRY_BY_ID = CORPUS_BY_ID

def judge(client: Anthropic, query: Query, entries: list[CorpusEntry]) -> str | None:
    """Ask Claude to pick one of `entries` for this query. None means it answered NONE.

    Prompt, tool schema and message come from the production judge
    (runbook/judge.py) so this eval always measures exactly what ships.
    """
    tool_choice: ToolChoiceToolParam = {"type": "tool", "name": "select_entry"}
    response = client.messages.create(
        model=RUNBOOK_JUDGE_MODEL,
        max_tokens=512,
        system=JUDGE_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": render_judge_message(query.text, entries)}],
        tools=[judge_tool(entries)],
        tool_choice=tool_choice,
    )
    block = next(b for b in response.content if isinstance(b, ToolUseBlock))
    chosen = cast(dict[str, Any], block.input)["entry_id"]
    return None if chosen == NONE else chosen


def summarize(name: str, queries: list[Query], chosen: list[str | None]) -> None:
    """Grade each query's chosen entry id (None = 'no match') by action and risk."""
    print(f"\n=== {name} ===")
    right = missed = correct_none = 0
    wrong_positive: list[str] = []  # positives given a different action
    false_accept: list[str] = []  # should-not-match queries that got an entry
    for query, pick in zip(queries, chosen, strict=True):
        picked_action = ENTRY_BY_ID[pick].recommended_action if pick else None
        if query.expected_ids:
            if pick is None:
                missed += 1
                verdict = "MISSED (said NONE)"
            elif picked_action == query.expected_action:
                right += 1
                verdict = "ok"
            else:
                wrong_positive.append(f"{query.id}->{picked_action}")
                verdict = f"WRONG ACTION ({ACTION_RISK[str(picked_action)]} risk)"
        elif pick is None:
            correct_none += 1
            verdict = "ok (correctly NONE)"
        else:
            false_accept.append(f"{query.id}->{picked_action}")
            verdict = f"FALSE ACCEPT ({ACTION_RISK[str(picked_action)]} risk)"
        print(f"    {query.split:<4} {query.id:<44} picked {pick or 'NONE':<8} {verdict}")

    positives = sum(1 for q in queries if q.expected_ids)
    negatives = len(queries) - positives
    high_risk_errors = [
        e for e in wrong_positive + false_accept if ACTION_RISK[e.split("->")[1]] == "high"
    ]
    print(f"  should-match:     right action {right}/{positives}, missed {missed}, "
          f"wrong action {len(wrong_positive)}")
    print(f"  should-not-match: correctly NONE {correct_none}/{negatives}, "
          f"false accepts {len(false_accept)}")
    print(f"  HIGH-RISK errors (the ones that matter most): {len(high_risk_errors)} "
          f"{high_risk_errors}")


def run_reranker(queries: list[Query], vector_ranked: list[list]) -> None:
    """Cross-encoder rescoring of the vector top-5. Reports accuracy and score separation."""
    print(f"\n=== G  vector top-5 -> cross-encoder reranker ({RERANKER_MODEL}) ===")
    reranker = TextCrossEncoder(model_name=RERANKER_MODEL)
    correct_scores: list[float] = []
    negative_scores: list[float] = []
    right = 0
    positives = 0
    for query, ranked in zip(queries, vector_ranked, strict=True):
        top5 = ranked[:5]
        documents = [ENTRY_BY_ID[r.candidate.entry_id].situation for r in top5]
        scores = list(reranker.rerank(query.text, documents))
        best = max(range(len(top5)), key=lambda i: scores[i])
        best_entry = top5[best].candidate
        if query.expected_ids:
            positives += 1
            ok = best_entry.recommended_action == query.expected_action
            right += ok
            if ok:
                correct_scores.append(scores[best])
            verdict = "ok" if ok else f"WRONG ACTION ({ACTION_RISK[best_entry.recommended_action]} risk)"
        else:
            negative_scores.append(scores[best])
            verdict = "(should-not-match: score only)"
        print(f"    {query.split:<4} {query.id:<44} picked {best_entry.entry_id:<8} "
              f"score {scores[best]:+.2f}  {verdict}")
    print(f"  should-match: right action {right}/{positives}")
    print(f"  score separation: correct picks min {min(correct_scores):+.2f} | "
          f"should-not-match picks max {max(negative_scores):+.2f} | "
          f"gap {min(correct_scores) - max(negative_scores):+.2f} "
          f"(positive gap => a threshold can separate them)")


def main() -> None:
    queries = load_queries()
    embedder = TextEmbedding(model_name=EMBEDDING_MODEL)
    # Variant B from the first eval: embed the "situation" text, plain embed().
    vector_ranked = rank_all(embedder, VARIANTS[1], queries)
    client = Anthropic(api_key=ANTHROPIC_API_KEY)

    top3_choices = [
        judge(client, q, [ENTRY_BY_ID[r.candidate.entry_id] for r in ranked[:3]])
        for q, ranked in zip(queries, vector_ranked, strict=True)
    ]
    summarize("E  vector top-3 -> Claude judge", queries, top3_choices)

    whole_corpus_choices = [judge(client, q, CORPUS) for q in queries]
    summarize("F  whole corpus -> Claude judge (no vectors)", queries, whole_corpus_choices)

    run_reranker(queries, vector_ranked)


if __name__ == "__main__":
    main()
