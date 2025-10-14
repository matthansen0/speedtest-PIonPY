#!/usr/bin/env python3
"""Pi-on-Py Unified Benchmark (Single Script)

Usage (simple):
        python3 run_benchmark.py

What it does:
    * Detects CPU vendor/arch (ARM / AMD / Intel)
    * Prefers PyPy for Intel if running under PyPy already (auto-detection only informational)
    * Ensures dependency `mpmath` is available (attempts install if missing)
    * Runs a parallel Chudnovsky-like benchmark using an APPROXIMATE segmented method
        (kept for throughput comparability; NOT a mathematically strict decomposition)
    * Shows wall time and last 50 digits (approximate) for relative comparison

Rationale:
    This project focuses on relative throughput across architectures, not producing
    formally validated long-digit expansions of π. For strict correctness a binary
    splitting or exact per-term method would be required; future enhancement could
    add a `--mode exact`.
"""
from __future__ import annotations

import math
import os
import platform
import sys
import time
from multiprocessing import Pool, cpu_count

DEFAULT_ITERATIONS = 10000
SHOW_PROGRESS = True  # always show per-segment progress by default


def ensure_mpmath():
    try:
        import mpmath  # noqa: F401
        return
    except ImportError:
        print('[setup] mpmath not found. Attempting installation...')
        # Try simple pip install; respect PEP 668 by offering guidance if blocked.
        import subprocess
        try:
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'mpmath'])
        except subprocess.CalledProcessError:
            print('[setup] Automatic install failed. Please install mpmath manually (e.g., create a venv).')
            sys.exit(1)


def detect_vendor() -> str:
    mach = platform.machine().lower()
    if 'arm' in mach or 'aarch64' in mach:
        return 'ARM'
    if mach in ('x86_64', 'amd64'):
        # Distinguish Intel vs AMD via /proc/cpuinfo
        vendor = None
        try:
            with open('/proc/cpuinfo', 'r') as f:
                for line in f:
                    if line.lower().startswith('vendor_id'):
                        vendor = line.split(':', 1)[1].strip().lower()
                        break
        except Exception:
            pass
        if vendor:
            if 'intel' in vendor:
                return 'Intel'
            if 'amd' in vendor or 'hygon' in vendor:
                return 'AMD'
        return 'x86'
    return mach.upper()


def _segment_work(args):
    """Approximate segment computation (not mathematically exact series split).
    Mirrors original per-arch logic to keep relative comparability.
    """
    (start, end, idx, total_segments) = args
    import mpmath
    mpmath.mp.dps = 100  # local dps sufficient for partial accumulation (final precision dominated by global)
    K = 6 + 12 * start
    M = 1
    X = 1
    L = 13591409 + 545140134 * start
    S = L
    segment_len = end - start + 1
    checkpoint = max(1, segment_len // 10)
    last_report = 0
    for i in range(start + 1, end + 1):
        M = (K**3 - 16 * K) * M // i**3
        L += 545140134
        X *= -262537412640768000
        S += mpmath.mpf(M * L) / X
        K += 12
        if SHOW_PROGRESS and (i - start) - last_report >= checkpoint:
            last_report = (i - start)
            pct = int((i - start) / segment_len * 100)
            print(f"[seg {idx+1}/{total_segments}] {pct}%")
    return S


def approximate_parallel(iterations: int):
    import mpmath
    mpmath.mp.dps = 10000
    segs = cpu_count()
    seg_size = iterations // segs
    bounds = []
    for s in range(segs):
        start = s * seg_size
        end = (s + 1) * seg_size - 1 if s < segs - 1 else iterations - 1
        bounds.append((start, end, s, segs))
    t0 = time.time()
    with Pool(processes=segs) as p:
        parts = p.map(_segment_work, bounds)
    S = sum(parts)
    C = 426880 * mpmath.sqrt(10005)
    pi_val = C / S
    return pi_val, time.time() - t0


def main():
    ensure_mpmath()
    vendor = detect_vendor()
    print(f"[info] Detected architecture/vendor: {vendor}")
    if vendor == 'Intel' and 'pypy' not in sys.version.lower():
        print('[hint] PyPy may yield higher Intel throughput (optional).')
    print(f"[info] Running approximate parallel benchmark with {DEFAULT_ITERATIONS} iterations...")
    pi_val, elapsed = approximate_parallel(DEFAULT_ITERATIONS)
    pi_str = str(pi_val)
    print("[result] Last 50 digits:", pi_str[-50:])
    # Color-coded elapsed time: green fast (<5s), yellow (<15s), red otherwise.
    if elapsed < 5:
        color_code = '92'  # bright green
    elif elapsed < 15:
        color_code = '93'  # yellow
    else:
        color_code = '91'  # red
    colored_elapsed = f"\033[{color_code}m{elapsed:.2f} s\033[0m"
    print(f"[result] Elapsed: {colored_elapsed} | Cores used: {cpu_count()} | Iterations: {DEFAULT_ITERATIONS}")
    print('[info] Progress checkpoints (10% per segment) enabled by default.')
    print("[note] Result is from an approximate segmented method (not exact decomposition).")


if __name__ == '__main__':
    main()
