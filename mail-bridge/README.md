# LQ.AI Mail Bridge (INTAKE-2)

The mail bridge is the email counterpart of `slack-bridge/` and `teams-bridge/`:
a small standalone service that mediates between an email provider (AgentMail in
v1) and the LQ.AI api. Per [ADR-F086](../docs/adr/F086-email-intake-architecture.md)
it is the **only holder of mailbox credentials** — the same key-holder pattern the
Inference Gateway applies to provider keys. The api never sees the AgentMail key
and never talks to AgentMail.

## What it does

- **Ingests** inbound mail: normalizes each message into the provider-agnostic
  `InboundEmailEnvelope` (`api/app/schemas/intake.py`), fetches attachment bytes,
  and POSTs to `POST /api/v1/internal/intake/emails` behind `LQ_AI_BRIDGE_TOKEN`.
- **Sends** human-approved replies: `POST /send` (contract landed now, consumed by
  INTAKE-4). Reply-only — keyed by the message being answered. There is no
  cold-send endpoint: v1 sends nothing unsolicited.
- Health: `GET /healthz` (liveness, wired into the compose healthcheck) and
  `GET /readyz` (the api is reachable).

Swapping provider (M365 Graph, Gmail) means a new bridge implementing the same
envelope — the api is untouched.

## Ingress: dev vs prod

| | Dev | Prod |
|---|---|---|
| Path | AgentMail **websocket subscriber** (dials out) | `POST /agentmail/webhook` (Svix-signed) |
| Why | the dev box has no public URL AgentMail could call | AgentMail's recommended production delivery |
| Enabled by | always on (lifespan background task) | mounted **only** when `AGENTMAIL_WEBHOOK_SECRET` is set |

Both ingresses converge on one normalize → fetch → forward pipeline
(`app/pipeline.py`), so behaviour cannot drift between them.

Two probe-verified properties shape the subscriber
(`docs/fork/evidence/intake-probe/findings.md`):

- The SDK has **no auto-reconnect**, so the loop reconnects with capped
  exponential backoff.
- A **clean close looks like success** — `websockets` swallows
  `ConnectionClosedOK` — so the backoff only resets after a session that actually
  stayed up. Otherwise a server closing with code 1000 produced a ~2/second
  reconnect storm, each cycle re-running a full reconciliation.
- AgentMail has **no event replay** (its event log records label changes only), so
  every (re)connect runs a **reconciliation poll** and re-forwards everything
  labelled `received`. The bridge keeps NO durable state: the api's
  `(thread, provider_message_id)` idempotency turns a re-POST into a cheap
  `duplicate: true`. An in-process high-water mark bounds the re-download cost
  (cold start sweeps the newest page; afterwards it asks only for what is newer,
  following `next_page_token`) — losing it on restart costs one extra sweep,
  never correctness.
- The subscription waits for the server's `Subscribed` ack before it counts as
  established, and `/readyz` reports how long ago the last frame arrived, so a
  silently dead subscription is observable.
- Self-sends never fire `message.received` (they fire `message.sent` +
  `message.delivered`), so filtering on the event type is a complete loop guard.

## Configuration

| Env var | Required | Purpose |
|---|---|---|
| `AGENTMAIL_API_KEY` | yes | AgentMail API key — the only copy in the deployment |
| `AGENTMAIL_INBOX_ADDRESS` | yes | The intake mailbox; AgentMail's `inbox_id` *is* the address |
| `AGENTMAIL_WEBHOOK_SECRET` | no | Svix signing secret (`whsec_…`). Set ⇒ the webhook route is mounted (prod). Unset ⇒ websocket only (dev) |
| `LQ_AI_BACKEND_URL` | yes | Base URL of the lq-ai api (e.g. `http://api:8000`) |
| `LQ_AI_BRIDGE_TOKEN` | yes | Shared secret on the bridge ↔ api channel, both directions |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | no | OpenTelemetry exporter — opt-in per PRD §5.7 |
| `OTEL_SERVICE_NAME` | no | Defaults to `lq-ai-mail-bridge` |
| `LQ_AI_MAIL_BRIDGE_LOG_LEVEL` | no | Defaults to `INFO` |

## Running locally

```bash
docker compose --profile mail up -d mail-bridge
```

The service ships behind the `mail` Compose profile so operators who do not run
email intake don't pay the SBOM cost. See `docker-compose.yml`.

## Security posture

- The AgentMail key lives only in this service's environment. It is never
  logged, never serialized into a response, never forwarded to the api.
- Attachment `download_url`s are **presigned, unauthenticated, ~1 h TTL** links —
  credentials in URL form. They are fetched server-side and never logged,
  persisted, or handed to a browser. Three separate leak paths are closed: httpx's
  own INFO request log (`mute_url_logging`), OpenTelemetry span attributes (the
  CDN client is deliberately not instrumented), and exception chaining (provider
  errors are re-raised `from None`, carrying only a type name or status code).
- Attachment bodies are **streamed with a hard abort** at the caps, and declared
  sizes are checked against the running aggregate, so an oversize set is never
  buffered into memory on a small box.
- **Email content is untrusted model input.** Every log line here carries counts,
  types and IDs only — never a subject, body, sender or attachment bytes.
- The bridge normalizes *down* to the api's bounds (body truncated with a visible
  `[truncated by mail-bridge]` marker, over-long recipients dropped, oversize
  attachments skipped) rather than letting the api's 422 lose an email that
  cannot be replayed.
- `POST /send` is gated by a constant-time `LQ_AI_BRIDGE_TOKEN` bearer check and
  can only reply into an existing thread.

## Tests

```bash
cd mail-bridge
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -q
```

The service requires Python 3.12. On a host that only has an older interpreter,
run the suite in the same base image CI and the Dockerfile use:

```bash
docker run --rm -v "$PWD:/w" -w /w python:3.12-slim \
  sh -c "pip install -q -e '.[dev]' && ruff check . && ruff format --check . && mypy app && pytest -q"
```

No test touches AgentMail: the SDK, the CDN download and the api are all faked at
the injection seams.
