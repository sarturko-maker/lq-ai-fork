"""Email stamping + threading-header parsing — INTAKE-4a (ADR-F088).

Pure functions, no I/O, no DB. Two directions:

**Outbound (written by INTAKE-4b).** :func:`tag_subject` appends the matter
reference to a reply's subject exactly once — ``Re: <original> [NWT-COM-0042]``.
The tag is the human-visible stamp that survives a forward, a client rewrite and
a quoted reply. It is the ONLY thing we stamp: the probe found the provider
assigns its own canonical ``Message-ID`` on send regardless of any caller-supplied
header, so the machine-readable stamp is that provider-assigned id, persisted on
``intake_messages.provider_message_id`` and matched back out of an inbound
``References`` header (layer 2) — we mint no ids of our own.

**Inbound (read by the resolver).** :func:`parse_references_header` pulls the
angle-bracket ids out of a ``References``/``In-Reply-To`` header;
:func:`parse_reference_tags` pulls ``[ORG-AREA-NNNN]`` tags out of a subject.

Everything parsed here is UNTRUSTED sender-controlled text: a subject tag is
anything a stranger cares to type. Both parsers are therefore strict (an exact
anchored pattern, bounded input, bounded output) and, crucially, neither of them
decides anything — a tag only ever *proposes* a matter, and the resolver still
requires the sender to be on that matter's roster before attaching (ADR-F088
trust ladder; weak layers never auto-merge).
"""

from __future__ import annotations

import re

from app.matters.reference import REFERENCE_MAX_CHARS

#: RFC 5322 caps a header line at 998 chars; we parse no more than that so a
#: pathological subject cannot turn into pathological regex work.
MAX_PARSED_SUBJECT_CHARS = 998
MAX_PARSED_HEADER_CHARS = 2_000

#: At most this many distinct ids/tags come back from one header/subject — a
#: sender cannot make the resolver do unbounded lookups.
MAX_PARSED_IDS = 20
MAX_PARSED_TAGS = 5

#: The subject tag. Anchored on the literal brackets and CASE-SENSITIVE by
#: design: the reference vocabulary is uppercase, so a lowercase look-alike
#: (``[nwt-com-0042]``) is NOT a tag and buys a spoofer nothing. Nested or
#: unbalanced brackets never match — ``[^\]]`` cannot cross a ``]``.
_TAG_RE = re.compile(r"\[([A-Z0-9]{2,6})-([A-Z0-9]{2,6})-([0-9]{4,})\]")

#: ``<id@host>`` tokens in a References/In-Reply-To header. Ids are opaque to us
#: (we only ever compare them to ids the provider gave us), so the inner shape is
#: deliberately loose — but bounded, and it cannot span a ``<`` or ``>``.
_MSGID_RE = re.compile(r"<([^<>\s]{1,500})>")

#: Prefix a reply subject carries when the original had none.
_REPLY_PREFIX = "Re: "


def parse_reference_tags(subject: str) -> list[str]:
    """Every ``[ORG-AREA-NNNN]`` tag in ``subject``, in order, de-duplicated.

    Returns an empty list for a subject with no well-formed tag — including a
    lowercase or malformed look-alike, a nested ``[[…]]`` and an unterminated
    ``[``. Bounded: only the first :data:`MAX_PARSED_SUBJECT_CHARS` characters
    are examined and at most :data:`MAX_PARSED_TAGS` tags come back.
    """

    seen: list[str] = []
    for match in _TAG_RE.finditer(subject[:MAX_PARSED_SUBJECT_CHARS]):
        tag = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
        if len(tag) > REFERENCE_MAX_CHARS:
            continue
        if tag not in seen:
            seen.append(tag)
        if len(seen) == MAX_PARSED_TAGS:
            break
    return seen


def has_reference_tag(subject: str, reference: str) -> bool:
    """Whether ``subject`` already carries exactly this matter's tag."""

    return reference in parse_reference_tags(subject)


def tag_subject(subject: str, reference: str) -> str:
    """``Re: <subject> [<reference>]`` — idempotent.

    Calling this on an already-tagged subject returns it unchanged (no second
    tag, no second ``Re:``), so a redraft, a retry or a resumed HITL approval
    can all stamp freely. An empty/whitespace-only subject yields just the
    prefix and the tag. The result is bounded to the RFC 5322 line limit, and
    the tag is never the part that gets trimmed — the ORIGINAL subject is
    shortened to make room, because the tag is what routes the reply home.
    """

    body = subject.strip()
    prefix = "" if _is_reply_prefixed(body) else _REPLY_PREFIX

    if has_reference_tag(body, reference):
        return f"{prefix}{body}"

    tag = f"[{reference}]"
    # Budget the ORIGINAL subject, never the tag: the tag is what routes a reply
    # home, so it is the last thing that may be trimmed.
    room = MAX_PARSED_SUBJECT_CHARS - len(prefix) - len(tag) - 1
    base = body if len(body) <= room else body[: max(room, 0)].rstrip()
    return f"{prefix}{base} {tag}" if base else f"{prefix}{tag}"


def _is_reply_prefixed(subject: str) -> bool:
    """``Re:``/``RE:``/``re :`` and the common non-English equivalents we would
    otherwise double up on. Conservative — a false negative only costs a
    duplicate-looking prefix, never a mis-routed reply."""

    head = subject[:8].lower().lstrip()
    return head.startswith(("re:", "re :", "aw:", "sv:", "vs:", "antw:"))


