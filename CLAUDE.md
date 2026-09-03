# CLAUDE.md

Guidance for Claude Code (and humans) working in this repository. Read this
first. It captures how the project is structured, how to run and verify it, the
invariants not to break, and where to take it next.

## What this project is

**Crucible** — an authoring, reward, and calibration harness for *runnable*
security tasks used as **SFT/RL training data** for AI agents. It was built for
an "AI Researcher — Cybersecurity Training-Data Design" take-home (Track A:
"author one original, runnable CTF with staged rewards"), but deliberately
generalized so the evaluation machinery is reusable across many tasks, not one.

Two layers:
- **`harness/`** — task-agnostic engine: grading, calibration, an acceptance
  gate, schema validation, environment runner, and a CLI. Knows nothing about
  any specific challenge.
- **`tasks/<id>/`** — concrete challenges that conform to a small contract and
  inherit grading/calibration/gate for free. Ships two reference tasks:
  `edge-pivot` (web) and `nonce-forge` (crypto) -- proving the contract
  generalizes across categories rather than asserting it.

The pitch: *the reusable asset is the contract, not any single challenge.*

## Repository map

```
harness/
  grader.py        staged-reward grader (schema-driven, monotonic credit, `negate`,
                    `guards:` anti-reward-hacking -- a guard violation voids the score)
  calibrate.py     reliability + difficulty-band measurement engine
                    (--seed-repeats for variance evidence, --agent to swap in a
                    real-model policy like llm_agent.py without touching the CI report)
  gate.py          enforce acceptance targets -> PASS/FAIL (CI-friendly)
  validate.py      check task.yaml/rubric.yaml against harness/schema/*.json
  runner.py        bring a task env up/down: container (Docker/Podman) OR local
  cli.py           single entry point: solve/grade/calibrate/gate/validate/verify/up/down
  transcript.py    the transcript format + Recorder (agent<->reward interface)
  schema/*.json    JSON Schemas for the rubric and the task manifest
tasks/edge-pivot/  (web)
  task.yaml        manifest (identity, env, rubric, solver, agent, targets)
  rubric.yaml      staged rewards (observable checks) + guards (anti-reward-hacking)
  solver.py        reference solution; emits a transcript
  agent.py         scripted stochastic agent policy: PROFILES + run_rollout
  llm_agent.py     REAL Gemini-backed agent, same contract -- an honest measurement
                    against the scripted proxy's assumption (see docs/calibration.md)
  run_local.py     no-Docker local env (LocalStack context manager)
  compose.yaml     container env (network-isolated collector; Docker & Podman)
  services/edge/   public API (mass-assignment, SSRF, publish gate)
  services/collector/   internal store (edge-origin gate, search leak) + seed.json
                   + seed-derived decoy documents (anti-memorization noise)
  tests/           test_grader.py, test_guardrails.py, test_guards.py
  report*.md/.json generated calibration output (report.json is the CI-enforced
                    one; report.llm*.json are separate real-agent measurements)
tasks/nonce-forge/ (crypto) -- same shape, one service: ECDSA nonce-reuse
  services/attest/ signs attestations with a nonce that never rotates
tasks/*/tests/test_guards.py   synthetic transcript proving a leaked flag
  voids the whole score even though every stage checkpoint was individually hit
docs/
  contract.md      the task contract + rubric check DSL  (READ THIS to add a task)
  extending.md     how the contract carries crypto/pwn/rev/forensics tasks
                    (crypto is now shipped, not sketched -- see nonce-forge)
  calibration.md   calibration methodology, seed-repeats variance, and the
                    real-agent (Gemini) findings
README.md          the pitch / overview
DESIGN_NOTE.md     1-page design rationale + roadmap
.env               GEMINI_API_KEY (git-ignored; never commit this)
```

## Environment setup (fresh machine / VDI)

Nothing here is committed as a build artifact; set up from scratch:

```bash
# 1) Python 3.11 (3.11.9 used originally; 3.11.x is fine)
python -m venv .venv && . .venv/Scripts/activate     # Windows: .venv\Scripts\activate
#                       . .venv/bin/activate          # Linux/macOS
# 2) tooling deps (solver / grader / calibration)
pip install -r requirements-tools.txt
```

