"""REST API server for StateCraft - enables deployment as web service.

SECURITY NOTICE:
- Always deploy with HTTPS/TLS in production
- Consider using AWS IAM roles or STS temporary credentials instead of long-lived access keys
- Credentials are not logged or persisted by this application
"""

import logging
import uuid
from enum import Enum
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from auth import require_service_token
from logs import request_id_var
from core import (
    BucketCreationError,
    bucket_is_statecraft_managed,
    create_dynamodb_table,
    create_s3_bucket,
    delete_dynamodb_table,
    delete_s3_bucket,
    delete_target_is_allowed,
    get_aws_clients,
    managed_tagset,
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="StateCraft API",
    description="Manage AWS resources (S3 Bucket and optional DynamoDB Table) for Terraform backend state",
    version="1.0.0",
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Bind the caller's X-Request-ID (or a new one) so it appears in every log
    line for this request and correlates with the backend and other services."""
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
    token = request_id_var.set(request_id)
    try:
        response = await call_next(request)
    finally:
        request_id_var.reset(token)
    response.headers["X-Request-ID"] = request_id
    return response


class LockingMechanism(str, Enum):
    """Locking mechanism choices for Terraform state."""

    dynamodb = "dynamodb"
    s3 = "s3"


class ResourceRequest(BaseModel):
    """Request model for resource creation/deletion operations."""

    region: str = Field(..., description="AWS region (e.g., us-east-1)")
    bucket_name: str = Field(..., description="S3 bucket name (globally unique)")
    locking_mechanism: LockingMechanism = Field(
        default=LockingMechanism.dynamodb,
        description="Locking mechanism: dynamodb (S3+DynamoDB) or s3 (native S3 locking)",
    )
    table_name: Optional[str] = Field(
        None, description="DynamoDB table name (required if locking_mechanism=dynamodb)"
    )
    aws_access_key_id: Optional[str] = Field(
        None,
        description="AWS access key ID (optional, falls back to environment). Use HTTPS in production!"
    )
    aws_secret_access_key: Optional[str] = Field(
        None,
        description="AWS secret access key (optional, falls back to environment). Use HTTPS in production!"
    )
    # Ownership metadata — tagged onto created buckets so delete can verify ownership.
    environment: Optional[str] = Field(
        None, description="OpenPrime environment id (tagged as OpenPrimeEnv on create)"
    )
    owner: Optional[str] = Field(
        None, description="Requesting user/identity (tagged as Owner; logged on delete)"
    )
    # Destructive-delete guards (ignored on create).
    confirm: Optional[str] = Field(
        None,
        description="Delete only: must equal bucket_name to authorize destruction",
    )
    dry_run: bool = Field(
        False, description="Delete only: report what would be deleted without deleting"
    )

    class Config:
        use_enum_values = True

    def __repr__(self):
        """Custom repr to prevent credentials from appearing in logs."""
        safe_dict = self.model_dump()
        if safe_dict.get('aws_access_key_id'):
            safe_dict['aws_access_key_id'] = '[REDACTED]'
        if safe_dict.get('aws_secret_access_key'):
            safe_dict['aws_secret_access_key'] = '[REDACTED]'
        return f"ResourceRequest({safe_dict})"


class ResourceResponse(BaseModel):
    """Response model for resource operations."""

    success: bool
    message: str
    details: dict = {}


@app.get("/", tags=["Health"])
async def root():
    """Health check endpoint."""
    return {"status": "healthy", "service": "StateCraft API"}


@app.get("/health", tags=["Health"])
async def health_check():
    """Detailed health check endpoint."""
    return {
        "status": "healthy",
        "service": "StateCraft API",
        "version": "1.0.0",
    }


@app.post(
    "/resources/create",
    response_model=ResourceResponse,
    tags=["Resources"],
    dependencies=[Depends(require_service_token)],
)
async def create_resources(request: ResourceRequest):
    """Create S3 bucket and optionally DynamoDB table for Terraform backend.

    AWS credentials can be provided in the request or via environment variables.
    """
    if request.locking_mechanism == LockingMechanism.dynamodb and not request.table_name:
        raise HTTPException(
            status_code=400,
            detail="table_name is required when locking_mechanism is 'dynamodb'",
        )

    try:
        clients = get_aws_clients(
            request.region,
            request.aws_access_key_id,
            request.aws_secret_access_key,
        )
    except Exception as e:
        logger.error(f"Failed to initialize AWS clients: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to initialize AWS clients. Check AWS credentials configuration.",
        )

    try:
        create_s3_bucket(
            clients["s3_client"],
            request.bucket_name,
            request.region,
            tags=managed_tagset(request.environment, request.owner),
        )
    except BucketCreationError as e:
        logger.error(f"S3 bucket creation failed: {e}")
        raise HTTPException(
            status_code=e.status_code,
            detail={"message": str(e), "details": {"s3_bucket": "failed"}},
        )

    if request.locking_mechanism == LockingMechanism.dynamodb:
        dynamodb_success = create_dynamodb_table(
            clients["dynamodb_client"], request.table_name
        )
        if not dynamodb_success:
            raise HTTPException(
                status_code=500,
                detail={
                    "message": "DynamoDB lock table creation failed",
                    "details": {"dynamodb_table": "failed"},
                },
            )

    return ResourceResponse(
        success=True,
        message=f"Resources created successfully in {request.region}",
        details={
            "bucket_name": request.bucket_name,
            "locking_mechanism": request.locking_mechanism,
            "table_name": request.table_name
            if request.locking_mechanism == LockingMechanism.dynamodb
            else None,
        },
    )


@app.post(
    "/resources/delete",
    response_model=ResourceResponse,
    tags=["Resources"],
    dependencies=[Depends(require_service_token)],
)
async def delete_resources(request: ResourceRequest):
    """Delete S3 bucket and optionally DynamoDB table.

    Guarded against accidental/malicious destruction: the caller must echo the
    bucket name in `confirm`, the name must match the delete allow-list, and the
    bucket must carry the StateCraft ownership tag. `dry_run` reports without deleting.
    """
    # Audit every destructive request (identity via the shared service token +
    # the caller-supplied owner/environment).
    logger.warning(
        "Delete requested: bucket=%s env=%s owner=%s dry_run=%s",
        request.bucket_name,
        request.environment,
        request.owner,
        request.dry_run,
    )

    if request.confirm != request.bucket_name:
        raise HTTPException(
            status_code=400,
            detail="confirm must equal bucket_name to authorize deletion",
        )
    if not delete_target_is_allowed(request.bucket_name):
        raise HTTPException(
            status_code=400,
            detail="bucket_name is not in the StateCraft delete allow-list",
        )

    try:
        clients = get_aws_clients(
            request.region,
            request.aws_access_key_id,
            request.aws_secret_access_key,
        )
    except Exception as e:
        logger.error(f"Failed to initialize AWS clients: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to initialize AWS clients. Check AWS credentials configuration.",
        )

    # Never delete a bucket StateCraft did not create.
    if not bucket_is_statecraft_managed(clients["s3_client"], request.bucket_name):
        logger.warning(
            "Refusing to delete unmanaged bucket '%s' (missing ManagedBy=statecraft tag)",
            request.bucket_name,
        )
        raise HTTPException(
            status_code=403,
            detail="Refusing to delete a bucket not tagged ManagedBy=statecraft",
        )

    if request.dry_run:
        return ResourceResponse(
            success=True,
            message=f"Dry run: '{request.bucket_name}' is managed, confirmed and allowed — it would be deleted.",
            details={"bucket_name": request.bucket_name, "dry_run": True},
        )

    dynamodb_success = True
    if request.locking_mechanism == LockingMechanism.dynamodb:
        if not request.table_name:
            raise HTTPException(
                status_code=400,
                detail="table_name is required when locking_mechanism is 'dynamodb'",
            )
        dynamodb_success = delete_dynamodb_table(
            clients["dynamodb_client"], request.table_name
        )

    if not dynamodb_success:
        raise HTTPException(
            status_code=500,
            detail="DynamoDB table deletion failed. S3 bucket deletion skipped.",
        )

    s3_success = delete_s3_bucket(
        clients["s3_client"], clients["s3_resource"], request.bucket_name
    )

    if not s3_success:
        raise HTTPException(
            status_code=500,
            detail="S3 bucket deletion failed.",
        )

    return ResourceResponse(
        success=True,
        message=f"Resources deleted successfully from {request.region}",
        details={
            "bucket_name": request.bucket_name,
            "table_name": request.table_name
            if request.locking_mechanism == LockingMechanism.dynamodb
            else None,
        },
    )


# Server entry point for running with uvicorn
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, log_config=None)
