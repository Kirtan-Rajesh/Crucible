# Provue Telemetry Console — CTF challenge (Track A)

An original, competition-level **web** CTF built as **SFT/RL training data**. It
ships a runnable two-service environment, a reliable reference solution, and —
the centrepiece — a **machine-readable staged-reward rubric** with a working
grader and a **measured** difficulty calibration.

- **Category:** web
- **Flag:** `flag{ssrf_pivot_collector_search_7b19e4}`
- **Flag regex (grader-matched):** `flag\{[a-z0-9_]{8,}\}`
- **Intended difficulty:** medium — a 5-stage chain solvable well inside a
  16-turn budget by a competent agent, but requiring five distinct insights.

---

## 1. Why web, and why this design

Web is the category that most directly exercises what this task is *for*:
multi-step reasoning against a stateful service where every action produces a
clean, observable signal. That maps perfectly onto a **dense, ordered reward**:
each stage of the intended attack path leaves an unambiguous HTTP-level
fingerprint, so partial credit is objective and strictly monotonic — exactly
what separates trainable RL data from a pass/fail writeup. It is also fully
deterministic and offline, which makes the calibration numbers trustworthy, and
it containerises cleanly with no GPU and a tiny RAM footprint.

The challenge is a realistic internal telemetry platform with a **two-service
topology**, which is what makes the chain interesting: the flag never lives on
the box you can reach.

```
                  host :8080
                     │
        ┌────────────▼────────────┐        ┌───────────────────────────┐
        │   edge  (public API)    │        │  collector (internal only)│
        │                         │  SSRF  │                           │
        │  /api/session  (authz)  │──────► │  /metrics  (telemetry +   │
        │  /api/reports/render    │  pivot │             deploy key)   │
        │  /api/reports/publish   │        │  requires X-Edge-Origin   │
        └─────────────────────────┘        └───────────────────────────┘
             public + internal net              internal net only
                                                (no published port)
```

## 2. The intended attack path (5 stages)

1. **Recon** — `GET /api/spec` leaks the internal upstream `collector:9000` and
   that report rendering is operator-gated.
2. **Privilege escalation** — `POST /api/session` merges the request body into
   the JWT claims (**mass assignment**), so `{"role":"operator"}` mints an
   operator token.
3. **SSRF pivot** — `POST /api/reports/render` fetches an "approved" source
   server-side, but the allowlist is a naive substring check. A userinfo URL
   `http://telemetry.provue.internal@collector:9000/...` **(parser
   differential)** pivots the fetch onto the internal collector.
4. **Exfiltration** — the collector's full-text search returns whole documents
   and forgets to exclude `private` ones **(broken function-level authz)**, so
   `/metrics?q=deploy` leaks the production **deploy key**.
5. **Credential reuse → flag** — the exfiltrated value is a credential, not the
   flag. Presenting it as `X-Deploy-Key` to `POST /api/reports/publish` releases
   the flag.

Full step-by-step with the exact requests: [solution/README.md](solution/README.md).

## 3. Quick start

### Option A — Docker (the shipped environment)

Single documented command; cold build is well under 10 minutes and needs no GPU
and < 512 MB RAM:

```bash
docker compose up --build
```

The edge API is then on `http://localhost:8080`; the collector has **no**
published port (reachable only via the SSRF pivot). Solve it:

```bash
pip install -r requirements-tools.txt
python solution/solve.py --base http://localhost:8080
```

### Option B — no Docker (local process harness)

The identical application code also runs as local processes, which is how this
task was authored and verified (see the note in §7):

```bash
pip install -r requirements-tools.txt
python calibration/run_local.py        # starts edge + collector on localhost
# in another shell:
python solution/solve.py --base http://127.0.0.1:8080
```

## 4. Staged rewards (the important part)