`.venv/` (and the original `.devenv/`) are gitignored and will NOT exist in the
VDI — recreate a venv there. Container work is **optional**: the default `--mode
local` runs the identical service code as local processes and needs no engine.

For containers, install Docker **or** Podman. The harness auto-detects the
provider (`docker compose`, else `podman compose`). Podman needs `podman-compose`
or `docker-compose` on PATH as its compose provider (`pip install podman-compose`).

## Everyday commands

Run from the repo root (the CLI is `python -m harness.cli <cmd> <task>`):

```bash
python -m harness.cli solve     edge-pivot                        # solve (local) + grade
python -m harness.cli verify    edge-pivot                        # validate + tests + calibrate + gate  <- the full check
python -m harness.cli validate  edge-pivot                        # schema-check task.yaml/rubric.yaml only
python -m harness.cli calibrate edge-pivot                        # regenerate report.md/report.json
python -m harness.cli calibrate edge-pivot --seed-repeats 5        # + variance evidence (N independent seed batches)
python -m harness.cli gate      edge-pivot                        # PASS/FAIL vs task.yaml targets
python -m harness.cli up        edge-pivot                        # containers, foreground
python -m harness.cli solve     edge-pivot --mode compose
python -m harness.cli grade     edge-pivot --transcript run.json

# Real-agent (Gemini) measurement -- separate report, does not touch the CI-enforced one:
python -m harness.cli calibrate edge-pivot --agent llm_agent --rollouts 15 \
    --skip-reliability --report-name report.llm   # needs GEMINI_API_KEY (.env or env var)
```

Also works on `nonce-forge` (swap the task name). `Makefile` mirrors the core
commands (`make verify TASK=edge-pivot`). Before committing any change, run
**`verify`** and keep the gate PASS.

## How grading works (don't break these invariants)

- **Transcript** = ordered list of turns `{request:{method,url,body},
  response:{status,text}}`. Everything downstream consumes this, not the live
  service. Schema in `harness/transcript.py`.
- **Rubric** = ordered stages, each with an observable `check` (DSL: `where`,
  `url_contains`, `status_in`/`status_not_in`, `pattern`, `negate`). See
  `docs/contract.md`.
- **Scoring is strictly monotonic "furthest-checkpoint" credit**: stage *i* is
  credited iff it or any later stage was reached. This holds only because each
  task is a strict chain — preserve that when editing a rubric.
- **Anti-reward-hacking**: `s5` credits the flag only from an *authorised* publish
  response (200 from `/api/reports/publish`). Do not loosen this to a bare flag
  regex, or an agent can score by echoing the flag. On top of that, a rubric
  `guards:` entry independently voids the *entire* score if the flag string
  appears in any turn before `s5` is legitimately reached -- belt and suspenders,
  see `harness/grader.py` and `tests/test_guards.py`.

## Calibration & acceptance gate

`calibrate` runs the solver N times (reliability) and drives `agent.py`'s
stochastic policy against the live service under the turn budget (difficulty
band). `--seed-repeats N` runs N independent seed batches instead of one fixed
sequence and reports the spread, not just a single number. `gate` checks the
report against `task.yaml -> calibration.targets`.

Current measured numbers (regenerate with `calibrate --seed-repeats 5`):
- **edge-pivot**: reference reliability 16/16 (~0.76s, 6 turns); scripted-proxy
  competent **91.6%** mean solve @ 16 turns (range [87%, 94%] over 5 batches,
  median 10 turns), naive **9.2%**; gate PASS.
- **nonce-forge**: reference reliability 16/16 (~0.75s, 5 turns); competent
  **84.2%** mean (range [80%, 89%]), naive **17.8%**; gate PASS.
