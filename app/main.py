import os
import random
import threading
import time
from datetime import datetime, timezone
from typing import Dict, Tuple

from flask import Flask, jsonify, request

app = Flask(__name__)

START_TIME = time.monotonic()
LOCK = threading.Lock()
CHAOS_STATE = {
    "mode": None,
    "duration": 0,
    "rate": 0.0,
}

LATENCY_BUCKETS = [
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
]
REQUEST_COUNTER: Dict[Tuple[str, str, str], int] = {}
LATENCY_BUCKET_COUNTER: Dict[float, int] = {bucket: 0 for bucket in LATENCY_BUCKETS}
LATENCY_COUNT = 0
LATENCY_SUM = 0.0


def current_mode() -> str:
    return os.getenv("MODE", "stable").strip().lower() or "stable"


def app_version() -> str:
    return os.getenv("APP_VERSION", "1.0.0")


def is_canary() -> bool:
    return current_mode() == "canary"


@app.before_request
def apply_chaos_behavior():
    request.environ["swiftdeploy_start_time"] = time.perf_counter()

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
    method = request.method
    path = request.path
    status_code = str(response.status_code)
    start_time = request.environ.get("swiftdeploy_start_time")
    duration = 0.0
    if isinstance(start_time, (int, float)):
        duration = max(0.0, time.perf_counter() - start_time)

    with LOCK:
        key = (method, path, status_code)
        REQUEST_COUNTER[key] = REQUEST_COUNTER.get(key, 0) + 1

        global LATENCY_COUNT, LATENCY_SUM
        LATENCY_COUNT += 1
        LATENCY_SUM += duration
        for bucket in LATENCY_BUCKETS:
            if duration <= bucket:
                LATENCY_BUCKET_COUNTER[bucket] = LATENCY_BUCKET_COUNTER.get(bucket, 0) + 1
                break

    if is_canary():
        response.headers["X-Mode"] = "canary"
    return response


def chaos_state_value() -> int:
    with LOCK:
        chaos_mode = CHAOS_STATE.get("mode")
    if chaos_mode == "slow":
        return 1
    if chaos_mode == "error":
        return 2
    return 0


def render_prometheus_metrics() -> str:
    lines = []

    lines.append("# HELP http_requests_total Total HTTP requests processed")
    lines.append("# TYPE http_requests_total counter")
    with LOCK:
        req_items = list(REQUEST_COUNTER.items())
    for (method, path, status), count in sorted(req_items):
        lines.append(
            f'http_requests_total{{method="{method}",path="{path}",status_code="{status}"}} {count}'
        )

    lines.append("# HELP http_request_duration_seconds Request latency histogram")
    lines.append("# TYPE http_request_duration_seconds histogram")
    cumulative = 0
    with LOCK:
        bucket_snapshot = {b: LATENCY_BUCKET_COUNTER.get(b, 0) for b in LATENCY_BUCKETS}
        latency_count = LATENCY_COUNT
        latency_sum = LATENCY_SUM
    for bucket in LATENCY_BUCKETS:
        cumulative += bucket_snapshot.get(bucket, 0)
        lines.append(f'http_request_duration_seconds_bucket{{le="{bucket}"}} {cumulative}')
    lines.append(f'http_request_duration_seconds_bucket{{le="+Inf"}} {latency_count}')
    lines.append(f"http_request_duration_seconds_sum {latency_sum}")
    lines.append(f"http_request_duration_seconds_count {latency_count}")

    uptime = time.monotonic() - START_TIME
    mode_value = 1 if is_canary() else 0
    chaos_value = chaos_state_value()

    lines.append("# HELP app_uptime_seconds Process uptime in seconds")
    lines.append("# TYPE app_uptime_seconds gauge")
    lines.append(f"app_uptime_seconds {uptime}")

    lines.append("# HELP app_mode Current mode (0=stable, 1=canary)")
    lines.append("# TYPE app_mode gauge")
    lines.append(f"app_mode {mode_value}")

    lines.append("# HELP chaos_active Active chaos mode (0=none, 1=slow, 2=error)")
    lines.append("# TYPE chaos_active gauge")
    lines.append(f"chaos_active {chaos_value}")

    return "\n".join(lines) + "\n"


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


@app.get("/metrics")
def metrics():
    payload = render_prometheus_metrics()
    return app.response_class(payload, mimetype="text/plain; version=0.0.4; charset=utf-8")


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
