# Reward signal-quality analysis — edge-pivot

120 stochastic-agent rollouts (competent + naive), graded by the
rubric. Regenerate: `python -m harness.cli analyze edge-pivot`.

- Solve rate: **47.5%**   mean score **8.72/14**
- Reward is monotonic within every rollout: **VERIFIED**

## Every checkpoint is exercised (per-stage reach frequency)

| stage | weight | reached |
|---|---|---|
| `s1_recon` | 1 | 99% |
| `s2_privesc` | 2 | 92% |
| `s3_ssrf_pivot` | 3 | 64% |
| `s4_exfil_key` | 3 | 53% |
| `s5_flag` | 5 | 48% |

A stage reached by ~0% or ~100% of rollouts carries little training signal; a
spread across stages means the reward discriminates partial progress.

## Dense signal on failed rollouts

The point of staged rewards is that a *failed* attempt still teaches something.

- Failed rollouts: **63**
- …of which earned partial credit (> 0): **62**
  (**98.4%**)
- Mean score among failed rollouts: **3.95/14**

A high partial-credit rate on failures is exactly what makes this trainable with
RL rather than a sparse pass/fail label.

## Final-score distribution

| score (of 14) | rollouts |
|---|---|
| 0 | 1 |
| 1 | 9 |
| 3 | 33 |
| 6 | 13 |
| 9 | 7 |
| 14 | 57 |
