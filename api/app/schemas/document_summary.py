"""Document-summary schema — WORKSPACE-1 (fork, ADR-F082): the per-document summary write boundary.

The model-free half of the workspace-awareness auto-write path. The agent's
``record_document_summary`` tool is a code-validated write (ADR-F018 shape): after the agent reads a
document it PROPOSES a short summary, code DISPOSES against this schema BEFORE commit — a pass is
written against the file, a failure is rejected back to the model with the reason (reject, never
truncate). This module imports nothing from the agent/runtime layers and touches no I/O, so the caps
are unit-testable with no model and no DB.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

# A document summary is a SHORT one/two-sentence description of what the document is
# (reject-not-truncate on overflow). Kept brief so an injected "documents in this matter" block
# (WORKSPACE-2) stays within the prompt budget even for a matter with many files.
DOCUMENT_SUMMARY_MAX_CHARS = 600
# A filename the model passes to address a document — mirrors the estimate_read_cost filename cap.
DOCUMENT_NAME_MAX_CHARS = 512


class RecordDocumentSummaryInput(BaseModel):
    """Validate one ``record_document_summary`` proposal.

    ``document_name`` names the matter file to summarise (exactly as shown by search_documents);
    ``summary`` is the short description. Both are stripped and must be non-blank; the summary must
    fit the cap — an over-budget summary is rejected so the model shortens it rather than the store
    truncating. Only A-class content args appear here — the resolved file, run id and timestamp are
    B-class, set by the tool.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    document_name: str = Field(min_length=1, max_length=DOCUMENT_NAME_MAX_CHARS)
    summary: str = Field(min_length=1, max_length=DOCUMENT_SUMMARY_MAX_CHARS)
