# Experiment 4.3 — Cryptographic Library Performance

This directory preserves the artefacts used for the cryptographic benchmark described in Section 4.3 of the paper.

## Contents
- `src/` — preserved benchmark source files
- `include/` — preserved headers
- `bin/` — preserved compiled benchmark binary
- `raw/` — preserved raw CSV outputs
- `Makefile` — preserved original build file

## Compile and execute in the three modes

All commands below assume execution from `experiments/03_crypto/` on ARM Morello / CheriBSD.

### Outside compartment (baseline)

```bash
mkdir -p rerun/build rerun/raw
clang-morello -O2 -Wall -Wextra -Wpedantic -std=c11 -Iinclude   src/crypto_bench.c src/crypto_workload.c -lcrypto   -o rerun/build/crypto_bench_outside
./rerun/build/crypto_bench_outside   --mode outside   --workload all   --repetitions 100   --warmup 1   --csv rerun/raw/crypto_outside.csv
```

### purecap ABI

```bash
mkdir -p rerun/build rerun/raw
clang-morello -O2 -Wall -Wextra -Wpedantic -std=c11 -Iinclude   -march=morello -mabi=purecap   src/crypto_bench.c src/crypto_workload.c -lcrypto   -o rerun/build/crypto_bench_purecap
proccontrol -m cheric18n -s enable ./rerun/build/crypto_bench_purecap   --mode purecap   --workload all   --repetitions 100   --warmup 1   --csv rerun/raw/crypto_purecap.csv
```

### purecap-benchmark ABI

```bash
mkdir -p rerun/build rerun/raw
clang-morello -O2 -Wall -Wextra -Wpedantic -std=c11 -Iinclude   -march=morello -mabi=purecap-benchmark   src/crypto_bench.c src/crypto_workload.c -lcrypto   -o rerun/build/crypto_bench_benchmark
proccontrol -m cheric18n -s enable ./rerun/build/crypto_bench_benchmark   --mode benchmark   --workload all   --repetitions 100   --warmup 1   --csv rerun/raw/crypto_benchmark.csv
```

## Archived raw references

- `raw/crypto_outside.csv`
- `raw/crypto_purecap.csv`
- `raw/crypto_benchmark.csv`

## Reproduce analysis

See `../../analyses/03_crypto/README.md`.
