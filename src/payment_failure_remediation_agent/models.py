from dataclasses import dataclass, field
from enum import StrEnum


class DeclineCategory(StrEnum):
    """Decline-code taxonomy, defined by remediation semantics
    (docs/DESIGN.md Section 3, Sprint 2). Lives here, not in
    `simulator/`, because it's a core domain concept `Diagnosis` needs
    -- `simulator/taxonomy.py` keeps only `category_of`, the
    decline_code -> category answer key, which really is
    simulator-internal reference data (see that module's docstring for
    why the diagnosis agent must never read it directly)."""

    # Never blind-retry. Fraud codes always escalate to a human, no
    # matter the customer; expired-card codes are only fixable via a
    # backup card.
    HARD_DECLINE = "HARD_DECLINE"
    # Safe to retry with backoff -- the "boring" bucket, included to
    # prove the system doesn't over-engineer every path.
    SOFT_DECLINE = "SOFT_DECLINE"
    # Retry-eligible, but *how* to retry depends on customer context --
    # the category the scripted scenarios lean on.
    FUNDS_ISSUE = "FUNDS_ISSUE"


class CaseStatus(StrEnum):
    CASE_CREATED = "CASE_CREATED"
    EVIDENCE_COLLECTION = "EVIDENCE_COLLECTION"
    DIAGNOSIS = "DIAGNOSIS"
    RUNBOOK_RETRIEVAL = "RUNBOOK_RETRIEVAL"
    HUMAN_RUNBOOK_AUTHORING = "HUMAN_RUNBOOK_AUTHORING"
    POLICY_RISK_CHECK = "POLICY_RISK_CHECK"
    REMEDIATION_PROPOSED = "REMEDIATION_PROPOSED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    EXECUTING = "EXECUTING"
    VERIFICATION = "VERIFICATION"
    RESOLUTION_ANALYSIS = "RESOLUTION_ANALYSIS"
    REINVESTIGATION = "REINVESTIGATION"
    CASE_CLOSED = "CASE_CLOSED"
    CASE_ESCALATED = "CASE_ESCALATED"


@dataclass
class CaseInput:
    case_id: str
    event_payload: dict[str, str]
    # Injectable hook used only by branch tests to force a non-happy-path
    # outcome out of an otherwise-hardcoded stub activity. None on the real
    # happy-path demo run.
    force_scenario: str | None = None


# Evidence values are scalar-typed (not just str) so numeric/boolean
# fields (amount, has_backup_payment_method, ...) don't need re-parsing
# by every downstream consumer -- see docs/DESIGN.md Section 3.
EvidenceValue = str | int | float | bool


@dataclass
class Evidence:
    source: str
    data: dict[str, EvidenceValue]
    missing: bool = False


@dataclass
class Diagnosis:
    root_cause: str
    # Structured, not just free text in root_cause -- Sprint 5's policy
    # engine needs a deterministic field to hard-block HARD_DECLINE cases
    # on, regardless of LLM confidence (docs/DESIGN.md Section 3).
    decline_category: DeclineCategory
    confidence: float
    evidence_cited: list[str] = field(default_factory=list)


@dataclass
class RunbookEntry:
    entry_id: str
    title: str
    recommended_action: str
    match_found: bool
    # Cosine similarity of the best candidate against the diagnosis, set
    # by the real Sprint 4 retrieval activity; None for entries that
    # never went through similarity search (human-authored via the
    # `author_runbook` signal, or older force_scenario test stubs).
    similarity_score: float | None = None


@dataclass
class RemediationProposal:
    action_name: str
    rationale: str
    risk_tier: str  # "auto" | "low" | "medium" | "high"


@dataclass
class PolicyDecision:
    approved: bool
    reason: str
    rule_fired: str


@dataclass
class ApprovalDecision:
    decision: str  # "approve" | "reject_try_different" | "reject_no_automation"
    approver: str
    reason: str = ""


@dataclass
class ActionResult:
    success: bool
    detail: str


@dataclass
class Verification:
    resolved: bool
    detail: str


@dataclass
class ResolutionAnalysis:
    new_info_found: bool
    summary: str


@dataclass
class RunbookReviewInput:
    case_id: str
    proposed_entry: RunbookEntry


@dataclass
class RunbookReviewDecision:
    decision: str  # "approve" | "request_changes" | "reject"
    reviewer: str
    comments: str = ""
