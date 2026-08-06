#!/usr/bin/env python3
"""Pi-on-Py: measure the cost value of optimizing a workload for a CPU architecture.

    python3 run_benchmark.py --sku azure_d2ps_v6
    python3 run_benchmark.py --size deep --price-per-month 56.94
    python3 compare_results.py results/

The benchmark computes a fixed number of digits of pi at five optimization
tiers. Total work is identical on every machine and at every tier, every tier's
output is verified against the known expansion of pi, and timings are repeated
to a wall-clock budget so a single unlucky sample cannot decide the result.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()


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
    p.add_argument("--size", choices=sorted(harness.SIZE_PRESETS), default="standard",
                   help="workload preset; every machine you compare must use the same one")
    p.add_argument("--digits", type=int,
                   help="explicit digit count, overrides --size")
    p.add_argument("--chunks", type=int, default=kernels.DEFAULT_CHUNKS,
                   help="fixed work decomposition; independent of core count by design")
    p.add_argument("--label", help="name for this machine in comparison tables")
    p.add_argument("--sku", help="key from pricing.json, e.g. azure_d2ps_v6")
    p.add_argument("--price-per-hour", type=float, help="hourly price for this machine")
    p.add_argument("--price-per-month", type=float,
                   help=f"monthly price ({cost.HOURS_PER_MONTH} hrs/month assumed)")
    p.add_argument("--pricing-file", type=Path, default=PROJECT_ROOT / "pricing.json")
    p.add_argument("--metric", choices=["median_seconds", "min_seconds"],
                   default="median_seconds",
                   help="median reflects sustained cost; min reflects best case")
    p.add_argument("--tiers", help="comma-separated subset of tiers to run")
    p.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "results")
    p.add_argument("--json-only", action="store_true", help="print JSON to stdout only")
    p.add_argument("--quiet", action="store_true", help="suppress per-repetition progress")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    digits = args.digits or harness.SIZE_PRESETS[args.size]
    tiers = harness.TIERS
    if args.tiers:
        wanted = {t.strip() for t in args.tiers.split(",")}
        unknown = wanted - {t.key for t in harness.TIERS}
        if unknown:
            print(f"[error] unknown tier(s): {', '.join(sorted(unknown))}", file=sys.stderr)
            return 2
        tiers = tuple(t for t in harness.TIERS if t.key in wanted)

    progress = None
    if not (args.quiet or args.json_only):
        def progress(tier, done, total):
            end = "\n" if done == total else "\r"
            print(f"  running {tier.key:<10} {done}/{total} reps", end=end, flush=True)
        print(f"[info] {digits:,} digits, {len(tiers)} tiers - this takes a few minutes")

    result = harness.run_suite(digits, chunks=args.chunks, tiers=tiers, progress=progress)
    result["label"] = args.label or result["environment"]["hostname"]
    result["size_preset"] = args.size if not args.digits else "custom"

    pricing = cost.load_pricing(args.pricing_file)
    resolved = cost.resolve_price(pricing, args.sku, args.price_per_hour, args.price_per_month)
    cost.annotate(result, resolved, metric=args.metric)
    result["pricing_warnings"] = cost.price_warnings(pricing, resolved)

    if args.json_only:
        print(json.dumps(result, indent=2))
    else:
        print(report.render_report(result))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in result["label"])
    path = args.output_dir / f"{safe}-{result['environment']['cpu']['arch']}-{int(time.time())}.json"
    path.write_text(json.dumps(result, indent=2))
    if not args.json_only:
        print(f"\nSaved {path}")
        print(f"Compare machines with: python3 compare_results.py {args.output_dir}/")

    failed = [t for t in result["tiers"] if t["status"] == "failed"]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
