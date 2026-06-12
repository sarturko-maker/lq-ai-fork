"""Session wiring for the F0-S9 qualification harness.

Everything is environment-driven so the same files run any (model x
N x scenario) slice without edits — the model is dependency injection
(maintainer directive 2026-06-11):

* ``LQAI_EVAL_API_URL``        — api base url (default ``http://api:8000``)
* ``DATABASE_URL``             — the stack's Postgres (steps + routing log)
* ``LQAI_EVAL_USER_EMAIL``     — run owner (default ``admin@lq.ai``)
* ``LQAI_EVAL_USER_PASSWORD``  — required
* ``LQAI_EVAL_MODELS``         — csv of gateway aliases (default ``smart``)
* ``LQAI_EVAL_N``              — cycles per (scenario x model) (default 1)
* ``LQAI_EVAL_SCENARIOS``      — csv filter (default: all four)
* ``LQAI_EVAL_OUT``            — results dir (default ``evals/out``)
* ``LQAI_EVAL_GIT_SHA``        — provenance stamp for the manifest
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from evals import runner as eval_runner

SCENARIOS_DIR = Path(__file__).parent / "scenarios"


def load_scenarios() -> list[dict[str, Any]]:
    wanted = {s.strip() for s in os.environ.get("LQAI_EVAL_SCENARIOS", "").split(",") if s.strip()}
    out = []
    for path in sorted(SCENARIOS_DIR.glob("*.json")):
        scenario = json.loads(path.read_text())
        if not wanted or scenario["id"] in wanted:
            out.append(scenario)
    return out


def eval_models() -> list[str]:
    return [m.strip() for m in os.environ.get("LQAI_EVAL_MODELS", "smart").split(",") if m.strip()]


def eval_n() -> int:
    return int(os.environ.get("LQAI_EVAL_N", "1"))


def instruction_sha() -> str:
    """Pin of every instruction surface the run sees (oscar's
    variant-pinning): base system prompt + matter addendum template +
    the per-scenario prompt is stamped per cycle separately."""
    from app.agents.runner import SYSTEM_PROMPT
    from app.api.agent_runs import _MATTER_PROMPT

    return hashlib.sha256((SYSTEM_PROMPT + _MATTER_PROMPT).encode()).hexdigest()


@pytest.fixture(scope="session")
def out_dir() -> Path:
    path = Path(os.environ.get("LQAI_EVAL_OUT", "evals/out"))
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture(scope="session")
def engine():
    engine = create_async_engine(os.environ["DATABASE_URL"])
    yield engine
    # Session teardown is sync; the engine's pool dies with the process.


@pytest.fixture(scope="session")
def api_client():
    client = httpx.AsyncClient(
        base_url=os.environ.get("LQAI_EVAL_API_URL", "http://api:8000"), timeout=30.0
    )
    yield client
    # Closed with the process; cycles are sequential so no leak pressure.


@pytest.fixture(scope="session")
async def token(api_client: httpx.AsyncClient) -> str:
    return await eval_runner.login(
        api_client,
        email=os.environ.get("LQAI_EVAL_USER_EMAIL", "admin@lq.ai"),
        password=os.environ["LQAI_EVAL_USER_PASSWORD"],
    )


@pytest.fixture(scope="session")
async def matter_ids(engine) -> dict[str, str]:
    """matter name -> project id, resolved once for the seeded fixtures."""
    owner = os.environ.get("LQAI_EVAL_USER_EMAIL", "admin@lq.ai")
    ids: dict[str, str] = {}
    for scenario in load_scenarios():
        name = scenario.get("matter")
        if name and name not in ids:
            matter_id = await eval_runner.fetch_matter_id(engine, name=name, owner_email=owner)
            if matter_id is None:
                raise RuntimeError(
                    f"matter {name!r} not seeded — run `python -m evals.seed_fixtures` first"
                )
            ids[name] = matter_id
    return ids


@pytest.fixture(scope="session", autouse=True)
def manifest(out_dir: Path):
    """Provenance stamp for the whole session (read by report.py)."""
    data = {
        "started_at": datetime.now(UTC).isoformat(),
        "git_sha": os.environ.get("LQAI_EVAL_GIT_SHA", "unknown"),
        "instruction_sha": instruction_sha(),
        "models": eval_models(),
        "n": eval_n(),
        "scenarios": [s["id"] for s in load_scenarios()],
        "api_url": os.environ.get("LQAI_EVAL_API_URL", "http://api:8000"),
    }
    (out_dir / "manifest.json").write_text(json.dumps(data, indent=2))
    return data
