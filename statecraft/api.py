"""REST API server for StateCraft - enables deployment as web service.

SECURITY NOTICE:
- Always deploy with HTTPS/TLS in production
- Consider using AWS IAM roles or STS temporary credentials instead of long-lived access keys
- Credentials are not logged or persisted by this application
"""

import logging
import uuid
from contextlib import asynccontextmanager
from enum import Enum
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, SecretStr

from .auth import ensure_auth_configured, require_service_token
from .version import __version__
from .logs import request_id_var
from .metrics import metrics_middleware, start_metrics_server
from .core import (
    BucketCreationError,
    aws_region_is_known,
    bucket_exists,
    bucket_is_statecraft_managed,
    create_dynamodb_table,
    create_s3_bucket,
    delete_dynamodb_table,
    delete_s3_bucket,
    delete_target_is_allowed,
    describe_lock_table,
    get_aws_clients,
    managed_tagset,
    tags_mark_statecraft,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Check auth is configured, then start the metrics listener in the process
    that serves requests.

    Only API server mode runs the lifespan, so a one-off CLI invocation never
    binds the metrics port.
    """
    ensure_auth_configured()
    start_metrics_server()
    yield


app = FastAPI(
    title="StateCraft API",
    description="Manage AWS resources (S3 Bucket and optional DynamoDB Table) for Terraform backend state",
    version=__version__,
    lifespan=lifespan,
)

app.middleware("http")(metrics_middleware)


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


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_request: Request, exc: RequestValidationError):
    """422 without the rejected input.

    FastAPI's default handler echoes each error's `input`: for a missing field,
    the whole request body, AWS secret key included, and callers log what they
    get back.
    """
    errors = [
        {"type": error["type"], "loc": error["loc"], "msg": error["msg"]}
        for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": errors})


class LockingMechanism(str, Enum):
    """Locking mechanism choices for Terraform state."""

    dynamodb = "dynamodb"
    s3 = "s3"


class ResourceRequest(BaseModel):
    """Request model for resource creation/deletion operations."""

    region: str = Field(..., description="AWS region (e.g., us-east-1)")
    bucket_name: str = Field(..., description="S3 bucket name (globally unique)")
    locking_mechanism: LockingMechanism = Field(
        default=LockingMechanism.s3,
        description="Locking mechanism: s3 (native S3 locking, default) or dynamodb "
        "(S3+DynamoDB; deprecated by Terraform)",
    )
    table_name: Optional[str] = Field(
        None, description="DynamoDB table name (required if locking_mechanism=dynamodb)"
    )
    # Required, but checked in the handlers so a missing key answers 400. StateCraft
    # never falls back to its own AWS identity (see _require_customer_credentials).
    aws_access_key_id: Optional[SecretStr] = Field(
        None,
        description="Customer's AWS access key ID (required). Use HTTPS in production!"
    )
    aws_secret_access_key: Optional[SecretStr] = Field(
        None,
        description="Customer's AWS secret access key (required). Use HTTPS in production!"
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


def _secret_value(secret: Optional[SecretStr]) -> Optional[str]:
    return secret.get_secret_value() if secret else None


def _require_known_region(region: str):
    if not aws_region_is_known(region):
        raise HTTPException(status_code=400, detail=f"Unknown AWS region '{region}'")


def _require_customer_credentials(request: ResourceRequest):
    """Reject a request that does not carry the customer's AWS keys.

    Without them boto3 would fall back to its default credential chain, which in
    a pod resolves to the platform's own identity, so the bucket would be created
    or deleted in the platform account instead of the customer's.
    """
    if not (
        _secret_value(request.aws_access_key_id)
        and _secret_value(request.aws_secret_access_key)
    ):
        raise HTTPException(
            status_code=400,
            detail="aws_access_key_id and aws_secret_access_key are required",
        )


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
        "version": __version__,
    }


@app.post(
    "/resources/create",
    response_model=ResourceResponse,
    tags=["Resources"],
    dependencies=[Depends(require_service_token)],
)
def create_resources(request: ResourceRequest):
    """Create S3 bucket and optionally DynamoDB table for Terraform backend.

    A plain `def` on purpose: boto3 calls and waiters block, so FastAPI must run
    this in its threadpool rather than on the event loop, where it would stall
    every other request, /health included.

    The customer's AWS credentials must be in the request.
    """
    _require_customer_credentials(request)
    if request.locking_mechanism == LockingMechanism.dynamodb and not request.table_name:
        raise HTTPException(
            status_code=400,
            detail="table_name is required when locking_mechanism is 'dynamodb'",
        )
    _require_known_region(request.region)

    try:
        clients = get_aws_clients(
            request.region,
            _secret_value(request.aws_access_key_id),
            _secret_value(request.aws_secret_access_key),
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
            clients["dynamodb_client"],
            request.table_name,
            tags=managed_tagset(request.environment, request.owner),
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
def delete_resources(request: ResourceRequest):
    """Delete S3 bucket and optionally DynamoDB table.

    A plain `def` for the same reason as create_resources.

    Guarded against accidental/malicious destruction: the caller must echo the
    bucket name in `confirm`, the name must match the delete allow-list, and the
    bucket and lock table must carry the StateCraft ownership tag. `dry_run`
    reports without deleting. Every check runs before anything is deleted; an
    already-deleted bucket or table counts as deleted.
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
    if request.locking_mechanism == LockingMechanism.dynamodb and not request.table_name:
        raise HTTPException(
            status_code=400,
            detail="table_name is required when locking_mechanism is 'dynamodb'",
        )
    _require_known_region(request.region)
    _require_customer_credentials(request)

    try:
        clients = get_aws_clients(
            request.region,
            _secret_value(request.aws_access_key_id),
            _secret_value(request.aws_secret_access_key),
        )
    except Exception as e:
        logger.error(f"Failed to initialize AWS clients: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to initialize AWS clients. Check AWS credentials configuration.",
        )

    # Never delete a bucket StateCraft did not create. One that is already gone
    # is the goal state, so a retried delete still succeeds.
    if not bucket_is_statecraft_managed(clients["s3_client"], request.bucket_name):
        if bucket_exists(clients["s3_client"], request.bucket_name):
            logger.warning(
                "Refusing to delete unmanaged bucket '%s' (missing ManagedBy=statecraft tag)",
                request.bucket_name,
            )
            raise HTTPException(
                status_code=403,
                detail="Refusing to delete a bucket not tagged ManagedBy=statecraft",
            )
        logger.info("Bucket '%s' is already gone", request.bucket_name)

    # Nor a lock table StateCraft did not create, and not one still protected.
    lock_table = None
    if request.locking_mechanism == LockingMechanism.dynamodb:
        lock_table = describe_lock_table(clients["dynamodb_client"], request.table_name)
        if lock_table and not tags_mark_statecraft(lock_table["tags"]):
            logger.warning(
                "Refusing to delete unmanaged table '%s' (missing ManagedBy=statecraft tag)",
                request.table_name,
            )
            raise HTTPException(
                status_code=403,
                detail="Refusing to delete a table not tagged ManagedBy=statecraft",
            )
        if lock_table and lock_table["deletion_protection"]:
            raise HTTPException(
                status_code=409,
                detail=f"Table '{request.table_name}' has deletion protection enabled. "
                "Disable it deliberately, then retry.",
            )

    if request.dry_run:
        return ResourceResponse(
            success=True,
            message=f"Dry run: '{request.bucket_name}' is managed, confirmed and allowed — it would be deleted.",
            details={"bucket_name": request.bucket_name, "dry_run": True},
        )

    # The bucket goes first: if emptying it fails, the lock table still guards
    # whatever state is left.
    s3_success = delete_s3_bucket(
        clients["s3_client"], clients["s3_resource"], request.bucket_name
    )

    if not s3_success:
        raise HTTPException(
            status_code=500,
            detail="S3 bucket deletion failed. DynamoDB table deletion skipped.",
        )

    if lock_table and not delete_dynamodb_table(
        clients["dynamodb_client"], request.table_name
    ):
        raise HTTPException(
            status_code=500,
            detail="S3 bucket deleted, but DynamoDB table deletion failed.",
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
