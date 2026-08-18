"""Measurement harness: runs the fixed workload in one mode and times it.

Design rules:
  * Total work is fixed. It does not shrink when the machine has more cores.
  * Both modes compute the same digits and are verified against a known
    expansion, so a fast-but-wrong result cannot win.
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

MIN_ITERATIONS = 7
MAX_ITERATIONS = 50
TARGET_SECONDS = 5.0
MAX_TOTAL_SECONDS = 60.0
NOISE_CV_THRESHOLD = 0.05

# Same calculation either way; only the numeric backend and core count differ.
MODES = ("generic", "optimized")


class MissingGMP(RuntimeError):
    """Raised when optimized mode is requested without a GMP build present."""


@dataclass
class Run:
    mode: str
    workers: int = 1
    gmp: str | None = None
    iterations: int = 0
    total_seconds: float = 0.0
    seconds_per_iteration: float = 0.0
    fastest_seconds: float = 0.0
    slowest_seconds: float = 0.0
    cv: float = 0.0
    noisy: bool = False
    verified: bool = False
    digest: str | None = None
    samples: list[float] = field(default_factory=list)


def _summarize(run: Run, samples: list[float]) -> Run:
    run.samples = [round(s, 6) for s in samples]
    run.iterations = len(samples)
    run.total_seconds = round(sum(samples), 4)
    run.seconds_per_iteration = statistics.median(samples)
    run.fastest_seconds = min(samples)
    run.slowest_seconds = max(samples)
    mean = statistics.fmean(samples)
    stdev = statistics.stdev(samples) if len(samples) > 1 else 0.0
    run.cv = stdev / mean if mean else 0.0
    run.noisy = run.cv > NOISE_CV_THRESHOLD
    return run


def _plan_iterations(calibration_seconds: float) -> int:
    if calibration_seconds <= 0:
        return MIN_ITERATIONS
    if calibration_seconds >= MAX_TOTAL_SECONDS:
        return 3
    wanted = math.ceil(TARGET_SECONDS / calibration_seconds)
    budget = max(1, int(MAX_TOTAL_SECONDS / calibration_seconds))
    return max(3, min(MAX_ITERATIONS, budget, max(MIN_ITERATIONS, wanted)))


def gmp_version() -> str | None:
    try:
        import gmpy2

        return gmpy2.mp_version()
    except ImportError:
        return None


def usable_workers(env: dict) -> int:
    workers = env["usable_cpus"]
    limit = env.get("cgroup_cpu_limit")
    if limit is not None:
        workers = max(1, min(workers, int(limit) or 1))
    return workers


def measurement_warnings(digits: int, run: Run, env: dict | None = None) -> list[str]:
    """Conditions that mean the numbers should not be quoted as-is."""
    out = []
    if run.seconds_per_iteration < MIN_CREDIBLE_SECONDS:
        out.append(
            f"An iteration takes {run.seconds_per_iteration * 1000:.0f} ms, below the "
            f"{MIN_CREDIBLE_SECONDS * 1000:.0f} ms credibility floor. Timer and scheduler "
            "noise dominate; re-run with a larger --size."
        )
    if run.noisy:
        out.append(
            f"Run-to-run variance is {run.cv * 100:.1f}%, above the "
            f"{NOISE_CV_THRESHOLD * 100:.0f}% threshold. Re-run on an idle machine."
        )
    if run.mode == "optimized" and env:
        build = (env.get("interpreter") or {}).get("gmp_build") or {}
        if build.get("portable_wheel"):
            out.append(
                "gmpy2 came from a portable wheel, so its bundled GMP is a generic "
                "build rather than one tuned for this CPU. Reinstall with "
                "'pip install --no-binary gmpy2 --force-reinstall gmpy2' to measure "
                "a genuinely architecture-tuned library."
            )
    return out


def run_suite(digits: int, mode: str = "generic", chunks: int = kernels.DEFAULT_CHUNKS,
              progress=None) -> dict:
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}; expected one of {', '.join(MODES)}")

    use_gmp = mode == "optimized"
    gmp = gmp_version()
    if use_gmp and gmp is None:
        raise MissingGMP(
            "optimized mode needs gmpy2 built against this machine's GMP; "
            "run prepare_benchmark.py first"
        )

    env = sysinfo.collect()
    workers = usable_workers(env)
    run = Run(mode=mode, workers=workers, gmp=gmp if use_gmp else None)

    monitor = sysinfo.StealMonitor()
    started = time.time()
    pool = Pool(processes=workers) if workers > 1 else None
    try:
        mapper = None
        if pool is not None:
            # Force worker processes to actually start before anything is timed.
            pool.map(_noop, range(workers))
            mapper = lambda fn, tasks: pool.map(fn, tasks, chunksize=1)  # noqa: E731

        def runner():
            return kernels.pi_binary_splitting(
                digits, chunks=chunks, use_gmp=use_gmp, mapper=mapper
            )

        # Calibration doubles as warm-up: it pays for imports, allocator growth
        # and pool page-faults, then is discarded.
        t0 = time.perf_counter()
        reference = runner()
        calibration = time.perf_counter() - t0

        run.verified = kernels.verify(reference, digits)
        if not run.verified:
            raise RuntimeError("result did not match the known digits of pi")
        run.digest = hashlib.sha256(str(reference).encode()).hexdigest()

        iterations = _plan_iterations(calibration)
        samples = []
        for i in range(iterations):
            t0 = time.perf_counter()
            value = runner()
            samples.append(time.perf_counter() - t0)
            if value != reference:
                raise RuntimeError("non-deterministic result between iterations")
            if progress:
                progress(i + 1, iterations)
        _summarize(run, samples)
    finally:
        if pool is not None:
            pool.close()
            pool.join()

    return {
        "schema": 3,
        "mode": mode,
        "digits": digits,
        "chunks": chunks,
        "terms": kernels.terms_for_digits(digits),
        "verification": kernels.verification_method(digits),
        "environment": env,
        "environment_warnings": sysinfo.warnings(env),
        "measurement_warnings": measurement_warnings(digits, run, env),
        "runtime": monitor.result(),
        "wall_seconds": round(time.time() - started, 2),
        "run": asdict(run),
    }


def _noop(_):
    return None
