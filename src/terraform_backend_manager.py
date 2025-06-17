import argparse
import logging
import boto3
from botocore.exceptions import ClientError
import sys

# --- Configuration ---
LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"
LOG_LEVEL = logging.INFO  # Change to logging.DEBUG for more verbose output

BANNER_ART = r"""

███████╗████████╗ █████╗ ████████╗███████╗ ██████╗██████╗  █████╗ ███████╗████████╗
██╔════╝╚══██╔══╝██╔══██╗╚══██╔══╝██╔════╝██╔════╝██╔══██╗██╔══██╗██╔════╝╚══██╔══╝
███████╗   ██║   ███████║   ██║   █████╗  ██║     ██████╔╝███████║█████╗     ██║   
╚════██║   ██║   ██╔══██║   ██║   ██╔══╝  ██║     ██╔══██╗██╔══██║██╔══╝     ██║   
███████║   ██║   ██║  ██║   ██║   ███████╗╚██████╗██║  ██║██║  ██║██║        ██║   
╚══════╝   ╚═╝   ╚═╝  ╚═╝   ╚═╝   ╚══════╝ ╚═════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝        ╚═╝   

                                      __          ___           ____           _____                 
                                     / /  __ __  / _ \___ _  __/ __ \___  ___ / ___/______  __ _____ 
                                    / _ \/ // / / // / -_) |/ / /_/ / _ \(_-</ (_ / __/ _ \/ // / _ \
                                   /_.__/\_, / /____/\__/|___/\____/ .__/___/\___/_/  \___/\_,_/ .__/
                                        /___/                     /_/                         /_/    

"""

# --- Logging Setup ---
logging.basicConfig(level=LOG_LEVEL, format=LOG_FORMAT, stream=sys.stdout)
file_handler = logging.FileHandler("terraform_backend_manager.log")
file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
logging.getLogger().addHandler(file_handler)

logger = logging.getLogger(__name__)  # Use __name__ for logger identification


# --- S3 Functions ---
def create_s3_bucket(s3_client, bucket_name, region):
    """
    Creates an S3 bucket configured for Terraform backend state.
    Versioning is essential for both DynamoDB and native S3 locking.

    Args:
        s3_client: Initialized boto3 S3 client.
        bucket_name (str): The name for the S3 bucket.
        region (str): The AWS region to create the bucket in.

    Returns:
        bool: True if successful, False otherwise.
    """
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

        # Enable Versioning (CRITICAL for state integrity and native S3 locking)
        s3_client.put_bucket_versioning(
            Bucket=bucket_name, VersioningConfiguration={"Status": "Enabled"}
        )
        logging.info(f"- Versioning enabled for bucket '{bucket_name}'.")

        # Enable Server-Side Encryption (AES256) - Recommended practice
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

        # Block Public Access - Recommended security practice
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
            # You might want to add checks here to ensure existing bucket config matches requirements (e.g., versioning)
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
                f"For 'us-east-1' region, do not specify LocationConstraint. Check Boto3/AWS behavior."
            )
            return False  # Should ideally not happen with the check above
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
    """
    Deletes all objects and versions within an S3 bucket, then deletes the bucket.

    Args:
        s3_client: Initialized boto3 S3 client.
        s3_resource: Initialized boto3 S3 resource.
        bucket_name (str): The name of the S3 bucket to delete.

    Returns:
        bool: True if successful, False otherwise.
    """
    logging.info(f"Attempting to delete S3 bucket '{bucket_name}'...")
    try:
        bucket = s3_resource.Bucket(bucket_name)

        # Check if bucket exists before attempting delete operations
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
                raise  # Re-raise other head_bucket errors

        # Empty the bucket (delete all objects and versions)
        logging.info(
            f"Emptying bucket '{bucket_name}' (deleting all object versions)..."
        )
        # Using object_versions.delete() handles both versioned and unversioned objects within the bucket
        deleted_count = 0
        for obj_version in bucket.object_versions.all():
            obj_version.delete()
            deleted_count += 1
        # Alternative/Simpler Boto3 call if preferred (less verbose):
        # bucket.object_versions.delete()
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


# --- DynamoDB Functions ---


