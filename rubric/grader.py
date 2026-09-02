#!/usr/bin/env python3
"""
grader.py — consume rubric.yaml + a transcript and award staged rewards.

The grader treats the transcript as the agent's observed behaviour and never
re-runs the challenge, so it is the same code path an RL trainer would use to
turn a rollout into a reward signal.

Transcript format (JSON):
    {
      "flag": "<optional>",
      "turns": [
        {"request": {"method": "...", "url": "...", "body": {...}},
         "response": {"status": 200, "text": "..."}},
        ...
      ]
    }

Usage:
    python rubric/grader.py --rubric rubric/rubric.yaml --transcript run.json
    python rubric/grader.py ... --json        # emit machine-readable result only
"""
import argparse
import json
import re
import sys

import yaml


def _turn_text(turn, where):
    req = turn.get("request", {}) or {}
    resp = turn.get("response", {}) or {}
    req_text = json.dumps(req, default=str)
    resp_text = resp.get("text")
    if resp_text is None:
        resp_text = json.dumps(resp.get("json"), default=str)
    if where == "request":
        return req_text
    if where == "response":
        return resp_text or ""
    return f"{req_text}\n{resp_text or ''}"


def _one_check_matches(check, turns):
    where = check.get("where", "any")
    url_contains = check.get("url_contains")
    status_not_in = check.get("status_not_in")
    pattern = check.get("pattern")
    regex = re.compile(pattern) if pattern else None

    for turn in turns:
        req = turn.get("request", {}) or {}
        resp = turn.get("response", {}) or {}

        if url_contains and url_contains not in (req.get("url") or ""):
            continue
        if status_not_in is not None and resp.get("status") in status_not_in:
            continue
        if regex and not regex.search(_turn_text(turn, where)):
            continue
        return True
    return False


def _stage_reached(stage, turns):
    check = stage["check"]
    checks = check if isinstance(check, list) else [check]
    # any-of semantics across alternative checks
    return any(_one_check_matches(c, turns) for c in checks)


def grade(rubric, transcript):
    turns = transcript.get("turns", [])
    stages = sorted(rubric["stages"], key=lambda s: s["order"])

    reached_raw = [_stage_reached(s, turns) for s in stages]

    # Monotonic furthest-checkpoint credit: stage i is credited if it or any
    # later stage was reached.
    cumulative = [any(reached_raw[j] for j in range(i, len(stages)))
                  for i in range(len(stages))]

    per_stage = []
    total = 0
    for stage, raw, credited in zip(stages, reached_raw, cumulative):
        awarded = stage["weight"] if credited else 0
        total += awarded
        per_stage.append({
            "id": stage["id"],
            "order": stage["order"],
            "title": stage["title"],
            "weight": stage["weight"],
            "reached": bool(raw),
            "credited": bool(credited),
            "score": awarded,
        })

    max_score = sum(s["weight"] for s in stages)
    solved_stage = rubric["meta"].get("solved_stage")
    solved = any(s["credited"] for s in per_stage if s["id"] == solved_stage)

    return {
        "task_id": rubric["meta"].get("task_id"),
        "total_score": total,
        "max_score": max_score,
        "fraction": round(total / max_score, 4) if max_score else 0.0,
        "solved": bool(solved),
        "stages_reached": sum(1 for s in per_stage if s["credited"]),
        "stages": per_stage,
    }


def _print_human(result):
    print(f"task: {result['task_id']}")
    print(f"score: {result['total_score']}/{result['max_score']} "
          f"({result['fraction']*100:.0f}%)   solved={result['solved']}")
    print("-" * 68)
    print(f"{'stage':<20}{'weight':>7}{'reached':>9}{'credit':>8}{'score':>7}")
    for s in result["stages"]:
        print(f"{s['id']:<20}{s['weight']:>7}{str(s['reached']):>9}"
              f"{str(s['credited']):>8}{s['score']:>7}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rubric", default="rubric/rubric.yaml")
    ap.add_argument("--transcript", required=True)
    ap.add_argument("--json", action="store_true", help="emit JSON result only")
    args = ap.parse_args()

    with open(args.rubric, encoding="utf-8") as fh:
        rubric = yaml.safe_load(fh)
    with open(args.transcript, encoding="utf-8") as fh:
        transcript = json.load(fh)

    result = grade(rubric, transcript)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        _print_human(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
