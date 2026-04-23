# Experiment 4.2 — Communication Performance

This directory preserves the artefacts used for the Unix pipe communication benchmark described in Section 4.2 of the paper.

## Contents
- `src/` — preserved benchmark source files
- `bin/` — preserved compiled binaries
- `raw/` — preserved raw CSV outputs

## Compile and execute in the three modes

All commands below assume execution from `experiments/02_communication/` on ARM Morello / CheriBSD.

### Outside compartment (baseline)

```bash
mkdir -p rerun/outside
clang-morello -g -o bin/pipe-out-experiment src/pipe-out-experiment.c -lm
(
  cd rerun/outside
  ../../bin/pipe-out-experiment
)
```

Generated CSV:
- `rerun/outside/pipe-out-experiment-results.csv`

### purecap ABI

```bash
mkdir -p rerun/purecap
clang-morello -march=morello -mabi=purecap -g -o bin/pipe-in-experiment-purecap src/pipe-in-experiment-purecap.c -lm
(
  cd rerun/purecap
  proccontrol -m cheric18n -s enable ../../bin/pipe-in-experiment-purecap
)
```

Generated CSV:
- `rerun/purecap/pipe-in-experiment-purecap-results.csv`

### purecap-benchmark ABI

```bash
mkdir -p rerun/benchmark
clang-morello -march=morello -mabi=purecap-benchmark -g -o bin/pipe-in-experiment-purecap-benchmark src/pipe-in-experiment-purecap-benchmark.c -lm
(
  cd rerun/benchmark
  proccontrol -m cheric18n -s enable ../../bin/pipe-in-experiment-purecap-benchmark
)
```

Generated CSV:
- `rerun/benchmark/pipe-in-experiment-purecap-benchmark-results.csv`

## Archived raw references

- `raw/pipe-out-experiment-results.csv`
- `raw/pipe-in-experiment-purecap-results.csv`
- `raw/pipe-in-experiment-purecap-benchmark-results.csv`

## Important note

The benchmark execution itself is preserved here. The published communication analysis was performed manually and is archived under `../../analyses/02_communication/`.
