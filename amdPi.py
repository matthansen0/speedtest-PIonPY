"""AMD x64 Pi benchmark (parallel Chudnovsky-style approximation)

Optimizations applied:
 - Multiprocessing across all logical cores (default) with configurable --processes
 - Precomputes constant C once instead of per segment
 - Reduces sqrt calls and object lookups (local variable binding)
 - Optional progress output (--progress)
 - Optional CPU affinity pinning (--affinity) to reduce context switching

NOTE: This segmentation mirrors the original repository logic and is an
approximation of the Chudnovsky series state partitioning (not mathematically
exact). Suitable for relative CPU throughput comparisons.
"""

import argparse
import os
import time
from multiprocessing import Pool, cpu_count
import mpmath

mpmath.mp.dps = 10000
C_CONST = 426880 * mpmath.sqrt(10005)  # computed once

def _maybe_set_affinity(core_id, affinity):
    if not affinity:
        return
    try:
        os.sched_setaffinity(0, {core_id})
    except Exception:
        pass  # Non-Linux or permission denied

def calculate_segment(args):
    start, end, segment_index, total_segments, progress, affinity = args
    _maybe_set_affinity(segment_index % os.cpu_count(), affinity)
    segment_start_time = time.time()
    segment_length = end - start + 1
    ten_percent = max(1, segment_length // 10)
    next_checkpoint = start + ten_percent if progress else end + 1

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
            pct = int(((i - start) / segment_length) * 100)
            print(f"[Segment {segment_index+1}/{total_segments}] {pct}% done (elapsed {time.time() - segment_start_time:.2f}s)")
            segment_start_time = time.time()
            next_checkpoint += ten_percent

    return S

def run_parallel(total_iterations, processes, progress, affinity):
    processes = processes or cpu_count()
    segment_size = total_iterations // processes
    remainder = total_iterations % processes
    args = []
    start = 0
    for idx in range(processes):
        size = segment_size + (1 if idx < remainder else 0)
        end = start + size - 1
        args.append((start, end, idx, processes, progress, affinity))
        start = end + 1
    t0 = time.time()
    with Pool(processes=processes) as pool:
        parts = pool.map(calculate_segment, args)
    S_total = sum(parts)
    return (C_CONST / S_total), time.time() - t0

def parse_args():
    p = argparse.ArgumentParser(description="AMD Pi benchmark")
    p.add_argument('--iterations', type=int, default=10000, help='Total iteration count (default 10000)')
    p.add_argument('--processes', type=int, default=0, help='Number of worker processes (default: cpu_count)')
    p.add_argument('--progress', action='store_true', help='Show per-segment progress')
    p.add_argument('--affinity', action='store_true', help='Pin worker processes to specific cores')
    return p.parse_args()

def main():
    args = parse_args()
    overall_start = time.time()
    pi_val, elapsed = run_parallel(args.iterations, args.processes, args.progress, args.affinity)
    total_elapsed = time.time() - overall_start
    pi_str = str(pi_val)
    print("Last 50 digits:", pi_str[-50:])
    print(f"Parallel time: {elapsed:.2f}s | Total time: {total_elapsed:.2f}s | Processes: {args.processes or cpu_count()} | Iterations: {args.iterations}")

if __name__ == '__main__':
    main()