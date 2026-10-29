"""Core business logic for StateCraft - shared by CLI and API."""

import functools
import logging
import os
import sys

import boto3
from botocore.exceptions import ClientError

# Structured JSON logging is configured on the root logger by the logs module.
from .logs import logger  # noqa: E402

# --- Ownership / destructive-delete guards -----------------------------------
# StateCraft tags every bucket it creates so delete can refuse anything it did
# not create. Delete additionally requires the name to match an allowed marker
# and an explicit confirm token (see api.delete_resources).
MANAGED_BY_KEY = "ManagedBy"
MANAGED_BY_VALUE = "statecraft"
ENVIRONMENT_KEY = "OpenPrimeEnv"


class BucketCreationError(Exception):
    """State-bucket creation failed. `message` is safe to surface to the user."""

    def __init__(self, message, status_code=500):
        super().__init__(message)
        self.status_code = status_code


# Map known AWS error codes to a user-actionable message + HTTP status. Anything
# not listed falls through to a generic 500 that still names the AWS error code.
_BUCKET_ERROR_MESSAGES = {
    "BucketAlreadyExists": (
        "Bucket name '{name}' is already taken by another AWS account. S3 bucket "
        "names are globally unique — use a different environment name or global prefix.",
        409,
    ),
    "BucketAlreadyOwnedByYou": (
        "Bucket '{name}' already exists in this AWS account and StateCraft did not "
        "create it for this environment. Use it as an existing backend, or choose a "
        "different environment name.",
        409,
    ),
    "InvalidBucketName": (
        "Invalid bucket name '{name}'. It must follow AWS S3 naming rules "
        "(lowercase letters, numbers and hyphens; 3-63 characters).",
        400,
    ),
    "AccessDenied": (
        "Access denied creating the state bucket. The AWS credentials are missing "
        "the required S3 permissions (s3:CreateBucket and related).",
        403,
    ),
    "AllAccessDisabled": (
        "Access denied creating the state bucket. The AWS credentials are missing "
        "the required S3 permissions (s3:CreateBucket and related).",
        403,
    ),
}


def _bucket_error(error_code, bucket_name):
    template, status = _BUCKET_ERROR_MESSAGES.get(
        error_code,
        ("Could not create the state bucket ({code}).", 500),
    )
    return BucketCreationError(
        template.format(name=bucket_name, code=error_code or "unknown error"),
        status_code=status,
    )


def managed_tagset(environment=None, owner=None):
    """Ownership tags applied to every StateCraft-created bucket."""
    tags = [{"Key": MANAGED_BY_KEY, "Value": MANAGED_BY_VALUE}]
    if environment:
        tags.append({"Key": ENVIRONMENT_KEY, "Value": str(environment)})
    if owner:
        tags.append({"Key": "Owner", "Value": str(owner)})
    return tags


def _tag_dict(tagset):
    return {tag["Key"]: tag["Value"] for tag in tagset}


def tags_mark_statecraft(tags):
    """True if a resource's tags (as a dict) carry ManagedBy=statecraft."""
    return tags.get(MANAGED_BY_KEY) == MANAGED_BY_VALUE


def _created_for_same_environment(existing, wanted):
    """True if an existing resource's tags show StateCraft created it for the
    environment the request is for (no environment tag on either side counts)."""
    return tags_mark_statecraft(existing) and existing.get(ENVIRONMENT_KEY) == wanted.get(
        ENVIRONMENT_KEY
    )


@functools.lru_cache(maxsize=1)
def _known_regions():
    # botocore's bundled endpoint data, all partitions; no network call.
    session = boto3.session.Session()
    return frozenset(
        region
        for partition in session.get_available_partitions()
        for region in session.get_available_regions("s3", partition_name=partition)
    )


def aws_region_is_known(region):
    """True if botocore knows the region. An unknown one would otherwise only
    fail later, as a connection error on a made-up endpoint."""
    return region in _known_regions()


def allowed_bucket_markers():
    """Substrings a bucket name must contain to be deletable.

    Configurable via STATECRAFT_DELETE_ALLOWED_MARKERS (comma-separated);
    defaults to the StateCraft Terraform-backend naming marker.
    """
    raw = os.getenv("STATECRAFT_DELETE_ALLOWED_MARKERS", "-terraform-")
    return [m.strip() for m in raw.split(",") if m.strip()]


