# Calibration methodology

The acceptance criteria say a task "is not done" until it is calibrated. Crucible
*measures* the numbers rather than asserting them, and `gate` enforces them.

## What is measured

**A "turn"** is one agent action and its observation — one HTTP request/response
here. The budget is 16 turns.

### 1. Reference-solution reliability
`harness/calibrate.py` runs the task's solver `reliability_runs` times against a
freshly launched environment. A run counts as a success only if the solver exits
`0` **and** the grader marks the resulting transcript solved (so a spurious exit
code can't inflate the number). It records wall-clock and turn count.

*Target:* ≥ 14/16 reliable, reference solve < 5 min. *Measured:* 16/16, ~0.5 s.

### 2. Difficulty band
The task supplies a stochastic agent policy (`PROFILES` + `run_rollout`). The
harness Monte-Carlos it against the live service under the turn budget and reports
the solve rate per profile. The policy is a **transparent proxy** for a competent
agent: it knows the techniques but not this target (it must read the spec to learn
the internal host), chooses among plausible actions probabilistically, and can
exhaust its budget — so the solve rate reflects task difficulty, not a script.

*Target:* competent solves ≥ 60% (fails < 40%); not trivial (> 2 turns); not
impossible (fail < 80%). *Measured:* competent **87%** (median 11 turns), naive
**8%**. Stable across seeds (87–92% / 5–8% over three seeds × 100 rollouts).

## Why these numbers are the right shape

- **Competent well inside the band, not saturated.** An earlier design ended at
  "search leaks the flag" and a competent agent solved ~100% — too easy to give
  signal. Adding the credential-reuse stage moved it to 87% with a median of 11 of
  16 turns actually used.
- **A real gradient.** The naive profile (~8%) is the weak-policy floor. The gap
  between naive and competent is the reward gradient a trainer climbs; partial
  credit from the 5 monotonic stages provides dense signal along the way.
- **Honest bound.** The proxy is imperfect by construction, so a stronger real
  agent (e.g. a frontier LLM harness) would land *higher* — the task is safely
  learnable. The transcript/rubric interface is exactly what you'd point such an
  agent's rollouts at, so swapping the proxy for a real agent is a drop-in.

## Reproduce

```bash
python -m harness.cli calibrate edge-pivot     # writes report.json + report.md
python -m harness.cli gate      edge-pivot     # PASS/FAIL vs task.yaml targets
```

Both container (`--mode compose`) and no-Docker (`--mode local`) environments are
supported; the numbers above are from local mode (identical application code).
