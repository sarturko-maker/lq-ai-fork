"""AI Compliance domain schema — AIC-1 (fork, ADR-F057/F018).

Pure validation-contract tests for ``AiSystemInput``: the reject-don't-sanitize
invariants the guarded write path enforces BEFORE commit. No DB.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.compliance import AiSystemInput

_VALID = {
    "name": "Applicant ranking model",
    "intended_purpose": "Score and rank job applicants for a recruiter to review.",
    "lifecycle_status": "in_service",
    "development_origin": "third_party",
}


def test_valid_input_coerces_enums() -> None:
    m = AiSystemInput(**_VALID)
    assert m.name == "Applicant ranking model"
    assert m.lifecycle_status.value == "in_service"
    assert m.development_origin.value == "third_party"
    assert m.is_gpai is False
    assert m.gpai_systemic is False
    assert m.notes is None


def test_off_enum_lifecycle_rejected() -> None:
    with pytest.raises(ValidationError):
        AiSystemInput(**{**_VALID, "lifecycle_status": "retired_yesterday"})


def test_off_enum_origin_rejected() -> None:
    with pytest.raises(ValidationError):
        AiSystemInput(**{**_VALID, "development_origin": "vibes"})


def test_blank_name_rejected() -> None:
    with pytest.raises(ValidationError):
        AiSystemInput(**{**_VALID, "name": "   "})


def test_blank_intended_purpose_rejected() -> None:
    with pytest.raises(ValidationError):
        AiSystemInput(**{**_VALID, "intended_purpose": ""})


def test_extra_field_rejected() -> None:
    # extra="forbid": a risk_tier the model tries to smuggle in is exactly the
    # presence-gate violation this refuses (the tier is the engine's, not a field).
    with pytest.raises(ValidationError):
        AiSystemInput(**{**_VALID, "risk_tier": "high"})


def test_systemic_without_gpai_rejected() -> None:
    with pytest.raises(ValidationError) as exc:
        AiSystemInput(**{**_VALID, "is_gpai": False, "gpai_systemic": True})
    assert "is_gpai" in str(exc.value)


def test_systemic_with_gpai_ok() -> None:
    m = AiSystemInput(**{**_VALID, "is_gpai": True, "gpai_systemic": True})
    assert m.is_gpai is True and m.gpai_systemic is True


def test_blank_notes_normalised_to_none() -> None:
    assert AiSystemInput(**{**_VALID, "notes": "   "}).notes is None
    assert AiSystemInput(**{**_VALID, "notes": "  see model card  "}).notes == "see model card"
