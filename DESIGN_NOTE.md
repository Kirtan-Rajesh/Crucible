# Design note — Crucible & its reference tasks

## What I optimised for

The brief calls reward design "the most important part" and says an uncalibrated
task "is not done." So I built two layers: **reference tasks** worth grading, and
a **harness** that makes the grading, calibration, and acceptance-checking
reusable — because at a training-data shop the recurring cost is authoring *many*
calibrated tasks, not one. The pitchable asset is the contract, not any single
challenge — which is why, with the extra time, I proved that claim by shipping a
*second* task (`nonce-forge`, crypto) through the identical harness rather than
just describing how it would work.

## Three decisions on the tasks

**1. A strict linear chain, so partial credit is objective and monotonic.** Every
stage leaves an unambiguous HTTP fingerprint (a status, a banner string, a
document name, a signature-verified response, the flag), and each depends on the
previous. The grader awards "furthest-checkpoint" credit that is monotonic by
construction: reaching stage N implies 1..N-1, so credit only increases toward
the flag. Branchy puzzles make reward assignment subjective; a chain makes it a
lookup. Both tasks use this shape with zero changes to the grader.

**2. Each task's hard part is a real insight, not a guessing game.** `edge-pivot`
chains three real bug classes (mass assignment, an allowlist parser
differential, broken function-level authz) so the flag is never on the box you
can reach — the collector has no published port and gates on a header, so the
SSRF is load-bearing, not decorative. `nonce-forge` is a single sharp
cryptographic insight (ECDSA nonce reuse leaks the private key via modular
arithmetic) that cannot be brute-forced or guessed into — you either spot that
two signatures share `r` and do the algebra, or you don't.

**3. A late, deliberately awkward final stage, so the task isn't free.** An
earlier `edge-pivot` draft ended at "search leaks the flag," solved by a
competent agent ~100% of the time. Making the leaked value a *deploy key* that
must be recognised and replayed against a privileged endpoint moved it off
saturation. `nonce-forge`'s equivalent: the service will not sign the required
claim directly (reserved device ids are refused), so recovering the key is
necessary, not just sufficient.

## Three decisions on the harness

**1. A tiny contract.** A task is five files plus two-to-three code interfaces (a
solver command, a scripted agent module, optionally a real-agent module sharing
the same `PROFILES`/`run_rollout` shape). Everything else — grading, calibration,
gating, schema validation, both run modes — is inherited. Building `nonce-forge`
touched zero lines of `harness/`.

**2. Measured, then enforced — and then re-measured with real variance.**
Calibration drives a live stochastic agent under the real turn budget; `gate`
turns the acceptance numbers into a CI PASS/FAIL. `--seed-repeats N` runs N
independent, non-overlapping seed batches instead of one fixed sequence and
reports the spread — this caught a real bug: `nonce-forge`'s first "naive"
profile measured **83%** (a per-turn retry loop meant even a low per-attempt
probability converged to near-certainty given the turn budget), which a single
calibration run would not obviously have flagged as wrong. Fixed to a one-shot
decision, it now measures a real floor (~18%).

**3. Anti-gaming and anti-memorization built in, and checked, not just claimed.**
Every task's final stage credits the flag only from an authorised response
(closing the flag-echo hack), and a rubric `guards:` block independently voids
the *entire* score if the flag string appears anywhere before that point —
`tests/test_guards.py` proves this against a synthetic reward-hacked transcript
on both tasks. Per-instance secrets derive from `CRUCIBLE_SEED`; `edge-pivot`'s
collector also carries seed-derived decoy documents so the *shape* of a full
listing isn't fully memorizable either.

## The centerpiece finding: the scripted "competent" agent oversells itself

The single biggest honesty gap in the original submission was that "competent
agent solves 87%" was a probability the scripted policy was tuned to produce,
not a measurement of anything. `tasks/edge-pivot/llm_agent.py` closes that gap
the direct way: it drives the identical live service through an actual model's
(Gemini 2.5 Flash) decisions, one HTTP action per turn, graded by the same
`harness.grader`, with zero vulnerability hints.

Result: **0/15 solved at the declared 16-turn budget**, even though transcript
inspection shows the model independently found the mass-assignment bug and the
userinfo SSRF bypass, unprompted — just too late in the budget. At 24 turns:
1/8, using every turn. A follow-up prompt change (explicit turn-economy
guidance, no vulnerability hints) did not close the gap at 16 turns (0/12).

This is reported honestly, in full, in `docs/calibration.md`, precisely because
it's uncomfortable: the scripted proxy's number is not what a real agent gets.
It does **not** mean the task or the CI gate is wrong — the gate stays pinned to
the declared, calibrated scripted baseline in `report.json`; the real-agent runs
live in separately named `report.llm*.json` files exactly so they can stay
honest about being harder than the assumption without anyone being tempted to
quietly retune knobs (the proxy's *or* the task's) until the numbers agree —
that would just relocate the original problem rather than fix it.

