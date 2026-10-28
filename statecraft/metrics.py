"""Prometheus metrics for StateCraft.

Served on a DEDICATED port (METRICS_PORT, default 9090) by a second listener,
never on the API port. The endpoint is unauthenticated, so on the API port it
would expose route names, error rates and latency distributions to anything
that can reach the API. On its own port it is only reachable in-cluster, where
Prometheus scrapes it through the chart's ServiceMonitor.

http_requests_total and http_request_duration_seconds share their names, labels
and buckets with the backend and Injecto, so one dashboard query shape works
across all three services.
"""

import os
import threading
import time

from fastapi import Request
from prometheus_client import Counter, Histogram, disable_created_metrics, start_http_server
from starlette.routing import Match

from .logs import logger

DEFAULT_METRICS_PORT = 9090

# The client library also exports a "<name>_created" timestamp series per label
# set. The Node backend does not, and nothing reads them, so they are switched
# off to keep the three services' output identical.
disable_created_metrics()

# Under uvicorn's h11 parser any token is a valid method, so an unbounded
# method label would let a client mint new series; anything else is "other".
KNOWN_METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"})

# Liveness and readiness probes hit /health every few seconds per pod; counting
# them would dominate the request rate and hide real traffic.
EXCLUDED_PATHS = frozenset({"/health"})

# prometheus_client appends "_total" to counter names on the wire, so this is
# published as http_requests_total. Adding the suffix here would double it.
http_requests_total = Counter(
    "http_requests",
    "HTTP requests handled, by method, matched route and status code",
    ["method", "route", "status_code"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds, by method, matched route and status code",
    ["method", "route", "status_code"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60),
)


async def metrics_middleware(request: Request, call_next):
    """Record RED metrics for every request except probes.

    The route label is the matched route PATTERN, never the raw path, so a
    parameterised route cannot explode metric cardinality. Requests no route
    matched (404s, trailing-slash redirects) share the single label "unmatched".
    """
    if request.url.path in EXCLUDED_PATHS:
        return await call_next(request)

    start = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        # An exception escaping the app still ends as a 500 for the caller, so
        # it is counted as one rather than dropped.
        labels = {
            "method": request.method if request.method in KNOWN_METHODS else "other",
            "route": _route_label(request),
            "status_code": str(status_code),
        }
        http_requests_total.labels(**labels).inc()
        http_request_duration_seconds.labels(**labels).observe(time.perf_counter() - start)


def _route_label(request: Request) -> str:
    """The matched route's path pattern, or "unmatched".

    FastAPI records the matched route in the scope for its own API routes only;
    the built-in Starlette routes (/docs, /openapi.json) are matched here
    instead, so they are not mislabelled as unmatched.
    """
    route = request.scope.get("route")
    if route is None:
        for candidate in request.app.router.routes:
            match, _ = candidate.matches(request.scope)
            if match == Match.FULL:
                route = candidate
                break
    return getattr(route, "path", None) or "unmatched"


# start_http_server() binds a real socket, so a second call in the same process
# fails with EADDRINUSE. Starting is therefore idempotent per process.
_server = None
_lock = threading.Lock()


def start_metrics_server(port: int = None):
    """Start the metrics listener on its own port.

    Returns the server, or None when metrics are disabled, METRICS_PORT is not a
    valid port, or the port could not be bound. Never raises: a failure to expose metrics must not stop StateCraft
    from serving traffic.
    """
    global _server

    if os.getenv("METRICS_ENABLED", "true").lower() == "false":
        logger.info("Metrics server disabled via METRICS_ENABLED=false")
        return None

    with _lock:
        if _server is not None:
            return _server

        if port is None:
            raw_port = os.getenv("METRICS_PORT", str(DEFAULT_METRICS_PORT))
            if not raw_port.isdigit() or int(raw_port) > 65535:
                logger.error(f"Metrics server not started: METRICS_PORT {raw_port!r} is not a valid port")
                return None
            port = int(raw_port)

        try:
            _server, _ = start_http_server(port)
        except OSError as exc:
            logger.error(f"Failed to start metrics server on port {port}: {exc}")
            return None

        logger.info(f"Prometheus metrics available on port {_server.server_port} at /metrics")
        return _server


def stop_metrics_server() -> None:
    """Shut the metrics listener down (used by tests)."""
    global _server

    with _lock:
        if _server is not None:
            _server.shutdown()
            _server.server_close()
            _server = None
