"""Unit tests for the chat schema helpers (Task C3).

Covers the small pure functions:

* :func:`usd_to_micros` / :func:`micros_to_usd` — round-trip with
  edge cases (None, 0, negative, large floats, fractional cents).
* :func:`derive_chat_title` — first-user-message auto-rename
  truncation logic.
* :func:`encode_cursor` / :func:`decode_cursor` — opaque base64
  keyset cursor.
"""

from __future__ import annotations

import math
import uuid
from datetime import UTC, datetime

import pytest

from app.schemas.chats import (
    AUTO_RENAME_MAX_CHARS,
    Cursor,
    decode_cursor,
    derive_chat_title,
    encode_cursor,
    micros_to_usd,
    usd_to_micros,
)

# ---------------------------------------------------------------------------
# Cost micros conversion
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUsdToMicros:
    def test_none_returns_none(self) -> None:
        assert usd_to_micros(None) is None

    def test_zero_returns_zero(self) -> None:
        # 0.0 must NOT collapse to None — operators want to see "we
        # routed this for free" distinctly from "we don't know".
        assert usd_to_micros(0.0) == 0

    def test_round_trip_typical_value(self) -> None:
        usd = 0.00025  # 250 micros
        assert usd_to_micros(usd) == 250
        assert micros_to_usd(250) == pytest.approx(0.00025, rel=1e-9)

    def test_round_trip_large_value(self) -> None:
        usd = 12.345678
        micros = usd_to_micros(usd)
        assert micros == 12_345_678
        assert micros_to_usd(micros) == pytest.approx(12.345678, rel=1e-9)

    def test_negative_value_preserves_sign(self) -> None:
        # The gateway shouldn't emit a negative cost, but if it does
        # we preserve the sign rather than silently coercing.
        assert usd_to_micros(-0.001) == -1_000

    def test_round_to_nearest_micro(self) -> None:
        # 0.0000004999 rounds to 0 (below 0.5 micros).
        # 0.0000005001 rounds to 1.
        assert usd_to_micros(0.0000004999) == 0
        assert usd_to_micros(0.0000005001) == 1

    def test_micros_to_usd_none(self) -> None:
        assert micros_to_usd(None) is None

    def test_micros_to_usd_zero(self) -> None:
        assert micros_to_usd(0) == 0.0

    def test_round_trip_loses_no_precision_at_micros(self) -> None:
        # Any USD value with at most 6 decimal places round-trips exactly.
        for usd in (0.000001, 0.123456, 1.0, 99.999999):
            micros = usd_to_micros(usd)
            assert micros is not None
            assert micros_to_usd(micros) == pytest.approx(usd, rel=1e-9)


# ---------------------------------------------------------------------------
# Auto-rename
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDeriveChatTitle:
    def test_empty_string_returns_default(self) -> None:
        assert derive_chat_title("") == "New chat"

    def test_only_whitespace_returns_default(self) -> None:
        assert derive_chat_title("   \n\n\t   ") == "New chat"

    def test_short_message_returned_verbatim(self) -> None:
        assert derive_chat_title("hello world") == "hello world"

    def test_first_line_only(self) -> None:
        # Multi-line messages take only the first non-empty line.
        msg = "Line one\nLine two\nLine three"
        assert derive_chat_title(msg) == "Line one"

    def test_skip_blank_first_line(self) -> None:
        # Leading blank lines are skipped to find the first content.
        msg = "\n\n   \nReal first line\nLine two"
        assert derive_chat_title(msg) == "Real first line"

    def test_collapse_whitespace(self) -> None:
        msg = "tabs\t\there  and    spaces"
        assert derive_chat_title(msg) == "tabs here and spaces"

    def test_truncated_with_ellipsis(self) -> None:
        long = "a" * (AUTO_RENAME_MAX_CHARS + 50)
        title = derive_chat_title(long)
        assert len(title) == AUTO_RENAME_MAX_CHARS
        assert title.endswith("…")

    def test_exactly_max_chars_no_ellipsis(self) -> None:
        msg = "b" * AUTO_RENAME_MAX_CHARS
        title = derive_chat_title(msg)
        assert title == msg
        assert "…" not in title

    def test_just_over_max_chars_truncated(self) -> None:
        msg = "c" * (AUTO_RENAME_MAX_CHARS + 1)
        title = derive_chat_title(msg)
        assert len(title) == AUTO_RENAME_MAX_CHARS
        assert title.endswith("…")

    def test_crlf_line_terminator_handled(self) -> None:
        msg = "Windows line\r\nNext line"
        assert derive_chat_title(msg) == "Windows line"