def create_dynamodb_table(dynamodb_client, table_name):
    """
    Creates a DynamoDB table configured for Terraform state locking.

    Args:
        dynamodb_client: Initialized boto3 DynamoDB client.
        table_name (str): The name for the DynamoDB table.

    Returns:
        bool: True if successful, False otherwise.
    """
    logging.info(f"Attempting to create DynamoDB table '{table_name}'...")
    try:
        dynamodb_client.create_table(
            TableName=table_name,
            AttributeDefinitions=[
                {"AttributeName": "LockID", "AttributeType": "S"}  # S = String
            ],
            KeySchema=[
                {"AttributeName": "LockID", "KeyType": "HASH"}  # HASH = Partition key
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
            # Optionally check schema here
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
    """
    Deletes a DynamoDB table.

    Args:
        dynamodb_client: Initialized boto3 DynamoDB client.
        table_name (str): The name of the DynamoDB table to delete.

    Returns:
        bool: True if successful, False otherwise.
    """
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


def display_banner():
    """Prints the ASCII art banner."""
    print(BANNER_ART)
    print("-" * 105)  # Add a separator line


# --- Main Execution ---
def main():
    display_banner()
    parser = argparse.ArgumentParser(
        description="Manage AWS resources (S3 Bucket and optional DynamoDB Table) for Terraform backend state.",
        formatter_class=argparse.RawTextHelpFormatter,  # Allows for better formatting in help
    )
    parser.add_argument(
        "action",
        choices=["create", "delete"],
        help="Action to perform: create or delete resources.",
    )
    parser.add_argument(
        "--region",
        required=True,
        help="AWS region for the resources (e.g., us-east-1).",
    )
    parser.add_argument(
        "--bucket-name",
        required=True,
        help="Name for the S3 bucket (must be globally unique).",
    )
    parser.add_argument(
        "--locking-mechanism",
        choices=["dynamodb", "s3"],
        default="dynamodb",
        help="Choose the locking mechanism:\n"
        "  dynamodb: Use S3 bucket + DynamoDB table (recommended for teams).\n"
        "  s3:       Use S3 bucket only (native S3 locking via versioning).\n"
        "(default: dynamodb)",
    )
    parser.add_argument(
        "--table-name",
        help="Name for the DynamoDB table (Required only if --locking-mechanism=dynamodb).",
    )

    args = parser.parse_args()

    # --- Argument Validation ---
    if args.locking_mechanism == "dynamodb" and not args.table_name:
        parser.error("--table-name is required when --locking-mechanism is 'dynamodb'")
    if args.locking_mechanism == "s3" and args.table_name:
        logging.warning(
            f"--table-name ('{args.table_name}') provided but ignored because --locking-mechanism is 's3'."
        )

    print(f"  Action: {args.action}")
    print(f"  Region: {args.region}")
    print(f"  S3 Bucket: {args.bucket_name}")
    print(f"  Locking Mechanism: {args.locking_mechanism}")
    if args.locking_mechanism == "dynamodb":
        print(f"  DynamoDB Table: {args.table_name}")
    print("-" * 105)

    # --- Initialize Boto3 Clients ---
    try:
        session = boto3.Session(region_name=args.region)
        s3_client = session.client("s3")
        s3_resource = session.resource("s3")  # Needed for bucket emptying/deletion
        dynamodb_client = None  # Initialize later only if needed
        if args.locking_mechanism == "dynamodb":
            dynamodb_client = session.client("dynamodb")
    except Exception as e:
        logging.error(f"Error initializing AWS clients: {e}", exc_info=True)
        logging.error(
            "Please ensure your AWS credentials and region are configured correctly."
        )
        sys.exit(1)

    # --- Execute Actions ---
    overall_success = True
    s3_success = False
    dynamodb_success = False  # Assume success if not needed

    if args.action == "create":
        s3_success = create_s3_bucket(s3_client, args.bucket_name, args.region)
        if args.locking_mechanism == "dynamodb":
            dynamodb_success = create_dynamodb_table(dynamodb_client, args.table_name)
            overall_success = s3_success and dynamodb_success
        else:
            # If only S3 locking, DynamoDB "succeeds" by default (not needed)
            dynamodb_success = True
            overall_success = s3_success

    elif args.action == "delete":
        # Delete DynamoDB table first if it was managed
        if args.locking_mechanism == "dynamodb":
            dynamodb_success = delete_dynamodb_table(dynamodb_client, args.table_name)
        else:
            # If only S3 locking, DynamoDB "succeeds" by default (wasn't managed)
            dynamodb_success = True

        # Always attempt S3 bucket deletion (as it's always created)
        # Only proceed with S3 delete if DynamoDB delete was successful (or not needed)
        if dynamodb_success:
            s3_success = delete_s3_bucket(s3_client, s3_resource, args.bucket_name)
            overall_success = (
                s3_success  # Overall success now depends only on S3 deletion success
            )
        else:
            logging.error(
                "Skipping S3 bucket deletion because DynamoDB table deletion failed."
            )
            s3_success = False  # Mark S3 as failed because we didn't attempt it
            overall_success = False

    # --- Final Status ---
    print("-" * 105)
    if overall_success:
        logging.info(f"Action '{args.action}' completed successfully.")
        sys.exit(0)
    else:
        logging.error(f"Action '{args.action}' encountered errors.")
        # Log which part failed specifically
        if not s3_success:
            logging.error("-> S3 Bucket operation failed.")
        if args.locking_mechanism == "dynamodb" and not dynamodb_success:
            logging.error("-> DynamoDB Table operation failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
