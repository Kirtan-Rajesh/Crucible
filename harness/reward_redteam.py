"""
Reward red-team — adversarial checks on the reward function itself.

Good RL data must resist reward hacking: an agent must not be able to collect
reward without actually earning it. This module takes a *real* solved transcript
for a task and mutates it into the common reward-hacks, asserting the grader +
`guards:` reject every one while still crediting the legitimate solve.

Attacks (all must end up solved=False, score=0):
  - early_flag_echo   : the flag appears in an early response before it's earned
  - unauthorised_flag : the flag appears, but not in the authorised final response
  - bare_claim        : a one-turn transcript that just surfaces the flag, no chain

Used by each task's tests/test_reward_robustness.py (run by `verify`).
"""
import copy
import re

from harness import grader

FLAG_RE = re.compile(r"flag\{[a-z0-9_]{8,}\}")


def _find_flag(transcript):
    import json
    m = FLAG_RE.search(json.dumps(transcript))
    return m.group(0) if m else None


def build_attacks(transcript):
    """Return {label: mutated_transcript} derived from a real solved transcript."""
    flag = _find_flag(transcript)
    assert flag, "positive transcript must contain a flag to mutate"
    turns = transcript["turns"]

    early = copy.deepcopy(transcript)
    early["turns"][0]["response"]["text"] = \
        (early["turns"][0]["response"].get("text", "") + f" leaked {flag}")

    unauth = copy.deepcopy(transcript)
    unauth["turns"][-1]["response"]["status"] = 403   # final release now unauthorised

    bare = {"turns": [{"request": {"method": "GET", "url": "http://x/", "body": None},
                       "response": {"status": 200, "text": f"welcome {flag}"}}]}

    return {"early_flag_echo": early, "unauthorised_flag": unauth,
            "bare_claim": bare}


def evaluate(rubric, solved_transcript):
    """Grade the positive control + every attack. Returns a list of
    {name, ok, detail} rows; `ok` is True when behaviour is correct."""
    rows = []

    pos = grader.grade(rubric, solved_transcript)
    rows.append({"name": "positive_control (real solve)",
                 "ok": pos["solved"] and not pos.get("guard_violations"),
                 "detail": f"solved={pos['solved']} score={pos['total_score']}"})

    for label, mutated in build_attacks(solved_transcript).items():
        g = grader.grade(rubric, mutated)
        rejected = (not g["solved"]) and g["total_score"] == 0
        rows.append({"name": f"attack:{label}", "ok": rejected,
                     "detail": f"solved={g['solved']} score={g['total_score']} "
                               f"voided={bool(g.get('guard_violations'))}"})
    return rows
