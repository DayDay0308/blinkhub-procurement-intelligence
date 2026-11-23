"""Where uploaded files live: a local folder (development, Docker volume) or Amazon S3.

Set DOCUMENT_BUCKET to use S3. Credentials come from the standard AWS chain, which on EC2
is the instance's IAM role, so no access keys are stored anywhere. Objects are written
with server-side encryption; the bucket itself blocks all public access (see infra/).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings


@lru_cache
def _s3():
    import boto3

    return boto3.client("s3")


def put(key: str, content: bytes, content_type: str) -> None:
    s = get_settings()
    if s.document_bucket:
        _s3().put_object(
            Bucket=s.document_bucket,
            Key=key,
            Body=content,
            ContentType=content_type,
            ServerSideEncryption="AES256",
        )
        return
    path = Path(s.document_dir) / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def get(key: str) -> bytes | None:
    s = get_settings()
    if s.document_bucket:
        try:
            return _s3().get_object(Bucket=s.document_bucket, Key=key)["Body"].read()
        except _s3().exceptions.NoSuchKey:
            return None
    path = Path(s.document_dir) / key
    return path.read_bytes() if path.is_file() else None
