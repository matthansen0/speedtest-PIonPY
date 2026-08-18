"""Measurement harness: optimization tiers, repetition policy, and statistics.

Design rules that the previous benchmark violated:
  * Total work is fixed. It does not shrink when the machine has more cores.
  * Every tier computes the same digits of pi and is verified against a known
    expansion, so a fast-but-wrong result cannot win.
  * Each tier isolates exactly one optimization lever, so the speedups can be
    attributed rather than guessed at.
  * Timing is repeated to a wall-clock budget and reported as a distribution,
    not a single sample.
"""
from __future__ import annotations

import hashlib
import math
import statistics
import time
from dataclasses import dataclass, field, asdict
from multiprocessing import Pool

from . import kernels, sysinfo

SIZE_PRESETS = {
    "quick": 50_000,
    "standard": 200_000,
    "deep": 500_000,
}

# A repetition shorter than this is dominated by scheduler and timer noise
# rather than by the CPU under test.
MIN_CREDIBLE_SECONDS = 0.25

MIN_REPS = 7
MAX_REPS = 50
TARGET_SECONDS = 5.0
MAX_TIER_SECONDS = 60.0
NOISE_CV_THRESHOLD = 0.05


@dataclass(frozen=True)
class Tier:
    key: str
    label: str
    lever: str
    parallel: bool
    use_gmp: bool
    kernel: str  # "linear" | "binary_splitting"


TIERS: tuple[Tier, ...] = (
    Tier("baseline", "Naive series, single core",
         "none (starting point)", False, False, "linear"),
    Tier("algorithm", "Binary splitting, single core",
         "algorithm (portable)", False, False, "binary_splitting"),
    Tier("native", "Binary splitting + GMP, single core",
         "native math library (arch-tuned)", False, True, "binary_splitting"),
    Tier("parallel", "Binary splitting, all cores",
         "parallelism", True, False, "binary_splitting"),
    Tier("optimized", "Binary splitting + GMP, all cores",
         "algorithm + native + parallelism", True, True, "binary_splitting"),
)


@dataclass
class TierResult:
    key: str
    label: str
    lever: str
    status: str = "ok"
    skipped_reason: str | None = None
    reps: int = 0
    workers: int = 1
    min_seconds: float = 0.0
    median_seconds: float = 0.0
    mean_seconds: float = 0.0
    stdev_seconds: float = 0.0
    cv: float = 0.0
    noisy: bool = False
    verified: bool = False
    digest: str | None = None
    samples: list[float] = field(default_factory=list)


def _summarize(result: TierResult, samples: list[float]) -> TierResult:
    result.samples = [round(s, 6) for s in samples]
    result.reps = len(samples)
    result.min_seconds = min(samples)
    result.median_seconds = statistics.median(samples)
    result.mean_seconds = statistics.fmean(samples)
    result.stdev_seconds = statistics.stdev(samples) if len(samples) > 1 else 0.0
    result.cv = result.stdev_seconds / result.mean_seconds if result.mean_seconds else 0.0
    result.noisy = result.cv > NOISE_CV_THRESHOLD
    return result


def _plan_reps(calibration_seconds: float) -> int:
    if calibration_seconds <= 0:
        return MIN_REPS
    if calibration_seconds >= MAX_TIER_SECONDS:
        return 3
    wanted = math.ceil(TARGET_SECONDS / calibration_seconds)
    budget = max(1, int(MAX_TIER_SECONDS / calibration_seconds))
    return max(3, min(MAX_REPS, budget, max(MIN_REPS, wanted)))


def _make_runner(tier: Tier, digits: int, chunks: int, pool):
    if tier.kernel == "linear":
        return lambda: kernels.pi_linear(digits, use_gmp=tier.use_gmp)
    mapper = None
    if tier.parallel and pool is not None:
        mapper = lambda fn, tasks: pool.map(fn, tasks, chunksize=1)  # noqa: E731
    return lambda: kernels.pi_binary_splitting(
        digits, chunks=chunks, use_gmp=tier.use_gmp, mapper=mapper
    )


