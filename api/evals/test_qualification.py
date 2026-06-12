"""F0-S9 qualification cycles — pytest parametrize(scenario x model x N).

A cycle PASSES when it executed cleanly: the run reached a terminal
state, and a completed run carries a non-empty final answer (runner
hygiene). Metric outcomes are recorded DATA, not assertions — L1 bars
are set AFTER the first baseline, never a priori, and never tighter
than the CI (pre-made decision 1, docs/fork/HANDOFF.md). A failed or
cap-exceeded run is a valid observation and lands in the matrix with
its error string; a STRANDED run (poll timeout) fails the cycle.

Run (see README.md):

    pytest evals/test_qualification.py -q --no-header -p no:cacheprovider
"""

from __future__ import annotations

import dataclasses
import json
from datetime import UTC, datetime

import pytest

from evals import runner as eval_runner, scoring
from evals.conftest import eval_models, eval_n, load_scenarios

_SCENARIOS = load_scenarios()
_PARAMS = [
    pytest.param(scenario, model, cycle, id=f"{scenario['id']}-{model}-c{cycle:02d}")
    for scenario in _SCENARIOS
    for model in eval_models()
    for cycle in range(1, eval_n() + 1)
]


@pytest.mark.parametrize(("scenario", "model_alias", "cycle"), _PARAMS)
async def test_cycle(scenario, model_alias, cycle, api_client, token, engine, matter_ids, out_dir):
    record = eval_runner.new_record(scenario["id"], model_alias, cycle)
    started = datetime.now(UTC)
    record.started_at = started.isoformat()

    run = await eval_runner.create_run(
        api_client,
        token=token,
        prompt=scenario["prompt"],
        project_id=matter_ids.get(scenario.get("matter") or ""),
        model_alias=model_alias,
        max_steps=int(scenario.get("max_steps", 30)),
    )
    record.run_id = str(run["id"])
    record.thread_id = str(run["thread_id"])

    run = await eval_runner.poll_run(api_client, token=token, run_id=record.run_id)
    finished = datetime.now(UTC)
    record.finished_at = finished.isoformat()
    record.duration_s = round((finished - started).total_seconds(), 1)
    record.status = str(run.get("status"))
    record.final_answer = run.get("final_answer")
    record.error = run.get("error")

    record.valid, record.invalid_reason = eval_runner.validate_cycle(run)
    record.steps = await eval_runner.fetch_steps(engine, record.run_id)
    # Score COMPLETED runs only: a failed/cap_exceeded run is a valid
    # observation (reported with its error string) but scoring it would
    # hand free PASSes to every tool_not_fired noise gate (S9 review).
    if record.valid and record.status == "completed":
        record.metrics = scoring.score_all(scenario["metrics"], record.steps, record.final_answer)

    tokens_in, tokens_out, calls, routed = await eval_runner.fetch_routing_window(
        engine, started_at=started, finished_at=finished
    )
    record.tokens_in, record.tokens_out = tokens_in, tokens_out
    record.gateway_calls, record.routed_model = calls, routed
    record.cost_usd_estimate = eval_runner.cost_estimate_usd(tokens_in, tokens_out)

    out_path = out_dir / eval_runner.stable_cycle_filename(record)
    out_path.write_text(json.dumps(dataclasses.asdict(record), indent=2))

    # The ONLY hard assertion: hygiene. Silence is never success.
    assert record.valid, f"invalid cycle ({record.invalid_reason}); results at {out_path}"
