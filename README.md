# SpeedTest: Pi-on-Py

<p align="center">
  <img src="media/pionpy.png" alt="Pi on Py" title="Pi on Py" width="400"/>
</p>

A benchmark that measures **what optimizing a workload for a CPU architecture is actually worth in dollars** — not just which chip is faster.

It computes a fixed number of digits of π at five increasing levels of optimization, verifies every digit, and converts the timings into cost-per-unit-of-work using the price you actually pay for the machine.

---

## Why v2 exists

The first version of this project produced numbers that looked plausible and were not. Two defects made every published figure meaningless.

**1. The workload shrank as core count grew.** The parallel "Chudnovsky-like" loop restarted its recurrence state in every segment, so total work scaled roughly as `n²/p²`. Measured serially — with no parallelism at all — simply changing the segment count changed the amount of work by **113x**:

| Segments | Serial work | π produced | Correct digits |
|---|---|---|---|
| 1 | 10.33 s | 3.14159265358979323846 | all |
| 2 | 2.59 s | 0.000078322139550761635 | **0** |
| 4 | 0.99 s | 0.000026107813774499589 | **0** |
| 8 | 0.32 s | 0.000011189116180930662 | **0** |
| 16 | 0.09 s | 0.0000052215974696473406 | **0** |

Because segment count was set to `cpu_count()`, a machine with more vCPUs did dramatically *less* work and then spread it over more cores. Most of the reported "speedup" was an artifact of the measurement.

**2. The answer was wrong.** Any run with more than one segment produced a value with zero correct digits of π. The "last 50 digits" the old script printed were noise.

Three further issues undermined the comparison:

- **PyPy was applied only to Intel/AMD.** Handing a JIT to one architecture and not the other is not a controlled experiment. PyPy supports aarch64.
- **Single sample, no statistics.** One run on a shared cloud host, with no repetition, variance, or steal-time check.
- **No cost model.** Prices lived in image captions; nothing computed cost per unit of work.

Everything below is the fix.

---

## Methodology

### Fixed work, identical everywhere

The benchmark computes `floor(π × 10^digits)` via **Chudnovsky binary splitting** over a term range cut into a **fixed number of chunks (128 by default), independent of how many cores the machine has**. The total arithmetic performed is identical on a 2-vCPU VM and a 96-vCPU VM. Only wall-clock time varies.

### Every result is verified

Each tier's output is checked digit-for-digit against an independent oracle (`mpmath`'s fixed-point π, a separate implementation). A tier that produces the wrong answer is marked `failed` and excluded — a fast-but-wrong kernel cannot win. Each run also records the SHA-256 of the digit string, so two machines can prove they did the same work.

### Five tiers isolate one optimization lever each

| Tier | What it runs | Lever being measured |
|---|---|---|
| `baseline` | Naive term-by-term series, 1 core | none — the starting point |
| `algorithm` | Binary splitting, 1 core | algorithmic change, fully portable |
| `native` | Binary splitting + GMP via gmpy2, 1 core | architecture-tuned native math library |
| `parallel` | Binary splitting, all cores | parallelism |
| `optimized` | Binary splitting + GMP, all cores | everything combined |

Because each tier changes exactly one thing, the speedups are attributable instead of guessed at. The `native` tier is the interesting one for an ARM migration: GMP ships hand-written assembly for both `x86-64` and `aarch64`, so it measures what recompiling a numeric stack for the target actually buys.

### Timings are distributions, not samples

Each tier runs one discarded calibration/warm-up repetition, then repeats to a wall-clock budget — a 5 s target, normally 7–50 repetitions, dropping to 3 when a single repetition already exceeds the per-tier time cap. The report gives median, best, and coefficient of variation, and flags any tier with more than 5% run-to-run variance.

### The environment is recorded and challenged

Cloud numbers are only defensible if you can prove what you ran on. Every run captures — and warns about — the things that most often invalidate an ARM-vs-x86 comparison:

- **vCPU ≠ core.** An x86 vCPU is usually an SMT sibling; an ARM vCPU is usually a whole physical core. A "2 vCPU vs 2 vCPU" comparison can silently be 1 physical core vs 2.
- **Hypervisor steal time**, measured across the run. A noisy neighbour inflates wall-clock time and the report says so.
- **cgroup CPU quota and affinity**, which often cap the usable CPU budget below the visible count.
- Interpreter, GMP version, page size, max frequency, virtualization vendor.

