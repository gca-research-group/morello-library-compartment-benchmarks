# Experiment 4.1 — Memory Performance

This directory preserves the artefacts used for the memory benchmark described in Section 4.1 of the paper.

## Contents
- `src/` — preserved benchmark source files
- `bin/` — preserved compiled binaries
- `raw/` — preserved raw CSV outputs

## Compile and execute in the three modes

All commands below assume execution from `experiments/01_memory/` on ARM Morello / CheriBSD.

### Outside compartment (baseline)

```bash
mkdir -p rerun/outside
clang-morello -g -o bin/memory-out-experiment src/memory-out-experiment.c -lm
(
  cd rerun/outside
  ../../bin/memory-out-experiment
)
```

Generated CSV:
- `rerun/outside/memory-out-experiment-results.csv`

### purecap ABI

```bash
mkdir -p rerun/purecap
clang-morello -march=morello -mabi=purecap -g -o bin/memory-in-experiment-purecap src/memory-in-experiment-purecap.c -lm
(
  cd rerun/purecap
  proccontrol -m cheric18n -s enable ../../bin/memory-in-experiment-purecap
)
```

Generated CSV:
- `rerun/purecap/memory-in-experiment-results.csv`

### purecap-benchmark ABI

```bash
mkdir -p rerun/benchmark
clang-morello -march=morello -mabi=purecap-benchmark -g -o bin/memory-in-experiment-purecap-benchmark src/memory-in-experiment-purecap-benchmark.c -lm
(
  cd rerun/benchmark
  proccontrol -m cheric18n -s enable ../../bin/memory-in-experiment-purecap-benchmark
)
```

Generated CSV:
- `rerun/benchmark/memory-in-experiment-benchmarkABI-results.csv`

## Archived raw references

- `raw/memory-out-experiment-results.csv`
- `raw/memory-in-experiment-purecap-results.csv`
- `raw/memory-in-experiment-purecap-benchmark-results.csv`

## Reproduce analysis

See `../../analyses/01_memory/README.md`.
