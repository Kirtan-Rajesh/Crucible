# Calibration Report — Provue Telemetry Console

Measured on the local process stack (identical application code to the Docker image). Numbers are reproduced by `python calibration/calibrate.py`.

## Environment reliability (reference solution)

- Runs: **16**
- Successes: **16/16** (reliability 100.0%)
- Reference solve turns: **6**
- Median wall-clock: **0.133 s**, max **0.156 s**
- Target: >= 14/16 reliability, < 5 min wall-clock -> **PASS**

## Difficulty band (live agent, 16-turn budget)

| profile | rollouts | solved | solve rate | median turns |
|---|---|---|---|---|
| competent | 100 | 87 | 87.0% | 11 |
| naive | 100 | 8 | 8.0% | 15 |

- Competent solve rate **87.0%** (target >= 60%) -> **PASS**
- Not trivial (median solve > 2 turns): **PASS**
- Not impossible (failure < 80%): **PASS**

