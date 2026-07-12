"""Adversarial-review schemas — ADV-1 (fork, ADR-F084): the hostile-reader output boundary.

The model-free half of the adversarial-review pass. The ``adversarial_review`` tool routes ONE
gateway chat completion whose output is UNTRUSTED model text; code disposes against these schemas
BEFORE anything is returned to the lead or audited (reject-not-truncate, ADR-F018 shape — a
malformed proposal is rejected back with the reason, never partially accepted). This module imports
nothing from the agent/runtime layers and touches no I/O, so the caps are unit-testable with no
model and no DB.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

# Bounds for one review proposal. A hostile read of one document that claims hundreds of
# findings is malformed, not thorough; each finding stays short so the rendered checklist
# (and the lead's context) stays bounded.
ADVERSARIAL_MAX_FINDINGS = 25
ADVERSARIAL_CLAUSE_MAX_CHARS = 300
ADVERSARIAL_ISSUE_MAX_CHARS = 600
ADVERSARIAL_SUGGESTION_MAX_CHARS = 600
ADVERSARIAL_OVERALL_MAX_CHARS = 1_000
# The optional focus the lead may pass ("liability and indemnity") — a short steer, not a brief.
ADVERSARIAL_FOCUS_MAX_CHARS = 300


class FindingSeverity(StrEnum):
    """How much a finding matters — drives the checklist ordering + the audit counts."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class FindingKind(StrEnum):
    """The hostile-reader taxonomy (ADR-F084) — the four ways a near-final draft fails."""

    OVER_REACH = "over_reach"  # we ask for more than the deal supports (invites pushback)
    UNDER_PROTECTION = "under_protection"  # a risk to our side left unaddressed
    INCONSISTENCY = "inconsistency"  # the document contradicts itself / a defined term
    GAP = "gap"  # a material head that should be covered and is absent


class AdversarialFinding(BaseModel):
    """One hostile-reader finding, anchored to the clause it attacks."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    severity: FindingSeverity
    kind: FindingKind
    # A short verbatim quote anchoring the finding to the document (or the nearest
    # heading for a GAP). Kept short — an anchor, not a reproduction.
    clause: str = Field(min_length=1, max_length=ADVERSARIAL_CLAUSE_MAX_CHARS)
    issue: str = Field(min_length=1, max_length=ADVERSARIAL_ISSUE_MAX_CHARS)
    suggestion: str | None = Field(default=None, max_length=ADVERSARIAL_SUGGESTION_MAX_CHARS)


class AdversarialReviewResult(BaseModel):
    """The validated hostile-reader proposal: bounded findings + a one-paragraph verdict."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    findings: list[AdversarialFinding] = Field(
        default_factory=list, max_length=ADVERSARIAL_MAX_FINDINGS
    )
    overall: str = Field(min_length=1, max_length=ADVERSARIAL_OVERALL_MAX_CHARS)
