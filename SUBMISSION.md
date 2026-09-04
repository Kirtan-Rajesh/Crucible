# Submission — Cybersecurity Training-Data Design (Track A)

This is the reviewer's map. It points every requirement and acceptance number to
the file that satisfies it, so nothing has to be taken on trust.

**What this is:** Track A (author an original, runnable CTF with staged rewards),
delivered as **Crucible** — a reusable authoring/reward/calibration harness — plus
**two** original tasks built on it: `edge-pivot` (web, the primary deliverable) and
`nonce-forge` (crypto, shipped to prove the harness generalizes with zero harness
changes). Start at [README.md](README.md); newcomers can read
[docs/guide.md](docs/guide.md) from scratch.

## Build & run — one command on a fresh machine (only Docker/Podman)

```bash
docker compose up --build          # or:  podman compose up --build
```

Builds both services and runs the primary task (`edge-pivot`); edge API on
http://localhost:8080, collector internal-only. Second task:
`docker compose -f tasks/nonce-forge/compose.yaml up --build`.

Developed and **verified on Podman** — the compose file is standard, so either
engine works. Podman: `podman machine start` (macOS/Windows, first time) +
`pip install podman-compose`, then the same `podman compose up --build`. If a
Podman machine can't reach `localhost:8080`, the no-engine path
(`python -m harness.cli solve edge-pivot`, `--mode local`) runs the identical code.

## Solve it / run the full checks (needs Python 3.11)

```bash
python -m venv .venv && . .venv/Scripts/activate      # or .venv/bin/activate
pip install -r requirements-tools.txt
python -m harness.cli solve  edge-pivot               # solve + grade (no engine needed)
python -m harness.cli verify edge-pivot --seed-repeats 5   # validate + tests + calibrate + gate
python -m harness.cli verify nonce-forge --seed-repeats 5
```

*(For the live session: [docs/walkthrough.md](docs/walkthrough.md) has a rehearsed
demo script and an anticipated-questions sheet.)*

## Deliverables → where they are

| Required deliverable | Location |
|---|---|
| Challenge source + runnable environment | `tasks/<task>/services/`, `tasks/<task>/compose.yaml` |
| One-command build/run | `docker compose up --build` at the repo root (Docker or Podman; no Python) |
| Reference solution | `tasks/<task>/solver.py` |
| Staged-reward rubric (machine-readable) | `tasks/<task>/rubric.yaml` (+ JSON Schema `harness/schema/`) |
| The grader that consumes it | `harness/grader.py` |
| README (build/run, difficulty, category, attack path) | `README.md`, `tasks/<task>/README.md` |
| Calibration report (measured numbers) | `tasks/<task>/report.md` / `report.json` |
| Design note (1 page) | `DESIGN_NOTE.md` |

## Acceptance criteria — targets vs. measured

Measured on this machine; regenerate any row with
`python -m harness.cli calibrate <task> --seed-repeats 5` then
`python -m harness.cli gate <task>`.

| criterion | target | edge-pivot | nonce-forge |
|---|---|---|---|
| Difficulty band — competent solve @ 16 turns | ≥ 60% | **91.6%** (5×100, range [87,94]) | **84.2%** (5×100, range [80,89]) |
| Not trivial (not solved in ≤ 2 turns) | > 2 turns | 6-turn min chain | 5-turn min chain |
| Not impossible (competent failure) | < 80% | ~8% | ~16% |
| Environment reliability (reference solution) | ≥ 14/16 | **16/16** | **16/16** |
| Reward granularity (gradable stages, monotonic) | 3–5 | **5** | **5** |
| Reference solve time (wall-clock) | < 5 min | **< 1 s** | **< 1 s** |
| Cold container build | < 10 min | ~30 s (Podman) | ~30 s (Podman) |
| Compute | no GPU, ≤ 8 GB | 256 MB/service | 256 MB/service |
| Offline at solve time | required | yes | yes |
| Flag format + exact regex | machine-checkable | `flag\{[a-z0-9_]{8,}\}` | `flag\{[a-z0-9_]{8,}\}` |

`gate` enforces these as PASS/FAIL (non-zero exit on any miss) and runs in CI on
every push. Both tasks currently: **RESULT: PASS**.

## Reward design (the weighted centerpiece)

Beyond the machine-readable rubric, the harness treats reward as a first-class
deliverable:

- **It emits the actual dataset.** `python -m harness.cli export <task>` writes
  `dataset/sft.jsonl` (the reference solve as a tool-call demonstration) and
  `dataset/rl.jsonl` (stochastic rollouts with **dense per-step rewards** from
  the rubric) — the artifact a training pipeline consumes. Schema in `DATA.md`.
- **It measures reward quality.** `analyze` → `reward_analysis.md`: every stage
  is exercised, reward is verified monotonic within each rollout, and **~85–90%
  of *failed* rollouts still earn partial credit** — the dense signal that makes
  this trainable, not sparse pass/fail.
- **It red-teams its own reward.** `tests/test_reward_robustness.py` mutates a
  real solve into reward-hacks (flag echoed early, flag outside the authorised
  response, bare claim) and asserts the grader + `guards:` void all of them.

## The one thing to read closely

The competent solve-rate above is from a **scripted** reference policy — a tuned
assumption, not a measurement. I tested it against a real model
(`tasks/edge-pivot/llm_agent.py`, Gemini) and it does *not* hit that band at 16
turns; I report that gap honestly and diagnose it rather than hide it. This is the
most important design discussion — see the calibration section of
[README.md](README.md) and the full log in
[docs/calibration.md](docs/calibration.md). The CI gate stays pinned to the
declared scripted baseline; real-agent runs live in separate `report.llm-fixed-*.json`
files by design.

### Reproduce the real-agent run (optional — the only step needing an API key)

Everything else — building/running the challenge, the reference solution, the
rubric, the scripted-agent calibration, the gate, and CI — needs **no API key**.
Only reproducing the *real-agent* measurement calls Gemini, so it needs a key:

```bash
export GEMINI_API_KEY=...          # or put GEMINI_API_KEY=... in a .env at repo root (git-ignored)

# Aggregate solve rate + written report (starts its own local stack):
python -m harness.cli calibrate edge-pivot --agent llm_agent --rollouts 6 \
    --skip-reliability --report-name report.llm-fixed-b16      # -> prints bands, writes report.llm-fixed-b16.{json,md}

# Watch the model attack it, one action per turn (see its decisions + the responses):
python -m harness.cli up edge-pivot        # terminal 1 (or: python tasks/edge-pivot/run_local.py)
GEMINI_API_KEY=... python tasks/edge-pivot/llm_agent.py \
    --base http://localhost:8080 --budget 16 --verbose        # terminal 2
```

The `--verbose` run prints each turn's chosen HTTP request and the server's
response, then the final `{solved, turns}`; `calibrate` prints the solve rate and
writes the report files. (Gemini's private "thinking" tokens aren't shown — only
the model's chosen actions and observations.)

## Originality & AI use

Both applications, their endpoints, vulnerability chains, and flags are original
and written from scratch; the underlying *techniques* are standard and cited per
task (see README "Notes"). I used an AI coding assistant as a tool while building
it; the design and decisions are mine, and I can explain and defend every part.
