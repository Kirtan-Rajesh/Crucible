"""
Reward red-team for nonce-forge: a real solve is fully credited, and every common
reward-hack mutation of it is rejected (solved=False, score=0). Self-contained.
"""
import pathlib
import sys

import yaml

TASK_DIR = pathlib.Path(__file__).resolve().parents[1]
REPO_ROOT = TASK_DIR.parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(TASK_DIR))

from harness.reward_redteam import evaluate     # noqa: E402
from harness.transcript import Recorder         # noqa: E402
from solver import solve                        # noqa: E402
from run_local import LocalStack                # noqa: E402


def main():
    rubric = yaml.safe_load((TASK_DIR / "rubric.yaml").read_text())
    with LocalStack() as urls:
        rec = Recorder()
        solve(urls["edge"], rec, verbose=False)
    rows = evaluate(rubric, rec.as_transcript())
    ok = True
    for r in rows:
        ok = ok and r["ok"]
        print(f"[{'PASS' if r['ok'] else 'FAIL'}] {r['name']}  ({r['detail']})")
    print(f"\n{sum(1 for r in rows if r['ok'])}/{len(rows)} reward-robustness checks passed")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
