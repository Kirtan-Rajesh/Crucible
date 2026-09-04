# Calibration Report — edge-pivot

Environment mode: **local**   turn budget: **16**   agent: **agent**   (regenerate: `python -m harness.cli calibrate edge-pivot`)

## Reference-solution reliability

- Successes: **16/16** (reliability 100.0%)
- Reference solve turns: **6**
- Median wall-clock: **0.448 s**, max **0.484 s**

## Difficulty band (live agent)

| profile | rollouts | solved | solve rate | median turns | batches | rate range (mean +/- stdev) |
|---|---|---|---|---|---|---|
| competent | 500 | 458 | 91.6% | 10 | 5 | [87.0%, 94.0%] (91.6% +/- 2.8pp) |
| naive | 500 | 46 | 9.2% | 14 | 5 | [8.0%, 11.0%] (9.2% +/- 1.6pp) |

_Each profile is measured as N independent, non-overlapping seed batches (not one fixed sequence); the range/stdev columns are the actual spread across those batches, so a solve rate near a target boundary is evidence, not a coincidence of one seed._
