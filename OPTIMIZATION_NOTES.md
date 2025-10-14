# Pi-on-Py Optimization Notes

This document summarizes the automatic optimizations now applied by `run_benchmark.py` and outlines potential future enhancements.

## Current Automatic Optimizations

| Optimization | Description | Rationale |
|--------------|-------------|-----------|
| Warm-up Pass | 1% of total iterations (min 100) run before timing | Stabilizes caches, triggers JIT (PyPy) |
| Core Affinity (best-effort) | Each worker process pins to a distinct core (Linux only) | Reduces context switching & migration |
| ARM Frequency Weighting | Segment sizes scaled by per-core `cpuinfo_max_freq` | Better utilization on big.LITTLE designs |
| Intel PyPy Auto Re-exec | If Intel + PyPy available and not already active, restarts under PyPy | JIT often improves loop throughput |
| JSON Result Output | Stores metadata + timing in `results_<epoch>.json` | Enables automated aggregation & comparisons |
| Progress Checkpoints | 10% per segment progress lines | Visibility into long runs |
| Color-Coded Elapsed Time | Green (<5s), Yellow (<15s), Red (>=15s) | Quick visual performance cue |

## Approximate Method Caveat
The current parallelization splits the Chudnovsky-like recurrence state across segments naively. This produces a π approximation adequate for **relative throughput** but is **not** mathematically exact. For correctness-oriented use, a future exact mode should compute each term independently or employ binary splitting.

## Planned / Potential Future Enhancements
1. Exact Mode (`--mode exact`): Independent term computation or binary splitting tree.
2. Binary Splitting High-Precision Path: Efficient for large digit counts; uses structured product/reduction.
3. JSON Aggregator Script: Combine multiple run artifacts into a comparative table (e.g., CSV/Markdown export).
4. Thermal & Frequency Sampling: Optional capture of `cpu MHz`, temperature sensors, throttle events.
5. Lightweight Result Validation: Compare first N digits to a trusted π prefix to detect significant deviations.
6. Optional Quiet Mode: Suppress per-segment progress for cleaner CI logs.
7. Multiple Iteration Sets: Automatically run short/medium/long sequences and summarize scaling.
8. gmpy2 Integration (if present): Faster big integer and rational arithmetic acceleration.

## Design Rationale
- **Single Entry Point:** Minimizes user friction and configuration divergence across architectures.
- **Best-Effort Pinning:** Avoids hard failure on systems lacking permission for `sched_setaffinity`.
- **Minimal External Dependencies:** Only `mpmath`; optional advanced libs intentionally not auto-installed to avoid environment conflicts.

## Adding an Exact Mode (Roadmap Sketch)
1. Implement per-term exact Chudnovsky term computation using integer arithmetic for `(6k)! / ((3k)!(k!)^3)` via multiplicative updates.
2. Parallelize by dividing k-range into blocks; each worker returns high-precision partial sum (pairwise summation for stability).
3. (Advanced) Implement binary splitting for improved asymptotics and fewer large factorial intermediates.
4. Provide a validation harness comparing exact vs approximate elapsed times and digit agreement.

## Notes on Interpreters
- **PyPy on Intel:** Largest relative gain expected due to strong JIT + robust single-core performance.
- **CPython on ARM:** Stable baseline; PyPy gains vary depending on workload mix (integer vs object overhead).
- **CPython on AMD:** Large core counts benefit primarily from process-level parallelism; JIT impact secondary.

---
Contributions and profiling data are welcome. Open an issue or PR to propose additional optimizations.
