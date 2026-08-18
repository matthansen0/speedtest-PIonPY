#!/usr/bin/env python3
"""Print saved benchmark results side by side, one row per machine and tier.

    python3 compare_results.py results/
    python3 compare_results.py results/ --tier optimized
    python3 compare_results.py results/ --markdown-out COMPARISON.md

This lays the measurements out and stops there. It does not pick a winner, a
reference machine, or a headline tier: which pair of rows matters depends on
the question being asked, so that choice is left to the reader.
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


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("paths", nargs="+", type=Path, help="result files or directories")
    p.add_argument("--tier", choices=[t.key for t in harness.TIERS],
                   help="show only this tier; by default every tier is shown")
    p.add_argument("--metric", default="median_seconds",
                   choices=["median_seconds", "min_seconds"])
    p.add_argument("--markdown-out", type=Path, help="also write the tables to a file")
    args = p.parse_args(argv)

    reports = load_reports(args.paths)
    if not reports:
        print("[error] no usable result files found", file=sys.stderr)
        return 2

    rows = cost.results_matrix(reports, args.metric, args.tier)
    boxes = cost.machines(reports)
    checks = cost.integrity(reports)

    sections = [
        "## Results",
        "",
        report.render_results_matrix(rows, args.metric),
        "",
        "## Machines",
        "",
        report.render_machines_markdown(boxes),
    ]

    notes = []
    if not checks["same_size"]:
        notes.append("- Digit targets differ across runs ("
                     + ", ".join(f"{d:,}" for d in checks["digits"])
                     + "); re-run every machine with the same `--size`.")
    if not checks["digests_match"]:
        notes.append("- Machines did not produce identical digits of pi, "
                     "so the work performed was not the same.")
    noisy = sorted({r["label"] for r in rows if r.get("noisy")})
    if noisy:
        notes.append(f"- Run-to-run variance above 5% on: {', '.join(noisy)}.")
    stealy = sorted({m["label"] for m in boxes if (m.get("steal_percent") or 0) >= 1})
    if stealy:
        notes.append(f"- Hypervisor steal above 1% on: {', '.join(stealy)}.")
    if notes:
        sections += ["", "### Caveats", "", *notes]

    text = "\n".join(sections)
    print(text)
    if args.markdown_out:
        args.markdown_out.write_text(text + "\n")
        print(f"\n[info] wrote {args.markdown_out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
