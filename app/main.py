import json
import os
import random
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

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


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SwiftDeployHandler(BaseHTTPRequestHandler):
    server_version = "SwiftDeployHTTP/1.0"

    def log_message(self, format: str, *args):
        # Keep logs in container stdout for Docker logging collection.
        super().log_message(format, *args)

    def _send_json(self, status_code: int, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if is_canary():
            self.send_header("X-Mode", "canary")
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return {}

        if content_length <= 0:
            return {}

        raw = self.rfile.read(content_length)
        try:
            parsed = json.loads(raw.decode("utf-8"))
            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    def _apply_chaos_behavior(self):
        if not is_canary():
            return None

        if self.path == "/chaos":
            return None

        with LOCK:
            chaos_mode = CHAOS_STATE.get("mode")
            duration = int(CHAOS_STATE.get("duration") or 0)
            rate = float(CHAOS_STATE.get("rate") or 0.0)

        if chaos_mode == "slow" and duration > 0:
            time.sleep(duration)

        if chaos_mode == "error" and rate > 0 and random.random() < rate:
            return {
                "status": 500,
                "payload": {
                    "status": "error",
                    "message": "Injected chaos error",
                    "mode": current_mode(),
                    "version": app_version(),
                },
            }

        return None

    def do_GET(self):
        chaos_result = self._apply_chaos_behavior()
        if chaos_result is not None:
            self._send_json(chaos_result["status"], chaos_result["payload"])
            return

        if self.path == "/":
            self._send_json(
                200,
                {
                    "message": "Welcome to SwiftDeploy API",
                    "mode": current_mode(),
                    "version": app_version(),
                    "timestamp": utc_now_iso(),
                },
            )
            return

        if self.path == "/healthz":
            uptime = int(time.monotonic() - START_TIME)
            self._send_json(
                200,
                {
                    "status": "ok",
                    "mode": current_mode(),
                    "version": app_version(),
                    "uptime_seconds": uptime,
                },
            )
            return

        self._send_json(404, {"status": "error", "message": "Not found"})

    def do_POST(self):
        chaos_result = self._apply_chaos_behavior()
        if chaos_result is not None:
            self._send_json(chaos_result["status"], chaos_result["payload"])
            return

        if self.path != "/chaos":
            self._send_json(404, {"status": "error", "message": "Not found"})
            return

        if not is_canary():
            self._send_json(
                403,
                {
                    "status": "rejected",
                    "message": "Chaos endpoint is only active in canary mode",
                },
            )
            return

        body = self._read_json_body()
        requested_mode = str(body.get("mode", "")).strip().lower()

        if requested_mode == "recover":
            with LOCK:
                CHAOS_STATE["mode"] = None
                CHAOS_STATE["duration"] = 0
                CHAOS_STATE["rate"] = 0.0
            self._send_json(200, {"status": "ok", "chaos": "recovered"})
            return

        if requested_mode == "slow":
            try:
                duration = int(body.get("duration", 0))
            except (TypeError, ValueError):
                duration = 0

            if duration <= 0:
                self._send_json(
                    400,
                    {"status": "error", "message": "duration must be a positive integer"},
                )
                return

            with LOCK:
                CHAOS_STATE["mode"] = "slow"
                CHAOS_STATE["duration"] = duration
                CHAOS_STATE["rate"] = 0.0

            self._send_json(200, {"status": "ok", "chaos": {"mode": "slow", "duration": duration}})
            return

        if requested_mode == "error":
            try:
                rate = float(body.get("rate", 0))
            except (TypeError, ValueError):
                rate = 0.0

            if rate <= 0 or rate > 1:
                self._send_json(400, {"status": "error", "message": "rate must be in (0, 1]"})
                return

            with LOCK:
                CHAOS_STATE["mode"] = "error"
                CHAOS_STATE["duration"] = 0
                CHAOS_STATE["rate"] = rate

            self._send_json(200, {"status": "ok", "chaos": {"mode": "error", "rate": rate}})
            return

        self._send_json(
            400,
            {
                "status": "error",
                "message": "invalid chaos mode; expected one of: slow, error, recover",
            },
        )


def run() -> None:
    host = "0.0.0.0"
    port = int(os.getenv("APP_PORT", "3000"))
    server = ThreadingHTTPServer((host, port), SwiftDeployHandler)
    server.serve_forever()


if __name__ == "__main__":
    run()
