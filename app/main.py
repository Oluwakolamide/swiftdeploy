"""
SwiftDeploy API Service — Stage 4B
Adds Prometheus /metrics endpoint alongside stable/canary/chaos logic.
"""

import os
import time
import random
import threading

from flask import Flask, request, jsonify, make_response, Response
from prometheus_client import (
    Counter, Histogram, Gauge,
    generate_latest, CONTENT_TYPE_LATEST,
)

app = Flask(__name__)

# ── Runtime constants ──────────────────────────────────────────────────────
START_TIME  = time.time()
MODE        = os.environ.get("MODE", "stable")
VERSION     = os.environ.get("APP_VERSION", "1.0.0")
PORT        = int(os.environ.get("APP_PORT", 3000))

# ── Prometheus metrics ─────────────────────────────────────────────────────
REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status_code"],
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["method", "path"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)
APP_UPTIME   = Gauge("app_uptime_seconds",  "Seconds since process start")
APP_MODE     = Gauge("app_mode",            "Deployment mode: 0=stable 1=canary")
CHAOS_ACTIVE = Gauge("chaos_active",        "Active chaos: 0=none 1=slow 2=error")

# Initialise static gauges
APP_MODE.set(1 if MODE == "canary" else 0)
CHAOS_ACTIVE.set(0)

# ── Chaos state ────────────────────────────────────────────────────────────
_chaos_lock  = threading.Lock()
_chaos_state = {"mode": None, "duration": None, "rate": None}


# ── Helpers ────────────────────────────────────────────────────────────────
def stamped_response(data, status=200):
    resp = make_response(jsonify(data), status)
    resp.headers["Content-Type"] = "application/json"
    if MODE == "canary":
        resp.headers["X-Mode"] = "canary"
    return resp


def _update_chaos_gauge():
    with _chaos_lock:
        m = _chaos_state["mode"]
    if m == "slow":
        CHAOS_ACTIVE.set(1)
    elif m == "error":
        CHAOS_ACTIVE.set(2)
    else:
        CHAOS_ACTIVE.set(0)


# ── Instrumentation middleware ─────────────────────────────────────────────
@app.before_request
def _before():
    request._start = time.perf_counter()
    APP_UPTIME.set(time.time() - START_TIME)

    # Apply chaos (canary only)
    if MODE != "canary":
        return
    with _chaos_lock:
        state = dict(_chaos_state)
    if state["mode"] == "slow" and state["duration"]:
        time.sleep(state["duration"])
    elif state["mode"] == "error" and state["rate"]:
        if random.random() < state["rate"]:
            return stamped_response({"error": "chaos-induced failure"}, 500)


@app.after_request
def _after(resp):
    if hasattr(request, "_start"):
        elapsed = time.perf_counter() - request._start
        path = request.path
        REQUEST_COUNT.labels(
            method=request.method,
            path=path,
            status_code=str(resp.status_code),
        ).inc()
        REQUEST_LATENCY.labels(method=request.method, path=path).observe(elapsed)
    return resp


# ── Routes ─────────────────────────────────────────────────────────────────
@app.get("/")
def index():
    return stamped_response({
        "message": f"Welcome to SwiftDeploy API — running in {MODE} mode",
        "mode":    MODE,
        "version": VERSION,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })


@app.get("/healthz")
def healthz():
    return stamped_response({
        "status": "ok",
        "uptime": round(time.time() - START_TIME, 2),
    })


@app.get("/metrics")
def metrics():
    APP_UPTIME.set(time.time() - START_TIME)
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


@app.post("/chaos")
def chaos():
    if MODE != "canary":
        return stamped_response(
            {"error": "chaos endpoint only available in canary mode"}, 403
        )

    body = request.get_json(silent=True)
    if not body or "mode" not in body:
        return stamped_response({"error": "invalid request body"}, 400)

    chaos_mode = body["mode"]
    with _chaos_lock:
        if chaos_mode == "slow":
            dur = body.get("duration", 5)
            if not isinstance(dur, (int, float)) or dur < 0:
                return stamped_response({"error": "invalid duration"}, 400)
            _chaos_state.update({"mode": "slow", "duration": dur, "rate": None})
        elif chaos_mode == "error":
            rate = body.get("rate", 0.5)
            if not isinstance(rate, (int, float)) or not 0 <= rate <= 1:
                return stamped_response({"error": "rate must be 0.0–1.0"}, 400)
            _chaos_state.update({"mode": "error", "rate": rate, "duration": None})
        elif chaos_mode == "recover":
            _chaos_state.update({"mode": None, "duration": None, "rate": None})
        else:
            return stamped_response({"error": f"unknown chaos mode: {chaos_mode!r}"}, 400)
        snapshot = dict(_chaos_state)

    _update_chaos_gauge()
    return stamped_response({"status": "chaos activated", "config": body, "active": snapshot})


# ── Entry point ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, threaded=True)
