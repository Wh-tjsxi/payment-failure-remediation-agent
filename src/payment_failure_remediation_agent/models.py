from dataclasses import dataclass, field
from enum import StrEnum


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


@dataclass
class Evidence:
    source: str
    data: dict[str, str]
    missing: bool = False


@dataclass
class Diagnosis:
    root_cause: str
    confidence: float
    evidence_cited: list[str] = field(default_factory=list)


@dataclass
class RunbookEntry:
    entry_id: str
    title: str
    recommended_action: str
    match_found: bool


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