- **edge-pivot real-agent (Gemini)**: the scripted proxy above is a hand-tuned
  assumption, not a measurement -- `llm_agent.py` drives the identical service
  through an actual model with zero vulnerability hints. First measurement:
  **0/15** at the declared 16-turn budget (1/8 at 24 turns). Diagnosed as turn
  economy, not capability, and iterated four times (state scratchpad ->
  thinking -> reasoning-consistency nudge, after tracing `thoughtsTokenCount`
  collapsing to 0 mid-rollout -> pinned-documentation scratchpad). Nothing
  tested ever reliably solves at 16 turns; best 24-turn result is **50%**
  (thinking *off*, full scaffold) -- the identical prompt change made the
  thinking-enabled profile *worse* (37.5% -> 12.5%), plausibly because it used
  the extra deliberation to chase wrong hypotheses (SQLi, a hand-forged JWT)
  instead of the real bug. Full iteration log, and why none of this touches
  the gate, in `docs/calibration.md#real-agent-measurement-gemini`.

Targets live in each task's `task.yaml`. If you make a task harder/easier,
re-measure and keep the *scripted-proxy* competent solve in **[0.60, ~0.90]**
(≥60% required; avoid saturating at ~100%, which gives no signal) -- and treat
that number as a lower-bound assumption, not ground truth, until it's checked
against a real agent the way edge-pivot's was.

## The edge-pivot attack chain (reference task)

recon (`/api/spec`) → mass-assignment privesc (`/api/session` merges body into
JWT claims) → SSRF via userinfo allowlist-bypass
(`http://telemetry.internal.example@collector:9000/...`) → collector search leaks
the private **deploy key** (`/metrics?q=deploy`) → reuse key at
`/api/reports/publish` (`X-Deploy-Key`) → flag. Full write-up:
`tasks/edge-pivot/README.md`.

## Conventions & invariants

- **Secrets & flag are seed-derived.** `edge` and `collector` derive
  `EDGE_ORIGIN_TOKEN`, `DEPLOY_KEY`, `JWT_SECRET`, and `FLAG` from `CRUCIBLE_SEED`
  (HMAC-SHA256; default `crucible-default`). Same seed on both services → matching
  shared secrets. Default-instance flag: `flag{edge_pivot_556ebc60584f}`.
  Explicit env vars override the derivation.
- **Solver and grader must stay seed-agnostic** (extract by regex/field, never
  hardcode a flag value) so any `CRUCIBLE_SEED` works. For unique RL rollouts:
  `CRUCIBLE_SEED=rollout-42 python -m harness.cli solve edge-pivot`.
- **Pinned builds.** `python:3.11.9-slim-bookworm`, pinned pip deps; keep builds
  deterministic and cold build < 10 min.
- **A task must satisfy the contract** in `docs/contract.md`: manifest + rubric +
  solver (a command) + agent (`PROFILES` + `run_rollout`) + env. The harness reads
  only `task.yaml` to find everything.

## Testing / verifying a change

```bash
python tasks/edge-pivot/tests/test_grader.py        # monotonic partial credit
python tasks/edge-pivot/tests/test_guardrails.py    # all shortcuts closed
python tasks/edge-pivot/tests/test_guards.py        # reward-hack guard voids a leaked flag
python -m harness.cli verify edge-pivot             # all of the above + validate + calibrate + gate
```

Same three test names under `tasks/nonce-forge/tests/`. All test scripts start
their own local stack, so they run standalone.

## Known gotchas (learned the hard way)

- **Podman-on-Windows host port-forwarding was flaky on an earlier verification
  pass** (needed solving from an attacker container on the task network instead
  of `localhost`); on this machine's Podman version, `localhost:8080` after
  `compose up -d` works directly. Treat it as environment-dependent -- if
  `localhost` hangs, fall back to
  `podman run --rm --network <task>_public ... python - --base http://edge:8080`.
- **podman-compose runs exec-form healthchecks via `/bin/sh`**, which breaks on
  inline-Python parentheses. That's why each service ships a `healthcheck.py`
  invoked as `["CMD","python","/app/healthcheck.py"]` — keep healthchecks free of
  shell metacharacters.
- **Git Bash mangles `/tmp/...` CLI args** to the Windows temp dir while in-script
  string literals resolve differently — don't mix the two; prefer explicit paths
  or in-process tests.
