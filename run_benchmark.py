#!/usr/bin/env python3
"""Pi-on-Py: time a fixed pi calculation on this machine.

    python3 run_benchmark.py --mode generic   --sku azure_d2s_v5
    python3 run_benchmark.py --mode optimized --sku azure_d2ps_v6
    python3 compare_results.py results/

Both modes compute the same digits of pi, saturate every usable core, and are
verified against the known expansion. The only difference is the big-integer
backend: `generic` uses stock CPython, `optimized` uses GMP built for this CPU.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()

# Which profile each machine is expected to run.
CPU_PROFILES = {"intel": "generic", "arm": "optimized"}
ARCH_FAMILY = {
    "x86_64": "intel", "amd64": "intel", "i386": "intel", "i686": "intel",
    "aarch64": "arm", "arm64": "arm",
}


def _reexec_into_venv() -> None:
    """Re-run under ./venv if it exists and we are not already inside a venv."""
    if os.environ.get("PIONPY_VENV_ACTIVE"):
        return
    if getattr(sys, "base_prefix", sys.prefix) != sys.prefix:
        return
    candidate = PROJECT_ROOT / "venv" / "bin" / "python"
    if not candidate.exists():
        return
    env = os.environ.copy()
    env["PIONPY_VENV_ACTIVE"] = "1"
    try:
        os.execve(str(candidate), [str(candidate), *sys.argv], env)
    except OSError as exc:
        print(f"[warn] could not re-exec into ./venv ({exc}); continuing", file=sys.stderr)


_reexec_into_venv()

from pionpy import cost, harness, kernels, report  # noqa: E402


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Benchmark the cost value of optimizing a workload per CPU architecture.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--cpu", choices=sorted(CPU_PROFILES),
                   help="which machine this is: intel runs the stock profile, "
                        "arm runs the architecture-optimized profile, and each "
                        "picks its price from pricing.json")
    p.add_argument("--mode", choices=harness.MODES,
                   help="choose the profile directly, overriding --cpu "
                        "(default: generic)")
    p.add_argument("--size", choices=sorted(harness.SIZE_PRESETS), default="standard",
                   help="workload preset; every machine you compare must use the same one")
    p.add_argument("--digits", type=int,
                   help="explicit digit count, overrides --size")
    p.add_argument("--chunks", type=int, default=kernels.DEFAULT_CHUNKS,
                   help="fixed work decomposition; independent of core count by design")
    p.add_argument("--label", help="name for this machine in comparison tables")
    p.add_argument("--price-per-hour", type=float, help="hourly price for this machine")
    p.add_argument("--price-per-month", type=float,
                   help=f"monthly price ({cost.HOURS_PER_MONTH} hrs/month assumed)")
    p.add_argument("--pricing-file", type=Path, default=PROJECT_ROOT / "pricing.json")
    p.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "results")
    p.add_argument("--json-only", action="store_true", help="print JSON to stdout only")
    p.add_argument("--quiet", action="store_true", help="suppress per-iteration progress")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    digits = args.digits or harness.SIZE_PRESETS[args.size]
    mode = args.mode or CPU_PROFILES.get(args.cpu, "generic")

    # A mislabelled run is worse than no run, so refuse an obvious mismatch.
    if args.cpu and not args.mode:
        actual = ARCH_FAMILY.get(platform.machine().lower())
        if actual and actual != args.cpu:
            print(f"[error] --cpu {args.cpu} was requested but this machine reports "
                  f"{platform.machine()}. Use --cpu {actual}, or pass --mode to pick "
                  "the profile explicitly.", file=sys.stderr)
            return 2

    progress = None
    if not (args.quiet or args.json_only):
        def progress(done, total):
            end = "\n" if done == total else "\r"
            print(f"  iteration {done}/{total}", end=end, flush=True)
        print(f"[info] {digits:,} digits in {mode} mode - this takes a few minutes")

    try:
        result = harness.run_suite(digits, mode=mode, chunks=args.chunks,
                                   progress=progress)
    except harness.MissingGMP as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1

    result["label"] = args.label or result["environment"]["hostname"]
    result["size_preset"] = args.size if not args.digits else "custom"

    pricing = cost.load_pricing(args.pricing_file)
    sku = (pricing.get("cpu_defaults") or {}).get(args.cpu) if args.cpu else None
    resolved = cost.resolve_price(pricing, sku, args.price_per_hour, args.price_per_month)
    cost.annotate(result, resolved)
    result["pricing_warnings"] = cost.price_warnings(pricing, resolved)

    if args.json_only:
        print(json.dumps(result, indent=2))
    else:
        print(report.render_report(result))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in result["label"])
    arch = result["environment"]["cpu"]["arch"]
    path = args.output_dir / f"{safe}-{mode}-{arch}-{int(time.time())}.json"
    path.write_text(json.dumps(result, indent=2))
    if not args.json_only:
        print(f"\nSaved {path}")
        print(f"Compare machines with: python3 compare_results.py {args.output_dir}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
