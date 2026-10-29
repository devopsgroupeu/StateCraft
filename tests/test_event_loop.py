"""Slow AWS work must not stall the API (audit finding C73).

boto3 calls and waiters block. Run inside an `async def` handler they block the
event loop of the single uvicorn worker, so /health stops answering and the
liveness probe restarts the pod mid-delete, leaving a half-emptied state bucket.
Run in the threadpool, they only occupy one worker thread.
"""

import asyncio
import threading
from unittest.mock import MagicMock

import httpx
import pytest

from statecraft import api
from statecraft.logs import request_id_var

BUCKET = "123456789012-terraform-prod"
REQUEST = {
    "region": "eu-west-1",
    "bucket_name": BUCKET,
    "locking_mechanism": "s3",
    "confirm": BUCKET,
    "aws_access_key_id": "AKIAEXAMPLE",
    "aws_secret_access_key": "example-secret",
}
# How long the fake delete waits for the test to release it. Only reached when
# the event loop is blocked, so it bounds how long a failing run takes.
BLOCK_SECONDS = 3


@pytest.fixture
def slow_delete(monkeypatch):
    """A bucket delete that blocks its thread until the test releases it."""
    started, release = threading.Event(), threading.Event()
    seen = {}

    def delete_s3_bucket(*_args, **_kwargs):
        seen["request_id"] = request_id_var.get()
        started.set()
        seen["released_by_test"] = release.wait(timeout=BLOCK_SECONDS)
        return True

    monkeypatch.setattr(api, "get_aws_clients", MagicMock())
    monkeypatch.setattr(api, "bucket_is_statecraft_managed", lambda *_: True)
    monkeypatch.setattr(api, "delete_s3_bucket", delete_s3_bucket)
    return started, release, seen


async def _health_during_delete(started, release):
    transport = httpx.ASGITransport(app=api.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://statecraft") as client:
        delete = asyncio.create_task(
            client.post("/resources/delete", json=REQUEST, headers={"X-Request-ID": "req-c73"})
        )
        while not started.is_set():
            await asyncio.sleep(0.01)

        health = await asyncio.wait_for(client.get("/health"), timeout=BLOCK_SECONDS)

        release.set()
        return health, await delete


def test_health_answers_while_a_slow_delete_is_running(slow_delete):
    started, release, seen = slow_delete

    health, delete = asyncio.run(_health_during_delete(started, release))

    assert health.status_code == 200
    # The delete was still blocked when /health answered: the test released it.
    assert seen["released_by_test"] is True
    assert delete.status_code == 200


def test_the_request_id_still_reaches_work_done_in_the_threadpool(slow_delete):
    started, release, seen = slow_delete

    asyncio.run(_health_during_delete(started, release))

    assert seen["request_id"] == "req-c73"
