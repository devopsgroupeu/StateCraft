"""Tests for service-token authentication (fail-closed, audit finding B17)."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from statecraft import api, auth
from statecraft.api import app
from statecraft.auth import token_is_authorized

CREATE_BODY = {
    "region": "eu-west-1",
    "bucket_name": "123456789012-terraform-prod",
    "locking_mechanism": "s3",
    "aws_access_key_id": "AKIAEXAMPLE",
    "aws_secret_access_key": "example-secret",
}


@pytest.fixture
def no_token_configured(monkeypatch):
    monkeypatch.setattr(auth, "SERVICE_TOKEN", None)
    monkeypatch.delenv("STATECRAFT_AUTH_DISABLED", raising=False)


@pytest.fixture
def aws_clients(monkeypatch):
    """Records whether a handler got as far as touching AWS."""
    get_clients = MagicMock()
    monkeypatch.setattr(api, "get_aws_clients", get_clients)
    return get_clients


def test_rejects_everything_when_no_token_is_configured():
    assert token_is_authorized(None, None) is False
    assert token_is_authorized("anything", None) is False
    assert token_is_authorized(None, "") is False


def test_dev_flag_only_applies_while_no_token_is_configured():
    assert token_is_authorized(None, None, auth_disabled=True) is True
    # A configured token is always enforced, whatever the flag says.
    assert token_is_authorized("wrong", "s3cr3t-token", auth_disabled=True) is False
    assert token_is_authorized(None, "s3cr3t-token", auth_disabled=True) is False


def test_accepts_matching_token():
    assert token_is_authorized("s3cr3t-token", "s3cr3t-token") is True


def test_rejects_wrong_token():
    assert token_is_authorized("wrong", "s3cr3t-token") is False


def test_rejects_missing_token_when_required():
    assert token_is_authorized(None, "s3cr3t-token") is False
    assert token_is_authorized("", "s3cr3t-token") is False


@pytest.mark.parametrize("path", ["/resources/create", "/resources/delete"])
def test_endpoints_reject_requests_when_no_token_is_configured(
    no_token_configured, aws_clients, path
):
    response = TestClient(app).post(path, json={**CREATE_BODY, "confirm": CREATE_BODY["bucket_name"]})

    assert response.status_code == 401
    aws_clients.assert_not_called()


def test_endpoints_require_the_configured_token(monkeypatch, aws_clients):
    monkeypatch.setattr(auth, "SERVICE_TOKEN", "s3cr3t-token")
    client = TestClient(app)

    assert client.post("/resources/create", json=CREATE_BODY).status_code == 401
    assert client.post(
        "/resources/create", json=CREATE_BODY, headers={"X-Service-Token": "wrong"}
    ).status_code == 401
    aws_clients.assert_not_called()


def test_api_refuses_to_start_without_a_token(no_token_configured, monkeypatch):
    monkeypatch.setattr(api, "start_metrics_server", lambda: None)

    with pytest.raises(RuntimeError, match="SERVICE_TOKEN"):
        with TestClient(app):
            pass


def test_api_starts_with_a_token(monkeypatch):
    monkeypatch.setattr(auth, "SERVICE_TOKEN", "s3cr3t-token")
    monkeypatch.delenv("STATECRAFT_AUTH_DISABLED", raising=False)
    monkeypatch.setattr(api, "start_metrics_server", lambda: None)

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200


def test_api_starts_without_a_token_only_with_the_dev_flag(no_token_configured, monkeypatch):
    monkeypatch.setenv("STATECRAFT_AUTH_DISABLED", "true")
    monkeypatch.setattr(api, "start_metrics_server", lambda: None)

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
