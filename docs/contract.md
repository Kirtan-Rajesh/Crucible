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

An optional top-level `guards:` list adds anti-reward-hacking invariants that
sit outside the stage ordering entirely:

```yaml
guards:
  - id: flag_before_authorised_publish
    pattern: "flag\\{[a-z0-9_]{8,}\\}"
    where: response
    forbidden_before: s5_flag   # a stage id
```

If `pattern` matches any turn strictly before the first turn that legitimately
reaches `forbidden_before`, the guard is violated and the grader zeroes the
**entire** transcript's score (not just that stage) -- a leaked reward signal
means nothing about the run can be trusted, not only the one checkpoint it
touched. Both reference tasks ship the flag-before-authorised-release guard;
`tests/test_guards.py` proves it against a synthetic reward-hacked transcript.

`python -m harness.cli validate <task>` checks a `rubric.yaml`/`task.yaml` pair
against the JSON Schemas (including that `solved_stage` and every guard's
`forbidden_before` actually name a defined stage) before anything is graded or
calibrated -- run it whenever you hand-edit either file.

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
harness owns the aggregation and the budget. `calibrate --agent <module>` swaps
in a *different* module satisfying the same two names -- e.g.
`tasks/edge-pivot/llm_agent.py`, a real Gemini-backed policy -- without any
harness change; pair it with `--report-name` so a real-agent measurement never
overwrites the report the CI gate reads.

**Design note for `agent.py` authors:** make a low-skill profile's failure mode
a genuine one-shot miss, not a per-turn retry of the same probability. A retry
loop converges to near-certain success given enough turns even at a low
per-attempt probability, which silently defeats the point of having a "naive"
floor at all -- this is not hypothetical, it's what happened while authoring
`nonce-forge` (naive measured 83% before the fix). `--seed-repeats N` on
`calibrate` is the cheap way to catch this kind of thing: a rate that looks
fine as one number but is actually an artifact shows up as suspiciously tight
variance or a rate nobody actually intended.

## What the harness provides for free

```
python -m harness.cli solve      <task>          # solve + grade
python -m harness.cli validate   <task>          # schema-check task.yaml/rubric.yaml
python -m harness.cli calibrate  <task>          # reliability + difficulty band (--seed-repeats N, --agent <module>)
python -m harness.cli gate       <task>          # enforce acceptance targets (CI-friendly)
python -m harness.cli verify     <task>          # validate + tests + calibrate + gate
python -m harness.cli up/down    <task>          # container environment
```

Add a task, satisfy the contract, and you inherit grading, calibration, the
acceptance gate, and both a container and a no-Docker run path. See
[extending.md](extending.md) for how the same contract carries other categories.
