# syntax=docker/dockerfile:1.7

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir .

COPY app/ ./app/

# A3 (Inference Gateway scaffold) requires a ``gateway.yaml`` at startup.
# The image ships without one — the operator supplies it via a volume mount
# (see the commented ``volumes:`` block in ``docker-compose.yml``). The
# gateway reads ``GATEWAY_CONFIG_PATH`` to find this file; default
# ``/etc/gateway.yaml`` matches the documented mount target.
ENV GATEWAY_CONFIG_PATH=/etc/gateway.yaml

EXPOSE 8001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
