"""Envelope normalization — INTAKE-2 (ADR-F086).

Every bound asserted here mirrors ``api/app/schemas/intake.py``. The bridge's
job is to land SOMETHING the human can see: an oversize body is truncated with a
visible marker, an over-long recipient is dropped, a NUL byte is stripped — none
of them may cost us the email, because AgentMail offers no replay.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app import normalize
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
    # F3: auth_state is derived honestly from the Authentication-Results header; the
    # default probe payload carries none, so a message with no verdict is "unknown"
    # (a neutral UI state), never a hardcoded "pass".
    assert message["auth_state"] == "unknown"
    assert message["attachments"] == []


_REAL_AR = (
    "amazonses.com; spf=pass (spfCheck: domain of _spf.google.com designates "
    "209.85.221.177 as permitted sender) client-ip=209.85.221.177; "
    "envelope-from=s.arturko@googlemail.com; helo=mail-vk1-f177.google.com; "
    "dkim=pass header.i=@googlemail.com; dmarc=pass header.from=googlemail.com;"
)
_FORGED_AR = "attacker.example; spf=pass; dkim=pass; dmarc=pass header.from=victim.com;"


def test_auth_state_real_pass_header_reads_pass() -> None:
    assert normalize._auth_state_from_headers({"Authentication-Results": _REAL_AR}) == "pass"


def test_auth_state_fail_header_reads_fail() -> None:
    fail = _REAL_AR.replace("dmarc=pass", "dmarc=fail")
    assert normalize._auth_state_from_headers({"Authentication-Results": fail}) == "fail"


def test_auth_state_absent_is_unknown() -> None:
    assert normalize._auth_state_from_headers({}) == "unknown"
    assert normalize._auth_state_from_headers(None) == "unknown"


def test_auth_state_ignores_dmarc_forged_into_an_earlier_ar_token() -> None:
    # `envelope-from=` / `helo=` are attacker-controlled (SMTP MAIL FROM local-part,
    # HELO) and appear in the AR value BEFORE the real `dmarc=`. A `\b`-anchored regex
    # would match the forged token first and upgrade a genuine fail to "pass"; the
    # method-boundary anchor must read only the real `; dmarc=fail`.
    via_envelope_from = (
        "amazonses.com; spf=fail (spfCheck: no) client-ip=1.2.3.4; "
        "envelope-from=dmarc=pass@evil.com; helo=mail.evil.com; "
        "dmarc=fail header.from=victim.com;"
    )
    assert (
        normalize._auth_state_from_headers({"Authentication-Results": via_envelope_from}) == "fail"
    )
    via_helo = "amazonses.com; helo=dmarc=pass.evil.com; dmarc=fail header.from=victim.com;"
    assert normalize._auth_state_from_headers({"Authentication-Results": via_helo}) == "fail"
    # A leading dmarc method (no authserv-id prefix before it) still parses.
    assert normalize._auth_state_from_headers({"Authentication-Results": "dmarc=pass"}) == "pass"


def test_auth_state_no_dmarc_verdict_is_unknown() -> None:
    # spf/dkim present but no DMARC (the alignment-aware verdict) → unknown.
    no_dmarc = "amazonses.com; spf=pass; dkim=pass;"
    assert normalize._auth_state_from_headers({"Authentication-Results": no_dmarc}) == "unknown"


def test_auth_state_garbage_is_unknown() -> None:
    assert normalize._auth_state_from_headers({"Authentication-Results": "]{[ nonsense"}) == (
        "unknown"
    )
    assert normalize._auth_state_from_headers({"Authentication-Results": 12345}) == "unknown"


def test_auth_state_trusts_only_the_first_receiver_header() -> None:
    # A sender-forged AR sits BELOW the receiver's real one (a list preserves order);
    # only the FIRST (topmost) is read, so a forged dmarc=pass under a real dmarc=fail
    # cannot upgrade the verdict.
    real_fail = _REAL_AR.replace("dmarc=pass", "dmarc=fail")
    headers = {"Authentication-Results": [real_fail, _FORGED_AR]}
    assert normalize._auth_state_from_headers(headers) == "fail"


def test_auth_state_case_insensitive_key_and_verdict() -> None:
    headers = {"authentication-results": "recv; DMARC=PASS header.from=x.com;"}
    assert normalize._auth_state_from_headers(headers) == "pass"


def test_authentication_results_is_carried_in_bound_headers() -> None:
    # F3(2): the raw AR value is forwarded (bounded) for api/UI transparency.
    from tests.conftest import make_message

    envelope = normalize_message(
        make_message(headers={"Authentication-Results": _REAL_AR}), inbox_id=INBOX
    )
    assert envelope["message"]["auth_state"] == "pass"
    assert envelope["message"]["headers"]["Authentication-Results"].endswith("googlemail.com;")


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


def test_long_references_chain_keeps_the_newest_ids() -> None:
    """INTAKE-4a (ADR-F088): ``References`` is trimmed from the HEAD.

    Every hop APPENDS the message it answered, so the newest ids sit at the tail
    — and the newest are the ones most likely to be OURS, which is the only
    thing the api's layer-2 resolver can act on. A head-first trim (what every
    other header gets) would throw away exactly the half that matters, and the
    attach would silently stop working on long threads.
    """

    chain = [f"<hop-{i:02d}-{'x' * 200}@example.com>" for i in range(12)]
    envelope = normalize_message(make_message(references=chain), inbox_id=INBOX)

    kept = envelope["message"]["headers"]["References"]
    assert len(kept) <= normalize.MAX_REFERENCES_VALUE_CHARS
    assert chain[-1] in kept, "the NEWEST id must survive — it is the one we may have sent"
    assert chain[0] not in kept, "the oldest ids are what a trim is allowed to lose"


def test_references_gets_a_larger_cap_than_the_other_headers() -> None:
    """It is the one allowlisted header that grows without bound."""

    assert normalize.MAX_REFERENCES_VALUE_CHARS > normalize.MAX_HEADER_VALUE_CHARS


def test_a_short_references_chain_is_untouched() -> None:
    envelope = normalize_message(
        make_message(references=["<a@example.com>", "<b@example.com>"]), inbox_id=INBOX
    )
    assert envelope["message"]["headers"]["References"] == "<a@example.com> <b@example.com>"


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
