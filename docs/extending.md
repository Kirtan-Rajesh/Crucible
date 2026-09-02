# Extending Crucible to other categories

The reusable asset is **the contract**, not the web bug. A task in any category
that emits a transcript of observable checkpoints inherits the grader, the
calibration engine, and the acceptance gate unchanged. What changes per category
is only the *environment*, the *reference solver*, and the *checkpoint signals*.

The design pattern that transfers: **a strict chain of 3–5 observable
checkpoints, each depending on the last, ending in the flag**, with a stochastic
agent policy so the difficulty band can be measured. Below is how each category
maps onto it.

### crypto — `nonce-reuse-oracle`
- **Environment:** a service that signs/encrypts under a scheme with a planted
  flaw (e.g. ECDSA nonce reuse, CBC padding oracle, or a truncated-MAC check).
- **Chain:** recon the scheme → collect two signatures/ciphertexts → detect the
  flaw (repeated nonce / oracle behaviour) → recover the key → forge a token / a
  request that unlocks the flag.
- **Checkpoints (observable):** obtained ≥2 samples; demonstrated the oracle
  distinguisher; recovered a value matching the key format; presented a forged
  artifact accepted with status 200. Same grader, same `status_in`/`pattern`
  checks.

### pwn — `off-by-one-service`
- **Environment:** a small networked C binary (compiled in the container) with a
  known-class memory bug; NX on, ASLR togglable per tier.
- **Chain / difficulty gradient** (mirrors the Track-B ladder): trigger a crash
  (checkpoint: service returns a crash signature / non-zero exit) → leak an
  address to defeat ASLR (checkpoint: leaked pointer in output) → ROP to a
  one-shot that prints the flag (checkpoint: flag in output).
- The transcript records each interaction; checks match the crash marker, the
  leak, and the flag. Calibration reports per-tier solve rates.

### rev — `licensed-binary`
- **Environment:** a stripped binary that prints the flag only for a valid
  license key derived by an obfuscated check.
- **Chain:** identify the check routine → recover the constraint → synthesise a
  key → binary prints the flag. Checkpoints: correct key *length/format*
  accepted, partial constraint satisfied (staged), full key accepted. Reward
  granularity comes from constraint sub-goals rather than network stages.

### forensics — `exfil-pcap`
- **Environment:** a capture / disk image plus a tiny viewer service, all offline.
- **Chain:** locate the suspicious stream → carve the transferred object →
  decode/decrypt it → extract the flag. Checkpoints: referenced the right
  stream id, carved artifact hash present, decoded plaintext marker, flag.

### misc — `multi-step-automation`
- Any puzzle expressible as ordered, checkable steps (a protocol state machine, a
  constraint solver, a scripting gauntlet). If the steps are observable, the
  contract applies.

## What stays identical across all of them

- `rubric.yaml` shape and the check DSL.
- `harness/grader.py` (monotonic furthest-checkpoint credit).
- `harness/calibrate.py` + `agent.py` contract (`PROFILES` + `run_rollout`).
- `harness/gate.py` acceptance targets — including the Track-B expectation that
  pass rate drops across tiers (encode one target set per tier, or one task per
  tier, and gate each).
- The transcript format and the two run modes (container / local).

Adding a category is therefore "write the service + solver + checkpoint patterns,"
not "rebuild the evaluation harness." That is the pitch.
