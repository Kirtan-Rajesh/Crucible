# Design note — Crucible & its reference tasks

*(One page. The full real-agent iteration log lives in
[docs/calibration.md](docs/calibration.md).)*

**What I optimised for.** The brief calls reward design "the most important part"
and says an uncalibrated task "is not done." So I built two layers: reference
*tasks* worth grading, and a reusable *harness* (grading, calibration, an
acceptance gate) — because at a training-data shop the recurring cost is
authoring many calibrated tasks, not one. With the extra time I proved that the
harness is the real asset by shipping a *second* task (`nonce-forge`, crypto)
through it with zero changes to `harness/`, rather than just describing how one
would.

**Key task decisions.**
- *A strict linear chain, so partial credit is objective and monotonic.* Every
  stage leaves an unambiguous fingerprint (a status, a banner, a doc name, a
  verified signature, the flag); the grader awards furthest-checkpoint credit, so
  reward only increases toward the flag. Branchy puzzles make reward subjective; a
  chain makes it a lookup.
- *The hard part is a real insight, not a guess.* `edge-pivot` chains three bug
  classes so the flag is never on the box you can reach (the collector has no
  published port and gates on a header — the SSRF is load-bearing). `nonce-forge`
  is one sharp insight (ECDSA nonce reuse → private-key recovery by algebra) that
  can't be brute-forced.
- *A deliberately awkward final stage, so it isn't free.* An early `edge-pivot`
  draft ended at "search leaks the flag" (~100% solve); making the leak a *deploy
  key* that must be replayed moved it off saturation. `nonce-forge` won't sign the
  required claim directly, so key recovery is necessary, not just sufficient.

**Key harness decisions.**
- *A tiny contract* (five files + two code interfaces) means a new task inherits
  grading, calibration, gating, schema-validation, and both run modes for free.
- *Measured, then enforced, with real variance.* `gate` turns the acceptance
  numbers into CI PASS/FAIL; `--seed-repeats N` runs independent seed batches and
  reports the spread — which caught a real bug (`nonce-forge`'s naive profile
  measured a bogus 83% from a per-turn retry loop before it was fixed to a
  one-shot decision, now ~18%).
- *Anti-gaming built in and tested.* Final stages credit the flag only from an
  authorised response, and a rubric `guards:` block voids the entire score if the
  flag appears earlier; `tests/test_guards.py` proves it on both tasks.

**The centerpiece honesty finding.** "Competent agent solves ~90%" is a number
the *scripted* policy was tuned to produce, not a measurement. `llm_agent.py`
drives the identical service through a real model (Gemini 2.5 Flash), same
grader, no hints. Running it live also caught a bug in my *own* eval harness —
the agent's JSON extractor used a greedy brace match that swallowed the model's
action whenever it trailed reasoning prose, stalling the agent; fixed to decode
the first valid action object (earlier per-run figures were measured through that
bug and are superseded). **Corrected:** at the 16-turn budget `gemini-2.5-flash`
solves **0/6** (thinking on and off). Transcripts show why it's honest difficulty
— the model does recon and finds the operator-gated endpoint but never discovers
the mass-assignment (it changes `user`, never `role`). So the scripted proxy's
~92% is an optimistic upper bound and the task has real headroom for a mid-tier
model. The gate stays pinned to the scripted baseline (`report.json`); real-agent
runs live in `report.llm-fixed-*.json`. Full log:
[docs/calibration.md](docs/calibration.md).

**Limitations (flagged, not hidden).** The corrected real-agent numbers are
small-sample (n=6 at 16 turns) and cover one mid-tier model; a fuller sweep
across budgets and stronger models is the obvious next step. `llm_agent.py`'s
one-call-per-turn interface is deliberately simple, so its numbers are a property
of *this* scaffold, not the task's ceiling. Containers were verified on Podman,
not Docker (compose targets both).

**What I'd do with more time.** Wider real-agent samples and a second model; a
richer per-turn action space to test how much of the 16-turn gap is scaffold vs.
genuine; a pwn/rev task to exercise the Track-B tier ladder against the check DSL;
more structural per-instance randomization for large-scale rollouts.

**AI assistance.** Built with Claude Code (design, implementation, and the
real-agent harness) under my direction; every design choice and number here I can
explain and defend. Commit trailers record where.
