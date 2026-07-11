"""Tests for the destructive-delete guards (audit -166).

Uses unittest.mock rather than a full AWS simulator: the point is to verify the
ownership/confirm/allow-list/dry-run logic and that the right boto3 calls happen.
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError
from fastapi import HTTPException

from api import ResourceRequest, delete_resources
from core import (
    bucket_is_statecraft_managed,
    create_s3_bucket,
    delete_target_is_allowed,
    managed_tagset,
)

REGION = "eu-west-1"
BUCKET = "123456789012-terraform-prod"


# --- pure helpers ---------------------------------------------------------


def test_delete_target_allowed_by_marker():
    assert delete_target_is_allowed(BUCKET, ["-terraform-"]) is True
    assert delete_target_is_allowed("some-random-bucket", ["-terraform-"]) is False


def test_managed_tagset_includes_owner_and_env():
    tags = {t["Key"]: t["Value"] for t in managed_tagset("prod", "alice")}
    assert tags["ManagedBy"] == "statecraft"
    assert tags["OpenPrimeEnv"] == "prod"
    assert tags["Owner"] == "alice"


def test_managed_tagset_minimal_is_managedby_only():
    assert {t["Key"]: t["Value"] for t in managed_tagset()} == {
        "ManagedBy": "statecraft"
    }


# --- ownership check ------------------------------------------------------


def _s3_with_tags(tagset):
    s3 = MagicMock()
    s3.get_bucket_tagging.return_value = {"TagSet": tagset}
    return s3


def test_managed_true_when_tag_present():
    s3 = _s3_with_tags([{"Key": "ManagedBy", "Value": "statecraft"}])
    assert bucket_is_statecraft_managed(s3, BUCKET) is True


def test_managed_false_when_tag_absent():
    s3 = _s3_with_tags([{"Key": "Owner", "Value": "someone-else"}])
    assert bucket_is_statecraft_managed(s3, BUCKET) is False


def test_managed_false_when_no_tagset():
    s3 = MagicMock()
    s3.get_bucket_tagging.side_effect = ClientError(
        {"Error": {"Code": "NoSuchTagSet"}}, "GetBucketTagging"
    )
    assert bucket_is_statecraft_managed(s3, BUCKET) is False


# --- create tags the bucket ----------------------------------------------


def test_create_applies_ownership_tags():
    s3 = MagicMock()
    assert create_s3_bucket(s3, BUCKET, REGION, tags=managed_tagset("prod", "alice"))
    s3.put_bucket_tagging.assert_called_once()
    sent = {
        t["Key"]: t["Value"]
        for t in s3.put_bucket_tagging.call_args.kwargs["Tagging"]["TagSet"]
    }
    assert sent["ManagedBy"] == "statecraft"
    assert sent["Owner"] == "alice"


def test_create_us_east_1_omits_location_constraint():
    # Regression: passing CreateBucketConfiguration={} for us-east-1 serializes
    # to an empty XML element real S3 rejects with MalformedXML. The kwarg must
    # be absent entirely for us-east-1.
    s3 = MagicMock()
    assert create_s3_bucket(s3, BUCKET, "us-east-1")
    s3.create_bucket.assert_called_once()
    kwargs = s3.create_bucket.call_args.kwargs
    assert kwargs["Bucket"] == BUCKET
    assert "CreateBucketConfiguration" not in kwargs


def test_create_other_region_sets_location_constraint():
    s3 = MagicMock()
    assert create_s3_bucket(s3, BUCKET, "eu-west-1")
    kwargs = s3.create_bucket.call_args.kwargs
    assert kwargs["CreateBucketConfiguration"] == {"LocationConstraint": "eu-west-1"}


# --- delete endpoint guards ----------------------------------------------


def _req(**kw):
    base = dict(region=REGION, bucket_name=BUCKET, locking_mechanism="s3")
    base.update(kw)
    return ResourceRequest(**base)


def _clients(s3):
    return {
        "s3_client": s3,
        "s3_resource": MagicMock(),
        "dynamodb_client": MagicMock(),
    }


def test_delete_rejects_confirm_mismatch():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(delete_resources(_req(confirm="wrong")))
    assert exc.value.status_code == 400


def test_delete_rejects_disallowed_name():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            delete_resources(
                _req(bucket_name="random-bucket", confirm="random-bucket")
            )
        )
    assert exc.value.status_code == 400


@patch("api.get_aws_clients")
def test_delete_refuses_unmanaged_bucket(mock_clients):
    mock_clients.return_value = _clients(_s3_with_tags([]))  # no ManagedBy tag
    with pytest.raises(HTTPException) as exc:
        asyncio.run(delete_resources(_req(confirm=BUCKET)))
    assert exc.value.status_code == 403


@patch("api.delete_s3_bucket")
@patch("api.get_aws_clients")
def test_delete_dry_run_does_not_delete(mock_clients, mock_delete):
    mock_clients.return_value = _clients(
        _s3_with_tags([{"Key": "ManagedBy", "Value": "statecraft"}])
    )
    resp = asyncio.run(delete_resources(_req(confirm=BUCKET, dry_run=True)))
    assert resp.details["dry_run"] is True
    mock_delete.assert_not_called()


@patch("api.delete_s3_bucket", return_value=True)
@patch("api.get_aws_clients")
def test_delete_proceeds_when_managed_and_confirmed(mock_clients, mock_delete):
    mock_clients.return_value = _clients(
        _s3_with_tags([{"Key": "ManagedBy", "Value": "statecraft"}])
    )
    resp = asyncio.run(delete_resources(_req(confirm=BUCKET)))
    assert resp.success is True
    mock_delete.assert_called_once()
