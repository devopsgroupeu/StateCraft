"""Ownership and state safety (audit findings C19, C20, C22, C23, C74, C75).

Against moto wherever AWS behaviour matters: the us-east-1 CreateBucket quirk,
DynamoDB deletion protection and S3 batch deletes are all things a mock would
only repeat back. The API tests send the request the backend sends, customer
keys included.
"""

from unittest.mock import MagicMock

import boto3
import pytest
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient
from moto import mock_aws
from pydantic import SecretStr

from statecraft import api
from statecraft.api import ResourceRequest, app
from statecraft.core import (
    BucketCreationError,
    create_dynamodb_table,
    create_s3_bucket,
    delete_s3_bucket,
    managed_tagset,
)

REGION = "eu-west-1"
BUCKET = "123456789012-terraform-prod"
TABLE = "123456789012-terraform-prod-lock"
SECRET = "customer-secret-do-not-echo"
KEYS = {"aws_access_key_id": "AKIACUSTOMEREXAMPLE", "aws_secret_access_key": SECRET}

client = TestClient(app)


@pytest.fixture
def aws():
    with mock_aws():
        yield {
            "s3": boto3.client("s3", region_name=REGION),
            "s3_resource": boto3.resource("s3", region_name=REGION),
            "dynamodb": boto3.client("dynamodb", region_name=REGION),
        }


def make_bucket(s3, name=BUCKET, region=REGION, tags=None):
    kwargs = {"Bucket": name}
    if region != "us-east-1":
        kwargs["CreateBucketConfiguration"] = {"LocationConstraint": region}
    s3.create_bucket(**kwargs)
    if tags:
        s3.put_bucket_tagging(
            Bucket=name, Tagging={"TagSet": [{"Key": k, "Value": v} for k, v in tags.items()]}
        )


def bucket_tags(s3, name=BUCKET):
    return {t["Key"]: t["Value"] for t in s3.get_bucket_tagging(Bucket=name)["TagSet"]}


def bucket_exists(s3, name=BUCKET):
    return name in [b["Name"] for b in s3.list_buckets()["Buckets"]]


def make_table(dynamodb, name=TABLE, tags=None, protected=False):
    kwargs = {}
    if tags:
        kwargs["Tags"] = [{"Key": k, "Value": v} for k, v in tags.items()]
    dynamodb.create_table(
        TableName=name,
        AttributeDefinitions=[{"AttributeName": "LockID", "AttributeType": "S"}],
        KeySchema=[{"AttributeName": "LockID", "KeyType": "HASH"}],
        BillingMode="PAY_PER_REQUEST",
        DeletionProtectionEnabled=protected,
        **kwargs,
    )


def table_exists(dynamodb, name=TABLE):
    return name in dynamodb.list_tables()["TableNames"]


def delete_request(**overrides):
    body = {"region": REGION, "bucket_name": BUCKET, "confirm": BUCKET, **KEYS}
    body.update(overrides)
    return client.post("/resources/delete", json=body)


OURS = {"ManagedBy": "statecraft", "OpenPrimeEnv": "prod"}


# --- C19: an existing bucket is never taken over ------------------------------


