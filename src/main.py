import argparse
import logging
import sys

from core import (
    create_dynamodb_table,
    create_s3_bucket,
    delete_dynamodb_table,
    delete_s3_bucket,
    get_aws_clients,
)

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

logger = logging.getLogger(__name__)


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

    # Initialize AWS clients
    try:
        clients = get_aws_clients(args.region)
        s3_client = clients["s3_client"]
        s3_resource = clients["s3_resource"]
        dynamodb_client = clients["dynamodb_client"]
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