#: A plus-tagged recipient — ``intake+NWT-COM-0042@example.com``. Probed live
#: (2026-08-30): plus-addressed mail reaches the base inbox and the provider
#: stores the recipient LOWER-CASED, so this parse is case-insensitive and the
#: result is upper-cased back into the reference vocabulary. Same trust as the
#: subject tag — a recipient address is sender-controlled text, so a hit here is
#: still Roster-gated and never auto-merges.
_PLUS_TAG_RE = re.compile(
    r"^[^@\s]{1,64}\+([A-Za-z0-9]{2,6}-[A-Za-z0-9]{2,6}-[0-9]{4,})@[^@\s]{1,255}$"
)

#: RFC 5321 4.5.3.1.3 forward-path limit — the same bound the envelope schema uses.
MAX_PARSED_ADDR_CHARS = 320


def parse_plus_tag(address: str) -> str | None:
    """The matter reference in a plus-tagged recipient address, or ``None``.

    ``"intake+nwt-com-0042@example.com"`` → ``"NWT-COM-0042"``. Anything else —
    a bare address, several plus segments, a malformed tag, an over-long string
    — yields ``None``. An angle-bracket display form (``Name <a+tag@b>``) is
    unwrapped first, since that is how recipients often arrive.
    """

    candidate = address.strip()[:MAX_PARSED_ADDR_CHARS]
    angle = _MSGID_RE.search(candidate)
    if angle is not None:
        candidate = angle.group(1).strip()
    match = _PLUS_TAG_RE.match(candidate)
    if match is None:
        return None
    tag = match.group(1).upper()
    return tag if len(tag) <= REFERENCE_MAX_CHARS else None


def normalise_address(value: str) -> str:
    """The bare, lower-cased addr-spec of an email address, for comparison only.

    ``"Jane Doe <Jane@Example.COM>"`` → ``"jane@example.com"``. A value with no
    angle-bracket form is taken as-is. Used to compare an inbound sender against
    a matter's roster aliases — both sides go through here, so the comparison is
    case-insensitive and display-name-insensitive on both. Never used to build
    SQL: the match happens in Python (ADR-F048 — roster aliases are untrusted).
    """

    candidate = value.strip()[:MAX_PARSED_ADDR_CHARS]
    angle = _MSGID_RE.search(candidate)
    if angle is not None:
        candidate = angle.group(1).strip()
    return candidate.lower()


def looks_like_address(value: str) -> bool:
    """Whether a normalised string is shaped like an email address at all.

    Deliberately crude — one ``@`` with something either side, no whitespace.
    Its only job is to keep NON-address text out of an address comparison: a
    matter's roster aliases hold display-name strings as well as addresses
    (ADR-F048 — they are the tracked-change author strings a person writes
    under), so comparing a sender to an alias like ``"Legal"`` or ``"Author"``
    would let a stranger who signs their mail with a common name walk through
    an identity check. Both sides of that comparison go through here first.
    """

    if not value or len(value) > MAX_PARSED_ADDR_CHARS:
        return False
    if any(ch.isspace() for ch in value):
        return False
    local, sep, domain = value.partition("@")
    return bool(sep) and bool(local) and bool(domain) and "@" not in domain


def parse_plus_tags(addresses: list[str]) -> list[str]:
    """Every distinct plus-tag reference across a recipient list, in order."""

    seen: list[str] = []
    for address in addresses[:MAX_PARSED_IDS]:
        tag = parse_plus_tag(address)
        if tag is not None and tag not in seen:
            seen.append(tag)
        if len(seen) == MAX_PARSED_TAGS:
            break
    return seen


def parse_references_header(value: str | None) -> list[str]:
    """The ``<message-id>`` tokens in a ``References``/``In-Reply-To`` header.

    Angle brackets are STRIPPED — the provider hands us bare ids on the way in
    (``intake_messages.provider_message_id``), so both sides of the later
    comparison are bare. Order is preserved (most senders append, so the last
    entry is the immediate parent) and duplicates are dropped. Bounded input and
    output; malformed junk simply yields no tokens.
    """

    if not value:
        return []
    seen: list[str] = []
    for match in _MSGID_RE.finditer(value[:MAX_PARSED_HEADER_CHARS]):
        token = match.group(1).strip()
        if token and token not in seen:
            seen.append(token)
        if len(seen) == MAX_PARSED_IDS:
            break
    return seen


def parse_threading_headers(in_reply_to: str | None, references: str | None) -> list[str]:
    """Every candidate parent id from both threading headers, parent-first.

    ``In-Reply-To`` names the immediate parent, so it is tried first; the
    ``References`` chain follows in reverse (nearest ancestor first).
    """

    ordered = parse_references_header(in_reply_to)
    for token in reversed(parse_references_header(references)):
        if token not in ordered:
            ordered.append(token)
    return ordered[:MAX_PARSED_IDS]


__all__ = [
    "MAX_PARSED_ADDR_CHARS",
    "MAX_PARSED_HEADER_CHARS",
    "MAX_PARSED_IDS",
    "MAX_PARSED_SUBJECT_CHARS",
    "MAX_PARSED_TAGS",
    "has_reference_tag",
    "looks_like_address",
    "normalise_address",
    "parse_plus_tag",
    "parse_plus_tags",
    "parse_reference_tags",
    "parse_references_header",
    "parse_threading_headers",
    "tag_subject",
]
