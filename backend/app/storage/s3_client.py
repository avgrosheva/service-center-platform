"""
S3-compatible object storage client wrapper (Milestone 10).

The backend's only direct interaction with the bucket is generating
short-lived presigned PUT URLs, per the Technical Blueprint's Section 7
upload flow: the frontend requests a presigned URL, uploads the binary
straight to the bucket, then confirms with a metadata-only call — the
FastAPI process never proxies the file itself.

Mirrors `database.py`'s pattern: settings are read once and the client is
built eagerly at import time. Building a boto3 client is local object
construction (no network call), so this stays safe to import even if
S3_* isn't configured yet or the bucket hasn't been provisioned —
provisioning the bucket itself is a deployment/local-dev step (see
docker-compose.yml's `minio` service), not something app code does at
startup, the same way `alembic upgrade head` — not app startup — is what
creates database tables.

Configured against whichever S3-compatible endpoint Settings points at:
MinIO for local dev, a real provider (AWS S3, Yandex Object Storage)
unmodified in production — boto3 abstracts the endpoint/addressing-style
differences via `endpoint_url` + `s3={"addressing_style": "path"}`.
"""

import boto3
from botocore.client import Config as BotoConfig

from app.config import get_settings

settings = get_settings()

# Long enough for a technician on a slow mobile connection to complete an
# upload, short enough that a leaked URL doesn't stay valid indefinitely.
PRESIGNED_URL_EXPIRY_SECONDS = 900

_client = boto3.client(
    "s3",
    endpoint_url=settings.s3_endpoint_url,
    aws_access_key_id=settings.s3_access_key,
    aws_secret_access_key=settings.s3_secret_key,
    config=BotoConfig(signature_version="s3v4", s3={"addressing_style": "path"}),
    region_name="us-east-1",
)

# A second client, identical except for its endpoint, used only for
# presigned URLs: those are handed to the browser, which — unlike this
# process — cannot resolve the Docker Compose service name `minio` and
# must be given whatever host it can actually reach (see
# `s3_public_endpoint_url`'s docstring in app/config.py).
_public_client = boto3.client(
    "s3",
    endpoint_url=settings.s3_public_endpoint_url or settings.s3_endpoint_url,
    aws_access_key_id=settings.s3_access_key,
    aws_secret_access_key=settings.s3_secret_key,
    config=BotoConfig(signature_version="s3v4", s3={"addressing_style": "path"}),
    region_name="us-east-1",
)


def generate_presigned_upload_url(key: str, content_type: str) -> str:
    """
    Returns a presigned URL the client can PUT the file's bytes to
    directly, valid for PRESIGNED_URL_EXPIRY_SECONDS. `content_type` must
    match the header the client actually sends on the PUT — S3 rejects the
    upload otherwise, since it's part of what's signed.
    """
    return _public_client.generate_presigned_url(
        "put_object",
        Params={"Bucket": settings.s3_bucket_name, "Key": key, "ContentType": content_type},
        ExpiresIn=PRESIGNED_URL_EXPIRY_SECONDS,
    )


def generate_presigned_download_url(key: str) -> str:
    """
    Returns a presigned URL the frontend can GET directly to view/download
    the object, valid for PRESIGNED_URL_EXPIRY_SECONDS — same short-lived,
    no-bucket-policy-change approach as the upload URL. Added for the
    frontend's Milestone F10: `PhotoRead` embeds this per photo so a
    thumbnail grid has something to point an `<img>` at without the bucket
    itself ever needing to be public.
    """
    return _public_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket_name, "Key": key},
        ExpiresIn=PRESIGNED_URL_EXPIRY_SECONDS,
    )


def upload_bytes(key: str, data: bytes, content_type: str) -> None:
    """
    Uploads bytes directly to the bucket via a normal (non-presigned)
    put_object call (Milestone 14). Unlike photos, there's no frontend
    client to hand a presigned URL to here — the backend generates the
    content itself (a PDF) and uploads it directly from within the
    document-generation background task.
    """
    _client.put_object(Bucket=settings.s3_bucket_name, Key=key, Body=data, ContentType=content_type)


def download_bytes(key: str) -> bytes:
    """Fetches an object's bytes directly. Currently used only by the test suite to verify generated document content."""
    return _client.get_object(Bucket=settings.s3_bucket_name, Key=key)["Body"].read()