def delete_target_is_allowed(bucket_name, markers=None):
    """True if the bucket name matches the delete allow-list (pure)."""
    markers = markers if markers is not None else allowed_bucket_markers()
    return any(marker in bucket_name for marker in markers)


def bucket_is_statecraft_managed(s3_client, bucket_name):
    """True only if the bucket carries the ManagedBy=statecraft tag.

    A bucket with no tag set, or owned by something else, returns False so it
    can never be deleted through StateCraft.
    """
    try:
        resp = s3_client.get_bucket_tagging(Bucket=bucket_name)
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code")
        if code in ("NoSuchTagSet", "NoSuchBucket"):
            return False
        raise
    for tag in resp.get("TagSet", []):
        if tag.get("Key") == MANAGED_BY_KEY and tag.get("Value") == MANAGED_BY_VALUE:
            return True
    return False


def _existing_bucket_tags(s3_client, bucket_name):
    """Tags of an existing bucket in this account as a dict ({} if it has none),
    or None if there is no such bucket here.

    AccessDenied also answers None: it is what another account's bucket returns,
    and CreateBucket then reports precisely whether the name is taken.
    """
    try:
        resp = s3_client.get_bucket_tagging(Bucket=bucket_name)
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code")
        if code == "NoSuchTagSet":
            return {}
        if code in ("NoSuchBucket", "AccessDenied"):
            return None
        raise
    return _tag_dict(resp.get("TagSet", []))


