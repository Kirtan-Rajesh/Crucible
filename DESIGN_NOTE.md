# Design note — Crucible & the edge-pivot task

## What I optimised for

The brief calls reward design "the most important part" and says an uncalibrated
task "is not done." So I built two layers: a **reference task** worth grading, and
a **harness** that makes the grading, calibration, and acceptance-checking
reusable — because at a training-data shop the recurring cost is authoring *many*
calibrated tasks, not one. The pitchable asset is the contract, not the web bug.

## Three decisions on the task

**1. A strict linear chain, so partial credit is objective and monotonic.** Every
stage leaves an unambiguous HTTP fingerprint (a status, a banner string, a
document name, the flag), and each depends on the previous. The grader awards
"furthest-checkpoint" credit that is monotonic by construction: reaching stage N
implies 1..N-1, so credit only increases toward the flag. Branchy puzzles make
reward assignment subjective; a chain makes it a lookup.

**2. Two services, so the pivot is real.** The flag is never on the box you can
reach. The collector has no published port and refuses anything lacking the
edge-origin header, so the SSRF is load-bearing, not decorative — defended in
depth (network isolation *and* an origin header), which also makes the no-Docker
local run faithful.

**3. Credential reuse as the final stage.** An earlier version ended at "search
leaks the flag," which a competent agent solved ~100% of the time — too easy to
give signal. Making the leaked value a *deploy key* that must be recognised and
replayed against a privileged endpoint added a genuine long-horizon step and
moved the competent solve rate from saturated to a measured **87%** (median 11 of
16 turns) — inside the learnable band, no longer free.

## Three decisions on the harness

**1. A tiny contract.** A task is five files plus two code interfaces (a solver
command, an agent module). Everything else — grading, calibration, gating, both
run modes — is inherited. Adding a task is not rebuilding the evaluator.

**2. Measured, then enforced.** Calibration drives a live stochastic agent under
the real turn budget; `gate` turns the acceptance numbers into a CI PASS/FAIL, so
"calibrated" is checkable, not claimed.

**3. Anti-gaming and anti-memorization built in.** The `s5` check credits the flag
only from an *authorised* publish response (closing the flag-echo hack), the DSL
supports `negate` checks, and per-instance secrets derive from `CRUCIBLE_SEED` so
rollouts can be unique yet reproducible.

## Honest limitations

- **The agent is a scripted proxy, not an LLM** — a defensible lower bound on a
  competent agent, but the right next step is to point their real reference agent
  at the same transcript/rubric interface (it's built for exactly that).
- **Container verification used Podman** on a WSL machine; Docker is the more
  common target and the compose file is written for both. One Podman-on-Windows
  quirk (host port-forwarding) meant I verified the container solve from an
  attacker container on the task network rather than via `localhost`.

## What I'd do with more time

1. A **second task in another category** (crypto nonce-reuse or a pwn tier ladder)
   to exercise the contract's generality end-to-end, not just on paper.
2. **Randomised structure per instance** beyond secrets — internal hostnames,
   search terms, decoy endpoints — with a turn-cost model to widen the band.
3. A **schema-validate command** and a GitHub Action that runs `verify` on every
   task on push (the workflow is stubbed in `.github/`).
4. **Richer reward-hacking coverage** — negative checks per stage, and a
   "canary flag" that must never appear pre-authorisation.
