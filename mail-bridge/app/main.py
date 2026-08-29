"""LQ.AI Mail Bridge — FastAPI entry point — INTAKE-2 (ADR-F086).

The bridge is the sole holder of mailbox credentials (ADR-F086, the gateway
key-holder pattern applied to email). It has two ingresses and one egress:

* **dev ingress — websocket subscriber** (``app.subscriber``), always started as
  a lifespan-managed background task. The dev box has no public URL, so the
  bridge dials out instead of being called.
* **prod ingress — ``POST /agentmail/webhook``**, mounted ONLY when
  ``AGENTMAIL_WEBHOOK_SECRET`` is configured. Svix-signed; a bad signature is a
  400, a forward failure is a 5xx so Svix retries.
* **egress — ``POST /send``** (INTAKE-4): a human-approved reply, gated by the
  same ``LQ_AI_BRIDGE_TOKEN`` bearer the bridge presents to the api.

Plus ``GET /healthz`` (liveness, wired into the compose healthcheck) and
``GET /readyz`` (the api is reachable).
"""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import json
import logging
from collections.abc import AsyncIterator
from typing import Annotated, Any

import httpx
from agentmail import AsyncAgentMail, MessageReceivedEvent
from agentmail.core.unchecked_base_model import construct_type
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from svix.webhooks import Webhook, WebhookVerificationError

from .attachments import AttachmentFetcher
from .config import Settings, get_settings
from .forwarder import IntakeForwarder
from .observability import init_otel, instrument_http_client, mute_url_logging
from .pipeline import RECEIVED_EVENT_TYPE, IntakePipeline
from .schemas import SendReplyRequest, SendReplyResponse
from .sender import MailSender
from .subscriber import MailSubscriber

log = logging.getLogger(__name__)

#: Generous enough for a 25 MB attachment over the presigned CDN link, tight
#: enough that a wedged provider does not pin a task forever.
_HTTP_TIMEOUT_SECONDS = 30.0

#: Webhook bodies are id envelopes plus inline text — attachment bytes are
#: fetched separately and never inlined by AgentMail. 2 MB is roomy for the
#: documented 1 MB event cap while bounding what an unauthenticated caller can
#: make this process buffer.
_MAX_WEBHOOK_BODY = 2 * 1024 * 1024


def _require_bridge_token(request: Request) -> None:
    """Gate ``/send`` on the shared bridge secret.

    Same shape as the api's ``require_bridge_auth`` (which authenticates this
    bridge in the other direction): a Bearer compared in constant time. 401 on
    anything else — no hint about which half was wrong.
    """

    settings: Settings = request.app.state.settings
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    # compare_digest on str raises TypeError for non-ASCII input (which would
    # surface as a 500, not a 401) — compare the encoded bytes instead.
    if scheme.lower() != "bearer" or not hmac.compare_digest(
        token.encode("utf-8"), settings.lq_ai_bridge_token.encode("utf-8")
    ):
        raise HTTPException(status_code=401, detail="invalid bridge token")


def _get_sender(request: Request) -> MailSender:
    sender: MailSender | None = getattr(request.app.state, "sender", None)
    if sender is None:  # pragma: no cover - only reachable if lifespan never ran
        raise HTTPException(status_code=503, detail="bridge not ready")
    return sender


def _get_pipeline(request: Request) -> IntakePipeline:
    pipeline: IntakePipeline | None = getattr(request.app.state, "pipeline", None)
    if pipeline is None:  # pragma: no cover - only reachable if lifespan never ran
        raise HTTPException(status_code=503, detail="bridge not ready")
    return pipeline


