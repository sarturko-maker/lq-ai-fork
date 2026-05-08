"""S3 / MinIO async client for the api/ service.

Uses `aioboto3` so file uploads, downloads, and metadata operations stay on
the asyncio event loop. The full upload/download surface lands in Task C4;
A4 needs only:

- a session-builder that returns an `aioboto3.Session` configured from `Settings`,
- `ensure_bucket()` to create the configured bucket on startup if missing,
- `check_storage()` for the readiness probe.

We talk to MinIO with path-style addressing (`http://minio:9000/<bucket>/<key>`)
because virtual-hosted-style requires DNS magic that MinIO does not provide
inside the Compose network.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import aioboto3
from botocore.config import Config as BotocoreConfig

from app.config import get_settings

log = logging.getLogger(__name__)


def _build_session() -> aioboto3.Session:
    settings = get_settings()
    return aioboto3.Session(
        aws_access_key_id=settings.s3_access_key or None,
        aws_secret_access_key=settings.s3_secret_key or None,
        region_name=settings.s3_region,
    )


@asynccontextmanager
async def s3_client() -> AsyncIterator[Any]:
    """Yield an aioboto3 S3 client configured for our endpoint.

    Use as:
        async with s3_client() as s3:
            await s3.head_bucket(Bucket=...)
    """
    settings = get_settings()
    session = _build_session()
    async with session.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url or None,
        config=BotocoreConfig(s3={"addressing_style": "path"}),
    ) as client:
        yield client


async def ensure_bucket() -> None:
    """Create the configured bucket if it does not exist.

    Called from the FastAPI lifespan on startup. A 404 from HeadBucket means
    "create it"; anything else (403, network error) propagates.
    """
    settings = get_settings()
    bucket = settings.s3_bucket
    async with s3_client() as s3:
        try:
            await s3.head_bucket(Bucket=bucket)
            return
        except Exception as exc:
            # Botocore raises ClientError with response['Error']['Code'] == '404'
            # for bucket-not-found. Anything else, re-raise. We catch the bare
            # Exception because botocore's ClientError is the dominant case but
            # endpoint-misconfiguration also surfaces socket errors here.
            code = getattr(exc, "response", {}).get("Error", {}).get("Code", "")
            if code not in {"404", "NoSuchBucket"}:
                raise
        # Create the bucket. CreateBucketConfiguration is region-specific:
        # for us-east-1 it MUST be omitted; for any other region it MUST be
        # provided. We honour both.
        kwargs: dict[str, Any] = {"Bucket": bucket}
        if settings.s3_region and settings.s3_region != "us-east-1":
            kwargs["CreateBucketConfiguration"] = {
                "LocationConstraint": settings.s3_region,
            }
        await s3.create_bucket(**kwargs)
        log.info("Created S3 bucket: %s", bucket)


async def check_storage() -> bool:
    """Readiness check: returns True if the configured bucket is reachable."""
    settings = get_settings()
    try:
        async with s3_client() as s3:
            await s3.head_bucket(Bucket=settings.s3_bucket)
        return True
    except Exception as exc:
        # Readiness probes never raise; report failure in the response body.
        log.warning("Storage readiness check failed: %s", exc)
        return False
