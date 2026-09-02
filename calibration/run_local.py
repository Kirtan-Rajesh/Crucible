"""
run_local.py — launch the challenge as local processes (no Docker required).

This is an authoring / CI convenience so the *identical* application code can be
exercised on a machine without Docker. It runs the collector on 127.0.0.1:9000
and the edge on 127.0.0.1:8080, and wires the edge's dev host-alias so that the
internal hostname `collector` (used verbatim in the exploit URL) resolves to the
local collector. In the shipped Docker topology this alias is unset and Docker
DNS resolves `collector` natively, so the exploit is byte-for-byte the same.

Usage:
    python calibration/run_local.py            # run until Ctrl+C
    with LocalStack() as urls: ...             # programmatic (see calibrate.py)
"""
import os
import pathlib
import subprocess
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
EDGE_ORIGIN_TOKEN = "edge-origin-2f9c1a7b4e"
JWT_SECRET = "provue-edge-hs256-6d1e9f0a"

EDGE_URL = "http://127.0.0.1:8080"
COLLECTOR_URL = "http://127.0.0.1:9000"


def _wait_healthy(url, timeout=20.0):
    deadline = time.time() + timeout
    last_err = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url + "/healthz", timeout=2) as resp:
                if resp.status == 200:
                    return True
        except Exception as exc:  # noqa: BLE001 - best-effort poll
            last_err = exc
        time.sleep(0.25)
    raise RuntimeError(f"service at {url} did not become healthy: {last_err}")


class LocalStack:
    """Context manager that starts both services and tears them down cleanly."""

    def __init__(self, python=None):
        self.python = python or sys.executable
        self.procs = []

    def __enter__(self):
        collector_env = dict(os.environ, PORT="9000",
                             EDGE_ORIGIN_TOKEN=EDGE_ORIGIN_TOKEN)
        edge_env = dict(
            os.environ,
            PORT="8080",
            EDGE_ORIGIN_TOKEN=EDGE_ORIGIN_TOKEN,
            JWT_SECRET=JWT_SECRET,
            DEV_HOST_ALIASES='{"collector": "127.0.0.1"}',
        )
        self.procs.append(subprocess.Popen(
            [self.python, str(ROOT / "challenge" / "collector" / "app.py")],
            env=collector_env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        ))
        self.procs.append(subprocess.Popen(
            [self.python, str(ROOT / "challenge" / "edge" / "app.py")],
            env=edge_env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        ))
        _wait_healthy(COLLECTOR_URL)
        _wait_healthy(EDGE_URL)
        return {"edge": EDGE_URL, "collector": COLLECTOR_URL}

    def __exit__(self, *exc):
        for proc in self.procs:
            proc.terminate()
        for proc in self.procs:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        return False


if __name__ == "__main__":
    with LocalStack():
        print(f"edge:      {EDGE_URL}")
        print(f"collector: {COLLECTOR_URL} (direct access is 401 without pivot)")
        print("Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nstopping...")
