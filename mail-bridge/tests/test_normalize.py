"""Envelope normalization — INTAKE-2 (ADR-F086).

Every bound asserted here mirrors ``api/app/schemas/intake.py``. The bridge's
job is to land SOMETHING the human can see: an oversize body is truncated with a
visible marker, an over-long recipient is dropped, a NUL byte is stripped — none
of them may cost us the email, because AgentMail offers no replay.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.normalize import (
    MAX_ADDRESSES,
    MAX_BODY_TEXT_CHARS,
    TRUNCATION_MARKER,
    normalize_message,
    truncate_body,
)
from tests.conftest import INBOX, make_message


def test_full_mapping() -> None:
    envelope = normalize_message(make_message(), inbox_id=INBOX)

    assert envelope["provider"] == "agentmail"
    assert envelope["inbox_id"] == INBOX
    assert envelope["thread"] == {
        "provider_thread_id": "2e1c9f73-4e29-424c-8404-c8cd03306c44",
        "subject": "Draft NDA for review",
    }
    message = envelope["message"]
    assert message["provider_message_id"] == "<CAF-abc123@mail.gmail.com>"
    assert message["from_addr"] == "Counterparty <counsel@example.com>"
    assert message["to"] == [INBOX]
    assert message["cc"] == []
    assert message["text"] == "Please review the attached NDA."
    assert message["timestamp"].startswith("2026-08-29T20:14:39")
    # v1 subscribes to plain message.received only; the .unauthenticated/.spam
    # variants are not forwarded, so a message that reaches here passed.
    assert message["auth_state"] == "pass"
    assert message["attachments"] == []


def test_missing_subject_becomes_empty_string() -> None:
    envelope = normalize_message(make_message(subject=None), inbox_id=INBOX)
    assert envelope["thread"]["subject"] == ""


def test_text_falls_back_to_extracted_text_then_empty() -> None:
    fallback = normalize_message(
        make_message(text=None, extracted_text="extracted body"), inbox_id=INBOX
    )
    assert fallback["message"]["text"] == "extracted body"

    empty = normalize_message(make_message(text=None), inbox_id=INBOX)
    assert empty["message"]["text"] == ""


def test_nul_bytes_are_stripped_everywhere() -> None:
    """The api REJECTS a NUL (422) — stripping here is what saves the email."""

    envelope = normalize_message(
        make_message(
            text="clean\x00body",
            subject="sub\x00ject",
            **{"from": "a\x00@example.com"},
        ),
        inbox_id=INBOX,
    )
    assert "\x00" not in envelope["message"]["text"]
    assert "\x00" not in envelope["thread"]["subject"]
    assert "\x00" not in envelope["message"]["from_addr"]


def test_body_truncated_with_marker() -> None:
    envelope = normalize_message(
        make_message(text="x" * (MAX_BODY_TEXT_CHARS + 5_000)), inbox_id=INBOX
    )
    text = envelope["message"]["text"]
    assert len(text) == MAX_BODY_TEXT_CHARS
    assert text.endswith(TRUNCATION_MARKER)


def test_body_at_the_cap_is_untouched() -> None:
    exact = "y" * MAX_BODY_TEXT_CHARS
    assert truncate_body(exact) == exact


def test_recipient_lists_are_capped_and_over_long_entries_dropped() -> None:
    too_many = [f"user{i}@example.com" for i in range(MAX_ADDRESSES + 10)]
    over_long = "x" * 400 + "@example.com"

    envelope = normalize_message(
        make_message(to=[over_long, *too_many], cc=[over_long]), inbox_id=INBOX
    )
    assert len(envelope["message"]["to"]) == MAX_ADDRESSES
    assert over_long not in envelope["message"]["to"]
    assert envelope["message"]["cc"] == []


def test_over_long_sender_prefers_the_angle_bracket_address() -> None:
    """``from_addr`` is required, so it can never be dropped — only bounded."""

    display = "D" * 500
    envelope = normalize_message(
        make_message(**{"from": f"{display} <counsel@example.com>"}), inbox_id=INBOX
    )
    assert envelope["message"]["from_addr"] == "counsel@example.com"


def test_over_long_sender_without_brackets_is_truncated() -> None:
    envelope = normalize_message(make_message(**{"from": "z" * 500}), inbox_id=INBOX)
    assert len(envelope["message"]["from_addr"]) == 320


def test_empty_sender_falls_back() -> None:
    envelope = normalize_message(make_message(**{"from": ""}), inbox_id=INBOX)
    assert envelope["message"]["from_addr"] == "(unknown sender)"


def test_headers_allowlist_only() -> None:
    """Only the four headers the api allowlists survive; the rest are dropped."""

    envelope = normalize_message(
        make_message(
            in_reply_to="<parent@example.com>",
            references=["<a@example.com>", "<b@example.com>"],
            headers={
                "Auto-Submitted": "auto-replied",
                "Precedence": "bulk",
                "X-Mailer": "evil-injector",
                "Subject": "not a real header carrier",
            },
        ),
        inbox_id=INBOX,
    )
    assert envelope["message"]["headers"] == {
        "In-Reply-To": "<parent@example.com>",
        "References": "<a@example.com> <b@example.com>",
        "Auto-Submitted": "auto-replied",
        "Precedence": "bulk",
    }


def test_missing_headers_are_omitted_not_empty() -> None:
    """The probe found ``headers`` arrives EMPTY even on real inbound mail."""

    envelope = normalize_message(make_message(headers={}), inbox_id=INBOX)
    assert envelope["message"]["headers"] == {}


def test_header_values_are_nul_stripped() -> None:
    envelope = normalize_message(
        make_message(in_reply_to="<par\x00ent@example.com>"), inbox_id=INBOX
    )
    assert envelope["message"]["headers"]["In-Reply-To"] == "<parent@example.com>"


def test_timestamp_string_is_coerced_not_crashed() -> None:
    """``construct_type`` does NOT validate: a str survives into a datetime field.

    A bare ``.isoformat()`` would raise inside the webhook handler, and because
    Svix retries a 5xx that single malformed field would become a permanent
    poison-retry against this bridge.
    """

    envelope = normalize_message(make_message(timestamp="not-a-timestamp-at-all"), inbox_id=INBOX)
    # Fell back to receipt time rather than raising; still a parsable ISO stamp.
    datetime.fromisoformat(envelope["message"]["timestamp"])


def test_iso_string_timestamp_is_preserved() -> None:
    envelope = normalize_message(
        make_message(timestamp="2026-08-29T20:14:39+00:00"), inbox_id=INBOX
    )
    assert envelope["message"]["timestamp"].startswith("2026-08-29T20:14:39")


def test_none_timestamp_falls_back_to_now() -> None:
    envelope = normalize_message(make_message(timestamp=None), inbox_id=INBOX)
    parsed = datetime.fromisoformat(envelope["message"]["timestamp"])
    assert (datetime.now(tz=UTC) - parsed).total_seconds() < 60
