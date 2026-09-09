"""
Verify llm_agent.py's batched-reconnaissance action parsing: a single action
dict still passes through as a one-item list; up to MAX_BATCH independent GET
requests may be bundled together; anything that could break turn-budget
accounting or POST sequencing (oversized batch, a POST mixed into a batch, a
missing 'path') must be rejected. Pure unit test, offline -- no live service,
no network, no API key required, so it costs nothing to run before spending
real Gemini calls on a change to the scaffold.
"""
import pathlib
import sys

TASK_DIR = pathlib.Path(__file__).resolve().parents[1]
REPO_ROOT = TASK_DIR.parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(TASK_DIR))

from llm_agent import _normalize_actions, MAX_BATCH  # noqa: E402


def _expect_ok(label, action, want):
    got = _normalize_actions(action)
    passed = got == want
    print(f"[{'PASS' if passed else 'FAIL'}] {label}: got={got}")
    return passed


def _expect_raises(label, action):
    try:
        _normalize_actions(action)
        passed = False
    except ValueError:
        passed = True
    print(f"[{'PASS' if passed else 'FAIL'}] {label}")
    return passed


def main():
    ok = True

    single = {"method": "GET", "path": "/api/spec"}
    ok = _expect_ok("single action wraps to a one-item list", single, [single]) and ok

    batch = {"actions": [{"method": "GET", "path": "/a"}, {"method": "GET", "path": "/b"}]}
    ok = _expect_ok("2 batched GETs pass through unchanged",
                     batch, batch["actions"]) and ok

    at_limit = {"actions": [{"method": "GET", "path": f"/p{i}"} for i in range(MAX_BATCH)]}
    ok = _expect_ok(f"exactly MAX_BATCH ({MAX_BATCH}) GETs is allowed",
                     at_limit, at_limit["actions"]) and ok

    over_limit = {"actions": [{"method": "GET", "path": f"/p{i}"} for i in range(MAX_BATCH + 1)]}
    ok = _expect_raises(f"more than MAX_BATCH ({MAX_BATCH}) actions is rejected", over_limit) and ok

    empty = {"actions": []}
    ok = _expect_raises("an empty 'actions' list is rejected", empty) and ok

    post_in_batch = {"actions": [{"method": "GET", "path": "/a"},
                                  {"method": "POST", "path": "/api/session"}]}
    ok = _expect_raises("a POST mixed into a batch is rejected (sequencing risk)",
                        post_in_batch) and ok

    single_post = {"method": "POST", "path": "/api/session", "body": {"role": "operator"}}
    ok = _expect_ok("a lone POST (not batched) still passes through normally",
                     single_post, [single_post]) and ok

    missing_path = {"actions": [{"method": "GET", "path": "/a"}, {"method": "GET"}]}
    ok = _expect_raises("a batched action missing 'path' is rejected", missing_path) and ok

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