class TestExistingBucketOnCreate:
    @pytest.mark.parametrize("region", ["eu-west-1", "us-east-1"])
    def test_refuses_a_bucket_statecraft_did_not_create(self, aws, region):
        """us-east-1 matters: there CreateBucket on a bucket the account already
        owns succeeds silently instead of answering BucketAlreadyOwnedByYou."""
        s3 = boto3.client("s3", region_name=region)
        make_bucket(s3, region=region, tags={"CostCenter": "42"})

        with pytest.raises(BucketCreationError) as exc:
            create_s3_bucket(s3, BUCKET, region, tags=managed_tagset("prod", "alice"))

        assert exc.value.status_code == 409
        assert bucket_tags(s3) == {"CostCenter": "42"}
        assert s3.get_bucket_versioning(Bucket=BUCKET).get("Status") is None

    def test_refuses_an_untagged_bucket(self, aws):
        make_bucket(aws["s3"])

        with pytest.raises(BucketCreationError) as exc:
            create_s3_bucket(aws["s3"], BUCKET, REGION, tags=managed_tagset("prod"))

        assert exc.value.status_code == 409

    def test_refuses_a_statecraft_bucket_of_another_environment(self, aws):
        make_bucket(aws["s3"], tags={"ManagedBy": "statecraft", "OpenPrimeEnv": "staging"})

        with pytest.raises(BucketCreationError) as exc:
            create_s3_bucket(aws["s3"], BUCKET, REGION, tags=managed_tagset("prod"))

        assert exc.value.status_code == 409
        assert bucket_tags(aws["s3"])["OpenPrimeEnv"] == "staging"

    def test_reconciles_its_own_bucket_and_keeps_foreign_tags(self, aws):
        make_bucket(aws["s3"], tags={**OURS, "CostCenter": "42"})

        assert create_s3_bucket(aws["s3"], BUCKET, REGION, tags=managed_tagset("prod", "alice"))

        assert bucket_tags(aws["s3"]) == {**OURS, "CostCenter": "42", "Owner": "alice"}
        assert aws["s3"].get_bucket_versioning(Bucket=BUCKET).get("Status") == "Enabled"

    def test_another_accounts_bucket_is_still_reported_as_taken(self):
        """GetBucketTagging on another account's bucket answers AccessDenied, so
        the look-before-create defers to CreateBucket, which says why."""
        s3 = MagicMock()
        s3.get_bucket_tagging.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied"}}, "GetBucketTagging"
        )
        s3.create_bucket.side_effect = ClientError(
            {"Error": {"Code": "BucketAlreadyExists"}}, "CreateBucket"
        )

        with pytest.raises(BucketCreationError) as exc:
            create_s3_bucket(s3, BUCKET, REGION, tags=managed_tagset("prod"))

        assert exc.value.status_code == 409
        assert "another AWS account" in str(exc.value)
        s3.put_bucket_tagging.assert_not_called()

    def test_api_answers_409_for_a_bucket_it_did_not_create(self, aws):
        make_bucket(aws["s3"], tags={"CostCenter": "42"})

        response = client.post(
            "/resources/create",
            json={"region": REGION, "bucket_name": BUCKET, "locking_mechanism": "s3",
                  "environment": "prod", **KEYS},
        )

        assert response.status_code == 409
        assert bucket_tags(aws["s3"]) == {"CostCenter": "42"}


# --- C20 / C75: lock tables ---------------------------------------------------


class TestLockTableCreate:
    def test_new_tables_are_tagged_and_deletion_protected(self, aws):
        assert create_dynamodb_table(aws["dynamodb"], TABLE, tags=managed_tagset("prod"))

        table = aws["dynamodb"].describe_table(TableName=TABLE)["Table"]
        tags = aws["dynamodb"].list_tags_of_resource(ResourceArn=table["TableArn"])["Tags"]
        assert table["DeletionProtectionEnabled"] is True
        assert {t["Key"]: t["Value"] for t in tags} == OURS

    def test_an_existing_table_it_did_not_create_is_a_failure(self, aws):
        make_table(aws["dynamodb"])

        assert create_dynamodb_table(aws["dynamodb"], TABLE, tags=managed_tagset("prod")) is False

    def test_its_own_active_table_is_success(self, aws):
        make_table(aws["dynamodb"], tags=OURS)

        assert create_dynamodb_table(aws["dynamodb"], TABLE, tags=managed_tagset("prod")) is True


# --- C20 / C74 / C75: delete --------------------------------------------------


