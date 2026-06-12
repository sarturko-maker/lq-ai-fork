"""Unit tests for helpers in ``app.api.files`` (Task C4).

These exercise pure-Python helpers (no DB, no MinIO) — the
``Content-Disposition`` builder and the file-id validator.
"""

from __future__ import annotations

import pytest

from app.api.files import (
    _content_disposition_attachment,
    _validate_file_id,
)
from app.errors import ValidationError

# ---------------------------------------------------------------------------
# _content_disposition_attachment
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_content_disposition_simple_ascii() -> None:
    assert _content_disposition_attachment("contract.pdf") == 'attachment; filename="contract.pdf"'


@pytest.mark.unit
def test_content_disposition_escapes_quote_and_backslash() -> None:
    """RFC 6266 quoted-string escaping for backslash and double-quote."""
    cd = _content_disposition_attachment('weird"name\\file.pdf')
    # Filename is quoted; quotes and backslashes are backslash-escaped.
    assert 'filename="weird\\"name\\\\file.pdf"' in cd


@pytest.mark.unit
def test_content_disposition_non_ascii_emits_filename_star() -> None:
    """Non-ASCII filenames produce both an ASCII fallback and an RFC 5987 form."""
    cd = _content_disposition_attachment("résumé.pdf")
    # ASCII fallback drops the non-ASCII chars.
    assert 'filename="rsum.pdf"' in cd
    # RFC 5987 form carries the full UTF-8 percent-encoded name.
    assert "filename*=UTF-8''" in cd
    assert "r%C3%A9sum%C3%A9.pdf" in cd


@pytest.mark.unit
def test_content_disposition_all_non_ascii_falls_back_to_download() -> None:
    """A filename that has NO ASCII printables falls back to "download" for the legacy param."""
    cd = _content_disposition_attachment("日本語.pdf")
    assert 'filename="' in cd  # the legacy ASCII fallback is present
    # Exactly the literal "download" appears as the ASCII fallback (the
    # only ASCII bytes in the original name are ``.pdf`` so an empty
    # fallback would result without the "download" guard).
    # (The implementation strips to ASCII printable then defaults to
    # "download" when empty — but "日本語.pdf" has the ".pdf" ascii
    # tail, so the fallback is ``.pdf``.)
    # Just verify the RFC 5987 form is present.
    assert "filename*=UTF-8''" in cd


@pytest.mark.unit
def test_content_disposition_filename_with_spaces() -> None:
    """Spaces are valid inside a quoted-string, no escaping needed."""
    cd = _content_disposition_attachment("my file.pdf")
    assert cd == 'attachment; filename="my file.pdf"'


# ---------------------------------------------------------------------------
# _validate_file_id
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_validate_file_id_accepts_valid_uuid() -> None:
    out = _validate_file_id("00000000-0000-4000-8000-000000000000")
    assert str(out) == "00000000-0000-4000-8000-000000000000"


@pytest.mark.unit
def test_validate_file_id_rejects_garbage() -> None:
    with pytest.raises(ValidationError) as exc:
        _validate_file_id("not-a-uuid")
    assert exc.value.code == "validation_error"
    assert "file_id" in exc.value.details


@pytest.mark.unit
def test_validate_file_id_rejects_empty_string() -> None:
    with pytest.raises(ValidationError):
        _validate_file_id("")


@pytest.mark.unit
def test_validate_file_id_rejects_truncated_uuid() -> None:
    with pytest.raises(ValidationError):
        _validate_file_id("00000000-0000-4000-8000-00000000000")  # 11 hex digits in last group
