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
import json
import shutil
import subprocess
from pathlib import Path
from datetime import datetime
from multiprocessing import Pool, cpu_count

DEFAULT_ITERATIONS = 10000
WARMUP_FRACTION = 0.01  # 1% of iterations (minimum 100) to warm caches / JIT
SHOW_PROGRESS = True  # always show per-segment progress by default
PIN_AFFINITY = True   # try to pin each worker to a distinct core
WEIGHT_ARM_FREQ = True  # weight ARM segments by max core frequency


def _maybe_reexec_into_project_venv():
    """If a local 'venv' directory exists and we're not inside any venv, re-exec under it.

    This allows a user to simply run `python3 run_benchmark.py` after having executed
    the prereq script without needing to remember to 'source venv/bin/activate'.
    Guarded by env var PIONPY_VENV_ACTIVE to prevent recursion. Silent fallback on error.
    """
    if os.environ.get('PIONPY_VENV_ACTIVE'):
        return
    # Detect if already in a venv
    in_venv = (hasattr(sys, 'real_prefix') or (getattr(sys, 'base_prefix', sys.prefix) != sys.prefix))
    if in_venv:
        return
    project_root = Path(__file__).parent.resolve()
    venv_dir = project_root / 'venv'
    candidate = venv_dir / 'bin' / 'python'
    if not candidate.exists():
        return
    try:
        print(f"[info] Re-executing under local venv: {candidate}")
        env = os.environ.copy()
        env['PIONPY_VENV_ACTIVE'] = '1'
        os.execve(str(candidate), [str(candidate)] + sys.argv, env)
    except Exception as e:
        print(f"[warn] Could not re-exec into venv (continuing with current interpreter): {e}")
        return


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
    (start, end, idx, total_segments, core_id) = args
    import mpmath
    mpmath.mp.dps = 100  # local dps sufficient for partial accumulation (final precision dominated by global)
    # Optional affinity pinning (best-effort)
    if PIN_AFFINITY and core_id is not None:
        try:
            os.sched_setaffinity(0, {core_id})
        except Exception:
            pass
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


def _read_arm_freqs(limit: int):
    freqs = []
    for i in range(limit):
        path = f"/sys/devices/system/cpu/cpu{i}/cpufreq/cpuinfo_max_freq"
        try:
            with open(path, 'r') as f:
                val = int(f.read().strip())
        except Exception:
            val = 1
        freqs.append(max(1, val))
    return freqs


def _allocate_segments(total: int, processes: int, weights):
    # weights length == processes
    wsum = sum(weights)
    raw_counts = [int(total * w / wsum) for w in weights]
    assigned = sum(raw_counts)
    # distribute remainder
    rem = total - assigned
    idx = 0
    while rem > 0:
        raw_counts[idx] += 1
        rem -= 1
        idx = (idx + 1) % processes
    # Build contiguous ranges
    ranges = []
    start = 0
    for i, count in enumerate(raw_counts):
        end = start + count - 1
        ranges.append((start, end))
        start = end + 1
    return ranges


def approximate_parallel(iterations: int, vendor: str):
    import mpmath
    mpmath.mp.dps = 10000
    processes = cpu_count()
    if vendor == 'ARM' and WEIGHT_ARM_FREQ:
        weights = _read_arm_freqs(processes)
    else:
        weights = [1] * processes
    seg_ranges = _allocate_segments(iterations, processes, weights)
    bounds = []
    for idx, (start, end) in enumerate(seg_ranges):
        core_id = idx if idx < processes else None
        bounds.append((start, end, idx, processes, core_id))
    t0 = time.time()
    with Pool(processes=processes) as p:
        parts = p.map(_segment_work, bounds)
    S = sum(parts)
    C = 426880 * mpmath.sqrt(10005)
    pi_val = C / S
    return pi_val, time.time() - t0, processes