def create_s3_bucket(s3_client, bucket_name, region, tags=None):
    """Create (or reconcile) the S3 bucket for Terraform backend state.

    Idempotent for StateCraft's own bucket: if it already exists and carries
    StateCraft's tags for the same environment, its versioning / encryption /
    public-access-block / tags are re-applied, so a retry after a partially-created
    bucket still ends fully configured. Any other existing bucket is refused
    (409) rather than taken over. Tags are merged into the bucket's own, never
    replace them.

    Returns True on success; raises BucketCreationError (with a user-safe
    message) on failure instead of collapsing the cause to a bare False.
    """
    wanted_tags = _tag_dict(tags if tags is not None else managed_tagset())
    logging.info(f"Ensuring S3 bucket '{bucket_name}' exists in region '{region}'...")
    try:
        # us-east-1 must NOT receive a CreateBucketConfiguration: an empty
        # LocationConstraint serializes to an empty XML element that real S3
        # rejects with MalformedXML. Only send the config for other regions.
        create_kwargs = {"Bucket": bucket_name}
        if region != "us-east-1":
            create_kwargs["CreateBucketConfiguration"] = {"LocationConstraint": region}

        # Look before creating: in us-east-1, CreateBucket on a bucket this
        # account already owns succeeds instead of answering BucketAlreadyOwnedByYou.
        existing_tags = _existing_bucket_tags(s3_client, bucket_name)
        if existing_tags is None:
            try:
                s3_client.create_bucket(**create_kwargs)
            except ClientError as e:
                # BucketAlreadyOwnedByYou here means it appeared since the look
                # above, which StateCraft cannot vouch for: also a 409.
                raise _bucket_error(e.response.get("Error", {}).get("Code"), bucket_name)
            existing_tags = {}
            logging.info(f"Bucket '{bucket_name}' created. Configuring settings...")
        elif _created_for_same_environment(existing_tags, wanted_tags):
            # Retry-safe: (re)apply the configuration below so a bucket left
            # half-configured by an earlier run is healed.
            logging.warning(
                f"Bucket '{bucket_name}' already exists and is StateCraft's — reconciling configuration."
            )
        else:
            logging.warning(
                f"Refusing to take over existing bucket '{bucket_name}' (tags: {sorted(existing_tags)})"
            )
            raise _bucket_error("BucketAlreadyOwnedByYou", bucket_name)

        s3_client.put_bucket_versioning(
            Bucket=bucket_name, VersioningConfiguration={"Status": "Enabled"}
        )
        logging.info(f"- Versioning enabled for bucket '{bucket_name}'.")

        s3_client.put_bucket_encryption(
            Bucket=bucket_name,
            ServerSideEncryptionConfiguration={
                "Rules": [
                    {"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}
                ]
            },
        )
        logging.info(
            f"- Server-side encryption (AES256) enabled for bucket '{bucket_name}'."
        )

        s3_client.put_public_access_block(
            Bucket=bucket_name,
            PublicAccessBlockConfiguration={
                "BlockPublicAcls": True,
                "IgnorePublicAcls": True,
                "BlockPublicPolicy": True,
                "RestrictPublicBuckets": True,
            },
        )
        logging.info(f"- Public access blocked for bucket '{bucket_name}'.")

        merged_tags = {**existing_tags, **wanted_tags}
        s3_client.put_bucket_tagging(
            Bucket=bucket_name,
            Tagging={"TagSet": [{"Key": k, "Value": v} for k, v in merged_tags.items()]},
        )
        logging.info(f"- Ownership tags applied to bucket '{bucket_name}'.")

        logging.info(f"S3 bucket '{bucket_name}' created and configured successfully.")
        return True

    except BucketCreationError:
        raise
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code")
        logging.error(
            f"Failed to configure bucket '{bucket_name}' ({error_code}): {e}",
            exc_info=True,
        )
        raise _bucket_error(error_code, bucket_name)
    except Exception as e:
        logging.error(
            f"An unexpected error occurred during S3 bucket creation: {e}",
            exc_info=True,
        )
        raise BucketCreationError(
            f"Unexpected error creating the state bucket '{bucket_name}'."
        )


def bucket_exists(s3_client, bucket_name):
    """True if the bucket exists; False only when S3 says it does not."""
    try:
        s3_client.head_bucket(Bucket=bucket_name)
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchBucket"):
            return False
        raise
    return True


def delete_s3_bucket(s3_client, s3_resource, bucket_name):
    """Deletes all objects and versions within S3 bucket, then deletes the bucket."""
    logging.info(f"Attempting to delete S3 bucket '{bucket_name}'...")
    try:
        bucket = s3_resource.Bucket(bucket_name)

        try:
            s3_client.head_bucket(Bucket=bucket_name)
            logging.info(f"Bucket '{bucket_name}' found. Proceeding with deletion.")
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                logging.warning(
                    f"Bucket '{bucket_name}' does not exist. Skipping deletion."
                )
                return True
            else:
                logging.error(
                    f"Error checking bucket existence for '{bucket_name}': {e}"
                )
                raise

        logging.info(
            f"Emptying bucket '{bucket_name}' (deleting all object versions)..."
        )
        # One DeleteObjects call per page of up to 1000 versions and delete
        # markers, instead of one request per version.
        responses = bucket.object_versions.delete()
        deleted_count = sum(len(r.get("Deleted", [])) for r in responses)
        errors = [err for r in responses for err in r.get("Errors", [])]
        if errors:
            logging.error(
                f"Could not delete {len(errors)} object versions from bucket "
                f"'{bucket_name}', e.g. {errors[0]}"
            )
            return False
        logging.info(
            f"Deleted {deleted_count} object versions from bucket '{bucket_name}'."
        )

        logging.info(f"Bucket '{bucket_name}' emptied. Deleting the bucket itself...")
        bucket.delete()
        logging.info(f"S3 bucket '{bucket_name}' deleted successfully.")
        return True

    except ClientError as e:
        logging.error(
            f"An error occurred deleting bucket '{bucket_name}': {e}", exc_info=True
        )
        return False
    except Exception as e:
        logging.error(
            f"An unexpected error occurred during S3 bucket deletion: {e}",
            exc_info=True,
        )
        return False


def describe_lock_table(dynamodb_client, table_name):
    """Status, tags and deletion protection of a table, or None if it does not exist."""
    try:
        table = dynamodb_client.describe_table(TableName=table_name)["Table"]
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            return None
        raise
    pages = dynamodb_client.get_paginator("list_tags_of_resource").paginate(
        ResourceArn=table["TableArn"]
    )
    return {
        "status": table["TableStatus"],
        "tags": _tag_dict(tag for page in pages for tag in page.get("Tags", [])),
        "deletion_protection": table.get("DeletionProtectionEnabled", False),
    }


def create_dynamodb_table(dynamodb_client, table_name, tags=None):
    """Creates DynamoDB table configured for Terraform state locking.

    The table is tagged like the bucket, so delete can verify ownership, and is
    created with deletion protection, so removing it takes a deliberate unlock.
    """
    tags = tags if tags is not None else managed_tagset()
    logging.info(f"Attempting to create DynamoDB table '{table_name}'...")
    try:
        dynamodb_client.create_table(
            TableName=table_name,
            AttributeDefinitions=[
                {"AttributeName": "LockID", "AttributeType": "S"}
            ],
            KeySchema=[
                {"AttributeName": "LockID", "KeyType": "HASH"}
            ],
            BillingMode="PAY_PER_REQUEST",
            DeletionProtectionEnabled=True,
            Tags=tags,
        )

        logging.info(f"Waiting for table '{table_name}' to become active...")
        waiter = dynamodb_client.get_waiter("table_exists")
        waiter.wait(TableName=table_name, WaiterConfig={"Delay": 5, "MaxAttempts": 20})
        logging.info(f"DynamoDB table '{table_name}' created successfully.")
        return True

    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceInUseException":
            # A table of that name exists, but it may be another one, or still
            # CREATING/DELETING: only StateCraft's own ACTIVE table counts.
            try:
                table = describe_lock_table(dynamodb_client, table_name)
            except ClientError as describe_error:
                logging.error(
                    f"DynamoDB table '{table_name}' already exists and could not be "
                    f"verified as StateCraft's: {describe_error}"
                )
                return False
            if (
                table
                and table["status"] == "ACTIVE"
                and _created_for_same_environment(table["tags"], _tag_dict(tags))
            ):
                logging.warning(
                    f"DynamoDB table '{table_name}' already exists. Skipping creation."
                )
                return True
            logging.error(
                f"DynamoDB table '{table_name}' already exists but is not StateCraft's "
                f"ACTIVE table for this environment (status: "
                f"{table['status'] if table else 'gone'})."
            )
            return False
        else:
            logging.error(
                f"An error occurred creating table '{table_name}': {e}", exc_info=True
            )
            return False
    except Exception as e:
        logging.error(
            f"An unexpected error occurred during DynamoDB table creation: {e}",
            exc_info=True,
        )
        return False


def delete_dynamodb_table(dynamodb_client, table_name):
    """Deletes DynamoDB table."""
    logging.info(f"Attempting to delete DynamoDB table '{table_name}'...")
    try:
        dynamodb_client.delete_table(TableName=table_name)

        logging.info(f"Waiting for table '{table_name}' to be deleted...")
        waiter = dynamodb_client.get_waiter("table_not_exists")
        waiter.wait(TableName=table_name, WaiterConfig={"Delay": 5, "MaxAttempts": 20})
        logging.info(f"DynamoDB table '{table_name}' deleted successfully.")
        return True

    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            logging.warning(
                f"DynamoDB table '{table_name}' does not exist. Skipping deletion."
            )
            return True
        else:
            logging.error(
                f"An error occurred deleting table '{table_name}': {e}", exc_info=True
            )
            return False
    except Exception as e:
        logging.error(
            f"An unexpected error occurred during DynamoDB table deletion: {e}",
            exc_info=True,
        )
        return False


def get_aws_clients(region, aws_access_key_id=None, aws_secret_access_key=None):
    """Initialize and return AWS clients for specified region.

    Args:
        region: AWS region
        aws_access_key_id: Optional AWS access key (falls back to environment/config)
        aws_secret_access_key: Optional AWS secret key (falls back to environment/config)
    """
    try:
        session = boto3.Session(
            region_name=region,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
        )
        return {
            "s3_client": session.client("s3"),
            "s3_resource": session.resource("s3"),
            "dynamodb_client": session.client("dynamodb"),
        }
    except Exception as e:
        logging.error(f"Error initializing AWS clients: {e}", exc_info=True)
        raise