---

## Running it

```bash
git clone https://github.com/matthansen0/speedtest-PIonPY
cd speedtest-PIonPY

python3 prepare_benchmark.py       # creates ./venv, installs deps, self-tests correctness
python3 run_benchmark.py --sku azure_d2ps_v6
```

`prepare_benchmark.py` refuses to declare success unless the kernels produce verified digits of π on this machine.

If `gmpy2` fails to build, install GMP headers and re-run — otherwise the most architecture-sensitive tier is skipped:

```bash
sudo apt install -y python3-dev libgmp-dev libmpfr-dev libmpc-dev build-essential   # Debian/Ubuntu
sudo dnf install -y python3-devel gmp-devel mpfr-devel libmpc-devel gcc             # RHEL/Fedora
```

### Options that matter

```bash
python3 run_benchmark.py --size deep                 # 500k digits; quick=50k, standard=200k
python3 run_benchmark.py --price-per-month 56.94     # price not in pricing.json
python3 run_benchmark.py --metric min_seconds        # best case instead of sustained
python3 run_benchmark.py --tiers baseline,optimized  # subset
```

**Every machine you intend to compare must use the same `--size`.** The comparison tool refuses to present runs as comparable if the digit targets or verified results differ.

### Pricing

`pricing.json` holds the SKU price table. Prices are **inputs, not measurements** — verify them for your region and commitment term, then set `as_of`. The tool warns when the file is undated or more than 120 days old.

### Comparing machines

Copy each machine's JSON from `results/` into one place, then:

```bash
python3 compare_results.py results/
python3 compare_results.py results/ --baseline intel-box --markdown-out COMPARISON.md
```

This emits two tables: hardware cost efficiency at a chosen tier, and the value of optimization per machine.

---

## Reading the output

**Cost per 1k runs** — what the fixed workload costs on this machine at this tier. This is the number to compare across architectures.

**Runs per $** — the inverse; higher is better. Cross-machine "value vs base" percentages are computed from this.

**Effective $/month** — the machine's real price divided by the total optimization speedup. If optimizing gives 10x, a $56.94/mo VM behaves like a $5.69/mo VM *for this workload*. This is the framing a budget conversation needs: optimization and instance choice become the same lever, measured in the same units.

**Result integrity** — read this before quoting anything. Steal time above ~1%, high variance, or a "too small" warning means the numbers describe the host's mood rather than the CPU.

---

## Honest limits

- **This is one workload.** Big-integer arithmetic with modest working sets. It exercises integer ALU throughput, multiply latency, and the quality of the platform's GMP build. It says little about SIMD/float throughput, memory bandwidth, branch-heavy code, or I/O. Do not generalize a fleet migration from one kernel.
- **The oracle shares an algorithm family.** `mpmath` also uses Chudnovsky. It is an independent *implementation* — different splitting, different scaling, different code — and results are additionally cross-checked against a published 100-digit prefix and across three of this project's own kernels. It is not an algorithmically independent proof.
- **Prices are inputs.** Reserved instances, spot, savings plans, and region move the answer more than the benchmark does.
- **`parallel` can be slower than `algorithm`.** On small sizes, or on a 2-vCPU x86 VM that is really one physical core, process overhead exceeds the gain. The report says so rather than hiding it. Use a larger `--size` before drawing conclusions about core scaling.
- **PyPy is no longer special-cased.** Run the suite under whichever interpreter you like; the implementation and version are recorded. Do not compare a PyPy run against a CPython run and call it an architecture difference.

## Publishing results

Include the `results/*.json` files alongside any chart. They contain the environment fingerprint, per-repetition samples, steal time, result digest, and pricing source that someone else needs to check the claim.

The screenshots in `media/` were produced by the v1 methodology described above and are **superseded**; they should not be cited.

## Contributing

Contributions welcome — particularly additional workload kernels (memory-bound, float/SIMD, branch-heavy) so the cost story can rest on a workload mix rather than one microbenchmark. See [OPTIMIZATION_NOTES.md](OPTIMIZATION_NOTES.md) for design rationale.

## License

MIT — see [LICENSE](LICENSE).