**Then it was fixed, iteratively, and each fix was measured, not assumed.**
The transcripts pointed at turn economy (redundant re-authentication, slow
convergence), not a capability ceiling, as the likely cause. Four scaffold
changes, each tested against the live service before moving to the next: a
state scratchpad (stop re-deriving a bearer token already held); enabling the
model's reasoning ("thinking", previously off for cost); a
reasoning-consistency nudge, added after tracing `thoughtsTokenCount` and
finding it collapsed to 0 from turn 3 onward -- the model was quietly
switching off deliberation right when the hard decision was still ahead, not
when it ran out of budget for it; and a pinned-documentation scratchpad, since
the model reliably read its own API-doc response once and then lost track of
specific fields in it many turns later.

None of these tell the model anything about the vulnerability -- all four are
generic HTTP-agent scaffold engineering. Two things worth being honest about
in how they landed: first, the reasoning-nudge's initial wording caused the
model to print prose instead of JSON as its visible reply (a real regression,
caught by re-tracing the same seed before spending a batch on it, not by luck).
Second, the results were not uniformly positive -- nothing tested ever
reliably solves at the declared 16-turn budget, and at 24 turns the full
scaffold pushed the non-thinking profile to **50%** (from 12.5%) while making
the thinking-enabled profile *worse* (37.5% down to 12.5%): diagnostic
transcripts suggest the same "reason more" instruction pushed the
reasoning-capable model toward wrong, more elaborate hypotheses (SQL
injection, a hand-forged JWT) instead of the actual simple bug, where the
non-thinking profile stayed more literal-minded on the identical prompt. That
reading is plausible, not proven by controlled ablation, and is reported as
such rather than rounded up into a cleaner story than the data supports.

This is a small, honest case study in exactly the kind of iteration a real
training-data pipeline would need to do many times over: measure against a
real agent, diagnose *why* it underperforms an assumption, fix the diagnosed
cause, remeasure, and report the parts that didn't go as hoped alongside the
parts that did.

## Honest limitations

- **The real-agent sample sizes are small** (n=8-15 per run) — enough to see a
  real, repeatable, and repeatably-improvable gap from the scripted proxy at
  reasonable API cost, not enough for a tight confidence interval. Treat
  "50%" as "clearly better than 12.5% under the same conditions," not as a
  precise rate; a wider sample is the natural next step (see below).
- **The "thinking hurts at 24 turns" finding is a plausible reading of a
  handful of diagnostic transcripts, not a controlled ablation.** It's
  reported because the pattern (more elaborate, wrong hypotheses) was visible
  and consistent where checked, not because the mechanism is proven --
  flagged explicitly rather than stated as settled.
- **`llm_agent.py`'s interface is still simple** (one HTTP action per model
  turn, plus a tracked-state and pinned-documentation scratchpad) — a
  production RL rollout harness might structure a turn differently again. The
  measured numbers are a property of *this* interface, budget, and model, not
  a claim about the task's difficulty ceiling for every possible scaffold.
- **`nonce-forge` has no network-isolation dimension to defend** (unlike
  `edge-pivot`'s two-tier SSRF), because the vulnerability class doesn't call
  for one — its difficulty is entirely in the cryptographic insight. Noted so
  it doesn't read as an oversight.
- **Container verification used Podman**, not Docker, since that's what was
  available; the compose files target both and `docker compose` should work
  identically (same provider-detection code path in `harness/runner.py`), but
  neither has been exercised with Docker itself. Verified end-to-end on Podman
  for both tasks: cold `--no-cache` builds in ~15–31s, containers healthy in
  ~9s, full solves 14/14 through the real topology — comfortably inside the
  10-minute build budget.

## What I'd do with more time

1. **Wider real-agent sample sizes and a second model**, once cost allows, to
   turn "50% beats 12.5%" into a tight, model-comparable number, to properly
   test the "thinking hurts under this prompt" finding with a controlled
   ablation instead of a handful of transcripts, and to check whether the
   recipe transfers past Gemini.
2. **Push the scaffold further**: turns were still capped at "one HTTP call,"
   and the best configuration found is still turn-starved at the declared
   16-turn budget (0% there regardless of scaffold) -- the natural next step
   is a genuinely richer per-turn action space (batched reconnaissance, full
   prior bodies instead of trailing summaries) to see how much of the
   remaining gap to the scripted proxy's 91.6% is scaffold-shaped versus
   genuinely hard, and whether 16 turns is reachable at all for this class of
   interface.
3. **A pwn or rev task** as a third contract exercise — the assignment's own
   Track-B Basic/Intermediate/Advanced gradient maps naturally onto a pwn tier
   ladder, and would stress a different corner of the check DSL (memory-safety
   crash signatures rather than HTTP status/pattern checks).
4. **More per-instance structural randomization** (internal hostnames, decoy
   endpoint names) beyond secrets and `edge-pivot`'s decoy documents, to widen
   the anti-memorization surface further for large-scale RL rollouts.