- **Local-mode ports are not auto-freed.** `run_local.py`'s `LocalStack` always
  binds `127.0.0.1:8080` (`:9000` too for edge-pivot's collector); a process you
  started manually and forgot to tear down (Ctrl+C, or the context manager exit)
  will silently make the *next* task's local solve talk to the *previous* task's
  service and fail in confusing ways. If a solve returns unexpected endpoints,
  `netstat -ano | grep 8080` and check what's actually listening before
  suspecting the task code.
- **Heavy `--mode local` churn can exhaust Windows ephemeral ports.** Each HTTP
  request opens a fresh short-lived connection; after enough back-to-back
  calibration runs (thousands of localhost requests in one session), Windows
  can accumulate tens of thousands of `TIME_WAIT` sockets and start failing new
  binds with `WinError 10048`, which surfaces as a spurious mid-solve
  `ConnectionError` that looks like a service crash but isn't — check
  `netstat -ano | grep TIME_WAIT | wc -l`; if it's enormous, wait ~2-3 minutes
  for entries to expire, or use `--mode compose` (containers don't share the
  host's ephemeral port table the same way) for a long test session. Not
  something CI hits (fresh runner per job).
- **LF→CRLF warnings** on Windows are harmless.

## Adding a new task (the point of the framework)

1. `cp -r tasks/edge-pivot tasks/<new>` and gut the `services/`.
2. Update `task.yaml` (id, category, flag regex, targets).
3. Build the challenge; write `rubric.yaml` with 3–5 observable checkpoint checks
   (`python -m harness.cli validate <new>` catches a malformed one immediately).
4. Write `solver.py` (emit a transcript) and `agent.py` (`PROFILES` +
   `run_rollout`) -- make the "naive" profile's failure mode a genuine one-shot
   miss, not a per-turn retry that converges to near-certain success given
   enough turns (this bit `nonce-forge` during authoring: naive measured 83%
   before the fix).
5. `python -m harness.cli verify <new> --seed-repeats 5` until the gate passes
   *and* the competent/naive spread looks like a real gradient, not saturation.

See `docs/extending.md` for category-specific sketches (pwn/rev/forensics still
open; crypto is now shipped as `nonce-forge`).

## Roadmap — how to make it better (prioritized)

1. **A pwn or rev task** to further stress-test the contract (crypto and web are
   both shipped now) -- the Track-B Basic/Intermediate/Advanced gradient in the
   assignment maps naturally onto a pwn tier ladder.
2. **Push `llm_agent.py`'s scaffold further.** The turn-economy diagnosis was
   confirmed across four iterations (best: 50% at 24 turns, up from 12.5%),
   but nothing tested reaches the declared 16-turn budget, and it's still
   one-bare-HTTP-call per turn -- richer per-turn context (full prior bodies,
   not trailing summaries) is the natural next lever before concluding how
   much of the remaining gap to the scripted proxy's 91.6% is scaffold-shaped
   vs genuinely hard. Also worth a controlled ablation: the same
   reasoning-nudge prompt helped the non-thinking profile and hurt the
   thinking one (37.5% -> 12.5%) -- currently just a plausible transcript
   reading, not confirmed.
3. **Wider real-agent sample sizes and a second model** once cost allows --
   current n=8-15 per run are enough to see a real, repeatable, and
   repeatably-improvable gap from the scripted proxy, not enough for a tight
   confidence interval or to know if the recipe generalizes past Gemini.
4. **More per-instance randomization** beyond secrets and decoy documents
   (internal hostnames, endpoint names) with a turn-cost model to widen the band
   further.
5. **Published calibration artifacts** across pushes (CI already uploads
   `report.md`/`report.json` per task; not yet trended over time).

## Git / commits

- Default branch `main`. No remote configured yet.
- Follow the session's attribution guidance for commit trailers. Run `verify`
  before committing; keep `report.md`/`report.json` in sync when calibration
  changes. Never commit `.env` (it holds `GEMINI_API_KEY`; already git-ignored).
