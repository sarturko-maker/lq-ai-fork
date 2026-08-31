# INTAKE-2 — AgentMail live probe findings

**Date:** 2026-08-29 · **SDK:** `agentmail==0.5.9` (pydantic 2.13.5, websockets 17.1) ·
**Inbox:** `oscar-lq@agentmail.to` (dev account, `inbox_id == email address`) ·
**Raw capture:** `events-captured.jsonl`

All calls below were made against the live API with our own dev key. No API key, and no signed
CDN URL query string, is reproduced in this directory. Probe scripts live in the session
scratchpad, not in the repo.

---

## Step 1 — Websocket subscribe

```python
with client.websockets.connect() as socket:               # sync context manager
    socket.send_subscribe(Subscribe(inbox_ids=[INBOX]))   # no event_types filter
    for frame in socket: ...                              # __iter__ yields parsed pydantic models
```

Connected in **0.76 s**; `Subscribed` ack arrived **298 ms** after the subscribe frame:

```json
{"type":"subscribed","inbox_ids":["oscar-lq@agentmail.to"],
 "organization_id":"7ec59ffb-c0e9-4ff4-8a13-671845e727cd"}
```

- Omitting `event_types` subscribes to **all** types — the ack echoes `inbox_ids` only and does
  not list an `event_types` set, i.e. no filter was applied.
- The ack carries `organization_id`, which is **not** a declared field of the SDK's `Subscribed`
  model. The SDK uses `construct_type` over an unchecked base model, so undeclared server fields
  survive into `model_dump()` but are invisible to static typing. This recurs below (`text_url`).
- `WebsocketsSocketClient._send_model` calls `data.dict()` (pydantic v1 API) — emits a
  `PydanticDeprecatedSince20` warning on every subscribe. Harmless today, breaks on pydantic v3.

## Step 2 — Send with attachment (self-send)

```python
client.inboxes.messages.send(
    INBOX, to=[INBOX], subject="INTAKE-2 probe - self-send round trip", text="...",
    attachments=[SendAttachment(filename="SecureScan-MSA.docx", content_type=DOCX_CT,
                                content=base64.b64encode(raw).decode("ascii"))])
```

Source file `sample-documents/commercial-redline-brief/SecureScan-MSA.docx` — 37 998 bytes,
sha256 `4ba36d4e...1de2b0`.

**Accepted.** `SendMessageResponse` carries exactly two fields:

| field | value |
|---|---|
| `message_id` | `<010001a04f28f3f1-...@email.amazonses.com>` (RFC-822 angle-bracket, SES-minted) |
| `thread_id` | `2e1c9f73-4e29-424c-8404-c8cd03306c44` (UUID) |

> **The FAQ claim that an agent "can only reply, cannot send without receiving first" is FALSE.**
> A cold outbound send from the inbox succeeded on the first attempt with no prior inbound message
> in that thread. `SendAttachment` takes base64 in `content` (an alternative `url` field exists).

## Step 3 — Which events fire for a self-send

Waited 120 s on the subscribed socket. Exactly **two** frames, both about the outbound copy:

| order of arrival | `py_type` | `event_type` | server `timestamp` |
|---|---|---|---|
| 1 | `MessageDeliveredEvent` | `message.delivered` | 20:14:39.514 Z |
| 2 | `MessageSentEvent` | `message.sent` | 20:14:39.060 Z |

- **No `message.received` ever arrived** — not in 120 s, and not since. Delivery to the inbox's
  own address is acknowledged by SES (`message.delivered`, `recipients: ["oscar-lq@agentmail.to"]`)
  but AgentMail does **not** re-ingest its own outbound as an inbound message.
  Confirmed independently: `messages.list` shows a single row for the probe, labelled `["sent"]`,
  and the inbox event log records only a `sent` label for it — no `received` label.
- **Frames arrive out of timestamp order.** `message.delivered` was received 1.07 s *before*
  `message.sent`, though its server timestamp is 454 ms *later*. Ordering must come from
  `timestamp`, never from arrival order.
