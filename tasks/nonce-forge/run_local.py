"""
Local process runner for the nonce-forge task (no container engine required).

Runs the identical service code the image uses, on 127.0.0.1:8080. Exposes
`LocalStack`, the context manager the Crucible harness uses for
`environment.local_runner` in task.yaml.
"""
import os
import pathlib
import subprocess
import sys
import time
import urllib.request

TASK_DIR = pathlib.Path(__file__).resolve().parent
SEED = os.environ.get("CRUCIBLE_SEED", "crucible-default")
EDGE_URL = "http://127.0.0.1:8080"


def _wait_healthy(url, timeout=20.0):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url + "/healthz", timeout=2) as resp:
                if resp.status == 200:
                    return True
        except Exception as exc:  # noqa: BLE001
            last = exc
        time.sleep(0.25)
    raise RuntimeError(f"service at {url} did not become healthy: {last}")


class LocalStack:
    def __init__(self, python=None):
        self.python = python or sys.executable
        self.procs = []

    def __enter__(self):
        env = dict(os.environ, CRUCIBLE_SEED=SEED, PORT="8080")
        self.procs.append(subprocess.Popen(
            [self.python, str(TASK_DIR / "services" / "attest" / "app.py")],
            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        _wait_healthy(EDGE_URL)
        return {"edge": EDGE_URL}

    def __exit__(self, *exc):
        for p in self.procs:
            p.terminate()
        for p in self.procs:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
        return False


if __name__ == "__main__":
    with LocalStack():
        print(f"attest: {EDGE_URL}")
        print("Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nstopping...")
