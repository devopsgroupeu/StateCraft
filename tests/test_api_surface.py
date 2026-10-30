"""What the API discloses and echoes (OP-270, B72): the interactive docs and
schema, and the caller's X-Request-ID."""

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from statecraft.api import app

client = TestClient(app, raise_server_exceptions=False)


# --- Docs and schema ------------------------------------------------------------


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_the_docs_and_the_schema_are_off_by_default(path):
    assert client.get(path).status_code == 404


def test_the_docs_can_be_turned_on_for_development():
    """The app is built at import, so the flag is read in a fresh interpreter."""
    probe = (
        "from fastapi.testclient import TestClient\n"
        "from statecraft.api import app\n"
        "c = TestClient(app)\n"
        "print([c.get(p).status_code for p in ('/docs', '/redoc', '/openapi.json')])\n"
    )
    env = {**os.environ, "STATECRAFT_DOCS_ENABLED": "true", "STATECRAFT_AUTH_DISABLED": "true"}
    env.pop("SERVICE_TOKEN", None)

    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.strip().splitlines()[-1] == "[200, 200, 200]"


# --- X-Request-ID ---------------------------------------------------------------


@pytest.mark.parametrize("request_id", ["corr-123", "0f8fad5b-d9cb-469f-a165-70867728950e", "a" * 64])
def test_a_well_formed_request_id_is_kept(request_id):
    response = client.get("/health", headers={"X-Request-ID": request_id})

    assert response.headers["X-Request-ID"] == request_id


@pytest.mark.parametrize(
    "request_id",
    ["a" * 65, "id with spaces", "<script>", "abc;rm", '{"json":1}', ""],
    ids=["too-long", "spaces", "markup", "semicolon", "json", "empty"],
)
def test_any_other_request_id_is_replaced_with_a_generated_one(request_id):
    response = client.get("/health", headers={"X-Request-ID": request_id})

    echoed = response.headers["X-Request-ID"]
    assert echoed != request_id
    assert re.fullmatch(r"[0-9a-f]{16}", echoed)
