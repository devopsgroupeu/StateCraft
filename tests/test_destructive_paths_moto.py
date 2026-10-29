"""The destructive paths, against a real S3/DynamoDB implementation.

test_resource_delete.py covers the guards in front of deletion (allow-list,
managed tag, confirmation, dry run) with mocks. It stops short of the functions
that actually destroy things, so `delete_s3_bucket` and `delete_dynamodb_table`
had no coverage at all - and the interesting half of `delete_s3_bucket` is
precisely the half a mock cannot demonstrate.

A versioned bucket cannot be deleted while any object version or delete marker
remains: S3 answers BucketNotEmpty. Asserting `.delete()` was called N times
proves nothing about that. moto implements the rule, so these tests fail if the
version sweep is ever dropped or narrowed to current objects.
"""

import boto3
import pytest
from moto import mock_aws

from statecraft.core import (
    create_dynamodb_table,
    create_s3_bucket,
    delete_dynamodb_table,
    delete_s3_bucket,
)

REGION = "eu-west-1"
BUCKET = "openprime-tfstate-test"
TABLE = "openprime-tflock-test"


@pytest.fixture
def aws():
    with mock_aws():
        yield {
            "s3": boto3.client("s3", region_name=REGION),
            "s3_resource": boto3.resource("s3", region_name=REGION),
            "dynamodb": boto3.client("dynamodb", region_name=REGION),
        }


def bucket_exists(s3, name):
    return name in [b["Name"] for b in s3.list_buckets()["Buckets"]]


class TestVersionAwareDelete:
    def test_deletes_a_bucket_holding_many_object_versions(self, aws):
        s3 = aws["s3"]
        create_s3_bucket(s3, BUCKET, REGION)

        # Three versions of one key, on a bucket create_s3_bucket has versioned.
        for body in (b"v1", b"v2", b"v3"):
            s3.put_object(Bucket=BUCKET, Key="terraform.tfstate", Body=body)
        versions = s3.list_object_versions(Bucket=BUCKET).get("Versions", [])
        assert len(versions) == 3, "precondition: the bucket must really be versioned"

        assert delete_s3_bucket(s3, aws["s3_resource"], BUCKET) is True
        assert not bucket_exists(s3, BUCKET)

    def test_deletes_a_bucket_whose_objects_are_hidden_behind_delete_markers(self, aws):
        """A deleted object in a versioned bucket leaves a delete marker, which
        still blocks bucket deletion even though the bucket looks empty."""
        s3 = aws["s3"]
        create_s3_bucket(s3, BUCKET, REGION)
        s3.put_object(Bucket=BUCKET, Key="terraform.tfstate", Body=b"state")
        s3.delete_object(Bucket=BUCKET, Key="terraform.tfstate")

        listing = s3.list_object_versions(Bucket=BUCKET)
        assert listing.get("DeleteMarkers"), "precondition: a delete marker must exist"
        assert not s3.list_objects_v2(Bucket=BUCKET).get("Contents"), "bucket looks empty"

        assert delete_s3_bucket(s3, aws["s3_resource"], BUCKET) is True
        assert not bucket_exists(s3, BUCKET)

    def test_deleting_an_empty_bucket_succeeds(self, aws):
        s3 = aws["s3"]
        create_s3_bucket(s3, BUCKET, REGION)

        assert delete_s3_bucket(s3, aws["s3_resource"], BUCKET) is True
        assert not bucket_exists(s3, BUCKET)

    def test_deleting_a_bucket_that_is_already_gone_is_not_an_error(self, aws):
        """Delete is retried after a partial failure; a missing bucket is the
        goal state, not a failure."""
        assert delete_s3_bucket(aws["s3"], aws["s3_resource"], "never-existed-openprime") is True


class TestCreateIdempotency:
    def test_creating_the_same_bucket_twice_succeeds_and_keeps_it_configured(self, aws):
        s3 = aws["s3"]

        assert create_s3_bucket(s3, BUCKET, REGION) is True
        assert create_s3_bucket(s3, BUCKET, REGION) is True

        assert s3.get_bucket_versioning(Bucket=BUCKET).get("Status") == "Enabled"
        assert s3.get_public_access_block(Bucket=BUCKET)["PublicAccessBlockConfiguration"][
            "BlockPublicAcls"
        ]
        assert s3.get_bucket_encryption(Bucket=BUCKET)["ServerSideEncryptionConfiguration"]["Rules"]

    def test_a_retry_does_not_destroy_state_already_in_the_bucket(self, aws):
        """The dangerous version of "idempotent" would recreate the bucket."""
        s3 = aws["s3"]
        create_s3_bucket(s3, BUCKET, REGION)
        s3.put_object(Bucket=BUCKET, Key="terraform.tfstate", Body=b"real state")

        create_s3_bucket(s3, BUCKET, REGION)

        assert s3.get_object(Bucket=BUCKET, Key="terraform.tfstate")["Body"].read() == b"real state"

    def test_creating_the_same_lock_table_twice_succeeds(self, aws):
        assert create_dynamodb_table(aws["dynamodb"], TABLE) is True
        assert create_dynamodb_table(aws["dynamodb"], TABLE) is True


class TestDynamoDbDelete:
    def test_deletes_the_lock_table_once_deliberately_unlocked(self, aws):
        dynamodb = aws["dynamodb"]
        create_dynamodb_table(dynamodb, TABLE)
        dynamodb.update_table(TableName=TABLE, DeletionProtectionEnabled=False)

        assert delete_dynamodb_table(dynamodb, TABLE) is True
        assert TABLE not in dynamodb.list_tables()["TableNames"]

    def test_a_protected_lock_table_is_not_deleted(self, aws):
        dynamodb = aws["dynamodb"]
        create_dynamodb_table(dynamodb, TABLE)

        assert delete_dynamodb_table(dynamodb, TABLE) is False
        assert TABLE in dynamodb.list_tables()["TableNames"]

    def test_deleting_a_table_that_is_already_gone_is_not_an_error(self, aws):
        assert delete_dynamodb_table(aws["dynamodb"], "never-existed-openprime") is True
