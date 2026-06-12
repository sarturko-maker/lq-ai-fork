"""F0-S9 model-qualification harness (NOT part of the CI test suite).

Lives outside ``api/tests/`` on purpose: every cycle drives the LIVE
dev stack (POST /agents/runs against a real gateway-routed model) and
spends real provider tokens. CI's ``pytest -q`` collects only
``tests/`` (``testpaths`` in pyproject.toml); run this harness
explicitly — see ``api/evals/README.md``.

Design: docs/fork/research/f0-s9-eval-reuse.md §3 (clean-room
reimplementation of oscar-gc's matter-runtime eval LOGIC against our
``agent_run_steps`` substrate — AGPL code never ported, ADR-F004).
"""
