# Reward signal-quality analysis — nonce-forge

120 stochastic-agent rollouts (competent + naive), graded by the
rubric. Regenerate: `python -m harness.cli analyze nonce-forge`.

- Solve rate: **55.0%**   mean score **9.53/14**
- Reward is monotonic within every rollout: **VERIFIED**

## Every checkpoint is exercised (per-stage reach frequency)

| stage | weight | reached |
|---|---|---|
| `s1_recon` | 1 | 100% |
| `s2_pubkey` | 1 | 100% |
| `s3_signature_collected` | 2 | 100% |
| `s4_forged_signature_verified` | 4 | 56% |
| `s5_flag` | 6 | 55% |

A stage reached by ~0% or ~100% of rollouts carries little training signal; a
spread across stages means the reward discriminates partial progress.

## Dense signal on failed rollouts

The point of staged rewards is that a *failed* attempt still teaches something.

- Failed rollouts: **54**
- …of which earned partial credit (> 0): **54**
  (**100.0%**)
- Mean score among failed rollouts: **4.07/14**

A high partial-credit rate on failures is exactly what makes this trainable with
RL rather than a sparse pass/fail label.

## Final-score distribution

| score (of 14) | rollouts |
|---|---|
| 4 | 53 |
| 8 | 1 |
| 14 | 66 |
