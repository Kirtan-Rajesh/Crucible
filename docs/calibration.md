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

Each profile is run as **N independent, non-overlapping seed batches**
(`--seed-repeats`), not one fixed sequence — `band()` in `harness/calibrate.py`
reports the pooled rate plus the per-batch range/mean/stdev, so a rate near a
target boundary is evidence, not an artifact of one lucky/unlucky seed. This
replaced an earlier version of this doc that *claimed* multi-seed stability
without the code actually being able to run more than one seed batch —
`--seed-repeats` is what makes that claim checkable instead of asserted.

*Target:* competent solves ≥ 60% (fails < 40%); not trivial (> 2 turns); not
impossible (fail < 80%). *Measured* (5 batches × 100 rollouts,
`--seed-repeats 5`): competent **91.6%** mean, range **[87%, 94%]**, stdev
**2.8pp** (median 10 turns); naive **9.2%** mean, range **[8%, 11%]** (median
14 turns). Regenerate with the command below; current numbers are always in
`report.json`/`report.md`.

## Why these numbers are the right shape

- **Competent well inside the band.** An earlier design ended at "search leaks
  the flag" and a competent agent solved ~100% — too easy to give signal. Adding
  the credential-reuse stage moved it down substantially, to a measured ~92% mean
  with a real ~8% failure rate — comfortably clear of both the 60% floor and the
  80% impossible line, and not saturated at 100%.
- **A real gradient.** The naive profile (~9%) is the weak-policy floor. The gap
  between naive and competent is the reward gradient a trainer climbs; partial
  credit from the 5 monotonic stages provides dense signal along the way.
- **Honest bound, not yet a real-agent measurement.** The profile is a hand-tuned
  scripted proxy, not an LLM — its solve rate reflects *this policy's* skill
  under the turn budget, not a frontier model's. It's a defensible lower bound
  (a stronger real agent should do at least as well), but "competent" here is an
  assumption, not something that was independently measured. See
  `tasks/edge-pivot/llm_agent.py` and the calibration section of `README.md` for
  the real-agent measurement that supersedes this proxy where available.

## Real-agent measurement (Gemini)

> **Correction — extractor bug found during live testing (supersedes the
> per-run figures in this section).** Re-running the real agent surfaced a bug in
> `llm_agent._extract_json`: a greedy brace match swallowed the model's action
> whenever it appended reasoning prose after the JSON, so those turns failed to
> parse and the agent stalled instead of acting. It is now fixed to decode the
> first valid action object. **Corrected measurement:** with the fix,
> `gemini-2.5-flash` solves **0/6** at the 16-turn budget (thinking on *and*
> off). Transcripts show why this is honest difficulty, not a harness artifact —
> the model does recon cleanly and finds the operator-gated render endpoint, but
> never discovers the mass-assignment (it changes the `user` field in the session
> body, never `role`), so it never escalates. The corrected 16-turn result lives
> in `report.llm-fixed-b16.json`. The tables and follow-ups below were measured
> **before** this fix and are kept only as a record of the scaffold exploration;
> treat their specific solve rates as unreliable.

The scripted policy above is a *proxy* by construction (see `agent.py`'s
docstring): its probabilities are an assumption about what a competent agent
does, not a measurement of one. `tasks/edge-pivot/llm_agent.py` closes that
gap the honest way -- it drives the identical live service through an actual
model's decisions, one HTTP action per turn, graded by the same
`harness.grader` (so it is subject to the same anti-reward-hacking guard as
every other solve), with **no vulnerability hints**: the model is told only
the base URL and the turn budget, and has to discover `/api/spec`, the
mass-assignment bug, and the userinfo SSRF bypass itself.

| run | model | budget | rollouts | solved | notes |
|---|---|---|---|---|---|
| 1 | gemini-2.5-flash, temp 0.4, thinking off | 16 | 15 | 0/15 (0%) | every transcript inspected made real progress; several independently found mass-assignment and/or the SSRF bypass, just too late in the budget |
| 2 | same, + turn-economy prompt guidance | 16 | 12 | 0/12 (0%) | discouraging redundant re-checks (e.g. re-verifying `/api/whoami` after every action) did not close the gap |
| 3 | same as run 1 | 24 | 8 | 1/8 (12.5%) | the one solve used the full 24-turn budget |

**Reading this honestly:** the synthetic "competent" profile's 91.6% at 16
turns is not what a real model gets. A real, capable model needs meaningfully
more than 16 turns with this simple one-action-per-turn interface, even though
the transcripts show it has the *conceptual* capability (it finds the actual
bug chain, unprompted). That's a genuine gap between an assumed proxy and a
measured agent, and it's exactly the kind of thing a scripted policy cannot
surface -- which is why this ships as a real (if small-N) measurement instead
of a claim.

What this does *not* mean: it does not mean the task is broken or the CI gate
is wrong. The gate is enforced against `report.json` (the scripted proxy, the
declared and calibrated baseline in `task.yaml`), which is untouched by this.
`report.llm*.json` are kept as separate, clearly-labeled files precisely so a
real-agent measurement can be honest about being harder than the assumption,
without forcing either the gate or the proxy's knobs to be quietly retuned
until they agree with it -- that would just relocate the original problem
(numbers designed to pass) rather than fix it.