def run_tier(tier: Tier, digits: int, chunks: int, pool, workers: int,
             progress=None) -> TierResult:
    result = TierResult(key=tier.key, label=tier.label, lever=tier.lever)
    result.workers = workers if tier.parallel else 1

    if tier.use_gmp:
        try:
            import gmpy2  # noqa: F401
        except ImportError:
            result.status = "skipped"
            result.skipped_reason = "gmpy2 not installed"
            return result

    runner = _make_runner(tier, digits, chunks, pool)

    # Calibration rep doubles as warm-up: it pays for imports, JIT warm-up,
    # allocator growth and pool page-faults, then is discarded.
    t0 = time.perf_counter()
    reference = runner()
    calibration = time.perf_counter() - t0

    result.verified = kernels.verify(reference, digits)
    if not result.verified:
        result.status = "failed"
        result.skipped_reason = "result did not match known digits of pi"
        return result
    result.digest = hashlib.sha256(str(reference).encode()).hexdigest()

    reps = _plan_reps(calibration)
    samples = []
    for i in range(reps):
        t0 = time.perf_counter()
        value = runner()
        samples.append(time.perf_counter() - t0)
        if value != reference:
            result.status = "failed"
            result.skipped_reason = "non-deterministic result between repetitions"
            return result
        if progress:
            progress(tier, i + 1, reps)

    return _summarize(result, samples)


def measurement_warnings(digits: int, results: list[TierResult], workers: int) -> list[str]:
    """Conditions that mean the numbers should not be quoted as-is."""
    out = []
    ok = {r.key: r for r in results if r.status == "ok"}
    if not ok:
        return out

    fastest = min(ok.values(), key=lambda r: r.median_seconds)
    if fastest.median_seconds < MIN_CREDIBLE_SECONDS:
        out.append(
            f"Fastest tier runs in {fastest.median_seconds * 1000:.0f} ms, below the "
            f"{MIN_CREDIBLE_SECONDS * 1000:.0f} ms credibility floor. Timer and scheduler "
            "noise dominate; re-run with a larger --size."
        )
    if "algorithm" in ok and "parallel" in ok and workers > 1:
        ratio = ok["algorithm"].median_seconds / ok["parallel"].median_seconds
        if ratio < 1.0:
            out.append(
                f"Parallelism made this {1 / ratio:.2f}x slower: at {digits:,} digits the "
                "per-chunk work is smaller than the process-communication overhead. "
                "Use a larger --size before drawing conclusions about core scaling."
            )
        elif ratio / workers < 0.5:
            out.append(
                f"Parallel efficiency is only {ratio / workers * 100:.0f}% across {workers} "
                "workers, so this size under-uses the machine."
            )
    return out


def run_suite(digits: int, chunks: int = kernels.DEFAULT_CHUNKS,
              tiers: tuple[Tier, ...] = TIERS, progress=None) -> dict:
    env = sysinfo.collect()
    workers = env["usable_cpus"]
    limit = env.get("cgroup_cpu_limit")
    if limit is not None:
        workers = max(1, min(workers, int(limit) or 1))

    monitor = sysinfo.StealMonitor()
    started = time.time()

    needs_pool = any(t.parallel for t in tiers) and workers > 1
    pool = Pool(processes=workers) if needs_pool else None
    try:
        if pool is not None:
            # Force worker processes to actually start before anything is timed.
            pool.map(_noop, range(workers))
        results = [run_tier(t, digits, chunks, pool, workers, progress) for t in tiers]
    finally:
        if pool is not None:
            pool.close()
            pool.join()

    digests = {r.digest for r in results if r.digest}
    return {
        "schema": 2,
        "digits": digits,
        "chunks": chunks,
        "terms": kernels.terms_for_digits(digits),
        "verification": kernels.verification_method(digits),
        "environment": env,
        "environment_warnings": sysinfo.warnings(env),
        "measurement_warnings": measurement_warnings(digits, results, workers),
        "runtime": monitor.result(),
        "wall_seconds": round(time.time() - started, 2),
        "cross_tier_digest_match": len(digests) <= 1,
        "tiers": [asdict(r) for r in results],
    }


def _noop(_):
    return None
