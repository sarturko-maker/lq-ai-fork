"""EU AI Act deterministic classification engine (AIC-2, ADR-F057).

The module's genuine IP: a pure, in-process engine that OWNS the risk-tier verdict
under Regulation (EU) 2024/1689 (as amended by the Digital Omnibus adopted
2026-06-30). The model supplies structured facts through a guarded, code-validated
tool; :func:`app.aiact.classify.classify` maps them deterministically to a sealed,
re-derivable verdict. There is no path by which the model asserts a tier
(server-side presence gate) — see :mod:`app.schemas.classification`.

Legal content lives in :mod:`app.aiact.ruleset` as VERSIONED DATA (a
``RULESET_VERSION`` stamp + a "pending counsel review — not legal advice"
disclaimer), so a legal update is a data + version bump, never an engine rewrite.
"""
