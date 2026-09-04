# Live walkthrough — 45-minute session prep

Two parts: a rehearsed ~6-minute demo that runs the task live, and an
anticipated-questions sheet. The goal of the demo is to show, in order, the four
things this project is really about: **it runs**, **the reward is dense and
ordered**, **the reward resists gaming**, and **the difficulty is measured, not
claimed**.

---

## Pre-flight (do this before the call)

```bash
cd Crucible-Provue-Assignment
python -m venv .venv && . .venv/Scripts/activate     # or .venv/bin/activate
pip install -r requirements-tools.txt
```

Everything below runs in **local mode** (no container engine needed), so it can't
fail on their machine's Docker. Have a second terminal ready. Do one dry run of
the whole script the morning of.

---

## The demo (≈6 minutes)

### 1. It runs, and it's a real chain (90s)
> "One command solves the reference task and grades the run against the rubric."

```bash
python -m harness.cli solve edge-pivot
```
Point at the 5 stages printing in order, then the `14/14  solved=True` table.
> "Five distinct insights — recon, a mass-assignment privesc, an SSRF via a URL
> parser differential, a search-bug exfil, then credential reuse. The flag is
> never on the box you can reach; it's on an internal service with no published
> port, so the pivot is load-bearing, not decorative."

### 2. The reward is dense and ordered — the part they weight most (90s)
```bash
python -m harness.cli analyze edge-pivot --rollouts 40
```
Point at `stage_reach` (a gradient, e.g. 95→85→70→60→55%), `monotonic: true`, and
`failed_partial_credit_rate`.
> "Every checkpoint is exercised, reward never decreases within a rollout, and —
> the key property for RL — around 85–90% of *failed* rollouts still earn partial
> credit. A failed attempt still teaches something; that's what makes this
> trainable rather than a sparse pass/fail label."

### 3. …and it's the actual dataset, with anti-gaming built in (120s)
```bash
python -m harness.cli export edge-pivot --rollouts 20
head -c 400 tasks/edge-pivot/dataset/rl.jsonl        # dense per-step rewards
```
> "Export emits what a training pipeline consumes: an SFT demonstration and RL
> rollouts with per-step rewards straight from the rubric."

Now break the reward on purpose:
```bash
python tasks/edge-pivot/tests/test_reward_robustness.py
```
> "I red-team my own reward function. Here I take a real solve and mutate it into
> the obvious hacks — echo the flag early, surface it outside the authorised
> response, or just claim it in one turn. The grader plus a rubric `guard` void
> the **entire** transcript to zero in every case, while the legitimate solve
> still scores full. A leaked reward signal means nothing about the run is
> trusted."

### 4. Difficulty is measured and enforced (60s)
```bash
python -m harness.cli gate edge-pivot
```
> "Calibration isn't a claim — `gate` enforces the assignment's numbers as
> PASS/FAIL, and it runs in CI. Competent agent solves ~92% at the 16-turn
> budget with a real ~8% failure and a naive floor near 9% — inside the learnable
> band, with a genuine skill gradient."

### 5. It generalizes (30s)
```bash
python -m harness.cli solve nonce-forge
```
> "Same harness, zero changes — a crypto task (ECDSA nonce reuse). The reusable
> asset is the contract, not the web bug."

**If you have time / they ask about real agents:** open
`docs/calibration.md` and walk the real-model (Gemini) measurement — the honest
finding that the scripted proxy oversells a real agent at 16 turns, and the
diagnosis.

---

## Anticipated questions (tight answers)

**Why furthest-checkpoint (monotonic) credit instead of scoring each stage
independently?** The task is a strict chain, so reaching stage N is proof stages
1..N-1 happened. Crediting "highest checkpoint reached" makes partial reward
provably monotonic toward the flag and immune to out-of-order noise — you can't
farm reward by triggering a late signal without the earlier progress.

**How do you stop reward hacking at scale?** Two layers, both tested. The final
stage credits the flag only from an *authorised* response (not any appearance of
the flag string). On top, a rubric `guards:` invariant voids the whole
transcript if the flag surfaces before it's legitimately earned. `negate` checks
extend this. The red-team test is the regression suite for it.

**Your competent number is from a scripted agent — isn't that circular?** Yes,
and I say so plainly. The scripted profile is a tuned *assumption*; I measured a
real model against the identical service and it does not hit the band at 16
turns. I deliberately did **not** retune the task or the proxy to make them
agree — that would just hide the gap. The gate stays pinned to the declared
baseline; the real-agent runs live in separate files. The honest next step is a
difficulty *curve* across stronger models and budgets.

**Why is ~90% the right competent solve rate?** The bar is "competent agent fails
< 40%." ~90% clears it comfortably without being trivial (median ~10 of 16 turns
actually used, 5 distinct insights). The naive profile (~9%) is the weak-policy
floor — the gap between them is the reward gradient a trainer climbs.

**How would you turn this into a curriculum?** Per-instance difficulty knobs:
hint verbosity, decoy density, and turn budget are already partly seed-driven;
expose them as tiers and gate each (the assignment's Track-B Basic/Intermediate/
Advanced ladder maps straight onto per-tier targets). Then order rollouts easy→
hard during training.

**How does this scale to many tasks?** The harness is task-agnostic; a task is
five files plus two code interfaces (a solver command, an agent policy). Grading,
calibration, the gate, schema validation, and both run modes are inherited.
`nonce-forge` was built with zero changes to `harness/` — that's the proof.

**How would a non-web category (pwn/rev) fit the same rubric?** The check DSL
matches observable signals in a transcript; those don't have to be HTTP. A pwn
task's checkpoints are a crash signature, an ASLR-defeating leak, then a shell/
flag — same monotonic-chain shape, same grader. `docs/extending.md` sketches it.

**Is it reproducible / deterministic?** Reference solution is 16/16 reliable,
sub-second, cold container build ~30s (verified on Podman; compose targets Docker
too). Fully offline after build, ≤256 MB per service. Secrets and flag derive
from `CRUCIBLE_SEED` (HMAC), so instances are unique per rollout yet reproducible
— anti-memorization without sacrificing determinism.

**Why two tasks when the brief said "not volume"?** The primary deliverable is
one deeply-worked task (`edge-pivot`). The second exists only to demonstrate the
harness generalizes rather than assert it — different category, same contract,
no harness changes. I'd rather show the reusable asset than describe it.

**What's original vs. standard?** The applications, endpoints, chains, and flags
are original. The underlying techniques (mass assignment, SSRF parser
differential, ECDSA nonce reuse) are standard and cited — the challenge tests
reasoning over a novel chain, not knowledge of a secret trick.

**How was AI used?** Built with Claude Code under my direction, disclosed in the
README/DESIGN_NOTE/SUBMISSION. Every design decision and number is one I can
derive and defend — this session is that proof.

**What would you do with more time?** (1) The real-agent difficulty curve across
stronger models. (2) A pwn/rev tier ladder. (3) Wider structural randomization
for large-scale rollouts. (4) A richer per-turn agent interface to separate
scaffold-limited from genuinely-hard.

---

## If something breaks live
- Everything is `--mode local`; no Docker dependency.
- If a port is busy, the local runner starts fresh each command — just re-run.
- Worst case, `python tasks/edge-pivot/solver.py --base ...` against a
  `python -m harness.cli up edge-pivot` container path is the fallback.
- Keep `tasks/edge-pivot/report.md` and `reward_analysis.md` open in a tab as
  static backups of the numbers.
