"""
SwiftDeploy API Service
Supports stable and canary modes via MODE environment variable.
"""

import os
import time
import random
import threading
from flask import Flask, request, jsonify, make_response, g

app = Flask(__name__)

# ── Runtime state ──────────────────────────────────────────────────────────
START_TIME  = time.time()
MODE        = os.environ.get("MODE", "stable")
VERSION     = os.environ.get("APP_VERSION", "1.0.0")
PORT        = int(os.environ.get("APP_PORT", 3000))

_chaos_lock  = threading.Lock()
_chaos_state = {"mode": None, "duration": None, "rate": None}


# ── Helpers ────────────────────────────────────────────────────────────────
def stamped_response(data, status=200):
    """Build a JSON response, injecting X-Mode header when in canary mode."""
    resp = make_response(jsonify(data), status)
    resp.headers["Content-Type"] = "application/json"
    if MODE == "canary":
        resp.headers["X-Mode"] = "canary"
    return resp


# ── Chaos middleware ───────────────────────────────────────────────────────
@app.before_request
def apply_chaos():
    """Apply active chaos effects to all incoming requests (canary only)."""
    if MODE != "canary":
        return

    with _chaos_lock:
        state = dict(_chaos_state)

    if state["mode"] == "slow" and state["duration"]:
        time.sleep(state["duration"])

    elif state["mode"] == "error" and state["rate"]:
        if random.random() < state["rate"]:
            return stamped_response(
                {"error": "chaos-induced failure", "chaos": "error"}, 500
            )


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
    uptime = round(time.time() - START_TIME, 2)
    return stamped_response({"status": "ok", "uptime": uptime})


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
            duration = body.get("duration", 5)
            if not isinstance(duration, (int, float)) or duration < 0:
                return stamped_response({"error": "invalid duration"}, 400)
            _chaos_state.update({"mode": "slow", "duration": duration, "rate": None})

        elif chaos_mode == "error":
            rate = body.get("rate", 0.5)
            if not isinstance(rate, (int, float)) or not (0 <= rate <= 1):
                return stamped_response({"error": "rate must be 0.0–1.0"}, 400)
            _chaos_state.update({"mode": "error", "rate": rate, "duration": None})

        elif chaos_mode == "recover":
            _chaos_state.update({"mode": None, "duration": None, "rate": None})

        else:
            return stamped_response(
                {"error": f"unknown chaos mode: {chaos_mode!r}"}, 400
            )

        snapshot = dict(_chaos_state)

    return stamped_response({
        "status": "chaos activated",
        "config": body,
        "active": snapshot,
    })


# ── Entry point ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Development only — production uses gunicorn
    app.run(host="0.0.0.0", port=PORT, threaded=True)