# ---------------------------------------------------------------------------
# Cursor encode/decode
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCursor:
    def test_round_trip(self) -> None:
        when = datetime(2026, 5, 8, 12, 34, 56, tzinfo=UTC)
        ident = uuid.UUID("00000000-0000-4000-8000-000000000001")

        encoded = encode_cursor(when, ident)
        decoded = decode_cursor(encoded)

        assert decoded.created_at == when
        assert decoded.id == ident

    def test_cursor_is_opaque_url_safe(self) -> None:
        when = datetime(2026, 5, 8, 12, 34, 56, tzinfo=UTC)
        ident = uuid.uuid4()
        encoded = encode_cursor(when, ident)
        # No URL-unsafe characters; no padding.
        assert "+" not in encoded
        assert "/" not in encoded
        assert not encoded.endswith("=")

    def test_decode_malformed_base64_raises(self) -> None:
        with pytest.raises(ValueError):
            decode_cursor("!!!not base64!!!")

    def test_decode_non_json_body_raises(self) -> None:
        import base64

        garbled = base64.urlsafe_b64encode(b"not json at all").rstrip(b"=").decode("ascii")
        with pytest.raises(ValueError):
            decode_cursor(garbled)

    def test_decode_wrong_shape_raises(self) -> None:
        import base64
        import json as _json

        body = _json.dumps({"unrelated": "shape"})
        encoded = base64.urlsafe_b64encode(body.encode()).rstrip(b"=").decode("ascii")
        with pytest.raises(Exception):  # noqa: B017 — pydantic ValidationError or ValueError
            decode_cursor(encoded)

    def test_class_decode_helper(self) -> None:
        when = datetime(2026, 5, 8, 12, 34, 56, tzinfo=UTC)
        ident = uuid.UUID("11111111-1111-4111-8111-111111111111")
        encoded = Cursor(created_at=when, id=ident).encode()
        decoded = Cursor.decode(encoded)
        assert decoded.created_at == when
        assert decoded.id == ident


# ---------------------------------------------------------------------------
# Schema validation smoke
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_message_to_response_translates_micros_to_usd() -> None:
    """``message_to_response`` reads the integer micros column and
    surfaces it as a USD float on the wire."""

    from app.schemas.chats import message_to_response

    class FakeRow:
        def __init__(self) -> None:
            self.id = uuid.uuid4()
            self.chat_id = uuid.uuid4()
            self.role = "assistant"
            self.content = "hi"
            self.applied_skills = ["nda-review"]
            self.routed_inference_tier = 3
            self.routed_provider = "anthropic-prod"
            self.routed_model = "claude-sonnet-4-6"
            self.requested_model = "smart"
            self.prompt_tokens = 10
            self.completion_tokens = 20
            self.cost_estimate_micros = 250
            self.error_code: str | None = None
            self.citations: list[object] = []
            self.created_at = datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC)

    response = message_to_response(FakeRow())
    assert response.cost_estimate is not None
    assert math.isclose(response.cost_estimate, 0.00025, rel_tol=1e-9)
    assert response.applied_skills == ["nda-review"]
    assert response.routed_inference_tier == 3
    assert response.requested_model == "smart"
    assert response.routed_model == "claude-sonnet-4-6"