### Follow-up: does fixing turn economy actually help?

Runs 1-3 above pointed at turn economy in the interface, not the model's
understanding, as the likely bottleneck: transcripts showed turns lost to
redundant `/api/whoami` re-checks and re-minted sessions before the two real
insights (mass assignment, the SSRF bypass) landed, often in the back half of
the budget. Two scaffold changes were tried against that hypothesis, in
`llm_agent.py`: a **state scratchpad** (the harness now tracks the last
bearer token it saw and restates it, plus turns remaining, before every
model turn, instead of letting the model re-derive or re-fetch it) and
**enabling the model's "thinking"** (`thinkingConfig`, previously forced off
for cost). Both are generic HTTP-agent scaffold changes -- neither tells the
model anything about the vulnerability.

| run | budget | scaffold | solved |
|---|---|---|---|
| 4 | 16 | + state scratchpad, thinking off | 1/10 (10%) |
| 5 | 16 | + state scratchpad, thinking on | 0/10 (0%) |
| 6 | 24 | + state scratchpad, thinking off | 1/8 (12.5%) |
| 7 | 24 | + state scratchpad, thinking on | **3/8 (37.5%)** |

The scratchpad alone gave a real lift at the original 16-turn budget (0% to
10%) by removing a genuine, budget-independent inefficiency. Thinking mode
turned out to help a lot, but *only* once there was enough budget to act on
the better decisions it produces (37.5% at 24 turns vs. 12.5% without it,
under otherwise identical conditions) -- at 16 turns the extra deliberation
per turn doesn't pay for itself, because the model still needs a floor number
of *actions* to complete a 5-stage chain regardless of how good each one is.

### Second follow-up: is the model actually still reasoning by turn 15?

Tracing `thoughtsTokenCount` per turn on a fixed seed showed it collapsing to
**0 from turn 3 onward** -- the thinking-enabled model was choosing to stop
deliberating once it settled into a rhythm, exactly when the hard decision
(the SSRF bypass) was still ahead of it. Two more changes: a **reasoning
nudge** (explicitly ask for reasoning on every turn, not just the first --
first wording of this caused the model to print prose instead of JSON as its
visible reply, a real regression caught by re-tracing the same seed before
running a batch; fixed by clarifying the reasoning is private and the reply
is still bare JSON, with `maxOutputTokens` raised for headroom) and a
**pinned-documentation scratchpad** (the model's own `/api/spec`-shaped
response stays restated every turn instead of relying on long-context recall
of something it was shown once, 14 turns ago).

| run | budget | scaffold | thinking off | thinking on |
|---|---|---|---|---|
| 8 | 16 | + reasoning nudge + pinned doc | 0/12 (0%) | 0/12 (0%) |
| 9 | 24 | + reasoning nudge + pinned doc | **4/8 (50%)** | 1/8 (12.5%) |

Neither change moved the 16-turn rate off zero. At 24 turns, the non-thinking
profile jumped from 12.5% to **50%** -- the best configuration measured across
this entire investigation, roughly 4x the first real-agent number. The
thinking profile went the other way, 37.5% down to 12.5%, under the identical
prompt change. Diagnostic transcripts of the thinking profile (not a
controlled ablation -- flagged as a plausible reading, not a proven one) show
it using the extra encouragement to deliberate into wrong, more "creative"
hypotheses -- SQL-injection-shaped payloads, hand-forging a JWT with a fake
signature -- instead of the actual, much simpler mass-assignment bug, where
the non-thinking profile stayed more literal-minded on the identical prompt
and did better for it.

**Overall reading:** turn economy, not conceptual capability, is the dominant
bottleneck for this task under a one-HTTP-call-per-turn interface -- nothing
tested reliably solves at 16 turns regardless of scaffold quality, and every
scaffold improvement's signal only shows up once the budget triples the
minimum 5-action chain length. That is itself useful, and different from
"the task is miscalibrated": it says something about *this interface's* turn
cost, not about whether the underlying insight is learnable.

None of this touches `task.yaml`'s declared 16-turn acceptance budget or
`report.json`, which stay pinned to the scripted-proxy baseline the CI gate
reads -- every real-agent run lives in its own separately-named
`report.llm-fixed*.json` file, for exactly the reason given above.

Reproduce (costs real Gemini API calls; needs `GEMINI_API_KEY`):
```bash
# Baseline profile (thinking off) and the thinking-enabled profile both run
# automatically -- PROFILES in llm_agent.py has both:
python -m harness.cli calibrate edge-pivot --agent llm_agent --rollouts 6 \
    --skip-reliability --report-name report.llm-fixed-b16          # budget 16 (task default)
python -m harness.cli calibrate edge-pivot --agent llm_agent --rollouts 6 \
    --skip-reliability --report-name report.llm-fixed-b24 --budget 24
```

## Reproduce

```bash
python -m harness.cli calibrate edge-pivot                      # single seed batch
python -m harness.cli calibrate edge-pivot --seed-repeats 5     # + variance evidence
python -m harness.cli gate      edge-pivot                      # PASS/FAIL vs task.yaml targets
```

Both container (`--mode compose`) and no-Docker (`--mode local`) environments are
supported; the numbers above are from local mode (identical application code).
