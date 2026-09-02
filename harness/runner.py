"""
Crucible task environment runner.

Brings a task's environment up and down and waits for health, in one of two
modes declared by the task manifest:

  - local   : import a task-provided context manager (e.g. run_local:LocalStack)
              that launches the services as local processes. No container engine
              needed; used for fast calibration and for machines without Docker.
  - compose : run `<provider> compose -f <file> up -d --build` against a real
              container engine (Docker or Podman), wait for the edge URL to be
              healthy, and tear down on exit. This is the shipped, reproducible
              path.

Both yield a dict of service URLs (at minimum {"edge": <url>}).
"""
import contextlib
import importlib.util
import os
import pathlib
import shutil
import subprocess
import sys
import time
import urllib.request

import yaml


def load_manifest(task_dir):
    task_dir = pathlib.Path(task_dir)
    with (task_dir / "task.yaml").open(encoding="utf-8") as fh:
        manifest = yaml.safe_load(fh)
    manifest["_dir"] = task_dir
    return manifest


def import_from_task(task_dir, spec):
    """Import `attr` from `module` where spec is 'module:attr' relative to task_dir."""
    module_name, _, attr = spec.partition(":")
    path = pathlib.Path(task_dir) / f"{module_name}.py"
    mod_spec = importlib.util.spec_from_file_location(
        f"crucible_task_{module_name}", path)
    module = importlib.util.module_from_spec(mod_spec)
    sys.modules[mod_spec.name] = module
    mod_spec.loader.exec_module(module)
    return getattr(module, attr) if attr else module


def wait_healthy(url, timeout=90.0):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:
                if resp.status == 200:
                    return True
        except Exception as exc:  # noqa: BLE001
            last = exc
        time.sleep(0.5)
    raise RuntimeError(f"{url} did not become healthy in {timeout}s: {last}")


def _compose_provider():
    """Return the compose command as a list, preferring Docker then Podman."""
    override = os.environ.get("CRUCIBLE_COMPOSE")
    if override:
        return override.split()
    if shutil.which("docker"):
        return ["docker", "compose"]
    podman = shutil.which("podman")
    if not podman:
        # common Windows install location when not on PATH
        cand = pathlib.Path(os.environ.get("LOCALAPPDATA", "")) \
            / "Programs" / "Podman" / "podman.exe"
        if cand.exists():
            podman = str(cand)
    if podman:
        return [podman, "compose"]
    raise RuntimeError("no compose provider found (need docker or podman)")


@contextlib.contextmanager
def task_env(manifest, mode="local"):
    env_cfg = manifest.get("environment", {})
    task_dir = manifest["_dir"]

    if mode == "local":
        runner_spec = env_cfg["local_runner"]
        stack_cls = import_from_task(task_dir, runner_spec)
        with stack_cls() as urls:
            yield urls
        return

    if mode == "compose":
        compose_file = task_dir / env_cfg["compose"]
        edge_url = env_cfg["edge_url"]
        provider = _compose_provider()
        up = provider + ["-f", str(compose_file), "up", "-d", "--build"]
        subprocess.run(up, check=True)
        try:
            wait_healthy(edge_url.rstrip("/") + "/healthz")
            yield {"edge": edge_url}
        finally:
            subprocess.run(provider + ["-f", str(compose_file), "down", "-v"],
                           check=False)
        return

    raise ValueError(f"unknown environment mode: {mode}")
