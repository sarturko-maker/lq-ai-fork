# InHouse AI Backend API

FastAPI service implementing the InHouse AI backend OpenAPI surface (`docs/api/backend-openapi.yaml`).

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
```

Health check: `curl http://localhost:8000/health`

## Tests

```bash
pytest                    # unit + integration
pytest -m "not provider"  # skip provider-integration tests
ruff check .
ruff format --check .
mypy .
```

## Status

M1 build in progress. See [`docs/M1-IMPLEMENTATION-ORDER.md`](../docs/M1-IMPLEMENTATION-ORDER.md) for task breakdown.
