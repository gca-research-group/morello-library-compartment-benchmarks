# Environment

The paper reports experiments on:

- **Hardware**: ARM Morello Board (Research Morello SoC r0p0, 4 CPU cores, 16 GB DDR4 ECC 2933 MT/s)
- **Operating system**: CheriBSD 24.5 / 24.05
- **Compiler/toolchain**: `clang-morello`
- **Execution modes**:
  - outside compartment (baseline)
  - `purecap ABI`
  - `purecap-benchmark ABI`
- **Control tool for compartment execution**: `proccontrol -m cheric18n -s enable`
- **Analysis stack**: Python with NumPy, pandas, matplotlib, SciPy, and scikit-learn
- **Crypto dependency**: OpenSSL development libraries (`-lcrypto`)

## Practical compilation notes

- The baseline mode is compiled without CHERI ABI flags.
- The `purecap ABI` mode is compiled with `-march=morello -mabi=purecap`.
- The `purecap-benchmark ABI` mode is compiled with `-march=morello -mabi=purecap-benchmark`.
- The compartmentalised binaries are executed with `proccontrol -m cheric18n -s enable` in the commands documented in the repository README and in each experiment README.
- The preserved source files write their CSV outputs to the current working directory. For this reason, the repository instructions use `rerun/` subdirectories so that regenerated results do not overwrite archived raw artefacts.
