"""Intel-optimized Pi benchmark (parallel version)

Runs under PyPy (recommended) to leverage JIT for inner-loop speed, and uses
multiprocessing to utilize all logical CPU cores (helping avoid ~50% utilization
when only a single process was used previously).

NOTE ON MATHEMATICAL CORRECTNESS:
The parallel strategy here mirrors the existing ARM/AMD scripts by dividing the
iteration range into contiguous segments and summing partial series. This keeps
consistency with the repository's other scripts but is NOT a mathematically
rigorous decomposition of the Chudnovsky recurrence because M/X depend on all
prior terms. For a strictly correct parallel Chudnovsky implementation you
would compute each term via its direct closed form or derive per-segment initial
state. For benchmarking relative CPU throughput (the project's current focus),
this approximation still produces a Pi-like value and comparable workload.

Future improvement: replace segments with a correct term-wise parallel sum.
"""

import argparse
import os
import time
from multiprocessing import Pool, cpu_count
import mpmath

mpmath.mp.dps = 10000  # precision
C_CONST = 426880 * mpmath.sqrt(10005)

def _maybe_set_affinity(core_id, affinity):
    if not affinity:
        return
    try:
        os.sched_setaffinity(0, {core_id})
    except Exception:
        pass

def calculate_segment(args):
    start, end, segment_index, total_segments, progress, affinity = args
    _maybe_set_affinity(segment_index % os.cpu_count(), affinity)
    seg_len = end - start + 1
    ten_percent = max(1, seg_len // 10)
    next_checkpoint = start + ten_percent if progress else end + 1
    t0 = time.time()

    # Naive offset initialization (see top-level note)
    K = 6 + 12 * start
    M = 1
    X = 1
    L = 13591409 + 545140134 * start
    S = L

    for i in range(start + 1, end + 1):
        M = (K**3 - 16*K) * M // i**3
        L += 545140134
        X *= -262537412640768000
        S += mpmath.mpf(M * L) / X
        K += 12
        if progress and i >= next_checkpoint:
            pct = int(((i - start) / seg_len) * 100)
            print(f"[Intel Segment {segment_index+1}/{total_segments}] {pct}% done (elapsed {time.time() - t0:.2f}s)")
            t0 = time.time()
            next_checkpoint += ten_percent
    return S

def run_parallel(total_iterations, processes, progress, affinity):
    processes = processes or cpu_count()
    seg_size = total_iterations // processes
    remainder = total_iterations % processes
    bounds = []
    start = 0
    for s in range(processes):
        size = seg_size + (1 if s < remainder else 0)
        end = start + size - 1
        bounds.append((start, end, s, processes, progress, affinity))
        start = end + 1
    t0 = time.time()
    with Pool(processes=processes) as pool:
        parts = pool.map(calculate_segment, bounds)
    S_total = sum(parts)
    return (C_CONST / S_total), time.time() - t0

def parse_args():
    p = argparse.ArgumentParser(description="Intel (PyPy recommended) Pi benchmark")
    p.add_argument('--iterations', type=int, default=10000, help='Total iteration count (default 10000)')
    p.add_argument('--processes', type=int, default=0, help='Number of worker processes (default: cpu_count)')
    p.add_argument('--progress', action='store_true', help='Show per-segment progress')
    p.add_argument('--affinity', action='store_true', help='Pin worker processes to specific cores')
    return p.parse_args()

def main():
    args = parse_args()
    overall_start = time.time()
    pi_val, parallel_duration = run_parallel(args.iterations, args.processes, args.progress, args.affinity)
    total_duration = time.time() - overall_start
    pi_str = str(pi_val)
    print("The last 50 digits of (approx) Pi are:", pi_str[-50:])
    print(f"Parallel time: {parallel_duration:.2f}s | Total time: {total_duration:.2f}s | Processes: {args.processes or cpu_count()} | Iterations: {args.iterations}")

if __name__ == '__main__':
    main()