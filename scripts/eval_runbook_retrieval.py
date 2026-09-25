"""Offline eval of runbook retrieval quality (docs/DESIGN.md Section 3, Sprint 4).

Runs several retrieval "variants" over the same labelled queries and prints
how well each one finds the right runbook entry -- so every design choice
(what text gets embedded, a query prefix, a category pre-filter) is
*measured*, not assumed. No database, no LLM, no API key: the corpus and
queries are embedded in memory with the local fastembed model.

Queries come from tests/fixtures/:
  - diagnoses_captured.json        real Claude diagnoses (scripts/capture_diagnosis_fixtures.py)
  - retrieval_queries_authored.json hand-written paraphrases + hard negatives
  - retrieval_queries_user.json     your own queries (empty until you add some)

Each query is labelled with the entry ids that count as correct, or none
at all when NO entry should match (fraud, high-value tier, uncovered
failures). Those "should not match" queries are as important as the
positive ones: a wrong match is worse than routing to a human.

    .venv/bin/python scripts/eval_runbook_retrieval.py
"""

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from fastembed import TextEmbedding

from payment_failure_remediation_agent.config import EMBEDDING_MODEL
from payment_failure_remediation_agent.runbook.corpus import CORPUS
from payment_failure_remediation_agent.runbook.ranking import Candidate, decide, rank_candidates

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"

# BGE's own recommended instruction for retrieval queries (documents get none).
# fastembed does NOT add this for us -- query_embed() is identical to embed().
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


@dataclass(frozen=True)
class Query:
    id: str
    split: str  # "dev" (ok to tune on) or "test" (held out, only reported)
    category: str
    text: str
    expected_ids: tuple[str, ...]  # empty => nothing should match
    expected_action: str | None


@dataclass(frozen=True)
class Variant:
    name: str
    doc_field: str  # which corpus text gets embedded: "body" or "situation"
    query_prefix: str
    filter_by_category: bool


# Each variant changes one thing relative to the previous one.
VARIANTS = [
    Variant("A  baseline (embed full body)", "body", "", False),
    Variant("B  embed situation only", "situation", "", False),
    Variant("C  B + BGE query prefix", "situation", BGE_QUERY_PREFIX, False),
    Variant("D  C + category pre-filter", "situation", BGE_QUERY_PREFIX, True),
]


def _query_text(category: str, root_cause: str) -> str:
    # Same "CATEGORY: text" shape the corpus texts use.
    return f"{category}: {root_cause}"


def load_queries() -> list[Query]:
    authored = json.loads((FIXTURES / "retrieval_queries_authored.json").read_text())
    captured = json.loads((FIXTURES / "diagnoses_captured.json").read_text())
    user = json.loads((FIXTURES / "retrieval_queries_user.json").read_text())

    queries = []
    # Real diagnoses: labels come from the scenario -> expected-entry map.
    for d in captured["diagnoses"]:
        label = authored["captured_labels"][d["scenario"]]
        queries.append(
            Query(
                id=f"real:{d['scenario']}",
                split="dev",
                category=d["decline_category"],
                text=_query_text(d["decline_category"], d["root_cause"]),
                expected_ids=tuple(label["expected_entry_ids"]),
                expected_action=label["expected_action"],
            )
        )
    for q in authored["queries"] + user["queries"]:
        queries.append(
            Query(
                id=q["id"],
                split=q["split"],
                category=q["decline_category"],
                text=_query_text(q["decline_category"], q["root_cause"]),
                expected_ids=tuple(q["expected_entry_ids"]),
                expected_action=q["expected_action"],
            )
        )
    return queries


def embed_all(model: TextEmbedding, texts: list[str]) -> list[np.ndarray]:
    return [np.array(v) for v in model.embed(texts)]


def rank_all(model: TextEmbedding, variant: Variant, queries: list[Query]) -> list[list]:
    """For one variant, return the ranked candidate list for every query."""
    doc_texts = [getattr(entry, variant.doc_field) for entry in CORPUS]
    candidates = [
        Candidate(e.entry_id, e.title, e.category, e.recommended_action, vec)
        for e, vec in zip(CORPUS, embed_all(model, doc_texts), strict=True)
    ]
    query_vecs = embed_all(model, [variant.query_prefix + q.text for q in queries])
    return [
        rank_candidates(vec, candidates, q.category if variant.filter_by_category else None)
        for q, vec in zip(queries, query_vecs, strict=True)
    ]


