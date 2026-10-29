"""StateCraft acts only with the customer's AWS credentials (audit finding C21).

A request without them must never reach boto3's default credential chain: in a
pod that chain resolves to the platform's own identity (env keys, IRSA, node
role), so a keyless request would create or delete buckets in the platform
account instead of the customer's.
"""

from unittest.mock import MagicMock

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from statecraft import core
from statecraft.api import app

REGION = "eu-west-1"
BUCKET = "123456789012-terraform-prod"
CUSTOMER_KEYS = {
    "aws_access_key_id": "AKIACUSTOMEREXAMPLE",
    "aws_secret_access_key": "customer-secret",
}

client = TestClient(app)


@pytest.fixture
def platform_account(monkeypatch):
    """The platform's own identity, resolvable through the default chain the
    way the pod's AWS_* env vars used to provide it."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIAPLATFORMEXAMPLE")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "platform-secret")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)
    with mock_aws():
        yield boto3.client("s3", region_name=REGION)


@pytest.fixture
def session_spy(monkeypatch):
    spy = MagicMock(wraps=boto3.Session)
    monkeypatch.setattr(core.boto3, "Session", spy)
    return spy


def bucket_names(s3):
    return [b["Name"] for b in s3.list_buckets()["Buckets"]]


@pytest.mark.parametrize(
    "keys",
    [
        {},
        {"aws_access_key_id": "AKIACUSTOMEREXAMPLE"},
        {"aws_secret_access_key": "customer-secret"},
        {"aws_access_key_id": "", "aws_secret_access_key": ""},
    ],
    ids=["no-keys", "access-key-only", "secret-only", "empty-keys"],
)
def test_create_without_customer_keys_is_rejected_before_any_session(
    platform_account, session_spy, keys
):
    response = client.post(
        "/resources/create",
        json={"region": REGION, "bucket_name": BUCKET, "locking_mechanism": "s3", **keys},
    )

    assert response.status_code == 400
    assert "aws_access_key_id" in response.json()["detail"]
    session_spy.assert_not_called()
    assert bucket_names(platform_account) == []


def test_delete_without_customer_keys_is_rejected_before_any_session(platform_account, session_spy):
    platform_account.create_bucket(
        Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": REGION}
    )
    platform_account.put_bucket_tagging(
        Bucket=BUCKET, Tagging={"TagSet": [{"Key": "ManagedBy", "Value": "statecraft"}]}
    )

    response = client.post(
        "/resources/delete",
        json={"region": REGION, "bucket_name": BUCKET, "locking_mechanism": "s3", "confirm": BUCKET},
    )

    assert response.status_code == 400
    session_spy.assert_not_called()
    assert bucket_names(platform_account) == [BUCKET]


def test_create_with_customer_keys_uses_exactly_those_keys(platform_account, session_spy):
    response = client.post(
        "/resources/create",
        json={"region": REGION, "bucket_name": BUCKET, "locking_mechanism": "s3", **CUSTOMER_KEYS},
    )

    assert response.status_code == 200
    session_spy.assert_called_once_with(region_name=REGION, **CUSTOMER_KEYS)
