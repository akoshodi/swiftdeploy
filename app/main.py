import os
import random
import threading
import time
from datetime import datetime, timezone

from flask import Flask, jsonify, request

app = Flask(__name__)

START_TIME = time.monotonic()
LOCK = threading.Lock()
CHAOS_STATE = {
    "mode": None,
    "duration": 0,
    "rate": 0.0,
}


def current_mode() -> str:
    return os.getenv("MODE", "stable").strip().lower() or "stable"


def app_version() -> str:
    return os.getenv("APP_VERSION", "1.0.0")


def is_canary() -> bool:
    return current_mode() == "canary"


@app.before_request
def apply_chaos_behavior():
    if not is_canary():
        return None

    if request.path == "/chaos":
        return None

    with LOCK:
        chaos_mode = CHAOS_STATE.get("mode")
        duration = int(CHAOS_STATE.get("duration") or 0)
        rate = float(CHAOS_STATE.get("rate") or 0.0)

    if chaos_mode == "slow" and duration > 0:
        time.sleep(duration)

    if chaos_mode == "error" and rate > 0 and random.random() < rate:
        return jsonify({
            "status": "error",
            "message": "Injected chaos error",
            "mode": current_mode(),
            "version": app_version(),
        }), 500

    return None


@app.after_request
def add_canary_header(response):
    if is_canary():
        response.headers["X-Mode"] = "canary"
    return response


@app.get("/")
def index():
    return jsonify({
        "message": "Welcome to SwiftDeploy API",
        "mode": current_mode(),
        "version": app_version(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


@app.get("/healthz")
def healthz():
    uptime = int(time.monotonic() - START_TIME)
    return jsonify({
        "status": "ok",
        "mode": current_mode(),
        "version": app_version(),
        "uptime_seconds": uptime,
    })


@app.post("/chaos")
def chaos():
    if not is_canary():
        return jsonify({
            "status": "rejected",
            "message": "Chaos endpoint is only active in canary mode",
        }), 403

    body = request.get_json(silent=True) or {}
    requested_mode = str(body.get("mode", "")).strip().lower()

    if requested_mode == "recover":
        with LOCK:
            CHAOS_STATE["mode"] = None
            CHAOS_STATE["duration"] = 0
            CHAOS_STATE["rate"] = 0.0
        return jsonify({"status": "ok", "chaos": "recovered"})

    if requested_mode == "slow":
        duration = int(body.get("duration", 0))
        if duration <= 0:
            return jsonify({"status": "error", "message": "duration must be a positive integer"}), 400

        with LOCK:
            CHAOS_STATE["mode"] = "slow"
            CHAOS_STATE["duration"] = duration
            CHAOS_STATE["rate"] = 0.0

        return jsonify({"status": "ok", "chaos": {"mode": "slow", "duration": duration}})

    if requested_mode == "error":
        rate = float(body.get("rate", 0))
        if rate <= 0 or rate > 1:
            return jsonify({"status": "error", "message": "rate must be in (0, 1]"}), 400

        with LOCK:
            CHAOS_STATE["mode"] = "error"
            CHAOS_STATE["duration"] = 0
            CHAOS_STATE["rate"] = rate

        return jsonify({"status": "ok", "chaos": {"mode": "error", "rate": rate}})

    return jsonify({
        "status": "error",
        "message": "invalid chaos mode; expected one of: slow, error, recover",
    }), 400


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("APP_PORT", "3000")))
