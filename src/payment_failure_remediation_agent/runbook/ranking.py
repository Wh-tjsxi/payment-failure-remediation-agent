"""Pure runbook ranking + match decision (no DB, no embedding model).

Kept separate from the activity so the ranking logic can be unit-tested
and evaluated offline: `runbook_retrieval.py` only supplies vectors and
candidates; everything that decides *which* entry wins, and *whether it
counts as a match*, lives here.
"""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Candidate:
    entry_id: str
    title: str
    category: str
    recommended_action: str
    embedding: np.ndarray


@dataclass(frozen=True)
class Ranked:
    candidate: Candidate
    score: float  # cosine similarity, same quantity as pgvector's 1 - (a <=> b)


@dataclass(frozen=True)
class Decision:
    match_found: bool
    best: Ranked | None
    # Gap between the best candidate and the best candidate recommending a
    # *different action*. None when every candidate agrees on the action.
    # Two near-tied entries that recommend the same action aren't
    # ambiguous, so they don't shrink this.
    action_margin: float | None


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def rank_candidates(
    query: np.ndarray, candidates: list[Candidate], category: str | None = None
) -> list[Ranked]:
    """Rank by cosine similarity, best first. When `category` is given,
    only candidates in that category are considered (hard pre-filter)."""
    pool = [c for c in candidates if category is None or c.category == category]
    ranked = [Ranked(c, _cosine(query, c.embedding)) for c in pool]
    return sorted(ranked, key=lambda r: r.score, reverse=True)


def decide(ranked: list[Ranked], threshold: float, min_action_margin: float = 0.0) -> Decision:
    """A match requires the best score to clear `threshold` AND to beat
    the nearest differently-actioned candidate by `min_action_margin`."""
    if not ranked:
        return Decision(match_found=False, best=None, action_margin=None)
    best = ranked[0]
    rival = next(
        (
            r
            for r in ranked[1:]
            if r.candidate.recommended_action != best.candidate.recommended_action
        ),
        None,
    )
    margin = None if rival is None else best.score - rival.score
    ok_margin = margin is None or margin >= min_action_margin
    return Decision(
        match_found=best.score >= threshold and ok_margin, best=best, action_margin=margin
    )
