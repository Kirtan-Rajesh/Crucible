# Design note — Provue Telemetry Console

## What I optimised for

The brief says the reward design is "the most important part," and that an
uncalibrated task "is not done." So I treated this less as *"build a cool CTF"*
and more as *"build a task whose every stage emits a clean, checkable signal, and
prove the difficulty with numbers."* Three decisions follow from that.

**1. A strict linear chain, so partial credit is objective and monotonic.**
Every stage leaves an unambiguous HTTP fingerprint — a status code, a banner
string, a document name, the flag regex — and each depends on the previous one.
That lets the grader award "furthest-checkpoint" credit that is *strictly*
monotonic by construction: reaching stage N proves stages 1..N-1 happened, so
credit can only increase toward the flag. Branchy or puzzle-box designs make
reward assignment subjective; a chain makes it a lookup.

**2. Two services, so the pivot is real.** The flag is never on the box you can
reach. The collector has no published port and refuses anything without the
edge-origin header the edge tier injects, so the SSRF is *load-bearing* rather
than decorative — and defended in depth (network isolation **and** an origin
header), which also makes the no-Docker local run faithful. This is what turns a
bag of individual bugs into a chain that requires sustained reasoning.

**3. Credential reuse as the final stage.** Early versions ended at "search
leaks the flag," which a competent agent solved ~100% of the time — too easy to
give signal. Making the leaked value a *deploy key* that must be recognised and
replayed against a privileged endpoint added a genuine long-horizon step. That
single change moved the competent solve rate from saturated to a measured **87%**
(median 11 of 16 turns) — comfortably inside the learnable band, but no longer
free.

## Calibration approach

I measured, rather than asserted. Reliability is the reference solution run 16×
(**16/16**, ~0.13 s). The difficulty band comes from a *live* stochastic agent
that drives the real service under the 16-turn budget: it knows the techniques
but not this target (it must read the spec to learn the internal host), picks
among plausible actions probabilistically, and can run out of budget. A
**competent** profile lands ~87% and a **naive** profile ~8% — the gradient
across skill is the evidence that the task is trainable, not a coin flip.

## Honest limitations

- **The agent model is a proxy, not an LLM.** It is a defensible lower bound on a
  competent agent (a stronger real agent would score higher), but it is scripted.
  The right next step is to run their actual reference agent through the same
  grader — the transcript/rubric interface is already built for exactly that.
- **Docker was verified indirectly.** The authoring machine lacked Docker, so the
  environment was proven via the local harness running identical code; the
  compose/Dockerfiles are standard and pinned but were not built here.

## What I'd do with more time

1. **Randomised instancing** — per-deploy flag, deploy key, internal hostname,
   and search terms, so memorising one rollout doesn't transfer. The code is
   already env-driven; this is mostly a seed generator.
2. **Reward-hacking hardening** — add negative checks to the rubric (e.g. penalise
   printing the flag regex without a preceding authorised `publish`) to close
   trivial spoofing of `s5`.
3. **Decoys with a turn-cost model** — a couple of plausible dead ends (a fake
   admin panel, an unexploitable `debug` param) to widen the band and study how
   agents budget turns.
4. **Cross-category generalisation** — the same rubric/grader/calibration spine
   is category-agnostic. A *crypto* variant swaps the SSRF for a nonce-reuse
   oracle; a *pwn* variant swaps it for a stack overflow; each keeps the "chain
   of observable checkpoints + measured band" contract. That contract, not this
   specific web bug, is the reusable asset.