def position_of_correct_entry(query: Query, ranked: list) -> int | None:
    """1-based rank of the first correct entry, or None if none is in the list."""
    for position, r in enumerate(ranked, start=1):
        if r.candidate.entry_id in query.expected_ids:
            return position
    return None


def top_score(ranked: list) -> float:
    return ranked[0].score if ranked else 0.0


def print_variant_report(variant: Variant, queries: list[Query], all_ranked: list[list]) -> None:
    print(f"\n=== {variant.name} ===")

    for split in ("dev", "test"):
        rows = [(q, r) for q, r in zip(queries, all_ranked, strict=True) if q.split == split]
        positives = [(q, r) for q, r in rows if q.expected_ids]
        negatives = [(q, r) for q, r in rows if not q.expected_ids]
        if not rows:
            continue

        positions = [position_of_correct_entry(q, r) for q, r in positives]
        hit1 = sum(1 for p in positions if p == 1)
        recall3 = sum(1 for p in positions if p is not None and p <= 3)
        mrr = sum(1 / p for p in positions if p) / len(positives)
        action1 = sum(1 for q, r in positives if r and r[0].candidate.recommended_action == q.expected_action)
        worst_negative = max((top_score(r) for _, r in negatives), default=0.0)

        print(
            f"  {split:<4} positives n={len(positives)}: hit@1 {hit1}/{len(positives)}  "
            f"recall@3 {recall3}/{len(positives)}  MRR {mrr:.2f}  action@1 {action1}/{len(positives)}"
            f"   | negatives n={len(negatives)}: highest top-1 score {worst_negative:.3f}"
        )

    # Can ANY score threshold separate right answers from wrong-to-match ones?
    right = [top_score(r) for q, r in zip(queries, all_ranked, strict=True)
             if q.expected_ids and r and r[0].candidate.recommended_action == q.expected_action]
    wrong = [top_score(r) for q, r in zip(queries, all_ranked, strict=True) if not q.expected_ids]
    print(
        f"  score separation: correct top-1 scores min {min(right):.3f} | "
        f"should-not-match top-1 scores max {max(wrong):.3f} | "
        f"gap {min(right) - max(wrong):+.3f} (positive gap => a threshold can separate them)"
    )

    print("  threshold sweep (all queries): false-accept = should-not-match but matched; "
          "false-reject = should-match but missed/wrong action")
    for threshold in np.arange(0.50, 0.96, 0.05):
        false_accept = false_reject = 0
        for q, r in zip(queries, all_ranked, strict=True):
            decision = decide(r, threshold=float(threshold))
            if not q.expected_ids and decision.match_found:
                false_accept += 1
            if q.expected_ids and not (
                decision.match_found
                and decision.best is not None
                and decision.best.candidate.recommended_action == q.expected_action
            ):
                false_reject += 1
        print(f"    threshold {threshold:.2f}: false-accept {false_accept:>2}  false-reject {false_reject:>2}")

    print("  per-query detail (score = top-1 cosine; margin = gap to nearest different-action entry)")
    for q, r in zip(queries, all_ranked, strict=True):
        decision = decide(r, threshold=0.0)
        got = decision.best.candidate.entry_id if decision.best else "-"
        margin = f"{decision.action_margin:.3f}" if decision.action_margin is not None else "  n/a"
        expected = "/".join(q.expected_ids) or "NONE"
        ok = "ok " if (got in q.expected_ids if q.expected_ids else False) else ("-- " if not q.expected_ids else "BAD")
        print(f"    [{ok}] {q.split:<4} {q.id:<44} expected {expected:<15} got {got:<8} "
              f"score {top_score(r):.3f} margin {margin}")


def main() -> None:
    model = TextEmbedding(model_name=EMBEDDING_MODEL)
    queries = load_queries()
    print(f"model {EMBEDDING_MODEL}; corpus {len(CORPUS)} entries; {len(queries)} queries")
    print("(per-query marker: ok = correct entry ranked first, BAD = wrong entry first, "
          "-- = should-not-match query, judged by the threshold sweep instead)")
    for variant in VARIANTS:
        print_variant_report(variant, queries, rank_all(model, variant, queries))


if __name__ == "__main__":
    main()