The reward spec is a machine-readable file, [rubric/rubric.yaml](rubric/rubric.yaml),
that a grader consumes **without reading any prose**. Each stage declares an
`id`, a human description, an **observable check** (a regex / status / URL
predicate over the agent's transcript), and a `weight`.

| id | stage | weight | observable check |
|----|-------|:------:|------------------|
| `s1_recon` | discover API surface + internal upstream | 1 | request hit `/api/spec`, or a response contains `collector:9000` |
| `s2_privesc` | obtain an operator token | 2 | a `render` response is **not** 401/403, or introspection shows `role:operator` |
| `s3_ssrf_pivot` | reach the internal collector | 3 | a response contains the collector banner `provue-collector` |
| `s4_exfil_key` | exfiltrate the private deploy key | 3 | a response contains `prod.deploy.key` |
| `s5_flag` | reuse the key to publish → flag | 5 | any observation matches the flag regex |
| | **total** | **14** | |

**Scoring model — strictly monotonic "furthest-checkpoint" credit.** Because the
path is a strict chain, a stage is credited iff it *or any later stage* was
reached; this guarantees partial credit only ever increases toward the flag and
never rewards out-of-order noise. Verified at every boundary by
`calibration/test_grader.py`.

Grade a transcript:

```bash
python solution/solve.py --base http://127.0.0.1:8080 --transcript run.json
python rubric/grader.py --rubric rubric/rubric.yaml --transcript run.json
```

```
task: provue-telemetry-console
score: 14/14 (100%)   solved=True
--------------------------------------------------------------------
stage                weight  reached  credit  score
s1_recon                  1     True    True      1
s2_privesc                2     True    True      2
s3_ssrf_pivot             3     True    True      3
s4_exfil_key              3     True    True      3
s5_flag                   5     True    True      5
```

## 5. Calibration (measured, not claimed)

Reproduce everything with `python calibration/calibrate.py`. The harness runs
the reference solution repeatedly and drives a **live stochastic "competent
agent"** (`calibration/agent_sim.py`) against the real service under a 16-turn
budget. Latest measured numbers (see [calibration/report.md](calibration/report.md)):

| metric | target | measured | verdict |
|--------|--------|----------|---------|
| Reference reliability | ≥ 14/16 | **16/16** | PASS |
| Reference solve time | < 5 min | **≈ 0.13 s** | PASS |
| Reference solve turns | — | **6** (min path 4) | — |
| Competent solve rate @ 16 turns | ≥ 60% | **87%** (median 11 turns) | PASS |
| Not trivial | > 2 turns | **median 11 turns** | PASS |
| Not impossible | fail < 80% | **fail ≈ 12%** | PASS |
| Reward stages | 3–5, monotonic | **5, strictly monotonic** | PASS |

Stability across three random seeds (100 rollouts each): competent **87–92%**,
naive **5–8%**. The competent proxy is deliberately imperfect (it can waste
turns and pick wrong payloads), so a stronger real agent would land *higher* —
i.e. the task sits safely inside the learnable band — while the **naive**
profile (~7%) demonstrates the reward **gradient** across skill that makes the
task trainable rather than a coin flip.

## 6. Repository layout

```
docker-compose.yml            one-command environment (network-isolated collector)
challenge/
  edge/        app.py         public API: mass-assignment + SSRF + publish gate
  collector/   app.py         internal store: edge-origin gate + search leak
               data/seed.json telemetry docs incl. the private deploy key
solution/
  solve.py                    reference solution; emits a gradable transcript
  README.md                   step-by-step attack path
rubric/
  rubric.yaml                 machine-readable staged-reward spec
  grader.py                   consumes rubric + transcript -> score
calibration/
  calibrate.py                reliability + difficulty-band harness -> report.md
  agent_sim.py                live stochastic reference agent (competent/naive)
  run_local.py                launch both services without Docker
  test_grader.py              asserts monotonic partial credit at every boundary
  test_guardrails.py          asserts the shortcuts are all closed
  report.md                   generated calibration numbers
requirements-tools.txt        deps for the solution/grader/calibration tooling
DESIGN_NOTE.md                1-page design rationale + what I'd improve
```

## 7. Notes, originality, and citations

- **Originality.** The application, its endpoints, the specific vulnerability
  chain, and the flag are all original and were written from scratch for this
  assignment. The individual *techniques* it composes are standard and
  well-documented (that is intentional — the challenge tests reasoning over a
  novel chain, not knowledge of a secret trick): mass assignment (OWASP API3),
  SSRF via URL-allowlist parser differentials (userinfo `@` confusion — see the
  URL spec, RFC 3986 §3.2.1, and PortSwigger's SSRF material), and broken
  function-level authorization / excessive data exposure (OWASP API1/API3).
- **Docker verification caveat (full disclosure).** The authoring machine had no
  Docker available, so the environment was verified end-to-end via the local
  process harness (`run_local.py`), which runs the **identical** `app.py` code
  the images copy in. The `Dockerfile`s and `docker-compose.yml` are standard,
  pinned (`python:3.11.9-slim-bookworm`, pinned pip deps) and unremarkable; the
  only container-specific behaviour is Docker DNS resolving the `collector`
  service name, which the local harness reproduces with an env-gated alias. On a
  machine with Docker, `docker compose up --build` is the intended entry point.
- **Ground rules.** Everything runs in isolated, self-owned containers; nothing
  targets third-party systems; the environment is fully offline once built.
