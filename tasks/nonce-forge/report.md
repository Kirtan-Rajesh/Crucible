# Calibration Report — nonce-forge

Environment mode: **local**   turn budget: **16**   agent: **agent**   (regenerate: `python -m harness.cli calibrate nonce-forge`)

## Reference-solution reliability

- Successes: **16/16** (reliability 100.0%)
- Reference solve turns: **5**
- Median wall-clock: **0.556 s**, max **0.747 s**

## Difficulty band (live agent)

| profile | rollouts | solved | solve rate | median turns | batches | rate range (mean +/- stdev) |
|---|---|---|---|---|---|---|
| competent | 500 | 421 | 84.2% | 6 | 5 | [80.0%, 89.0%] (84.2% +/- 3.2pp) |
| naive | 500 | 89 | 17.8% | 9 | 5 | [16.0%, 21.0%] (17.8% +/- 2.5pp) |

_Each profile is measured as N independent, non-overlapping seed batches (not one fixed sequence); the range/stdev columns are the actual spread across those batches, so a solve rate near a target boundary is evidence, not a coincidence of one seed._
