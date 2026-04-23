from pathlib import Path

required = [
    'experiments/01_memory/raw/memory-out-experiment-results.csv',
    'experiments/01_memory/raw/memory-in-experiment-purecap-results.csv',
    'experiments/01_memory/raw/memory-in-experiment-purecap-benchmark-results.csv',
    'experiments/02_communication/raw/pipe-out-experiment-results.csv',
    'experiments/02_communication/raw/pipe-in-experiment-purecap-results.csv',
    'experiments/02_communication/raw/pipe-in-experiment-purecap-benchmark-results.csv',
    'experiments/03_crypto/raw/crypto_outside.csv',
    'experiments/03_crypto/raw/crypto_purecap.csv',
    'experiments/03_crypto/raw/crypto_benchmark.csv',
]

missing = [p for p in required if not Path(p).exists()]
if missing:
    print('Missing artefacts:')
    for p in missing:
        print('-', p)
    raise SystemExit(1)
print('All required preserved artefacts are present.')
