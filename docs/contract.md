# The Crucible task contract

Crucible separates a **reusable harness** (grading, calibration, the acceptance
gate) from **tasks** (the actual challenges). Anything that satisfies this
contract gets grading and calibration for free. The contract is deliberately
small — five files and two tiny code interfaces.

```
tasks/<id>/
  task.yaml            # manifest (validated by harness/schema/task.schema.json)
  rubric.yaml          # staged rewards (validated by harness/schema/rubric.schema.json)
  solver.py            # reference solution (a command)
  agent.py             # stochastic agent policy (a module)
  run_local.py         # no-Docker environment (a context manager)  [optional]
  compose.yaml         # container environment
  services/…           # the challenge itself
  tests/…              # self-contained checks
```

## 1. The manifest — `task.yaml`

Declares identity, the flag regex, how to stand the environment up, and the
acceptance targets. See [`harness/schema/task.schema.json`](../harness/schema/task.schema.json)
for the full schema. The harness reads only the manifest to locate everything
else, so tasks can be laid out however they like.

## 2. The rubric — `rubric.yaml`

An ordered list of stages, each with an `id`, `weight`, and an **observable
check**. The check DSL runs over a transcript (below):

| field | meaning |
|-------|---------|
| `where` | `request` \| `response` \| `any` — which text the pattern runs on |
| `url_contains` | substring required in the turn's request URL |
| `status_in` / `status_not_in` | constrain the response status |
| `pattern` | regex; must be found (`re.search`) |
| `negate` | if true, the pattern must **not** be found (anti-reward-hacking) |

A stage's `check` is one check or a list of any-of checks. Scoring is strictly
monotonic "furthest-checkpoint" credit: stage *i* is credited iff it or any later
stage was reached, which keeps partial credit ordered toward the flag. See
[`harness/grader.py`](../harness/grader.py).

## 3. The transcript

The interface between "an agent acted" and "assign a reward" — a JSON list of
turns, each one request and its response. Any agent (the reference solver, a
scripted policy, or a real LLM harness) can emit it; the grader consumes it
without touching the live service. Schema in [`harness/transcript.py`](../harness/transcript.py).

## 4. The solver — a command

```
python solver.py --base <URL> --transcript <PATH> [--quiet]
```

Must exit `0` on success and write a transcript. Language-agnostic in principle
(it's just a command); the reference task uses Python.

## 5. The agent policy — a module

Exposes exactly two names:

```python
PROFILES = {"competent": {...}, "naive": {...}}   # named skill profiles
def run_rollout(base, profile, budget, seed) -> {"solved": bool, "turns": int}
```

The harness Monte-Carlos this to measure the difficulty band. Keeping the policy
in the task (not the harness) lets each task model its own action space, while the
harness owns the aggregation and the budget.

## What the harness provides for free

```
python -m harness.cli solve      <task>          # solve + grade
python -m harness.cli calibrate  <task>          # reliability + difficulty band
python -m harness.cli gate       <task>          # enforce acceptance targets (CI-friendly)
python -m harness.cli verify     <task>          # tests + calibrate + gate
python -m harness.cli up/down    <task>          # container environment
```

Add a task, satisfy the contract, and you inherit grading, calibration, the
acceptance gate, and both a container and a no-Docker run path. See
[extending.md](extending.md) for how the same contract carries other categories.
