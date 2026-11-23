"""Document storage: local folder by default, S3 when DOCUMENT_BUCKET is set."""

import boto3
import pytest
from moto import mock_aws

from app.core.config import get_settings
from app.services import storage


def test_local_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "document_dir", str(tmp_path))
    monkeypatch.setattr(get_settings(), "document_bucket", "")
    storage.put("s1/a.pdf", b"%PDF-1", "application/pdf")
    assert (tmp_path / "s1" / "a.pdf").read_bytes() == b"%PDF-1"
    assert storage.get("s1/a.pdf") == b"%PDF-1" and storage.get("s1/missing.pdf") is None


@pytest.fixture
def s3(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "af-south-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    with mock_aws():
        storage._s3.cache_clear()
        client = boto3.client("s3", region_name="af-south-1")
        client.create_bucket(
            Bucket="blinkhub-docs", CreateBucketConfiguration={"LocationConstraint": "af-south-1"}
        )
        monkeypatch.setattr(get_settings(), "document_bucket", "blinkhub-docs")
        yield client
    storage._s3.cache_clear()


def test_s3_bucket_encrypted(s3):
    storage.put("s1/a.pdf", b"%PDF-1", "application/pdf")
    head = s3.head_object(Bucket="blinkhub-docs", Key="s1/a.pdf")
    assert head["ServerSideEncryption"] == "AES256" and head["ContentType"] == "application/pdf"
    assert storage.get("s1/a.pdf") == b"%PDF-1"
    assert storage.get("s1/missing.pdf") is None


def test_production_refuses_development_secrets():
    from pydantic import ValidationError

    from app.core.config import Settings

    with pytest.raises(ValidationError, match="JWT_SECRET, DATA_ENCRYPTION_KEY, ASK_DB_PASSWORD"):
        Settings(environment="production")
    ok = Settings(
        environment="production", jwt_secret="x" * 40, data_encryption_key="k" * 40, ask_db_password="p" * 30
    )
    assert ok.environment == "production"
