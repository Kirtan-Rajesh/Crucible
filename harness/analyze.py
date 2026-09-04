"""
Crucible reward signal-quality analysis.

Runs stochastic-agent rollouts and reports whether the staged reward is actually
a *good training signal*, not just a pass/fail label:

  - per-stage reach frequency (is every checkpoint exercised?)
  - distribution of final scores (is there a spread, or is it bimodal 0/max?)
  - dense-signal-on-failure: what fraction of FAILED rollouts still earn partial
    credit, and how much (this is what lets RL learn from non-solving rollouts)
  - monotonicity: cumulative reward never decreases within a rollout (verified,
    not assumed)

Writes `reward_analysis.md` into the task dir.

Usage:
    python -m harness.cli analyze <task> [--rollouts N] [--mode local|compose]
"""
import statistics

import yaml

from harness import grader
from harness.runner import import_from_task, load_manifest, task_env
from harness.rollout import record_rollout


def _load_rubric(manifest):
    with (manifest["_dir"] / manifest["rubric"]).open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def analyze(task_dir, rollouts=120, mode="local", seed_base=9000):
    manifest = load_manifest(task_dir)
    rubric = _load_rubric(manifest)
    stages = sorted(rubric["stages"], key=lambda s: s["order"])
    max_score = sum(s["weight"] for s in stages)
    budget = manifest.get("calibration", {}).get("turn_budget", 16)

    agent_mod = import_from_task(task_dir, manifest["agent"]["entry"] + ":")
    profiles = list(import_from_task(task_dir, manifest["agent"]["entry"] + ":PROFILES").values())

    stage_reached = {s["id"]: 0 for s in stages}
    finals, monotonic_ok, n = [], True, 0
    failed_scores = []

    with task_env(manifest, mode=mode) as urls:
        base = urls["edge"]
        for i in range(rollouts):
            profile = profiles[i % len(profiles)]
            _, transcript = record_rollout(agent_mod, base, profile, budget,
                                          seed_base + i)
            turns = transcript["turns"]
            graded = grader.grade(rubric, {"turns": turns})
            n += 1
            finals.append(graded["total_score"])
            for s in graded["stages"]:
                if s["credited"]:
                    stage_reached[s["id"]] += 1
            if not graded["solved"]:
                failed_scores.append(graded["total_score"])
            # monotonicity: cumulative score over prefixes never decreases
            prev = 0
            for t in range(1, len(turns) + 1):
                cur = grader.grade(rubric, {"turns": turns[:t]})["total_score"]
                if cur < prev:
                    monotonic_ok = False
                prev = cur

    solved = sum(1 for f in finals if f == max_score)
    failed_with_credit = sum(1 for s in failed_scores if s > 0)
    report = {
        "rollouts": n, "max_score": max_score,
        "solved": solved, "solve_rate": round(solved / n, 4) if n else 0,
        "mean_score": round(statistics.mean(finals), 2) if finals else 0,
        "stage_reach": {sid: round(c / n, 4) for sid, c in stage_reached.items()},
        "failed": len(failed_scores),
        "failed_with_partial_credit": failed_with_credit,
        "failed_partial_credit_rate": (round(failed_with_credit / len(failed_scores), 4)
                                       if failed_scores else 0.0),
        "mean_partial_credit_on_failure": (round(statistics.mean(failed_scores), 2)
                                           if failed_scores else 0.0),
        "monotonic": monotonic_ok,
        "score_histogram": {str(v): finals.count(v) for v in sorted(set(finals))},
    }
    _write_md(manifest, stages, report)
    return report


def _write_md(manifest, stages, r):
    reach = "\n".join(
        f"| `{s['id']}` | {s['weight']} | {r['stage_reach'][s['id']]*100:.0f}% |"
        for s in stages)
    hist = "\n".join(f"| {k} | {v} |" for k, v in r["score_histogram"].items())
    (manifest["_dir"] / "reward_analysis.md").write_text(f"""# Reward signal-quality analysis — {manifest['id']}

{r['rollouts']} stochastic-agent rollouts (competent + naive), graded by the
rubric. Regenerate: `python -m harness.cli analyze {manifest['id']}`.

- Solve rate: **{r['solve_rate']*100:.1f}%**   mean score **{r['mean_score']}/{r['max_score']}**
- Reward is monotonic within every rollout: **{'VERIFIED' if r['monotonic'] else 'FAILED'}**

## Every checkpoint is exercised (per-stage reach frequency)

| stage | weight | reached |
|---|---|---|
{reach}

A stage reached by ~0% or ~100% of rollouts carries little training signal; a
spread across stages means the reward discriminates partial progress.

## Dense signal on failed rollouts

The point of staged rewards is that a *failed* attempt still teaches something.

- Failed rollouts: **{r['failed']}**
- …of which earned partial credit (> 0): **{r['failed_with_partial_credit']}**
  (**{r['failed_partial_credit_rate']*100:.1f}%**)
- Mean score among failed rollouts: **{r['mean_partial_credit_on_failure']}/{r['max_score']}**

A high partial-credit rate on failures is exactly what makes this trainable with
RL rather than a sparse pass/fail label.

## Final-score distribution

| score (of {r['max_score']}) | rollouts |
|---|---|
{hist}
""", encoding="utf-8")