def _maybe_reexec_with_pypy(vendor: str):
    """Attempt to re-exec under a local PyPy virtual environment for x86 vendors.

    Improvements over the previous simplistic approach:
      * Creates a project-local .pypy_venv so we never install into the system environment (PEP 668 safe).
      * Installs mpmath inside that venv if missing.
      * Respects SKIP_PYPY=1 to allow the user to force using the current interpreter.
      * Uses an env guard (PIONPY_PYPY_ACTIVE) to prevent infinite recursion.
      * Falls back silently to current interpreter on any failure.
    """
    if os.environ.get("SKIP_PYPY"):
        return
    if os.environ.get("PIONPY_PYPY_ACTIVE"):
        return  # already running inside PyPy venv
    if 'pypy' in sys.version.lower():
        return  # already PyPy (possibly user managed)
    if vendor not in ("Intel", "AMD", "x86"):
        return

    pypy = shutil.which('pypy3')
    if not pypy:
        return  # silently ignore if PyPy not installed

    project_root = Path(__file__).parent.resolve()
    venv_dir = project_root / '.pypy_venv'
    python_path = venv_dir / 'bin' / 'python'

    try:
        if not venv_dir.exists():
            print(f"[info] Creating local PyPy venv at {venv_dir} ...")
            subprocess.run([pypy, '-m', 'venv', str(venv_dir)], check=True)
        # Verify python exists
        if not python_path.exists():
            print('[warn] PyPy venv creation did not produce expected python binary; skipping PyPy optimization.')
            return
        # Ensure mpmath inside PyPy venv
        code_check = 'import mpmath; print(1)'
        check_res = subprocess.run([str(python_path), '-c', code_check], capture_output=True, text=True)
        if check_res.returncode != 0:
            print('[info] Installing mpmath inside local PyPy venv...')
            install_res = subprocess.run([str(python_path), '-m', 'pip', 'install', '--disable-pip-version-check', 'mpmath'])
            if install_res.returncode != 0:
                print('[warn] Failed to install mpmath in PyPy venv; falling back to current interpreter.')
                return
        print(f"[info] Re-executing under local PyPy venv: {python_path}")
        env = os.environ.copy()
        env['PIONPY_PYPY_ACTIVE'] = '1'
        os.execve(str(python_path), [str(python_path)] + sys.argv, env)
    except Exception as e:
        print(f"[warn] PyPy optimization skipped due to error: {e}")
        return


def main():
    _maybe_reexec_into_project_venv()
    ensure_mpmath()
    vendor = detect_vendor()
    print(f"[info] Detected architecture/vendor: {vendor}")
    _maybe_reexec_with_pypy(vendor)
    # Warm-up (small fraction) to stabilize JIT / caches
    warmup_iters = max(100, int(DEFAULT_ITERATIONS * WARMUP_FRACTION))
    print(f"[info] Warm-up run: {warmup_iters} iterations (not timed in final result)")
    global SHOW_PROGRESS
    saved_progress = SHOW_PROGRESS
    SHOW_PROGRESS = False  # suppress progress during warm-up
    approximate_parallel(warmup_iters, vendor)
    SHOW_PROGRESS = saved_progress
    print(f"[info] Running approximate parallel benchmark with {DEFAULT_ITERATIONS} iterations...")
    pi_val, elapsed, procs = approximate_parallel(DEFAULT_ITERATIONS, vendor)
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
    print(f"[result] Elapsed: {colored_elapsed} | Cores used: {procs} | Iterations: {DEFAULT_ITERATIONS}")
    print('[info] Progress checkpoints (10% per segment) enabled by default.')
    if vendor == 'ARM' and WEIGHT_ARM_FREQ:
        print('[info] ARM frequency weighting applied to segment distribution.')
    if PIN_AFFINITY:
        print('[info] Core affinity pinning attempted (best-effort).')
    print("[note] Result is from an approximate segmented method (not exact decomposition).")

    # Write JSON results
    result = {
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'vendor': vendor,
        'python_impl': platform.python_implementation(),
        'python_version': platform.python_version(),
        'iterations': DEFAULT_ITERATIONS,
        'warmup_iterations': warmup_iters,
        'elapsed_seconds': elapsed,
        'processes': procs,
        'affinity': PIN_AFFINITY,
        'arm_frequency_weighting': (vendor == 'ARM' and WEIGHT_ARM_FREQ),
        'approximate_method': True,
    }
    fname = f"results_{int(time.time())}.json"
    try:
        with open(fname, 'w') as f:
            json.dump(result, f, indent=2)
        print(f"[info] JSON results written to {fname}")
    except Exception as e:
        print(f"[warn] Failed to write JSON results: {e}")


if __name__ == '__main__':
    main()
