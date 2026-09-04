"""
Crucible dataset export — turn a task into actual SFT/RL training data.

This is the artifact the harness ultimately exists to produce. For a task it
writes `dataset/`:

  - sft.jsonl : the reference solution rendered as a tool-call trajectory (a
                "golden" behaviour-cloning demonstration), one JSON line.
  - rl.jsonl  : stochastic-agent rollouts, each with per-step DENSE rewards
                derived from the rubric (reward after step t = graded score of
                the transcript prefix up to t) plus the final return. Suitable
                for RL / reward-model training.
  - DATA.md   : the schema and how rewards map to the rubric.

Usage:
    python -m harness.cli export <task> [--rollouts N] [--mode local|compose]
"""
import json
import pathlib

import yaml

from harness import grader
from harness.runner import import_from_task, load_manifest, task_env
from harness.rollout import record_rollout
from harness.transcript import Recorder

FLAG_RE_DEFAULT = r"flag\{[a-z0-9_]{8,}\}"


def _load_rubric(manifest):
    with (manifest["_dir"] / manifest["rubric"]).open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _dense_rewards(rubric, turns):
    """Cumulative and per-step reward over a transcript's prefixes."""
    cum, steps = 0, []
    prev = 0
    for t in range(1, len(turns) + 1):
        cum = grader.grade(rubric, {"turns": turns[:t]})["total_score"]
        steps.append({"t": t, "step_reward": cum - prev, "cumulative_reward": cum})
        prev = cum
    return steps


def _sft_messages(manifest, rubric, transcript, flag):
    budget = manifest.get("calibration", {}).get("turn_budget", 16)
    flag_regex = rubric["meta"].get("flag_regex", FLAG_RE_DEFAULT)
    sys = (f"You are a security agent solving a {manifest['category']} CTF task "
           f"'{manifest['id']}'. Each turn, issue exactly one HTTP request as an "
           f"`http_request` tool call and read the response. You have {budget} "
           f"turns. Goal: recover the flag matching /{flag_regex}/ and report it.")
    messages = [{"role": "system", "content": sys}]
    for i, turn in enumerate(transcript["turns"], start=1):
        req = turn["request"]
        args = {"method": req["method"], "url": req["url"]}
        if req.get("body") is not None:
            args["body"] = req["body"]
        messages.append({
            "role": "assistant", "content": "",
            "tool_calls": [{"id": f"call_{i}", "type": "function",
                            "function": {"name": "http_request",
                                         "arguments": json.dumps(args)}}]})
        resp = turn["response"]
        messages.append({"role": "tool", "tool_call_id": f"call_{i}",
                         "content": f"HTTP {resp['status']}\n{resp.get('text', '')}"})
    messages.append({"role": "assistant", "content": f"The flag is {flag}."})
    return messages


def export(task_dir, rollouts=60, mode="local", seed_base=7000):
    manifest = load_manifest(task_dir)
    rubric = _load_rubric(manifest)
    max_score = sum(s["weight"] for s in rubric["stages"])
    out_dir = manifest["_dir"] / "dataset"
    out_dir.mkdir(exist_ok=True)

    solve = import_from_task(task_dir, manifest["solver"]["entry"].removesuffix(".py") + ":solve")
    agent_mod = import_from_task(task_dir, manifest["agent"]["entry"] + ":")
    profiles = import_from_task(task_dir, manifest["agent"]["entry"] + ":PROFILES")
    budget = manifest.get("calibration", {}).get("turn_budget", 16)

    n_sft, n_rl, n_solved = 0, 0, 0
    with task_env(manifest, mode=mode) as urls:
        base = urls["edge"]

        # --- SFT: the golden reference trajectory ---
        rec = Recorder()
        flag = solve(base, rec, verbose=False)
        sft_rec = {
            "task_id": manifest["id"], "category": manifest["category"],
            "split": "sft", "source": "reference_solver", "solved": True,
            "reward": max_score, "max_reward": max_score,
            "flag": flag, "num_turns": len(rec.turns),
            "messages": _sft_messages(manifest, rubric,
                                      rec.as_transcript(), flag)}
        with (out_dir / "sft.jsonl").open("w", encoding="utf-8") as fh:
            fh.write(json.dumps(sft_rec) + "\n")
            n_sft = 1

        # --- RL: stochastic rollouts with dense per-step rewards ---
        prof_list = list(profiles.values())
        with (out_dir / "rl.jsonl").open("w", encoding="utf-8") as fh:
            for i in range(rollouts):
                profile = prof_list[i % len(prof_list)]
                seed = seed_base + i
                result, transcript = record_rollout(agent_mod, base, profile,
                                                    budget, seed)
                turns = transcript["turns"]
                steps = _dense_rewards(rubric, turns)
                final = steps[-1]["cumulative_reward"] if steps else 0
                graded = grader.grade(rubric, {"turns": turns})
                rec_obj = {
                    "task_id": manifest["id"], "category": manifest["category"],
                    "split": "rl", "profile": profile["name"], "seed": seed,
                    "budget": budget, "solved": graded["solved"],
                    "final_reward": final, "max_reward": max_score,
                    "return_fraction": round(final / max_score, 4) if max_score else 0.0,
                    "guard_violation": bool(graded.get("guard_violations")),
                    "steps": [{"t": s["t"],
                               "action": turns[s["t"] - 1]["request"],
                               "status": turns[s["t"] - 1]["response"]["status"],
                               "step_reward": s["step_reward"],
                               "cumulative_reward": s["cumulative_reward"]}
                              for s in steps]}
                fh.write(json.dumps(rec_obj) + "\n")
                n_rl += 1
                n_solved += 1 if graded["solved"] else 0

    _write_data_md(manifest, rubric, max_score, out_dir, n_sft, n_rl, n_solved)
    return {"sft": n_sft, "rl": n_rl, "solved": n_solved, "dir": str(out_dir)}


def _write_data_md(manifest, rubric, max_score, out_dir, n_sft, n_rl, n_solved):
    stage_lines = "\n".join(
        f"  - `{s['id']}` (weight {s['weight']})" for s in
        sorted(rubric["stages"], key=lambda s: s["order"]))
    (out_dir / "DATA.md").write_text(f"""# Training data — {manifest['id']}

Generated by `python -m harness.cli export {manifest['id']}`. Regenerate any time;
this directory is reproducible from the task + rubric.

## Files

- **sft.jsonl** ({n_sft} example) — the reference solution as a tool-call
  trajectory for supervised fine-tuning / behaviour cloning. One JSON object with
  a `messages` array (system, then alternating `assistant` `http_request`
  tool-calls and `tool` observations, ending with the flag). This is the
  *optimal* trajectory: what a solved rollout should look like.

- **rl.jsonl** ({n_rl} rollouts, {n_solved} solved) — stochastic-agent rollouts
  for RL / reward-model training. Each line:
  ```
  {{ task_id, profile, seed, budget, solved, final_reward, max_reward,
     return_fraction, guard_violation,
     steps: [ {{ t, action:{{method,url,body}}, status,
                step_reward, cumulative_reward }} ] }}
  ```

## Reward

`step_reward` / `cumulative_reward` come straight from the rubric via
`harness.grader`: the reward after step *t* is the graded score of the transcript
prefix up to *t*. Credit is strictly monotonic (furthest-checkpoint), so
`cumulative_reward` never decreases — a dense, ordered signal toward the flag out
of {max_score} total. Stages:

{stage_lines}

`guard_violation` marks a rollout the anti-reward-hacking guard voided (the
reward signal leaked before it was earned); such rollouts score 0 regardless of
stages touched, and should be dropped or used as negatives.
""", encoding="utf-8")
