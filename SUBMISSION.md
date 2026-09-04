# Submission — Cybersecurity Training-Data Design (Track A)

This is the reviewer's map. It points every requirement and acceptance number to
the file that satisfies it, so nothing has to be taken on trust.

**What this is:** Track A (author an original, runnable CTF with staged rewards),
delivered as **Crucible** — a reusable authoring/reward/calibration harness — plus
**two** original tasks built on it: `edge-pivot` (web, the primary deliverable) and
`nonce-forge` (crypto, shipped to prove the harness generalizes with zero harness
changes). Start at [README.md](README.md); newcomers can read
[docs/guide.md](docs/guide.md) from scratch.

## Run it in 60 seconds (no container engine needed)

```bash
python -m venv .venv && . .venv/Scripts/activate      # or .venv/bin/activate
pip install -r requirements-tools.txt
python -m harness.cli solve  edge-pivot               # solve + grade
python -m harness.cli verify edge-pivot --seed-repeats 5   # validate + tests + calibrate + gate
python -m harness.cli verify nonce-forge --seed-repeats 5
```

Containers (Docker or Podman): `python -m harness.cli up edge-pivot`, then
`solve edge-pivot --mode compose`.

*(For the live session: [docs/walkthrough.md](docs/walkthrough.md) has a rehearsed
demo script and an anticipated-questions sheet.)*

## Deliverables → where they are

| Required deliverable | Location |
|---|---|
| Challenge source + runnable environment | `tasks/<task>/services/`, `tasks/<task>/compose.yaml` |
| One-command build/run | `python -m harness.cli up <task>` (Docker/Podman); or `--mode local` |
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
declared scripted baseline; real-agent runs live in separate `report.llm-v4*.json`
files by design.

## Originality & AI use

Both applications, their endpoints, vulnerability chains, and flags are original
and written from scratch; the underlying *techniques* are standard and cited per
task (see README "Notes"). Built with Claude Code under my direction — every part
is one I can explain and defend in the walkthrough.
