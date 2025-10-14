"""ARM Pi benchmark with basic big.LITTLE awareness and parallel execution.

Enhancements:
 - Core frequency weighting: attempts to read max freq per core to weight work distribution
 - Configurable iterations/processes via argparse
 - Optional progress output and CPU affinity pinning
 - Single computation of constant C

Similar mathematical caveat as other scripts: segmentation approximates the
Chudnovsky recurrence state. Suitable for relative throughput benchmarking.
"""

import argparse
import os
import time
from multiprocessing import Pool, cpu_count
import mpmath

mpmath.mp.dps = 10000
C_CONST = 426880 * mpmath.sqrt(10005)

def read_core_frequencies(limit):
    freqs = []
    for core in range(limit):
        path = f"/sys/devices/system/cpu/cpu{core}/cpufreq/cpuinfo_max_freq"
        try:
            with open(path, 'r') as f:
                val = int(f.read().strip())
        except Exception:
            val = 1  # fallback
        freqs.append(max(val, 1))
    # Normalize (keep original magnitudes for weighting algorithm)
    return freqs

def allocate_ranges(total_iterations, processes, weights):
    total_w = sum(weights)
    base_counts = [int(total_iterations * w / total_w) for w in weights]
    assigned = sum(base_counts)
    # distribute leftover
    leftover = total_iterations - assigned
    idx = 0
    while leftover > 0:
        base_counts[idx] += 1
        leftover -= 1
        idx = (idx + 1) % processes
    # build ranges
    ranges = []
    start = 0
    for i, count in enumerate(base_counts):
        end = start + count - 1
        ranges.append((start, end, i, processes))
        start = end + 1
    return ranges

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
            print(f"[ARM Segment {segment_index+1}/{total_segments}] {pct}% done (elapsed {time.time() - t0:.2f}s)")
            t0 = time.time()
            next_checkpoint += ten_percent
    return S

def run_parallel(total_iterations, processes, progress, affinity, weight):
    processes = processes or cpu_count()
    if weight:
        freqs = read_core_frequencies(processes)
    else:
        freqs = [1] * processes
    ranges = allocate_ranges(total_iterations, processes, freqs)
    args = [(start, end, idx, processes, progress, affinity) for (start, end, idx, _) in ranges]
    t0 = time.time()
    with Pool(processes=processes) as pool:
        parts = pool.map(calculate_segment, args)
    S_total = sum(parts)
    return (C_CONST / S_total), time.time() - t0

def parse_args():
    p = argparse.ArgumentParser(description="ARM Pi benchmark")
    p.add_argument('--iterations', type=int, default=10000, help='Total iteration count (default 10000)')
    p.add_argument('--processes', type=int, default=0, help='Number of worker processes (default: cpu_count)')
    p.add_argument('--progress', action='store_true', help='Show per-segment progress')
    p.add_argument('--affinity', action='store_true', help='Pin worker processes to specific cores')
    p.add_argument('--weight-freq', action='store_true', help='Weight work by core max frequency (big.LITTLE)')
    return p.parse_args()

def main():
    args = parse_args()
    overall_start = time.time()
    pi_val, elapsed = run_parallel(args.iterations, args.processes, args.progress, args.affinity, args.weight_freq)
    total_elapsed = time.time() - overall_start
    print("Last 50 digits:", str(pi_val)[-50:])
    print(f"Parallel time: {elapsed:.2f}s | Total time: {total_elapsed:.2f}s | Processes: {args.processes or cpu_count()} | Iterations: {args.iterations} | Weighted: {args.weight_freq}")

if __name__ == '__main__':
    main()