def create_app(
    settings: Settings | None = None,
    *,
    pipeline: IntakePipeline | None = None,
    sender: MailSender | None = None,
    subscriber: MailSubscriber | None = None,
    run_subscriber: bool = True,
) -> FastAPI:
    """Build the FastAPI application.

    Every collaborator is injectable (CLAUDE.md: inject dependencies, wire up
    once at the composition root). Production passes none of them and the
    lifespan constructs the real AgentMail client, httpx client, fetcher,
    forwarder, pipeline, sender and subscriber; tests pass fakes and
    ``run_subscriber=False``.
    """

    cfg = settings or get_settings()

    logging.basicConfig(
        level=cfg.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    # Must happen before any attachment download: httpx logs full URLs at INFO
    # and ours are presigned credentials. See observability.mute_url_logging.
    mute_url_logging()

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with contextlib.AsyncExitStack() as stack:
            if getattr(app.state, "pipeline", None) is None or (
                getattr(app.state, "sender", None) is None
            ):
                # THREE httpx clients, deliberately:
                #
                #  * `api_http`   — bridge → LQ.AI api. Traced.
                #  * `sdk_http`   — handed to the SDK so the AgentMail client's
                #    transport is owned by this stack: AsyncAgentMail exposes no
                #    close()/aclose(), so passing our own client is the only way
                #    its connections are released at shutdown. Traced.
                #  * `cdn_http`   — presigned attachment downloads. NOT traced:
                #    the httpx instrumentation records the full request URL as a
                #    span attribute, and these URLs ARE the credential. Same
                #    leak class as the httpx INFO log (see mute_url_logging).
                api_http = await stack.enter_async_context(
                    httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS)
                )
                sdk_http = await stack.enter_async_context(
                    httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS)
                )
                cdn_http = await stack.enter_async_context(
                    httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS)
                )
                instrument_http_client(api_http)
                instrument_http_client(sdk_http)

                # The API key never leaves this object: it is not logged, not
                # placed on app.state under its own name, and not forwarded.
                client = AsyncAgentMail(api_key=cfg.agentmail_api_key, httpx_client=sdk_http)
                if getattr(app.state, "pipeline", None) is None:
                    app.state.pipeline = IntakePipeline(
                        inbox_id=cfg.agentmail_inbox_address,
                        fetcher=AttachmentFetcher(client=client, http=cdn_http),
                        forwarder=IntakeForwarder(
                            backend_url=cfg.lq_ai_backend_url,
                            bridge_token=cfg.lq_ai_bridge_token,
                            http=api_http,
                        ),
                    )
                if getattr(app.state, "sender", None) is None:
                    app.state.sender = MailSender(
                        client=client, inbox_id=cfg.agentmail_inbox_address
                    )
                app.state.agentmail_client = client

            task: asyncio.Task[None] | None = None
            loop_subscriber = subscriber
            if loop_subscriber is None and app.state.agentmail_client is not None:
                loop_subscriber = MailSubscriber(
                    client=app.state.agentmail_client,
                    pipeline=app.state.pipeline,
                    inbox_id=cfg.agentmail_inbox_address,
                )
            app.state.subscriber = loop_subscriber
            if run_subscriber and loop_subscriber is not None:
                task = asyncio.create_task(loop_subscriber.run())
            try:
                yield
            finally:
                if task is not None:
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task

    app = FastAPI(
        title="LQ.AI Mail Bridge",
        version="0.1.0",
        description=(
            "Email intake ingress for LQ.AI (ADR-F086). Holds the mailbox "
            "credentials; normalizes inbound mail into the provider-agnostic "
            "InboundEmail envelope and lands it on the api."
        ),
        lifespan=lifespan,
    )

    app.state.settings = cfg
    # Injected collaborators are visible BEFORE the lifespan runs so a test can
    # drive the routes with a plain TestClient.
    app.state.pipeline = pipeline
    app.state.sender = sender
    app.state.agentmail_client = None
    app.state.subscriber = subscriber

    init_otel(cfg)
    FastAPIInstrumentor.instrument_app(app)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz(request: Request) -> JSONResponse:
        """Readiness — the bridge is useless if the api cannot be reached.

        Reasons are fixed status WORDS, never exception text: an httpx error
        string carries the backend host and port, and a readiness probe is the
        one endpoint an operator is most likely to expose.

        The subscription snapshot is reported but does NOT gate readiness — a
        reconnect in progress is normal, and flapping ready/unready on it would
        be worse than a stale-age number an operator can alert on themselves.
        """

        body: dict[str, object] = {"status": "ok"}
        active: MailSubscriber | None = getattr(request.app.state, "subscriber", None)
        if active is not None:
            body["subscription"] = active.health()

        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.get(f"{cfg.lq_ai_backend_url}/health")
                if res.status_code != 200:
                    return JSONResponse(
                        status_code=503,
                        content={**body, "status": "unready", "reason": "backend_unhealthy"},
                    )
        except (httpx.HTTPError, OSError):
            return JSONResponse(
                status_code=503,
                content={**body, "status": "unready", "reason": "backend_unreachable"},
            )
        return JSONResponse(content=body)

    @app.post(
        "/send",
        response_model=SendReplyResponse,
        dependencies=[Depends(_require_bridge_token)],
        summary="Send one human-approved reply into an existing thread",
    )
    async def send_reply(
        payload: SendReplyRequest,
        mail_sender: Annotated[MailSender, Depends(_get_sender)],
    ) -> SendReplyResponse:
        return await mail_sender.reply(payload)

    if cfg.agentmail_webhook_secret is not None:
        # PROD ingress. Mounted only when a Svix secret exists, so a dev
        # deployment has no unauthenticated-by-omission route at all.
        webhook = Webhook(cfg.agentmail_webhook_secret)

        @app.post("/agentmail/webhook", summary="AgentMail (Svix) webhook ingress")
        async def agentmail_webhook(
            request: Request,
            intake: Annotated[IntakePipeline, Depends(_get_pipeline)],
        ) -> dict[str, str]:
            # Refuse an oversized delivery BEFORE reading it into memory. An
            # AgentMail event is an id envelope plus inline text (attachment
            # BYTES are never inlined — the probe confirmed only metadata
            # arrives), so 2 MB is generous; without this check an attacker who
            # merely knows the URL can make the process buffer arbitrary bytes
            # before the signature is ever examined.
            declared = request.headers.get("content-length")
            if declared is not None and declared.isdigit() and int(declared) > _MAX_WEBHOOK_BODY:
                log.warning(
                    "mail-bridge: webhook body over cap; refused unread",
                    extra={"event": "mail_webhook_too_large", "declared_bytes": int(declared)},
                )
                raise HTTPException(status_code=413, detail="payload too large")

            # Svix signs the RAW body bytes — never the re-serialized JSON.
            body = await request.body()
            if len(body) > _MAX_WEBHOOK_BODY:
                # Chunked delivery: no Content-Length to pre-check against.
                raise HTTPException(status_code=413, detail="payload too large")
            try:
                webhook.verify(body, dict(request.headers))
            except WebhookVerificationError:
                log.warning(
                    "mail-bridge: webhook signature rejected",
                    extra={"event": "mail_webhook_bad_signature"},
                )
                raise HTTPException(status_code=400, detail="invalid signature") from None

            try:
                payload: Any = json.loads(body)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="malformed payload") from None

            if not isinstance(payload, dict) or payload.get("event_type") != RECEIVED_EVENT_TYPE:
                # Our own message.sent/delivered copies, and every other kind
                # of event — acknowledged, never acted on (the loop guard).
                return {"status": "ignored"}

            # Same deserializer the SDK's websocket client uses, so both
            # ingresses build byte-identical events from the same JSON.
            #
            # A construct failure on a SIGNED delivery is never junk mail — it
            # is our bug or a provider contract change, and the email is real.
            # 5xx (so Svix retries and the delivery survives long enough to be
            # noticed) rather than a 4xx that discards it permanently.
            try:
                event = construct_type(type_=MessageReceivedEvent, object_=payload)
            except Exception as exc:
                log.error(
                    "mail-bridge: signed message.received could not be deserialized",
                    extra={
                        "event": "mail_webhook_construct_failed",
                        "error_type": type(exc).__name__,
                    },
                )
                raise HTTPException(status_code=500, detail="event not deserializable") from None
            if not isinstance(event, MessageReceivedEvent):
                log.error(
                    "mail-bridge: signed message.received deserialized to the wrong type",
                    extra={
                        "event": "mail_webhook_construct_failed",
                        "error_type": type(event).__name__,
                    },
                )
                raise HTTPException(status_code=500, detail="event not deserializable")

            # A forward failure MUST surface as a 5xx: Svix retries, and a
            # swallowed error would drop a real email on the floor.
            await intake.process_event(event)
            return {"status": "ok"}

    return app


app = create_app()