class TestDelete:
    def test_refuses_a_lock_table_it_did_not_create_before_deleting_anything(self, aws):
        make_bucket(aws["s3"], tags=OURS)
        make_table(aws["dynamodb"])

        response = delete_request(locking_mechanism="dynamodb", table_name=TABLE)

        assert response.status_code == 403
        assert bucket_exists(aws["s3"])
        assert table_exists(aws["dynamodb"])

    def test_refuses_a_deletion_protected_table_before_deleting_anything(self, aws):
        make_bucket(aws["s3"], tags=OURS)
        make_table(aws["dynamodb"], tags=OURS, protected=True)

        response = delete_request(locking_mechanism="dynamodb", table_name=TABLE)

        assert response.status_code == 409
        assert bucket_exists(aws["s3"])
        assert table_exists(aws["dynamodb"])

    def test_the_bucket_goes_first_so_a_failed_bucket_delete_keeps_the_lock_table(
        self, aws, monkeypatch
    ):
        make_bucket(aws["s3"], tags=OURS)
        make_table(aws["dynamodb"], tags=OURS)
        monkeypatch.setattr(api, "delete_s3_bucket", lambda *_: False)

        response = delete_request(locking_mechanism="dynamodb", table_name=TABLE)

        assert response.status_code == 500
        assert table_exists(aws["dynamodb"])

    def test_deletes_its_bucket_and_lock_table(self, aws):
        make_bucket(aws["s3"], tags=OURS)
        aws["s3"].put_object(Bucket=BUCKET, Key="terraform.tfstate", Body=b"state")
        make_table(aws["dynamodb"], tags=OURS)

        response = delete_request(locking_mechanism="dynamodb", table_name=TABLE)

        assert response.status_code == 200
        assert not bucket_exists(aws["s3"])
        assert not table_exists(aws["dynamodb"])

    def test_deleting_a_bucket_that_is_already_gone_succeeds(self, aws):
        response = delete_request(locking_mechanism="s3")

        assert response.status_code == 200

    def test_emptying_a_bucket_deletes_versions_in_batches(self, aws):
        make_bucket(aws["s3"], tags=OURS)
        aws["s3"].put_bucket_versioning(
            Bucket=BUCKET, VersioningConfiguration={"Status": "Enabled"}
        )
        for body in (b"v1", b"v2", b"v3", b"v4", b"v5"):
            aws["s3"].put_object(Bucket=BUCKET, Key="terraform.tfstate", Body=body)
        calls = []
        aws["s3_resource"].meta.client.meta.events.register(
            "before-call.s3.*", lambda model, **_: calls.append(model.name)
        )

        assert delete_s3_bucket(aws["s3"], aws["s3_resource"], BUCKET) is True

        assert "DeleteObject" not in calls
        assert calls.count("DeleteObjects") == 1
        assert not bucket_exists(aws["s3"])


def test_a_version_the_batch_could_not_delete_fails_the_delete():
    """DeleteObjects reports per-key failures in its response instead of raising."""
    s3_resource = MagicMock()
    bucket = s3_resource.Bucket.return_value
    bucket.object_versions.delete.return_value = [
        {"Deleted": [{"Key": "a"}], "Errors": [{"Key": "terraform.tfstate", "Code": "AccessDenied"}]}
    ]

    assert delete_s3_bucket(MagicMock(), s3_resource, BUCKET) is False
    bucket.delete.assert_not_called()


# --- C75: region --------------------------------------------------------------


@pytest.mark.parametrize("path", ["/resources/create", "/resources/delete"])
def test_an_unknown_region_is_rejected_before_touching_aws(monkeypatch, path):
    get_clients = MagicMock()
    monkeypatch.setattr(api, "get_aws_clients", get_clients)

    response = client.post(
        path,
        json={"region": "mars-north-1", "bucket_name": BUCKET, "locking_mechanism": "s3",
              "confirm": BUCKET, **KEYS},
    )

    assert response.status_code == 400
    assert "mars-north-1" in response.json()["detail"]
    get_clients.assert_not_called()


# --- C22: secrets ------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        {"bucket_name": BUCKET, **KEYS},  # region missing: FastAPI echoed the whole body
        {"region": REGION, "bucket_name": BUCKET, "locking_mechanism": "bogus", **KEYS},
        {"region": REGION, "bucket_name": BUCKET, "aws_access_key_id": "AKIA",
         "aws_secret_access_key": {"nested": SECRET}},
    ],
    ids=["missing-field", "invalid-enum", "secret-wrong-type"],
)
def test_validation_errors_never_echo_the_request(body):
    response = client.post("/resources/create", json=body)

    assert response.status_code == 422
    assert SECRET not in response.text
    assert all("input" not in error for error in response.json()["detail"])


def test_credentials_are_secret_types_that_never_print():
    request = ResourceRequest(region=REGION, bucket_name=BUCKET, **KEYS)

    assert isinstance(request.aws_secret_access_key, SecretStr)
    assert isinstance(request.aws_access_key_id, SecretStr)
    assert SECRET not in str(request)
    assert SECRET not in repr(request)


# --- C23: locking default ----------------------------------------------------


def test_s3_native_locking_is_the_default(aws):
    response = client.post(
        "/resources/create", json={"region": REGION, "bucket_name": BUCKET, **KEYS}
    )

    assert response.status_code == 200
    assert response.json()["details"]["locking_mechanism"] == "s3"
    assert aws["dynamodb"].list_tables()["TableNames"] == []
