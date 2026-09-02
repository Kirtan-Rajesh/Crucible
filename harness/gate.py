"""
Crucible acceptance gate.

Turns the calibration report into an enforced PASS/FAIL against the task's
declared targets (the assignment's numeric acceptance criteria). This is what
makes calibration a contract rather than a claim: `gate` exits non-zero if any
criterion is missed, so it can run in CI.

Targets (from task.yaml `calibration.targets`):
    reliability_min      : reference reliability floor            (e.g. 0.875 = 14/16)
    solve_time_max_s     : reference wall-clock ceiling
    competent_solve_min  : competent-profile solve-rate floor     (e.g. 0.60)
    max_fail             : competent-profile failure ceiling      (e.g. 0.80)
    min_stages           : minimum gradable reward stages
"""
import json
import pathlib
import sys

import yaml


def _rubric_stage_count(task_dir, manifest):
    with (task_dir / manifest["rubric"]).open(encoding="utf-8") as fh:
        return len(yaml.safe_load(fh)["stages"])


def evaluate(task_dir):
    task_dir = pathlib.Path(task_dir)
    with (task_dir / "task.yaml").open(encoding="utf-8") as fh:
        manifest = yaml.safe_load(fh)
    report = json.loads((task_dir / "report.json").read_text(encoding="utf-8"))
    targets = manifest.get("calibration", {}).get("targets", {})

    rel = report["reliability"]
    competent = next((b for b in report["bands"] if b["profile"] == "competent"),
                     report["bands"][0] if report["bands"] else {"solve_rate": 0})
    n_stages = _rubric_stage_count(task_dir, manifest)

    checks = []

    def add(name, measured, ok, target_desc):
        checks.append({"criterion": name, "measured": measured,
                       "target": target_desc, "pass": bool(ok)})

    if "reliability_min" in targets:
        add("reference reliability", f"{rel['reliability']*100:.1f}%",
            rel["reliability"] >= targets["reliability_min"],
            f">= {targets['reliability_min']*100:.1f}%")
    if "solve_time_max_s" in targets:
        mx = rel["max_solve_s"] or 0
        add("reference solve time", f"{mx}s",
            mx < targets["solve_time_max_s"], f"< {targets['solve_time_max_s']}s")
    if "competent_solve_min" in targets:
        add("competent solve rate", f"{competent['solve_rate']*100:.1f}%",
            competent["solve_rate"] >= targets["competent_solve_min"],
            f">= {targets['competent_solve_min']*100:.0f}%")
    if "max_fail" in targets:
        fail = 1 - competent["solve_rate"]
        add("competent failure rate", f"{fail*100:.1f}%",
            fail < targets["max_fail"], f"< {targets['max_fail']*100:.0f}%")
    if "min_stages" in targets:
        add("gradable reward stages", str(n_stages),
            n_stages >= targets["min_stages"], f">= {targets['min_stages']}")

    return {"task_id": report["task_id"], "checks": checks,
            "passed": all(c["pass"] for c in checks)}


def print_gate(result):
    print(f"acceptance gate: {result['task_id']}")
    print("-" * 74)
    print(f"{'criterion':<26}{'measured':>12}{'target':>18}{'verdict':>10}")
    for c in result["checks"]:
        print(f"{c['criterion']:<26}{c['measured']:>12}{c['target']:>18}"
              f"{'PASS' if c['pass'] else 'FAIL':>10}")
    print("-" * 74)
    print("RESULT:", "PASS" if result["passed"] else "FAIL")


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("task_dir")
    args = ap.parse_args(argv)
    result = evaluate(args.task_dir)
    print_gate(result)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
