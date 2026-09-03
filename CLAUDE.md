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
  gate, environment runner, and a CLI. Knows nothing about any specific challenge.
- **`tasks/<id>/`** — concrete challenges that conform to a small contract and
  inherit grading/calibration/gate for free. Ships one reference task,
  `edge-pivot` (web).

The pitch: *the reusable asset is the contract, not any single challenge.*

## Repository map

```
harness/
  grader.py        staged-reward grader (schema-driven, monotonic credit, `negate`)
  calibrate.py     reliability + difficulty-band measurement engine
  gate.py          enforce acceptance targets -> PASS/FAIL (CI-friendly)
  runner.py        bring a task env up/down: container (Docker/Podman) OR local
  cli.py           single entry point: solve/grade/calibrate/gate/verify/up/down
  transcript.py    the transcript format + Recorder (agent<->reward interface)
  schema/*.json    JSON Schemas for the rubric and the task manifest
tasks/edge-pivot/
  task.yaml        manifest (identity, env, rubric, solver, agent, targets)
  rubric.yaml      staged rewards (observable checks)
  solver.py        reference solution; emits a transcript
  agent.py         stochastic agent policy: PROFILES + run_rollout (for calibration)
  run_local.py     no-Docker local env (LocalStack context manager)
  compose.yaml     container env (network-isolated collector; Docker & Podman)
  services/edge/   public API (mass-assignment, SSRF, publish gate)
  services/collector/   internal store (edge-origin gate, search leak) + seed.json
  tests/           test_grader.py (monotonic credit) + test_guardrails.py (shortcuts closed)
  report.md/.json  generated calibration output
docs/
  contract.md      the task contract + rubric check DSL  (READ THIS to add a task)
  extending.md     how the contract carries crypto/pwn/rev/forensics tasks
  calibration.md   calibration methodology and why the numbers are the right shape
README.md          the pitch / overview
DESIGN_NOTE.md     1-page design rationale + roadmap
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
python -m harness.cli solve     edge-pivot            # solve (local) + grade
python -m harness.cli verify    edge-pivot            # tests + calibrate + gate  <- the full check
python -m harness.cli calibrate edge-pivot            # regenerate report.md/report.json
python -m harness.cli gate      edge-pivot            # PASS/FAIL vs task.yaml targets
python -m harness.cli up        edge-pivot            # containers, foreground
python -m harness.cli solve     edge-pivot --mode compose
python -m harness.cli grade     edge-pivot --transcript run.json
```

`Makefile` mirrors these (`make verify TASK=edge-pivot`). Before committing any
change, run **`verify`** and keep the gate PASS.

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
  regex, or an agent can score by echoing the flag.

## Calibration & acceptance gate

`calibrate` runs the solver N times (reliability) and drives `agent.py`'s
stochastic policy against the live service under the turn budget (difficulty
band). `gate` checks the report against `task.yaml -> calibration.targets`.

Current measured numbers (regenerate with `calibrate`):
- reference reliability **16/16**, solve ~**0.45 s**, **6** turns
- competent agent **~87%** solve @ 16 turns (median 11), naive **~8%**
- gate: **PASS** on all five criteria

Targets live in `tasks/edge-pivot/task.yaml`. If you make the task harder/easier,
re-measure and keep competent solve in **[0.60, ~0.90]** (≥60% required; avoid
saturating at ~100%, which gives no signal).

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
python -m harness.cli verify edge-pivot             # the above + calibrate + gate
```

Both test scripts start their own local stack, so they run standalone.

## Known gotchas (learned the hard way)

- **Podman on Windows does not forward published ports to Windows `localhost`.**
  Verify a container solve from an attacker container on the task network instead:
  `podman run --rm --network edge-pivot_public ... python - --base http://edge:8080`.
  On Docker, `localhost:8080` works normally.
- **podman-compose runs exec-form healthchecks via `/bin/sh`**, which breaks on
  inline-Python parentheses. That's why each service ships a `healthcheck.py`
  invoked as `["CMD","python","/app/healthcheck.py"]` — keep healthchecks free of
  shell metacharacters.
- **Git Bash mangles `/tmp/...` CLI args** to the Windows temp dir while in-script
  string literals resolve differently — don't mix the two; prefer explicit paths
  or in-process tests.
- **LF→CRLF warnings** on Windows are harmless.

## Adding a new task (the point of the framework)

1. `cp -r tasks/edge-pivot tasks/<new>` and gut the `services/`.
2. Update `task.yaml` (id, category, flag regex, targets).
3. Build the challenge; write `rubric.yaml` with 3–5 observable checkpoint checks.
4. Write `solver.py` (emit a transcript) and `agent.py` (`PROFILES` +
   `run_rollout`).
5. `python -m harness.cli verify <new>` until the gate passes.

See `docs/extending.md` for category-specific sketches (crypto/pwn/rev/forensics).

## Roadmap — how to make it better (prioritized)

1. **Second task in another category** (e.g. crypto nonce-reuse oracle, or a pwn
   tier ladder mirroring the Track-B Basic/Intermediate/Advanced gradient) to
   prove the contract's generality end-to-end, not just on paper.
2. **`crucible validate`** command that checks each `rubric.yaml`/`task.yaml`
   against the JSON Schemas (add `jsonschema` to tooling deps).
3. **Richer anti-reward-hacking**: per-stage negative checks and a "canary" value
   that must never appear before authorisation.
4. **More per-instance randomization** beyond secrets (internal hostname, search
   terms, decoy endpoints) with a turn-cost model to widen the band.
5. **Swap the scripted agent for a real LLM agent** in calibration — the
   transcript/rubric interface is already built for it; report both numbers.
6. **Multi-task CI matrix** and published calibration artifacts.

## Git / commits

- Default branch `main`. No remote configured yet (set one in the VDI:
  `git remote add origin <url> && git push -u origin main`).
- Follow the session's attribution guidance for commit trailers. Run `verify`
  before committing; keep `report.md`/`report.json` in sync when calibration
  changes.