- `MessageSentEvent` and `MessageDeliveredEvent` carry **no message body and no attachment data** —
  only an id envelope (`inbox_id`, `thread_id`, `message_id`, `timestamp`, `recipients`,
  `organization_id`, `pod_id`) under a `send` / `delivery` key respectively. Only
  `MessageReceivedEvent` declares a full `message: Message` plus `thread: ThreadItem`.

### The inbound path does work — evidence from history

`messages.list(..., include_trash=True)` returns **15 rows labelled `received`** (from
`vibelegal@proton.me` etc., March 2026), all subsequently trashed — which is why the default
listing showed 7 rows, all `sent`. The inbox event log corroborates: 46 events, all
`label.added`, with values `{received: 14, unread: 13, trash: 11, sent: 8}`.

A real inbound message has this shape (values elided):

```
labels: ["received", "unread", "trash"]     message_id: <...@proton.me>  (sender-minted, not SES)
text / html / extracted_text / extracted_html : all populated
headers: {}                                  <-- EMPTY even on a genuine inbound message
attachments: [{attachment_id, filename, size, content_type, content_disposition}]
plus undeclared: organization_id, pod_id, smtp_id
```

Its attachment downloads cleanly today (42 916 bytes, magic `PK\x03\x04`), so the inbound
fetch path the bridge needs is verified end-to-end even without a fresh external send.

## Step 4 — Attachment semantics

`messages.get_attachment(inbox_id, message_id, attachment_id)` returns
**`agentmail.attachments.types.attachment_response.AttachmentResponse` — a pydantic object, not
bytes and not an iterator**:

```
attachment_id, filename, size, content_type, content_disposition,
download_url : str    -> https://cdn.agentmail.to/attachments/{attachment_id}?<presigned>
expires_at   : datetime
text_url     : str    -> UNDECLARED extra field (see below)
```

- `download_url` is a **presigned CloudFront URL, valid ~1 hour** (`expires_at` was consistently
  `send_time + 61 min`). A plain `httpx.get` with **no Authorization header returns 200** — the URL
  is itself the credential. It must never be logged, persisted, or handed to a client.
- Downloaded bytes are **byte-identical to the source**: 37 998 bytes,
  sha256 `4ba36d4e...1de2b0` on both the original message and the reply. Full round trip through
  SES is lossless for a .docx.
- `threads.get_attachment(thread_id, attachment_id)` returns the **same shape and the same CDN
  path**, differing only in the freshly-minted signature and `expires_at`. Its bytes hash
  identically. `inboxes.threads.get_attachment(inbox_id, thread_id, attachment_id)` also exists.
  There is no functional difference — pick whichever ids are in hand.
- **`text_url` is an undeclared server field** (absent from `AttachmentResponse.model_fields`,
  reachable only via `model_dump()["text_url"]`). It serves AgentMail's own plain-text extraction
  of the attachment: for our .docx, `text/plain; charset=utf-8`, 2 871 bytes, opening
  `"MASTER SERVICES AGREEMENT\n\nThis Master Services Agreement is entered into between
  SecureScan, Inc. ..."`. **It is not guaranteed**: the March-2026 inbound .docx has no `text_url`
  at all. Treat it as an opportunistic preview only; never as the extraction path.

## Step 5 — Reply round-trip

```python
client.inboxes.messages.reply(INBOX, message_id, text="INTAKE-2 probe - reply with attachment",
                              attachments=[SendAttachment(...)])   # no `to` passed
```

**Accepted with no recipients supplied** — reply is keyed purely by `message_id` and derives
recipients itself. It also worked against a message labelled `sent` (replying to our own message),
so reply is not gated on the target being inbound.

- New `message_id`, **same `thread_id`** (`2e1c9f73-...`).
- `in_reply_to` on the reply = the original's `message_id`; `references` = `[original message_id]`.
  The original has both `null`.
- Events: again **`message.delivered` then `message.sent`, no `message.received`**, delivered
  frame arriving 0.92 s before the sent frame.
- The reply's attachment gets a **new `attachment_id`** (`02559464-...` vs `ea77d0f0-...`) —
  attachments are **not** deduplicated by content, even for identical bytes in the same thread.
  Both download to the same sha256.
