# Formulas used in the communication summary

- **Latency** = `Write Time + Read Time`
- **Standard deviation** = sample standard deviation of latency within each message size and execution mode
- **Coefficient of variation (%)** = `100 * std(latency) / mean(latency)`
- **Throughput (MB/s)** = transmitted message size divided by latency, expressed in MB/s
- **Latency overhead (%)** = percentage increase in mean latency relative to the non-compartmentalised baseline

These formulas document the intended methodology. The preserved published summary files remain the authoritative archived artefacts for Section 4.2.
