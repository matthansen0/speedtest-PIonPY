# Design Rationale

Why the benchmark is built the way it is, and what was rejected.

## The problem being solved

"Is ARM cheaper?" is not answerable by a benchmark. Two questions are:

1. **What does this hardware cost per unit of work?** — a property of the machine and its price.
2. **What did optimizing the code buy me on this hardware?** — a property of the software, which differs by architecture.

The second question is the one most migration write-ups skip, and it is usually the larger number. Conflating the two is why ARM cost comparisons tend to be unconvincing: a reader cannot tell whether the win came from the silicon, the core count, the price sheet, or from someone finally recompiling the hot path.

The tier structure exists to separate them.

## Rules the design has to obey

### 1. Total work must not depend on the machine

The v1 benchmark set its segment count to `cpu_count()` and restarted the series recurrence in each segment, so total work fell as roughly `p²`. A 16-way split did 113x less work than a 1-way split — before any parallelism was applied. Any measurement built on that is unrecoverable.

Binary splitting over a **fixed** chunk count fixes this. `--chunks` is recorded in every result file and must match across machines being compared.

### 2. A wrong answer must not be able to win

Speed is only meaningful if the work was actually done. Every tier is verified digit-for-digit against `mpmath`'s independently implemented fixed-point π, and repetitions are compared to each other to catch non-determinism. Failures are reported, not silently ranked.

The SHA-256 of the digit string travels in the result file so cross-machine comparison can assert that both machines produced the same output.

### 3. One lever per tier

| Tier | Kernel | Backend | Cores |
|---|---|---|---|
| `baseline` | naive linear series | Python int | 1 |
| `algorithm` | binary splitting | Python int | 1 |
| `native` | binary splitting | GMP (gmpy2) | 1 |
| `parallel` | binary splitting | Python int | all |
| `optimized` | binary splitting | GMP (gmpy2) | all |

`algorithm` and `parallel` use the *same* chunk decomposition executed serially versus across a pool, so their ratio is pure parallel scaling with no algorithmic difference mixed in.

### 4. Report the distribution, and the conditions

A single timing on a shared cloud host is a rumour. Each tier gets a discarded warm-up repetition, then repeats to a wall-clock budget. Median is the default cost metric because it reflects sustained behaviour; `--metric min_seconds` is available for best-case capability.

Hypervisor steal time and involuntary context switches are measured across the whole suite. If the host was oversubscribed, the report says so instead of letting the reader assume the CPU was slow.

## Decisions and rejected alternatives

**Fixed chunk count instead of chunks-per-core.** Per-core chunking would load-balance slightly better but would reintroduce machine-dependent work. Load balancing is instead handled dynamically (`chunksize=1`, results reordered by index), which keeps the decomposition fixed and the result deterministic.

**gmpy2/GMP as the "native" lever.** GMP has hand-written assembly for both `x86-64` and `aarch64`, so the tier measures something real about porting a numeric stack, and the gain legitimately differs by architecture. Rejected alternatives: NumPy (wrong problem shape for big integers), hand-written intrinsics (not representative of what teams actually do).

**PyPy removed as an architecture-conditional path.** v1 re-executed under PyPy only for Intel/AMD, which biased every comparison. The interpreter is now recorded as metadata; run the suite under whatever you like, but compare like with like.

**Affinity pinning removed.** v1 pinned worker *i* to CPU *i*, which is wrong inside a container whose allowed CPU set may not start at zero or be contiguous. The harness now reads `sched_getaffinity` and the cgroup quota to decide worker count, and leaves placement to the scheduler.

**Naive tier kept, deliberately.** It is slow and it scales badly. That is the point: it is the code most people actually ship, and it sets the denominator for "what was optimization worth".

**Prices are inputs, never measurements.** `pricing.json` carries an `as_of` date and the tool warns when it is missing or stale. Hardcoded cloud prices go wrong quietly.

## Known gaps

1. **Single workload family.** Big-integer arithmetic only. A defensible fleet migration argument needs a mix — memory-bandwidth-bound, float/SIMD, branch-heavy, and allocation-heavy kernels. This is the most valuable contribution the project could take.
2. **No energy measurement.** Perf-per-watt is a large part of the ARM argument and is not captured. RAPL on x86 and vendor-specific counters on ARM are not portable enough to compare directly, and are usually unavailable inside a VM.
3. **No thermal or frequency sampling during the run.** Sustained-clock behaviour under load is not tracked, only the advertised maximum.
4. **Parallel scaling is bounded by the serial combine step.** At high core counts the final reduction becomes the limit. That is a genuine property of the algorithm, but it means the parallel tiers understate very wide machines.
5. **No reserved/spot pricing model.** Only a flat hourly or monthly rate.

## Result schema

Result files carry `"schema": 2`. The comparison tool rejects anything else, including all v1 output, because those runs are not comparable to these.