- AgentMail auto-quotes the parent body into the reply (`"...\n\nOn Sat, Aug 29, 2026 at 8:14 PM
  UTC Oscar <...> wrote:\n\n> INTAKE-2 probe body..."`).

## Step 6 — Thread object

`threads.get(thread_id)` -> `Thread`: `inbox_id, thread_id, labels, timestamp, received_timestamp,
sent_timestamp, senders, recipients, subject, preview, attachments, last_message_id, message_count,
size, updated_at, created_at, messages[]` (+ undeclared `organization_id`, `pod_id`).

- `message_count: 2`, `labels: ["sent"]`, `last_message_id` = the reply, `messages[]` inlines both
  full `Message` objects. `received_timestamp` is absent, `sent_timestamp` set — thread labels and
  timestamps are a **union over its messages**.
- **Trap: the thread-level `attachments` array is not the union of its messages' attachments.**
  It listed only `ea77d0f0-...` (the first message's), while the two messages carry `ea77d0f0-...`
  and `02559464-...` respectively. Re-fetched after indexing had settled — still one entry.
  Enumerate `thread.messages[].attachments`; never trust `thread.attachments` as complete.

## Verdicts

**(a) Self-send delivery semantics / which events fire.**
A send to the inbox's own address is accepted and delivered, and fires exactly
`message.sent` + `message.delivered` — **never `message.received`**. AgentMail suppresses
self-ingestion, so a self-send cannot exercise the inbound path. Consequence for the bridge: the
dev-loop guard *can* rely on inbound and outbound being distinct event types (they are, cleanly),
but a self-send is **useless as a dev fixture for the receive path** — an external sender is
required to see `message.received` live. That is a maintainer action; not attempted here.
Cold outbound sending works, so the "reply-only" FAQ note is wrong.

**(b) Attachment download = bytes or URL.**
**URL.** `get_attachment` returns an `AttachmentResponse` whose `download_url` is a presigned,
unauthenticated CloudFront link expiring in ~1 hour; the caller performs a second HTTP GET. Bytes
are byte-exact (sha256 verified on three separate attachments, inbound and outbound). The
thread-scoped variant is equivalent. Treat the URL as a short-lived credential.

**(c) Reply threading.**
Keyed by `message_id` alone — no `to`, no `thread_id` needed. Lands in the same `thread_id`, sets
`in_reply_to` and `references` correctly, and accepts attachments. Works even when the target
message is one of our own `sent` messages.

**(d) Websocket subscribe/ack, keepalive, disconnects.**
`Subscribe(inbox_ids=[...])` with no `event_types` yields an all-events subscription, acked in
~300 ms. The connection stayed **open and healthy for the full ~8-minute observation window
(20:14:09Z until deliberately killed at 20:22Z) with zero
disconnects, zero reconnects, and no application-level ping/pong visible** (websockets 17.1 handles
protocol-level keepalive internally; no frames other than the ack and the four event frames were
delivered). Frames deserialize into typed pydantic models; unknown types are dropped with a
warning rather than surfaced. **The socket has no replay/backfill**: `inboxes.events.list` is a
paginated durable log but contains **only `label.added` events** (46/46), not
received/sent/delivered — so a bridge that misses frames while disconnected cannot replay them from
the event API. Reconcile by polling `messages.list(after=...)`, or by watching `label.added` with
`label == "received"`, which does durably record every inbound arrival.

## Surprises vs the research doc

| Research doc predicted | Observed |
|---|---|
| Full message inline in events, capped at 1 MB, `text`/`html` silently dropped over the cap | Only `MessageReceivedEvent` declares an inline `message`. `message.sent` / `message.delivered` carry **no body at all** — just an id envelope. The 1 MB truncation claim was **not exercised** (no `message.received` could be provoked) and remains unverified. |
| `get_attachment` ambiguous, bytes vs URL | **Unambiguously a URL** — `AttachmentResponse.download_url`, presigned, ~1 h TTL, no auth header needed. Never raw bytes. |
| Reply keyed by `message_id` | **Confirmed**, and stronger than assumed: `to` is not required at all, and replying to one's own `sent` message works. |
| — (not predicted) | `text_url`: an undeclared field carrying AgentMail's own plain-text extraction of the attachment. Present on new sends, absent on the older inbound message. |
| — (not predicted) | `thread.attachments` is **not** the union of message attachments. |
| — (not predicted) | `message.delivered` arrives **before** `message.sent` despite a later server timestamp. |
| — (not predicted) | `headers` is `{}` even on a genuine inbound message. |
| — (not predicted) | `inboxes.events.list` is a **label-only** log — no delivery-event replay. |
| — (not predicted) | SDK 0.5.9 lags the API: `organization_id`, `pod_id`, `smtp_id`, `text_url` all arrive undeclared, typed as absent. |

## Impact on the mail-bridge design

1. **Dev ingress (websocket subscribe loop) is viable** — stable for the full ~8 min observed, typed frames, fast ack.
   But it needs a **reconciliation poll** (`messages.list(after=last_seen)`), because there is no
   event replay for missed delivery frames.
2. **The bridge must fetch, not read.** Inbound events give ids; bodies for `sent`/`delivered` and
   all attachment bytes require follow-up API calls. Budget two HTTP calls per attachment
   (`get_attachment` -> presigned GET) before the POST to our internal intake endpoint.
3. **The presigned URL is a credential with a ~1 h TTL.** Fetch and forward bytes server-side;
   never persist the URL in `files`, audit rows, or receipts, and never hand it to the browser.
4. **Key attachments by `(message_id, attachment_id)`, and de-duplicate on our own content hash** —
   AgentMail mints a fresh `attachment_id` for identical bytes, so its ids cannot carry our
   `hash_sha256` duplicate marker (ADR-F082). Our own sha256 remains the source of truth.
5. **Enumerate attachments per message**, never from `thread.attachments`.
6. **The dev loop guard is cheap**: `message.sent`/`message.delivered` are distinct event types and
   self-sends never re-enter as `message.received`, so filtering on
   `event_type == "message.received"` is sufficient to avoid the agent replying to itself.
7. **A live inbound test needs an external sender** (maintainer action). Everything downstream of
   arrival — `messages.get` shape, attachment fetch, reply threading — is already verified against
   real inbound rows in this inbox.
8. Prod ingress: `inboxes.webhooks.list` returns `{"count": 0}` — no Svix endpoint is configured on
   this inbox yet; the CRUD surface (`create/get/update/delete/get_headers/update_headers`) exists.

## Addendum (2026-08-29, same day) — live `message.received` frame captured

The maintainer sent a real external email (Gmail, subject "Any subject", one .docx attachment,
12,775 bytes) to the inbox while the probe listener was re-running. The frame closed the last
gap and is in `events-captured.jsonl` (lines 9+). Facts:

- **Event shape**: top-level keys `type`, `event_type` (`message.received`), `event_id`
  (32-hex — the natural idempotency key alongside our `(thread_id, provider_message_id)`
  anchor), a full inline `message`, **and a full inline `thread` object** (the research doc did
  not predict the embedded thread; message_count/size/subject come for free).
- **Message inline**: `text`, `html`, `preview`, AND AgentMail's own `extracted_text` /
  `extracted_html` — for a small message nothing is dropped (the 1 MB text/html-drop
  behaviour for large messages remains unobserved, keep the GET-by-id fallback).
- **`message_id` is the sender's original RFC-822 id** (`<...@mail.gmail.com>`) — angle
  brackets and all; treat as an opaque string, URL-encode in REST paths (SDK handles it).
  `thread_id` is an AgentMail UUID.
- **Attachment metadata inline, no bytes**: `attachment_id` (UUID), `filename`,
  `content_type`, `content_disposition`, `content_id`, `size` — confirms the
  fetch-per-attachment budget (`get_attachment` → presigned GET).
- `labels` arrives as `['received', 'unread']`; `headers` again absent/empty on the wire —
  do not rely on raw headers for threading.
- Undeclared-by-SDK fields present here too: `organization_id`, `pod_id`, `smtp_id`.

> **Correction (2026-08-30, INTAKE security review).** The blanket "`headers` absent/empty on the
> wire" above is over-general and was contradicted by this addendum's OWN captured frame:
> `events-captured.jsonl` line 13 (this external Gmail-sourced `message.received`) carries a fully
> populated `payload.message.headers` — `Authentication-Results`, `DKIM-Signature`/`ARC-*`, etc. —
> including the receiver-prepended verdict `Authentication-Results: amazonses.com; spf=pass … dkim=pass
> … dmarc=pass …`. `construct_type` maps that straight onto the SDK `Message.headers` field
> `normalize_message` reads. So: raw headers should NOT be relied on for THREADING (the typed
> `in_reply_to`/`references` fields remain correct there), but the **sender-authentication verdict IS on
> the wire when the sender's infra emits it**, and the original `auth_state="pass"` constant was
> discarding it. The security slice makes `auth_state` honest (`"unknown"` unless a real
> `Authentication-Results` DMARC verdict is present). An empty-`headers` message (some senders/paths, as
> first observed) simply yields `"unknown"` — never a false "pass".

With this, every semantic the mail-bridge depends on has been observed live: subscribe/ack,
`message.received` (external), `message.sent` + `message.delivered` (self-send), attachment
download (presigned URL → bytes, sha256-verified), cold `send`, `reply` threading by
message_id, and thread fetch. Remaining unobserved: >1 MB payload truncation, webhook (Svix)
delivery — both prod-path items for the bridge slice's own tests.

## INTAKE-4 probe (2026-08-30): Message-ID / custom headers / plus-address

**Date:** 2026-08-30 · **SDK:** `agentmail==0.5.9` (pydantic 2.13.5, unchanged since INTAKE-2) ·
**Inbox:** `oscar-lq@agentmail.to` · **Maintainer address used:** `s.arturko@googlemail.com`
(the address the INTAKE-2 addendum's external send came from — not explicitly recorded above,
recovered from `events-captured.jsonl`'s raw `from`/DKIM lines). Run against
`docker compose exec mail-bridge` (container up 11h, unmodified). No API key or bridge token
was printed at any point; only message ids, header names/values we ourselves set, and HTTP
status codes are recorded below.

### SDK signatures (ground truth, `inspect.signature` inside the running container)

```
AsyncMessagesClient.send(self, inbox_id, *, labels=..., reply_to=..., to=..., cc=..., bcc=...,
    subject=..., text=..., html=..., attachments=..., headers: Optional[Dict[str, str]] = ...,
    idempotency_key=None, request_options=None) -> SendMessageResponse

AsyncMessagesClient.reply(self, inbox_id, message_id, *, labels=..., reply_to=..., to=..., cc=...,
    bcc=..., reply_all=..., text=..., html=..., attachments=..., headers: Optional[Dict[str, str]] = ...,
    idempotency_key=None, request_options=None) -> SendMessageResponse

AsyncMessagesClient.get(self, inbox_id, message_id, *, request_options=None) -> Message
AsyncMessagesClient.list(self, inbox_id, *, limit=None, page_token=None, labels=None, before=None,
    after=None, ascending=None, include_spam=None, include_blocked=None,
    include_unauthenticated=None, include_trash=None, from_=None, to=None, subject=None,
    request_options=None) -> ListMessagesResponse
```

`Message.model_fields` (declared): `inbox_id, thread_id, message_id, labels, timestamp, from_,
reply_to, to, cc, bcc, subject, preview, text, html, extracted_text, extracted_html, attachments,
in_reply_to, references, headers, size, updated_at, created_at`. `SendMessageResponse` declares
only `message_id, thread_id` — no `headers` or `in_reply_to` echoed on the send response itself
(confirms you must `messages.get` the returned id to see what stuck).

Both `send` and `reply` take `headers: Optional[Dict[str, str]]` and `reply_to:
Union[str, List[str], None]` — no dedicated `message_id`/`in_reply_to`/`references` parameter on
either call (those are read-only, provider-derived, on the `Message` you get back).

### Docs findings

- `https://docs.agentmail.to/api-reference/inboxes/messages/send` and
  `.../messages/reply`: both document a `headers` field, "map from string to string" / "Headers
  to include in message" — matches the SDK. Neither page documents `message_id`, `in_reply_to`,
  or `references` as request-body fields (the SDK signatures above corroborate: they simply
  aren't parameters).
- `https://docs.agentmail.to/introduction/inboxes` and the inbox-create reference: **no mention
  of plus-addressing, sub-addressing, aliasing, or catch-all/wildcard routing anywhere** in the
  fetched pages. This is an absence-of-evidence, not a documented "unsupported" — AgentMail may
  simply not document the receiving-MTA's subaddressing behaviour either way.

### Experiment 1 — custom `Message-ID` + custom header via `send`

Sent (`inboxes.messages.send`) from `oscar-lq@agentmail.to` to `s.arturko@googlemail.com` with
`headers={"Message-ID": "<m.NWT-COM-0001.probe-intake4-abc123@oscar-lq.agentmail.to>",
"X-Matter-Ref": "NWT-COM-0001"}`.

| | |
|---|---|
| Requested custom Message-ID | `<m.NWT-COM-0001.probe-intake4-abc123@oscar-lq.agentmail.to>` |
| `SendMessageResponse.message_id` (provider's own) | `<010001a051dfbf29-423df461-...-000000@email.amazonses.com>` (SES-minted, as in INTAKE-2) |
| Provider id == our custom id? | **No.** |
| `messages.get(inbox, provider_id).message_id` | Same SES id as above — unchanged by our header |
| `messages.get(...).headers` | `{'X-Matter-Ref': 'NWT-COM-0001', 'Message-ID': '<m.NWT-COM-0001.probe-intake4-abc123@oscar-lq.agentmail.to>'}` — **both custom values are stored and echoed back verbatim** |
| `messages.get(...).in_reply_to` / `.references` | `None` / `None` (this was a cold send, not a reply — expected) |

**Reading:** AgentMail accepts and stores an arbitrary `headers` dict, including a key literally
named `Message-ID`, and returns it unchanged from `messages.get`. But the SDK's own canonical
`message_id` field — the one everything else in the codebase (idempotency, `reply()`'s target,
INTAKE-2's whole threading model) keys off — stays the SES-generated id regardless. **Not
verified**: whether the recipient's actual raw RFC-5322 `Message-ID:` header (what a reply's
`In-Reply-To`/`References` would echo) is our custom value, the SES value, or both duplicated —
that requires inspecting the raw message as received by an external mail client, out of scope
for this probe (no external inbox instrumented). Treat "custom Message-ID becomes the wire
header a reply will reference" as **unconfirmed**, not proven.

### Experiment 2 — plus-address delivery + `reply_to` plus-address

**2a — self-send to `oscar-lq+NWT-COM-0001@agentmail.to`:** accepted; `SendMessageResponse`
returned normally; the *sent* copy's `.to` came back as `['oscar-lq+nwt-com-0001@agentmail.to']`
(lower-cased) with `labels: ['sent']`. Polled `messages.list(ascending=False)` every 5s for 60s:
**no `received` row ever appeared addressed to the plus-tag** — the only `received` rows in that
window (from earlier real traffic) all show `to: ['oscar-lq@agentmail.to']` (no tag).

**This result is inconclusive, not negative.** INTAKE-2 already established that AgentMail never
re-ingests ANY self-send as inbound (`message.received` never fires for a send from an inbox to
itself, tag or no tag) — so a self-send can't distinguish "plus-address delivers to the base
inbox" from "self-sends never arrive as received at all." The same structural limitation that
forced INTAKE-2 to rely on a maintainer-sent external Gmail message applies here: **a real
external sender targeting the plus-address is required for a conclusive answer**, and none was
available in this probe run.

**Additional signal (control-plane, not receiving-path):** `inboxes.get("oscar-lq+NWT-COM-
0001@agentmail.to")` → **404**; `inboxes.get("oscar-lq@agentmail.to")` → 200. AgentMail's inbox
object model (`inbox_id == address`, per INTAKE-2) does **not** recognise the plus-tagged address
as an inbox at all — there is no aliasing at the inbox-CRUD layer. This is suggestive that
plus-addressing is not a first-class AgentMail concept, but it does not by itself prove the SMTP
receiving side rejects or mis-routes such mail (Gmail-style subaddressing is normally stripped
by the MTA *before* inbox lookup, which this control-plane check cannot see).

**2b — `reply_to` field, does it accept a plus-address:** yes. Sent with
`reply_to="oscar-lq+NWT-COM-0001@agentmail.to"`; `messages.get(...).reply_to` came back as
`['oscar-lq+nwt-com-0001@agentmail.to']`. The field exists, takes a plus-tagged address with no
validation error, and is stored/returned faithfully. Whether a recipient's mail client actually
honours `Reply-To` on send is client-side behaviour outside AgentMail's control either way (RFC
5322 semantics, not a provider question).

### Experiment 3 — In-Reply-To / References field names + existing wiring

No new live send was needed here — INTAKE-2 Step 5 already exercised `reply()` and captured
`in_reply_to`/`references` populated correctly on the reply, and the Message model fields are
confirmed above via `inspect`. Cross-checked against the actual code:

- **Field names, confirmed via `Message.model_fields`:** `in_reply_to: Optional[str]` (singular
  string, the parent's `message_id`) and `references: Optional[List[str]]` (a list, not a raw
  header string) — both are **typed SDK fields**, populated by AgentMail's own parse of the
  inbound RFC-5322 headers, **not** sourced from the generic `headers` dict (which INTAKE-2
  already found empty (`{}`) even on a genuine inbound message, and which experiment 1 above
  shows is only populated when *we* explicitly pass `headers=` on an outbound send).
- **`messages.get` includes them:** yes — both fields are declared on `Message` and returned by
  `messages.get` (verified structurally via `model_fields`; INTAKE-2 verified them populated
  live on a reply's `Message`).
- **mail-bridge already forwards them — this is the interesting finding.**
  `mail-bridge/app/normalize.py::_bound_headers()` (INTAKE-2 code, already shipped) reads
  `message.in_reply_to` and `message.references` off the typed SDK fields (explicitly NOT the
  raw `headers` dict, per its own docstring) and writes them into the envelope's
  `message.headers["In-Reply-To"]` / `["References"]`. `api/app/schemas/intake.py`'s
  `ALLOWED_HEADER_KEYS` allowlist already includes exactly `{"Auto-Submitted", "Precedence",
  "In-Reply-To", "References"}`, so the envelope validates and reaches the landing endpoint
  intact.
  **But `api/app/api/intake_emails.py::ingest_email` never reads `envelope.message.headers` at
  all** — the `IntakeMessage` row it inserts sets `thread_id, provider_message_id, direction,
  from_addr, to_addrs, subject, body_text, provider_timestamp` and nothing else; `headers` is
  validated then silently discarded. `IntakeMessage` (`api/app/models/intake.py`) also has **no
  column** to hold it. So: the wire-format plumbing for layer 2 (`References` reaching the api)
  is 100% built already from INTAKE-2; **what's missing for INTAKE-4 is entirely at the landing
  endpoint and schema**: (1) a way to persist/read `envelope.message.headers.get("References")` /
  `.get("In-Reply-To")` at ingest, (2) an outbound `provider_message_id` column on
  `IntakeMessage` for `direction='out'` rows (doesn't exist yet — `MailSender.reply()` in
  `mail-bridge/app/sender.py` returns `provider_message_id` today but nothing in `api/` calls it
  or stores it), and (3) per the plan, `UNIQUE(thread_id, provider_message_id)` is
  thread-scoped — a layer-2 lookup by `References` needs to search **across all threads**, which
  works against that constraint's underlying index but would benefit from its own plain index on
  `provider_message_id` alone (cross-thread lookup today would do a full-table equality scan
  without one).

### Verdicts (answering the three questions)

1. **Custom Message-ID / custom headers: partially honoured, don't rely on the Message-ID
   sticking as the canonical id.** `send`/`reply` both accept an arbitrary `headers: Dict[str,
   str]`; whatever you pass — including a key named `Message-ID` — is stored and echoed back
   verbatim by `messages.get`. But `SendMessageResponse.message_id` / `Message.message_id`
   (the field the whole codebase keys idempotency and `reply()` off) stays the SES-minted id
   regardless of what you pass in `headers["Message-ID"]`, and whether the *wire* RFC-5322
   `Message-ID:` a recipient's client would see and reference in a reply is our custom value was
   not verifiable in this probe. **Recommendation for INTAKE-4:** do NOT depend on a
   caller-chosen Message-ID surviving as the id a counterparty's `References` will contain — this
   is exactly the plan's documented fallback case. Persist the **provider-assigned**
   `message_id` returned from `reply()`/`send()` on the outbound `intake_messages` row and match
   layer 2 on that opaque id. A custom `X-Matter-Ref` header, however, IS reliably stored (proven
   above) and could be sent as a redundant belt-and-braces signal alongside the subject tag —
   but since `headers` isn't guaranteed to survive to the wire for the *recipient's mail client*
   either (only proven round-trip through AgentMail's own storage, not through an external
   inbox), treat it as no stronger than the subject tag (layer 3, weak) unless separately
   verified with an external round trip.

2. **Plus-addressing: inconclusive — self-send structurally cannot answer this question, and a
   control-plane signal (404 on `inboxes.get` for the tagged address) leans toward "not
   supported" but doesn't prove the receiving path.** `reply_to` DOES accept and store a
   plus-tagged address (field exists, works). **Recommendation for INTAKE-4:** the 10-minute
   plus-addressing probe the plan calls out is **still open** — it needs the same kind of
   maintainer action INTAKE-2 needed for `message.received` (an external send, this time to
   `oscar-lq+NWT-COM-0001@agentmail.to`) before this is decided either way. Given the 404 and the
   total absence of plus-addressing from AgentMail's docs, default to **not** relying on
   plus-addressing for INTAKE-4a/b unless that follow-up send confirms delivery; the subject-tag
   (layer 3) + References (layer 2) combination in ADR-F088 does not need it to work.

3. **In-Reply-To / References: dedicated typed fields (`in_reply_to: str | None`,
   `references: list[str] | None`) on `Message`, confirmed via `model_fields` and already
   populated live in INTAKE-2's reply test — and the mail-bridge ALREADY forwards them into the
   envelope's `message.headers["In-Reply-To"]`/`["References"]` today (shipped in INTAKE-2,
   `normalize.py::_bound_headers`), already inside the api's `ALLOWED_HEADER_KEYS` allowlist.**
   **What's actually missing for INTAKE-4 is entirely on the api side**, not the bridge: (a)
   `ingest_email` in `intake_emails.py` must read `envelope.message.headers.get("References")` /
   `.get("In-Reply-To")` (currently ignored), (b) `IntakeMessage` needs a way to persist the
   **outbound** `provider_message_id` per row (the column exists for inbound rows already;
   `MailSender.reply()` already returns it, nothing stores it), and (c) the layer-2 lookup needs
   a query across all threads by `provider_message_id`, which the current
   `UNIQUE(thread_id, provider_message_id)` constraint doesn't index for on its own — worth its
   own index if this becomes a hot lookup.

### Plus-address — RESOLVED (external send, 2026-08-30 08:58 UTC)

An external message (Gmail → `oscar-lq+NWT-COM-0001@agentmail.to`, subject
`Plus-address delivery probe [NWT-COM-0001]`) was delivered to the base inbox, forwarded by the
bridge, and processed as intake thread `9a08f4c2…` (outcome `handled`). The stored recipient is
`oscar-lq+nwt-com-0001@agentmail.to` — the tag survives (lowercased by the provider, so the
resolver must compare case-insensitively). Verdict: **plus-addressing is supported**. INTAKE-4b
should set `reply_to` = `<inbox-local>+<ORG-AREA-NNNN>@<domain>` on every outbound reply and the
resolver should treat a plus-tag on the recipient address as a strong signal (the recipient
address is set by us, not by the sender; it is still combined with layer 2/3 rules — a stranger
can type it, so it ranks like the subject tag: Roster-gated).
