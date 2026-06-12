"""Run-cycle driver for the F0-S9 qualification harness.

One cycle = POST a run to the LIVE api → poll the run row until it
settles → read the settled ``agent_run_steps`` rows + the routing-log
token counts straight from the DB. Scoring never parses LLM turns; it
reads what the runner persisted (ADR-F004 render-deterministic rule).

Runner hygiene (oscar's silent-403 lesson): a cycle is only VALID when
the run reached a terminal state AND (status='completed' implies a
non-empty final answer). Anything else is recorded as an errored cycle
with the run's own error string — never silently scored as zeros.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

POLL_INTERVAL_S = 3.0
# Runner wall clock is 300s (DEFAULT_WALL_CLOCK_SECONDS) + finalize slack.
POLL_TIMEOUT_S = 420.0

# Spend accounting constants — MiniMax-M3 published pay-as-you-go rates
# (USD per MTok, standard band ≤512k context; the launch promo is half
# this, so these are the conservative upper bound). gateway.yaml has no
# cost_tracking rate for minimax, so cost_estimate is NULL on routing
# rows and the harness computes spend from token counts itself.
# HONESTY NOTE: these rates apply to the MiniMax-routed aliases only;
# when a second family lands, add its rates keyed by routed_model (the
# cycle JSON records routed_model precisely so this stays correctable).
MINIMAX_M3_USD_PER_MTOK_IN = 0.60
MINIMAX_M3_USD_PER_MTOK_OUT = 2.40


@dataclass
class CycleRecord:
    """Everything one cycle persists into its results JSON."""

    scenario_id: str
    model_alias: str
    cycle: int
    run_id: str = ""
    thread_id: str = ""
    status: str = ""
    final_answer: str | None = None
    error: str | None = None
    valid: bool = False
    invalid_reason: str | None = None
    steps: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    started_at: str = ""
    finished_at: str = ""
    duration_s: float | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    gateway_calls: int = 0
    routed_model: str | None = None
    cost_usd_estimate: float | None = None


async def login(client: httpx.AsyncClient, *, email: str, password: str) -> str:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    response.raise_for_status()
    token = response.json().get("access_token")
    if not token:
        raise RuntimeError("login returned no access_token (MFA challenge?)")
    return str(token)


async def create_run(
    client: httpx.AsyncClient,
    *,
    token: str,
    prompt: str,
    project_id: str | None,
    model_alias: str,
    max_steps: int,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "prompt": prompt,
        "model_alias": model_alias,
        "max_steps": max_steps,
    }
    if project_id is not None:
        body["project_id"] = project_id
    response = await client.post(
        "/api/v1/agents/runs", json=body, headers={"Authorization": f"Bearer {token}"}
    )
    response.raise_for_status()
    return dict(response.json())


async def poll_run(
    client: httpx.AsyncClient,
    *,
    token: str,
    run_id: str,
    timeout_s: float = POLL_TIMEOUT_S,
) -> dict[str, Any]:
    """Poll until the run leaves 'running' or the timeout lapses.

    A still-running run after the timeout is returned as-is — the caller
    records it as a stranded (invalid) cycle; it must never hang the
    whole matrix.
    """
    import asyncio

    deadline = datetime.now(UTC) + timedelta(seconds=timeout_s)
    while True:
        response = await client.get(
            f"/api/v1/agents/runs/{run_id}", headers={"Authorization": f"Bearer {token}"}
        )
        response.raise_for_status()
        # AgentRunDetailResponse wraps the row: {"run": {...}, "steps": [...]}.
        run = dict(response.json()["run"])
        if run.get("status") != "running" or datetime.now(UTC) >= deadline:
            return run
        await asyncio.sleep(POLL_INTERVAL_S)


async def fetch_steps(engine: AsyncEngine, run_id: str) -> list[dict[str, Any]]:
    """The settled step rows — the scoring substrate (ADR-F004)."""
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT seq, kind, name, summary, parent_step_id "
                    "FROM agent_run_steps WHERE run_id = :rid ORDER BY seq"
                ),
                {"rid": run_id},
            )
        ).mappings()
        return [
            {
                "seq": r["seq"],
                "kind": r["kind"],
                "name": r["name"],
                "summary": r["summary"],
                "parent_step_id": str(r["parent_step_id"]) if r["parent_step_id"] else None,
            }
            for r in rows
        ]


async def fetch_matter_id(engine: AsyncEngine, *, name: str, owner_email: str) -> str | None:
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT p.id FROM projects p JOIN users u ON u.id = p.owner_id "
                    "WHERE p.name = :name AND u.email = :email AND p.archived_at IS NULL"
                ),
                {"name": name, "email": owner_email},
            )
        ).first()
        return str(row[0]) if row else None


async def fetch_routing_window(
    engine: AsyncEngine,
    *,
    started_at: datetime,
    finished_at: datetime,
    purpose: str = "agent_loop",
) -> tuple[int, int, int, str | None]:
    """(tokens_in, tokens_out, calls, routed_model) for the cycle window.

    Correlation is purpose + timestamp window — agent runs don't stamp
    chat/message ids onto routing rows. Window = [started_at,
    finished_at + 5s]: routing rows are stamped at WRITE time (after the
    provider call completes), so every row of this cycle carries
    timestamp >= started_at by construction — a leading pad would
    double-count the PREVIOUS sequential cycle's final row (S9 review
    fix; the trailing pad only covers a row committing while the run
    settles, and the query runs before the next cycle starts). Cycles
    run SEQUENTIALLY on an otherwise-idle dev stack; concurrent foreign
    traffic would inflate counts and is called out in the README.
    """
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT COALESCE(SUM(tokens_in),0), COALESCE(SUM(tokens_out),0), "
                    "COUNT(*), MAX(routed_model) FROM inference_routing_log "
                    "WHERE purpose = :purpose AND timestamp BETWEEN :t0 AND :t1"
                ),
                {
                    "purpose": purpose,
                    "t0": started_at,
                    "t1": finished_at + timedelta(seconds=5),
                },
            )
        ).first()
    if row is None:
        return 0, 0, 0, None
    return int(row[0]), int(row[1]), int(row[2]), row[3]


def cost_estimate_usd(tokens_in: int, tokens_out: int) -> float:
    return round(
        tokens_in / 1_000_000 * MINIMAX_M3_USD_PER_MTOK_IN
        + tokens_out / 1_000_000 * MINIMAX_M3_USD_PER_MTOK_OUT,
        6,
    )


def validate_cycle(run: dict[str, Any]) -> tuple[bool, str | None]:
    """Runner hygiene: terminal state + answer-or-error, never silence."""
    status = run.get("status")
    if status == "running":
        return False, "stranded: run still 'running' after poll timeout"
    if status == "completed":
        if not (run.get("final_answer") or "").strip():
            return False, "completed run carries an empty final_answer"
        return True, None
    if status in ("failed", "cap_exceeded"):
        # A surfaced failure is a valid OBSERVATION (the cycle executed;
        # the matrix reports it with its error string) — but it is NOT
        # scored: tool_not_fired noise gates would auto-pass on a run
        # that died before dispatching anything (S9 review). The scoring
        # gate lives in test_qualification.py (status == "completed").
        return True, None
    return False, f"unknown terminal status {status!r}"


def new_record(scenario_id: str, model_alias: str, cycle: int) -> CycleRecord:
    return CycleRecord(scenario_id=scenario_id, model_alias=model_alias, cycle=cycle)


def stable_cycle_filename(record: CycleRecord) -> str:
    safe_run = record.run_id or uuid.uuid4().hex[:12]
    return f"{record.scenario_id}--{record.model_alias}--c{record.cycle:02d}--{safe_run}.json"
