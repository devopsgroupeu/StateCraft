"""Prometheus metrics (OP-176): RED metrics by route pattern, on their own port.

The metrics endpoint is unauthenticated, so the property that matters most is
that the API app does NOT serve it - only the separate listener does, on a port
no ingress routes to.
"""

import socket
import urllib.error
import urllib.request

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY, generate_latest

from statecraft import api, metrics
from statecraft.api import app

client = TestClient(app, raise_server_exceptions=False)


def requests_count(**labels):
    return REGISTRY.get_sample_value("http_requests_total", labels) or 0.0


@pytest.fixture
def mini_client():
    """An app with a parameterised route and one that raises, behind the middleware."""
    mini = FastAPI()
    mini.middleware("http")(metrics.metrics_middleware)

    @mini.get("/items/{item_id}")
    def get_item(item_id: str):
        return {"id": item_id}

    @mini.get("/explode")
    def explode():
        raise RuntimeError("unhandled")

    return TestClient(mini, raise_server_exceptions=False)


@pytest.fixture
def listener(monkeypatch):
    """Start the metrics listener on an ephemeral port; shut it down afterwards."""
    monkeypatch.delenv("METRICS_ENABLED", raising=False)
    server = metrics.start_metrics_server(port=0)
    yield f"http://127.0.0.1:{server.server_port}"
    metrics.stop_metrics_server()


def test_requests_are_labelled_with_the_route_pattern_not_the_raw_path(mini_client):
    before = requests_count(method="GET", route="/items/{item_id}", status_code="200")

    mini_client.get("/items/abc")
    mini_client.get("/items/def")

    assert requests_count(method="GET", route="/items/{item_id}", status_code="200") == before + 2
    assert REGISTRY.get_sample_value(
        "http_requests_total", {"method": "GET", "route": "/items/abc", "status_code": "200"}
    ) is None


def test_an_unhandled_exception_is_counted_as_a_500(mini_client):
    before = requests_count(method="GET", route="/explode", status_code="500")

    assert mini_client.get("/explode").status_code == 500

    assert requests_count(method="GET", route="/explode", status_code="500") == before + 1


def test_api_routes_are_counted_by_status():
    before = requests_count(method="POST", route="/resources/create", status_code="422")

    # region and bucket_name are required: a deterministic 422, no AWS call.
    assert client.post("/resources/create", json={}).status_code == 422

    assert requests_count(method="POST", route="/resources/create", status_code="422") == before + 1


def test_unmatched_paths_share_one_label():
    before = requests_count(method="GET", route="unmatched", status_code="404")

    client.get("/no/such/path")
    client.get("/another/missing/path")

    assert requests_count(method="GET", route="unmatched", status_code="404") == before + 2


def test_probe_traffic_is_not_counted():
    client.get("/health")

    assert REGISTRY.get_sample_value(
        "http_requests_total", {"method": "GET", "route": "/health", "status_code": "200"}
    ) is None


def test_the_api_app_never_serves_metrics():
    response = client.get("/metrics")

    assert response.status_code == 404
    assert "http_requests_total" not in response.text


def test_the_listener_serves_metrics_on_its_own_port(listener):
    client.get("/no/such/path")

    with urllib.request.urlopen(f"{listener}/metrics") as response:
        body = response.read().decode()

    assert response.status == 200
    assert "# TYPE http_requests_total counter" in body
    assert "http_request_duration_seconds_bucket" in body


def test_starting_twice_returns_the_running_listener(listener):
    first = metrics.start_metrics_server(port=0)

    assert metrics.start_metrics_server(port=0) is first


def test_metrics_can_be_disabled(monkeypatch):
    monkeypatch.setenv("METRICS_ENABLED", "false")

    assert metrics.start_metrics_server(port=0) is None


def test_invalid_metrics_port_is_logged_not_raised(monkeypatch):
    monkeypatch.delenv("METRICS_ENABLED", raising=False)
    monkeypatch.setenv("METRICS_PORT", "metrics")

    assert metrics.start_metrics_server() is None


def test_a_port_already_in_use_is_logged_not_raised(monkeypatch):
    # The listener starts in the lifespan, where an exception would abort the
    # API's startup instead of just leaving metrics unavailable.
    monkeypatch.delenv("METRICS_ENABLED", raising=False)
    with socket.socket() as blocker:
        blocker.bind(("0.0.0.0", 0))
        blocker.listen()
        try:
            assert metrics.start_metrics_server(port=blocker.getsockname()[1]) is None
        finally:
            metrics.stop_metrics_server()


def test_builtin_routes_are_labelled_by_their_path(mini_client):
    # The mini app keeps FastAPI's default /openapi.json; StateCraft's own app
    # serves it only when STATECRAFT_DOCS_ENABLED is set (OP-270).
    before = requests_count(method="GET", route="/openapi.json", status_code="200")

    mini_client.get("/openapi.json")

    assert requests_count(method="GET", route="/openapi.json", status_code="200") == before + 1


def test_no_created_timestamp_series_are_exported():
    client.get("/no/such/path")

    assert "http_requests_created" not in generate_latest().decode()


def test_the_lifespan_starts_the_metrics_listener(monkeypatch):
    calls = []
    monkeypatch.setattr(api, "start_metrics_server", lambda: calls.append(True))

    with TestClient(app):
        pass

    assert calls == [True]


def test_unknown_http_methods_share_one_label(mini_client):
    before = requests_count(method="other", route="unmatched", status_code="404")

    mini_client.request("FOOBAR", "/no/such/path")
    mini_client.request("XYZZY", "/no/such/path")

    assert requests_count(method="other", route="unmatched", status_code="404") == before + 2
    assert REGISTRY.get_sample_value(
        "http_requests_total", {"method": "FOOBAR", "route": "unmatched", "status_code": "404"}
    ) is None
