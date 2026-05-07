#!/usr/bin/env sh
set -eu

echo "[preflight] Checking host connectivity to PyPI..."
if ! curl -fsS --max-time 8 https://pypi.org/simple/flask/ >/dev/null; then
  echo "[preflight] ERROR: Host cannot reach pypi.org. Check your internet connection or firewall."
  exit 1
fi

echo "[preflight] Checking Docker container DNS/network path to PyPI..."
if ! docker run --rm --pull never python:3.12-alpine sh -c "python -m pip --disable-pip-version-check index versions Flask >/dev/null" >/dev/null 2>&1; then
  cat <<'EOF'
[preflight] ERROR: Docker cannot reach PyPI from containers.

Likely causes:
- Docker DNS misconfiguration
- Firewall rules blocking container egress/NAT

Quick checks:
1) Ensure /etc/docker/daemon.json includes a working DNS list, for example:
   "dns": ["8.8.8.8", "1.1.1.1"]
2) Restart Docker:
   sudo systemctl restart docker
3) Re-run this preflight.
EOF
  exit 1
fi

echo "[preflight] OK: Docker can resolve and reach PyPI."