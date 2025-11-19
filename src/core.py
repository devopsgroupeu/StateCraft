"""Core business logic for StateCraft - shared by CLI and API."""

import logging
import sys

import boto3
from botocore.exceptions import ClientError

# Logging setup
LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"
LOG_LEVEL = logging.INFO

logging.basicConfig(level=LOG_LEVEL, format=LOG_FORMAT, stream=sys.stdout)
# File handler writes to /tmp for Kubernetes read-only filesystems
file_handler = logging.FileHandler("/tmp/statecraft.log")
file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
logging.getLogger().addHandler(file_handler)

logger = logging.getLogger(__name__)


def create_s3_bucket(s3_client, bucket_name, region):
    """Creates S3 bucket configured for Terraform backend state with versioning and encryption."""
    logging.info(
        f"Attempting to create S3 bucket '{bucket_name}' in region '{region}'..."
    )
    try:
        location_args = {}
        if region != "us-east-1":
            location_args["LocationConstraint"] = region

        s3_client.create_bucket(
            Bucket=bucket_name, CreateBucketConfiguration=location_args
        )
        logging.info(f"Bucket '{bucket_name}' created. Configuring settings...")

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

        logging.info(f"S3 bucket '{bucket_name}' created and configured successfully.")
        return True

    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code")
        if error_code == "BucketAlreadyOwnedByYou":
            logging.warning(
                f"Bucket '{bucket_name}' already exists and is owned by you. Skipping creation."
            )
            return True
        elif error_code == "BucketAlreadyExists":
            logging.error(
                f"Bucket name '{bucket_name}' already exists but is owned by someone else or in a different region setup."
            )
            return False
        elif error_code == "InvalidBucketName":
            logging.error(
                f"Invalid bucket name: '{bucket_name}'. Please check AWS naming rules."
            )
            return False
        elif (
            error_code == "IllegalLocationConstraintException" and region == "us-east-1"
        ):
            logging.error(
                "For 'us-east-1' region, do not specify LocationConstraint. Check Boto3/AWS behavior."
            )
            return False
        else:
            logging.error(
                f"An unexpected error occurred creating bucket '{bucket_name}': {e}",
                exc_info=True,
            )
            return False
    except Exception as e:
        logging.error(
            f"An unexpected error occurred during S3 bucket creation: {e}",
            exc_info=True,
        )
        return False


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
        deleted_count = 0
        for obj_version in bucket.object_versions.all():
            obj_version.delete()
            deleted_count += 1
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


def create_dynamodb_table(dynamodb_client, table_name):
    """Creates DynamoDB table configured for Terraform state locking."""
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
        )

        logging.info(f"Waiting for table '{table_name}' to become active...")
        waiter = dynamodb_client.get_waiter("table_exists")
        waiter.wait(TableName=table_name, WaiterConfig={"Delay": 5, "MaxAttempts": 20})
        logging.info(f"DynamoDB table '{table_name}' created successfully.")
        return True

    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceInUseException":
            logging.warning(
                f"DynamoDB table '{table_name}' already exists. Skipping creation."
            )
            return True
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
