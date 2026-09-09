"""
Local process runner for the nonce-forge task (no container engine required).

Runs the identical service code the image uses, on 127.0.0.1:8090. Uses 8090
rather than 8080/8081/8000/3000/etc specifically because those are extremely
common defaults for other local dev tooling (other frameworks' dev servers,
proxies, etc.) -- a port collision with something unrelated already running on
a developer's machine is a real, previously-hit failure mode, not a
hypothetical. 8090 keeps this well clear of edge-pivot's 8080 too. Exposes
`LocalStack`, the context manager the Crucible harness uses for
`environment.local_runner` in task.yaml.
"""
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import urllib.request

TASK_DIR = pathlib.Path(__file__).resolve().parent
SEED = os.environ.get("CRUCIBLE_SEED", "crucible-default")
EDGE_URL = "http://127.0.0.1:8090"


def _wait_healthy(url, proc, label, timeout=20.0):
    """Poll url/healthz until OUR service responds, or fail fast (not after
    the full timeout) the moment the process exits, surfacing its captured
    output -- a silently-swallowed startup crash (e.g. a missing dependency)
    used to look identical to a slow machine for the whole timeout window.

    Checks the exact response body ("ok"), not just HTTP 200: on a dev
    machine, some other already-running local server can be squatting the
    same port (seen in practice -- an unrelated SPA dev server answering
    every path, including /healthz, with 200). A bare status check would
    misreport that as healthy and then fail confusingly deep into the actual
    test; checking the literal body this app returns catches a port
    collision with anything else immediately, on any machine."""
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        if proc.poll() is not None:
            proc._out_fh.seek(0)
            output = proc._out_fh.read()
            raise RuntimeError(
                f"{label} process exited early (code {proc.returncode}) "
                f"before becoming healthy. Its output:\n{'-'*60}\n"
                f"{output or '(no output captured)'}\n{'-'*60}")
        try:
            with urllib.request.urlopen(url + "/healthz", timeout=2) as resp:
                body = resp.read(16).decode("utf-8", "replace").strip()
                if resp.status == 200 and body == "ok":
                    return True
                last = RuntimeError(
                    f"port {url} answered but not with this service "
                    f"(got status={resp.status} body={body!r} -- likely "
                    f"another local server already using this port)")
        except Exception as exc:  # noqa: BLE001
            last = exc
        time.sleep(0.25)
    proc._out_fh.seek(0)
    output = proc._out_fh.read()
    raise RuntimeError(
        f"{label} at {url} did not become healthy in {timeout}s: {last}\n"
        f"Captured output so far:\n{'-'*60}\n{output or '(no output captured)'}\n{'-'*60}")


class LocalStack:
    def __init__(self, python=None):
        self.python = python or sys.executable
        self.procs = []

    def __enter__(self):
        env = dict(os.environ, CRUCIBLE_SEED=SEED, PORT="8090")
        out_fh = tempfile.TemporaryFile(mode="w+")
        print("starting attest ...")
        proc = subprocess.Popen(
            [self.python, str(TASK_DIR / "services" / "attest" / "app.py")],
            env=env, stdout=out_fh, stderr=subprocess.STDOUT)
        proc._out_fh = out_fh
        self.procs.append(proc)
        _wait_healthy(EDGE_URL, proc, "attest")
        print("service healthy.")
        return {"edge": EDGE_URL}

    def __exit__(self, *exc):
        for p in self.procs:
            p.terminate()
        for p in self.procs:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
        for p in self.procs:
            p._out_fh.close()
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
