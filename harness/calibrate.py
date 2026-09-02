"""
Crucible calibration engine (task-agnostic).

Given a task manifest, it measures the two things the acceptance criteria care
about, against a freshly launched environment:

  1. Reference reliability : run the task's solver repeatedly; a run counts as a
     success iff the solver exits 0 AND the grader marks the resulting transcript
     solved. Records wall-clock and turn count.
  2. Difficulty band       : drive the task's stochastic agent policy against the
     live service under the turn budget, for one or more skill profiles.

Writes report.json + report.md into the task directory. Nothing here is specific
to any challenge; a task supplies its solver, agent policy, and rubric.
"""
import json
import pathlib
import statistics
import subprocess
import sys
import tempfile
import time

import yaml

from harness import grader
from harness.runner import import_from_task, task_env

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load_rubric(manifest):
    with (manifest["_dir"] / manifest["rubric"]).open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def reliability(manifest, base, runs):
    rubric = _load_rubric(manifest)
    solver = manifest["_dir"] / manifest["solver"]["entry"]
    env = dict(**_subprocess_env())
    successes, times, turns = 0, [], []
    for _ in range(runs):
        with tempfile.NamedTemporaryFile("r", suffix=".json", delete=False) as tf:
            tpath = tf.name
        t0 = time.time()
        proc = subprocess.run(
            [sys.executable, str(solver), "--base", base,
             "--transcript", tpath, "--quiet"],
            capture_output=True, text=True, env=env, cwd=str(REPO_ROOT))
        dt = time.time() - t0
        ok = proc.returncode == 0
        if ok:
            try:
                with open(tpath, encoding="utf-8") as fh:
                    transcript = json.load(fh)
                result = grader.grade(rubric, transcript)
                ok = result["solved"]
                if ok:
                    turns.append(len(transcript.get("turns", [])))
            except Exception:  # noqa: BLE001
                ok = False
        if ok:
            successes += 1
            times.append(dt)
        pathlib.Path(tpath).unlink(missing_ok=True)
    return {
        "runs": runs, "successes": successes,
        "reliability": round(successes / runs, 4) if runs else 0.0,
        "median_solve_s": round(statistics.median(times), 3) if times else None,
        "max_solve_s": round(max(times), 3) if times else None,
        "solve_turns": turns[0] if turns else None,
    }


def _subprocess_env():
    import os
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    return env


def band(run_rollout, base, profile, budget, rollouts, base_seed=1000):
    solved, turn_counts = 0, []
    for i in range(rollouts):
        res = run_rollout(base, profile, budget=budget, seed=base_seed + i)
        if res["solved"]:
            solved += 1
            turn_counts.append(res["turns"])
    return {
        "profile": profile["name"], "rollouts": rollouts, "solved": solved,
        "solve_rate": round(solved / rollouts, 4) if rollouts else 0.0,
        "median_turns_on_solve": (sorted(turn_counts)[len(turn_counts) // 2]
                                  if turn_counts else None),
    }


def calibrate(task_dir, mode="local", reliability_runs=16, rollouts=100):
    from harness.runner import load_manifest
    manifest = load_manifest(task_dir)
    cal = manifest.get("calibration", {})
    budget = cal.get("turn_budget", 16)

    run_rollout = import_from_task(task_dir, manifest["agent"]["entry"] + ":run_rollout")
    profiles_obj = import_from_task(task_dir, manifest["agent"]["entry"] + ":PROFILES")

    with task_env(manifest, mode=mode) as urls:
        base = urls["edge"]
        rel = reliability(manifest, base, reliability_runs)
        bands = [band(run_rollout, base, p, budget, rollouts)
                 for p in profiles_obj.values()]

    report = {"task_id": manifest["id"], "mode": mode, "turn_budget": budget,
              "reliability": rel, "bands": bands,
              "targets": cal.get("targets", {})}
    _write_reports(manifest, report)
    return report


def _write_reports(manifest, report):
    task_dir = manifest["_dir"]
    (task_dir / "report.json").write_text(json.dumps(report, indent=2),
                                          encoding="utf-8")

    rel, bands = report["reliability"], report["bands"]
    L = [f"# Calibration Report — {report['task_id']}", ""]
    L.append(f"Environment mode: **{report['mode']}**   turn budget: "
             f"**{report['turn_budget']}**   (regenerate: "
             f"`python -m harness.cli calibrate {task_dir.name}`)\n")
    L.append("## Reference-solution reliability\n")
    L.append(f"- Successes: **{rel['successes']}/{rel['runs']}** "
             f"(reliability {rel['reliability']*100:.1f}%)")
    L.append(f"- Reference solve turns: **{rel['solve_turns']}**")
    L.append(f"- Median wall-clock: **{rel['median_solve_s']} s**, "
             f"max **{rel['max_solve_s']} s**\n")
    L.append("## Difficulty band (live agent)\n")
    L.append("| profile | rollouts | solved | solve rate | median turns |")
    L.append("|---|---|---|---|---|")
    for b in bands:
        L.append(f"| {b['profile']} | {b['rollouts']} | {b['solved']} | "
                 f"{b['solve_rate']*100:.1f}% | {b['median_turns_on_solve']} |")
    (task_dir / "report.md").write_text("\n".join(L) + "\n", encoding="utf-8")
