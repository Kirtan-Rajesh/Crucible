"""
Local process runner for the edge-pivot task (no container engine required).

Runs the identical service code the images use: collector on 127.0.0.1:9000 and
edge on 127.0.0.1:8080, wiring the edge dev host-alias so the internal hostname
`collector` (used verbatim in the exploit URL) resolves locally. In the shipped
container topology this alias is unset and container DNS resolves `collector`
natively, so the exploit is byte-for-byte the same.

Exposes `LocalStack`, the context manager the Crucible harness uses for
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
COLLECTOR_URL = "http://127.0.0.1:9000"


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
        base = dict(os.environ, CRUCIBLE_SEED=SEED)
        collector_env = dict(base, PORT="9000")
        edge_env = dict(base, PORT="8080",
                        DEV_HOST_ALIASES='{"collector": "127.0.0.1"}')
        self.procs.append(subprocess.Popen(
            [self.python, str(TASK_DIR / "services" / "collector" / "app.py")],
            env=collector_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        self.procs.append(subprocess.Popen(
            [self.python, str(TASK_DIR / "services" / "edge" / "app.py")],
            env=edge_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        _wait_healthy(COLLECTOR_URL)
        _wait_healthy(EDGE_URL)
        return {"edge": EDGE_URL, "collector": COLLECTOR_URL}

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
        print(f"edge:      {EDGE_URL}")
        print(f"collector: {COLLECTOR_URL} (direct access is 401 without the pivot)")
        print("Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nstopping...")
