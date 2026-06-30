# F2 Tabular T1 — live grid evidence (ADR-F055)

Live, model-driven verification of the agentic "grids" tool on the dev stack
(`tests/agents/scenarios/test_tabular_grid_live.py`, provider-marked). DeepSeek
(`smart` → `deepseek-v4-flash`) was given a Commercial matter with three small NDAs
(distinct Term / Governing-law clauses) and asked to build a comparison grid.

**Result: PASS.** The run completed; the agent searched, read all three documents, then
called `start_tabular_review` → `record_tabular_row` ×3 → `finalize_tabular_review`,
persisting a `mode='agentic'` grid (`status=completed`, `fill_mode=fanout`) whose JSONB is
exactly `TabularResults`. Every cell is correct, `confidence=high`, with a verbatim
`source_quote` (the LQ-Grid-derived field). The agent also flagged that nda-gamma frames
its term as a confidentiality-survival period — unprompted judgment, not a grid mechanic.

Tool sequence: `search_documents`, `read_document`×3, `start_tabular_review`,
`record_tabular_row`×3, `finalize_tabular_review` (6 model turns, no fan-out needed at 3
docs — lead read-and-recorded, the ≤quota path).

Per ADR-F015 this is a recorded finding, not a model pass/fail gate; the rig assertions
only confirm a terminal run that turned the live model.

```json
{
  "status": "completed",
  "model_turns": 6,
  "tools_called": [
    "search_documents", "read_document", "read_document", "read_document",
    "start_tabular_review", "record_tabular_row", "record_tabular_row",
    "record_tabular_row", "finalize_tabular_review"
  ],
  "task_calls": 0,
  "delegated": false,
  "grid_status": "completed",
  "grid_fill_mode": "fanout",
  "grid_columns": ["Term", "Governing law"],
  "grid_rows": [
    {"document_name": "nda-alpha.txt", "cells": {
      "Term": {"value": "Two (2) years from the Effective Date", "confidence": "high",
               "source_quote": "This Agreement remains in force for two (2) years from the Effective Date."},
      "Governing law": {"value": "Laws of England and Wales", "confidence": "high",
               "source_quote": "This Agreement is governed by the laws of England and Wales."}}},
    {"document_name": "nda-beta.txt", "cells": {
      "Term": {"value": "Three (3) years", "confidence": "high",
               "source_quote": "This Agreement continues for a period of three (3) years."},
      "Governing law": {"value": "Laws of the State of New York", "confidence": "high",
               "source_quote": "This Agreement is governed by the laws of the State of New York."}}},
    {"document_name": "nda-gamma.txt", "cells": {
      "Term": {"value": "Five (5) years (confidentiality obligations survive for this period)", "confidence": "high",
               "source_quote": "The confidentiality obligations survive for five (5) years."},
      "Governing law": {"value": "Laws of Singapore", "confidence": "high",
               "source_quote": "This Agreement is governed by the laws of Singapore."}}}
  ]
}
```
