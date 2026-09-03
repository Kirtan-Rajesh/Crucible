"""
Crucible CLI — one entry point for every task operation.

    python -m harness.cli <command> <task> [options]

Commands:
    up        build + run the task environment (containers, foreground)
    down      stop + remove the task environment
    validate  check task.yaml/rubric.yaml against the JSON Schemas
    solve     run the reference solver against the task, then grade the run
    grade     grade an existing transcript:  grade <task> --transcript run.json
    calibrate measure reliability + difficulty band -> report.json / report.md
    gate      check the latest report against the task's acceptance targets
    verify    validate, then run task tests, then calibrate + gate (full local check)

<task> is a task name (resolved under tasks/<name>) or a path to a task dir.
"""
import argparse
import json
import pathlib
import subprocess
import sys
import tempfile

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


def resolve_task(arg):
    p = pathlib.Path(arg)
    if (p / "task.yaml").exists():
        return p
    cand = REPO_ROOT / "tasks" / arg
    if (cand / "task.yaml").exists():
        return cand
    raise SystemExit(f"no task found at '{arg}' or tasks/{arg}")


def _provider():
    from harness.runner import _compose_provider
    return _compose_provider()


def cmd_up(task, args):
    from harness.runner import load_manifest
    m = load_manifest(task)
    compose = task / m["environment"]["compose"]
    return subprocess.run(_provider() + ["-f", str(compose), "up", "--build"]).returncode


def cmd_down(task, args):
    from harness.runner import load_manifest
    m = load_manifest(task)
    compose = task / m["environment"]["compose"]
    return subprocess.run(_provider() + ["-f", str(compose), "down", "-v"]).returncode


def cmd_validate(task, args):
    from harness import validate
    return validate.main([str(task)])


def cmd_grade(task, args):
    from harness import grader
    from harness.runner import load_manifest
    m = load_manifest(task)
    return grader.main(["--rubric", str(task / m["rubric"]),
                        "--transcript", args.transcript])


def cmd_solve(task, args):
    from harness import grader
    from harness.runner import load_manifest, task_env
    import os
    m = load_manifest(task)
    rubric = str(task / m["rubric"])
    solver = task / m["solver"]["entry"]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    with task_env(m, mode=args.mode) as urls:
        tpath = tempfile.NamedTemporaryFile(suffix=".json", delete=False).name
        subprocess.run([sys.executable, str(solver), "--base", urls["edge"],
                        "--transcript", tpath], env=env, cwd=str(REPO_ROOT))
        print()
        grader.main(["--rubric", rubric, "--transcript", tpath])
    return 0


def cmd_calibrate(task, args):
    from harness import calibrate
    report = calibrate.calibrate(task, mode=args.mode,
                                 reliability_runs=args.reliability_runs,
                                 rollouts=args.rollouts,
                                 seed_repeats=args.seed_repeats,
                                 agent_entry=args.agent,
                                 report_name=args.report_name,
                                 measure_reliability=not args.skip_reliability,
                                 budget_override=args.budget)
    print(json.dumps({"reliability": report["reliability"],
                      "bands": report["bands"]}, indent=2))
    return 0


def cmd_gate(task, args):
    from harness import gate
    return gate.main([str(task)])


def cmd_verify(task, args):
    from harness.runner import load_manifest
    import os
    print("== validate ==")
    rc = cmd_validate(task, args)
    if rc != 0:
        return rc
    m = load_manifest(task)
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    print("== running task tests ==")
    for t in m.get("tests", []):
        print(f"-- {t}")
        rc = subprocess.run([sys.executable, str(task / t)],
                            env=env, cwd=str(REPO_ROOT)).returncode
        if rc != 0:
            print(f"TEST FAILED: {t}")
            return rc
    print("== calibrate ==")
    cmd_calibrate(task, args)
    print("== gate ==")
    return cmd_gate(task, args)


COMMANDS = {
    "up": cmd_up, "down": cmd_down, "validate": cmd_validate, "solve": cmd_solve,
    "grade": cmd_grade, "calibrate": cmd_calibrate, "gate": cmd_gate, "verify": cmd_verify,
}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="crucible")
    ap.add_argument("command", choices=COMMANDS)
    ap.add_argument("task")
    ap.add_argument("--mode", choices=["local", "compose"], default="local",
                    help="environment mode for solve/calibrate/verify")
    ap.add_argument("--transcript", help="transcript path for grade")
    ap.add_argument("--reliability-runs", type=int, default=16)
    ap.add_argument("--rollouts", type=int, default=100)
    ap.add_argument("--seed-repeats", type=int, default=1,
                    help="independent seed batches per profile band (variance evidence)")
    ap.add_argument("--agent", default=None,
                    help="override the manifest's agent module (e.g. llm_agent for a real-model measurement)")
    ap.add_argument("--report-name", default="report",
                    help="basename for report.json/report.md (use a distinct name for --agent runs)")
    ap.add_argument("--skip-reliability", action="store_true",
                    help="skip the reference-solver reliability pass (irrelevant when only comparing agent policies)")
    ap.add_argument("--budget", type=int, default=None, help="override calibration.turn_budget")
    args = ap.parse_args(argv)
    task = resolve_task(args.task)
    return COMMANDS[args.command](task, args)


if __name__ == "__main__":
    sys.exit(main())
