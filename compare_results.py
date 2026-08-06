#!/usr/bin/env python3
"""Aggregate benchmark JSON files into a cross-architecture cost comparison.

    python3 compare_results.py results/
    python3 compare_results.py results/ --tier optimized --baseline intel-box
    python3 compare_results.py results/ --markdown-out COMPARISON.md

Refuses to present machines as comparable unless they ran the same digit
target and produced the same verified result.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pionpy import cost, harness, report


def load_reports(paths: list[Path]) -> list[dict]:
    files: list[Path] = []
    for p in paths:
        files.extend(sorted(p.glob("*.json")) if p.is_dir() else [p])
    reports = []
    for f in files:
        try:
            data = json.loads(f.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[warn] skipping {f}: {exc}", file=sys.stderr)
            continue
        if data.get("schema") != 2:
            print(f"[warn] skipping {f}: not a schema-2 result "
                  "(produced by an older, non-comparable version)", file=sys.stderr)
            continue
        data["_path"] = str(f)
        reports.append(data)
    return reports


def render_optimization_table(reports: list[dict]) -> str:
    """Per-machine view of what each optimization lever was worth."""
    lever_keys = ["algorithm", "native_math_library", "parallelism"]
    head = ["Machine", "Arch", "Baseline", "Optimized", "Total speedup",
            *[k.replace("_", " ") for k in lever_keys], "Effective $/mo"]
    lines = ["| " + " | ".join(head) + " |",
             "|" + "|".join(["---"] * len(head)) + "|"]
    for rep in reports:
        val = rep.get("optimization_value") or {}
        if not val:
            continue
        levers = val.get("lever_speedups") or {}
        cells = [
            rep.get("label", "?"), rep["environment"]["cpu"]["arch"],
            f"{val['baseline_seconds']:.3f}s", f"{val['best_seconds']:.3f}s",
            f"{val['optimization_speedup']:.2f}x",
            *[f"{levers[k]:.2f}x" if k in levers else "-" for k in lever_keys],
            f"${val['effective_price_per_month']:,.2f}"
            if val.get("effective_price_per_month") else "-",
        ]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("paths", nargs="+", type=Path, help="result files or directories")
    p.add_argument("--tier", default="optimized",
                   choices=[t.key for t in harness.TIERS],
                   help="tier to compare machines at")
    p.add_argument("--metric", default="median_seconds",
                   choices=["median_seconds", "min_seconds"])
    p.add_argument("--baseline", help="label of the machine to treat as 100%%")
    p.add_argument("--markdown-out", type=Path, help="also write the tables to a file")
    args = p.parse_args(argv)

    reports = load_reports(args.paths)
    if not reports:
        print("[error] no usable result files found", file=sys.stderr)
        return 2

    comparison = cost.compare(reports, args.baseline, args.metric, args.tier)

    sections = [
        f"## Hardware cost efficiency (`{args.tier}` tier)",
        "",
        report.render_comparison_markdown(comparison),
        "",
        "## Value of optimization, per machine",
        "",
        render_optimization_table(reports),
        "",
        "_Effective $/mo is the real price divided by the total optimization speedup: "
        "what the machine would have to cost for unoptimized code to be as cheap "
        "to run as the optimized code is today._",
    ]
    noisy = [r["label"] for r in comparison["rows"] if r.get("noisy")]
    stealy = [r["label"] for r in comparison["rows"]
              if (r.get("steal_percent") or 0) >= 1]
    if noisy or stealy:
        sections += ["", "### Caveats", ""]
        if noisy:
            sections.append(f"- High run-to-run variance on: {', '.join(noisy)}. Re-run when idle.")
        if stealy:
            sections.append(f"- Hypervisor steal time above 1% on: {', '.join(stealy)}. "
                            "The host was shared; results understate real capability.")

    text = "\n".join(sections)
    print(text)
    if args.markdown_out:
        args.markdown_out.write_text(text + "\n")
        print(f"\n[info] wrote {args.markdown_out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
