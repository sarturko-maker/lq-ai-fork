# INTAKE research 2/4 — AgentMail integration contract (Sonnet sub-agent, 2026-08-16)

> Commissioned for the INTAKE milestone plan (`docs/fork/plans/INTAKE-INBOX-plan.md`, task #536).
> Web research against primary sources; verbatim from the research agent, unedited.

## 1. Account, Auth & Pricing

**Base URL:** `https://api.agentmail.to/v0` · **Websocket URL:** `wss://ws.agentmail.to/v0`
**Auth header (confirmed on every endpoint fetched):** `Authorization: Bearer <api_key>` — not `x-api-key`.
Keys are minted in the console (`console.agentmail.to` → API Keys, shown once). Two scopes exist: **organization-level** keys (full access) and **scoped keys** restricted to one Pod or Inbox.

**Hierarchy:** `Organization` (your account) → optional `Pods` (isolated multi-tenant workspaces, each with its own inboxes/domains/threads/drafts) → `Inboxes`. Pods are opt-in — "if you are only managing email for your own organization, Pods are optional... work directly with inboxes." For a single test inbox, skip Pods entirely.
`GET /v0/organizations` returns the org for the authenticated key: `organization_id, inbox_count, domain_count, inbox_limit?, domain_limit?, billing_id?, billing_type?, billing_subscription_id?, created_at, updated_at`. No separate "who-am-i" endpoint exists — this doubles as one.

**Pricing (agentmail.to/pricing, current):**

| Tier | Price | Inboxes | Emails/mo | Emails/day | Storage | Custom domains | Seats |
|---|---|---|---|---|---|---|---|
| Free | $0 | 3 | 3,000 | 100 | 3 GB | **0** | — |
| Developer | $20/mo | 10 | 10,000 | 1,000 | 10 GB | 10 | 2 |
| Startup | $200/mo | 150 | 150,000 | 15,000 | 150 GB | 150 | 10 |
| Enterprise | custom | unlimited | custom | custom | custom | custom | white-label, EU region, BYO cloud |

All tiers include threads/labels/attachments/drafts/schedule-send/SDKs/MCP server. **Free tier has zero custom domains** — for a literal `legal-intake@yourdomain.com` you need Developer ($20/mo) minimum. A default `@agentmail.to` address needs **no setup at all**.

**Custom domain setup** (if wanted): create via console/API/CLI → returns DNS records → add MX (`inbound-smtp.us-east-1.amazonaws.com`, prio 10), SPF TXT (`include:spf.agentmail.to`), DKIM TXT (selector e.g. `mail._domainkey` — on Route53 split >255-char value into two quoted strings, no space between), DMARC TXT at `_dmarc` → verify in console (minutes–48h). BIND zonefile download offered for bulk import (Cloudflare/Route53/Porkbun supported).

## 2. Core Objects & Endpoints

| Action | Method + Path |
|---|---|
| Create/List/Get inbox | `POST/GET /v0/inboxes`, `GET /v0/inboxes/{inbox_id}` |
| List/Get thread | `GET /v0/inboxes/{inbox_id}/threads` (params `limit`, `page_token`), `GET .../threads/{thread_id}` |
| List/Get message | `GET /v0/inboxes/{inbox_id}/messages` (params `page_token`, `after`, `before` datetimes, `limit`≤100, `labels[]`, `ascending`), `GET .../messages/{message_id}` |
| Send new message | `POST /v0/inboxes/{inbox_id}/messages/send` |
| Reply | `POST /v0/inboxes/{inbox_id}/messages/{message_id}/reply` (**keyed by message_id**, not thread_id) |
| Reply-all / Forward | `POST .../messages/{message_id}/reply-all`, `POST .../messages/{message_id}/forward` |
| Get attachment | `GET /v0/inboxes/{inbox_id}/messages/{message_id}/attachments/{attachment_id}` (thread-scoped variant also exists) |
| Draft create/update | `POST /v0/inboxes/{inbox_id}/drafts`, `PATCH .../drafts/{draft_id}` |
| Webhook create/list | `POST /v0/webhooks` (`url`, `event_types[]`, `client_id?`), `GET /v0/webhooks` |

**Inbox object:** `pod_id, inbox_id, email, updated_at, created_at, display_name?, client_id?, metadata?`
**Thread object:** `inbox_id, thread_id, labels[], timestamp, senders[], recipients[], last_message_id, message_count, size, created_at, updated_at, subject?, preview?, attachments?[]`
**Message object:** `inbox_id, thread_id, message_id, labels[], timestamp, from, to, size, created_at, updated_at` + optional `subject, preview, text, html, extracted_text, extracted_html, reply_to, cc, bcc, in_reply_to, references, headers{}, attachments[]`. Attachment metadata: `attachment_id, size (required), filename?, content_type?, content_disposition (inline|attachment)?, content_id?`.

**Sending attachments** (identical shape in `send`, `reply`, and drafts): a list of objects, each `{filename, content_type, content_disposition, content_id, content, url}` — `content` is **base64-encoded** file bytes. No separate upload endpoint; it's inline JSON, not multipart. `client_id` on create calls is your idempotency key (re-POST with same value returns the existing resource) — this pattern was **not** confirmed for `send`/`reply`.

**Downloading attachment bytes:** documented REST response contains a JSON `download_url` field (signed, hosted at `cdn.agentmail.to`, ~1-hour expiry per a GitHub SDK reference doc — "fetch immediately, never persist the URL"). SDK code samples elsewhere show `client.inboxes.messages.get_attachment(...)` handing back raw bytes in one call. These two descriptions weren't fully reconcilable from docs alone — see Could-Not-Verify.

## 3. Event Delivery

**Event types:** `message.received`, `message.received.spam`, `message.received.blocked`, `message.received.unauthenticated`, `message.sent`, `message.delivered`, `message.bounced`, `message.complained`, `message.rejected`, `domain.verified`. Spam/blocked/unauthenticated are **excluded by default** unless explicitly listed.

**Payload:** embeds the **full message inline** (`event_type, event_id, message: {..., text, html, attachments:[{attachment_id, filename}]}}`) — capped at **1 MB total**; if the full message would exceed that, `text`/`html` are silently dropped from the payload (you must then `GET` the message by ID). So: mostly self-contained, with a documented fallback-to-fetch path for large messages.

**Signature verification:** AgentMail uses **Svix**. Headers: `svix-id`, `svix-timestamp`, `svix-signature` (format `v1,<base64>`), 5-minute timestamp tolerance, secret prefixed `whsec_`. Recommended via the `svix` Python package, verifying the **raw request body bytes**.

**Retries:** AgentMail's own docs don't publish their own attempt schedule — they only say to expect retries and to return `200` fast. Since delivery is delegated to Svix, Svix's public default (8 attempts over ~27.5h: immediate, +5s, +5m, +30m, +2h, +5h, +10h, +10h; endpoint auto-disabled after 5 days of total failure) is a reasonable proxy but is **not confirmed as AgentMail's actual configuration**.

**Loop protection:** the only documented mechanism is app-level — "filter out `message.sent` events to prevent your agent from replying to its own messages in a loop." No mention of AgentMail setting `Auto-Submitted`/`Precedence` headers itself, nor of it detecting other systems' autoreplies.

**Websocket alternative:** `wss://ws.agentmail.to/v0`, auth via `auth_token` param or `Authorization` header, `client.websockets.connect()` → `socket.send_subscribe(Subscribe(inbox_ids=[...]))` → iterate typed events (`Subscribed`, `MessageReceivedEvent`, ...). Positioned explicitly as the **local-dev, no-public-URL** alternative to webhooks (no ngrok needed); webhooks remain the production-recommended path.

**Polling fallback:** fully viable — `GET /v0/inboxes/{inbox_id}/messages?after=<ts>&page_token=<tok>&limit=100&ascending=true`, response `{count, messages[], next_page_token?}`. Store the last `after` timestamp or `next_page_token` and poll from an arq cron job.

## 4. Python SDK

Package **`agentmail`** on PyPI, current **v0.5.9**, released **2026-08-03** (confirmed via PyPI JSON API `upload_time_iso_8601`). Requires Python `>=3.8,<4.0`; deps `httpx>=0.21.2`, `pydantic>=1.9.2`, `websockets>=12.0`. Fern-generated (`github.com/agentmail-to/agentmail-python`, 63 stars, 2 open issues, releases every 1–3 weeks — small but actively maintained, plus a broader org with `agentmail-toolkit`, `langchain-agentmail`, `agentmail-mcp`, `agentmail-skills`). Both sync (`AgentMail`) and async (`AsyncAgentMail`) clients, plus a websocket sub-client with sync/async context managers.

**(a) FastAPI webhook receiver with signature verification**
```python
import os
from fastapi import FastAPI, Request, HTTPException
from svix.webhooks import Webhook, WebhookVerificationError
from arq import create_pool
from arq.connections import RedisSettings

app = FastAPI()
WEBHOOK_SECRET = os.environ["AGENTMAIL_WEBHOOK_SECRET"]  # whsec_...

@app.post("/webhooks/agentmail")
async def agentmail_webhook(request: Request):
    body = await request.body()  # RAW bytes — required, not request.json()
    try:
        payload = Webhook(WEBHOOK_SECRET).verify(body, dict(request.headers))
    except WebhookVerificationError:
        raise HTTPException(status_code=400, detail="bad signature")

    if payload["event_type"] == "message.sent":
        return {"ok": True}  # loop guard: ignore our own outbound copies

    redis = await create_pool(RedisSettings.from_dsn(os.environ["REDIS_URL"]))
    await redis.enqueue_job("triage_inbound_email", payload)
    return {"ok": True}  # ack fast; do real work in the arq worker
```

**(b) Fetch a thread and download its attachments**
```python
import os
from agentmail import AgentMail

client = AgentMail(api_key=os.environ["AGENTMAIL_API_KEY"])

def fetch_thread_attachments(inbox_id: str, thread_id: str, dest_dir: str) -> list[str]:
    thread = client.inboxes.threads.get(inbox_id=inbox_id, thread_id=thread_id)
    message = client.inboxes.messages.get(
        inbox_id=inbox_id, message_id=thread.last_message_id
    )
    saved = []
    for att in message.attachments or []:
        data = client.inboxes.messages.get_attachment(   # SDK docs show raw bytes;
            inbox_id=inbox_id, message_id=message.message_id,
            attachment_id=att.attachment_id,
        )                                                 # verify against download_url behavior — see gotchas
        path = os.path.join(dest_dir, att.filename or att.attachment_id)
        with open(path, "wb") as f:
            f.write(data)
        saved.append(path)
    return saved
```

**(c) Reply in-thread with a .docx attachment**
```python
import base64, os
from agentmail import AgentMail

client = AgentMail(api_key=os.environ["AGENTMAIL_API_KEY"])

def reply_with_docx(inbox_id: str, message_id: str, body_text: str, docx_path: str):
    content_b64 = base64.b64encode(open(docx_path, "rb").read()).decode()
    return client.inboxes.messages.reply(
        inbox_id=inbox_id,
        message_id=message_id,
        text=body_text,
        attachments=[{
            "filename": os.path.basename(docx_path),
            "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "content_disposition": "attachment",
            "content": content_b64,
        }],
    )  # -> {"message_id": ..., "thread_id": ...}
```

## 5. Gotchas

- Signature check needs **raw bytes** (`await request.body()`), not parsed JSON — parse-then-reserialize breaks the HMAC.
- Webhook payload caps at **1 MB**; oversized messages silently drop `text`/`html` — always have a GET-by-ID fallback path, since legal-intake emails with attachments will trip this.
- Attachment download semantics disagree across doc pages (signed `download_url` vs. raw bytes from the SDK helper) — verify empirically before relying on either in production code.
- Free tier = **0 custom domains**; use default `@agentmail.to` for the fastest dev-box setup, upgrade only if you need the literal company domain in the From address.
- `/reply` is keyed by `message_id`; `thread_id` comes back in the response. Overlapping surface exists: dedicated `/reply-all` and `/forward` endpoints AND a `reply_all` boolean on the plain `/reply` body — pick one and confirm against the live OpenAPI spec (`docs.agentmail.to/openapi.json`).
- `client_id` gives idempotent creates for inboxes/webhooks/drafts; no generic `Idempotency-Key` header was found for `send`/`reply` — duplicate-send protection on retry is on you.
- Rate limiting is per-API-key, standard `429` + `Retry-After`; the generated SDK already retries 5xx/429 with backoff.
- Pods are optional — ignore them for a single test inbox.

## 6. Nearest Alternatives (confirmation only)

- **Gmail API + Pub/Sub push** — free, but needs a real Workspace domain, GCP project, and 7-day `watch()` renewal; far more moving parts.
- **Postmark inbound webhooks** — mature, reliable, but inbound is bolt-on to a transactional-send product; no thread/agent-native modeling.
- **Resend inbound webhooks** — clean DX, but inbound email is a newer addition; less mature thread/attachment ergonomics.
- **Mailslurp** — purpose-built disposable test inboxes, closest in spirit, but QA/test-automation framed, not agent-native (no MCP).
- **Mailgun routes** — powerful, battle-tested, but low-level: you parse raw MIME yourself.

AgentMail is the lowest-friction choice here: free-tier default address works in minutes with no domain, JSON message/thread objects need no MIME parsing, and its Python SDK + webhook model map directly onto a FastAPI/arq stack.

## Could Not Verify (flagged, not guessed)

- Exact attachment size limits in MB (inbound/outbound) — no primary doc page stated a number to my fetches; a search-engine synthesis surfaced "40 MB outbound ceiling" but I could not trace it to a primary AgentMail page verbatim.
- Whether `get_attachment()` returns raw bytes or a signed URL you must follow — docs disagree (see Gotchas).
- AgentMail's actual webhook retry attempt count/timing (Svix's public default is a proxy, not a confirmed AgentMail number).
- Concrete data retention period — only generic privacy-policy language ("as long as necessary"), no day/month figure.
- Whether a dedicated sandbox/test mode exists — found no evidence of one; Free tier appears to be the de facto dev environment using real, deliverable addresses.
- Explicit thread_id stability/forking rules (e.g., does a subject change ever fork a new thread_id).
- Whether AgentMail sets `Auto-Submitted`/`Precedence` headers on outbound mail, or filters other systems' autoreplies against your inbox.
- One FAQ fetch suggested agents "can only reply... cannot send without receiving first" — conflicts with the documented `messages/send` endpoint and wasn't corroborated elsewhere; likely a deliverability best-practice note, not a hard restriction, but flagged rather than asserted.
- List/Get Inbox response shape was not independently re-fetched (assumed identical to the documented Create Inbox object).
- Webhook management endpoints beyond create/list (single get/update/delete) not individually confirmed.

**Sources:** [docs.agentmail.to](https://docs.agentmail.to) (API reference, webhook-setup, webhook-verification, custom-domains, attachments, websockets, knowledge-base/rate-limits, knowledge-base/pods-multi-tenant, faq), [agentmail.to/pricing](https://www.agentmail.to/pricing), [pypi.org/project/agentmail](https://pypi.org/project/agentmail/), [github.com/agentmail-to/agentmail-python](https://github.com/agentmail-to/agentmail-python), [github.com/agentmail-to/agentmail-skills](https://github.com/agentmail-to/agentmail-skills), [github.com/agentmail-to/agentmail-docs](https://github.com/agentmail-to/agentmail-docs).
