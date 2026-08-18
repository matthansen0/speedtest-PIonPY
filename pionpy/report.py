"""Console and Markdown rendering of benchmark reports."""
from __future__ import annotations

import os
import sys

_ANSI = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _c(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _ANSI else text


def bold(t): return _c(t, "1")
def dim(t): return _c(t, "2")
def green(t): return _c(t, "92")
def yellow(t): return _c(t, "93")
def red(t): return _c(t, "91")
def cyan(t): return _c(t, "96")


def _rule(width: int = 78) -> str:
    return dim("-" * width)


def _table(headers: list[str], rows: list[list[str]], aligns: str = "") -> str:
    aligns = aligns.ljust(len(headers), "l")
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(_strip(cell)))

    def fmt(cell, i):
        pad = widths[i] - len(_strip(cell))
        return (" " * pad + cell) if aligns[i] == "r" else (cell + " " * pad)

    out = ["  ".join(fmt(bold(h), i) for i, h in enumerate(headers))]
    out.append("  ".join(dim("-" * w) for w in widths))
    for row in rows:
        out.append("  ".join(fmt(c, i) for i, c in enumerate(row)))
    return "\n".join(out)


def _strip(s: str) -> str:
    out, i = [], 0
    while i < len(s):
        if s[i] == "\033":
            while i < len(s) and s[i] != "m":
                i += 1
            i += 1
            continue
        out.append(s[i])
        i += 1
    return "".join(out)


def render_environment(report: dict) -> str:
    env = report["environment"]
    cpu, topo, interp = env["cpu"], env["topology"], env["interpreter"]
    lines = [bold("Environment")]
    lines.append(f"  CPU            {cpu.get('model') or 'unknown'}  ({cpu['arch']})")
    cores = f"{topo['logical_cpus']} vCPU"
    if topo.get("physical_cores"):
        cores += f" / {topo['physical_cores']} physical core(s)"
    if topo.get("smt_enabled"):
        cores += "  " + yellow(f"SMT {topo['threads_per_core']}x")
    else:
        cores += "  " + green("no SMT")
    lines.append(f"  Cores          {cores}")
    lines.append(f"  Usable CPUs    {env['usable_cpus']}"
                 + (f"  (cgroup limit {env['cgroup_cpu_limit']})" if env.get("cgroup_cpu_limit") else ""))
    lines.append(f"  Runtime        {interp['implementation']} {interp['version']}"
                 + (f"  |  GMP {interp['gmp']} via gmpy2 {interp['gmpy2']}" if interp.get("gmp") else "  |  no GMP"))
    lines.append(f"  Host           {env['os']}  |  {env.get('virtualization') or 'bare metal / unknown'}")
    if cpu.get("max_freq_mhz"):
        lines.append(f"  Max frequency  {cpu['max_freq_mhz']} MHz")
    return "\n".join(lines)


def render_workload(report: dict) -> str:
    return (f"{bold('Workload')}\n"
            f"  {report['digits']:,} digits of pi  |  {report['terms']:,} series terms  "
            f"|  {report['chunks']} fixed chunks\n"
            f"  {dim('Work is identical on every machine and every tier; only time varies.')}")


def render_tiers(report: dict) -> str:
    headers = ["Tier", "Optimization lever", "Cores", "Median", "Best", "±CV", "vs base", "Verified"]
    rows = []
    ok = {t["key"]: t for t in report["tiers"] if t["status"] == "ok"}
    base = ok.get("baseline")
    for t in report["tiers"]:
        if t["status"] != "ok":
            rows.append([t["key"], t["lever"], "-", dim("skipped"), "-", "-", "-",
                         dim(t.get("skipped_reason") or t["status"])])
            continue
        speedup = f"{base['median_seconds'] / t['median_seconds']:.2f}x" if base else "-"
        cv = f"{t['cv'] * 100:.1f}%"
        rows.append([
            t["key"], t["lever"], str(t["workers"]),
            f"{t['median_seconds']:.3f}s", f"{t['min_seconds']:.3f}s",
            yellow(cv) if t["noisy"] else cv,
            cyan(speedup) if speedup != "-" else "-",
            green("yes") if t["verified"] else red("NO"),
        ])
    return bold("Optimization tiers") + "\n" + _table(headers, rows, "lllrrrrl")


def render_economics(report: dict) -> str:
    price = (report.get("pricing") or {}).get("price_per_hour")
    if price is None:
        return ""
    headers = ["Tier", "Runs/hour", "Cost / 1k runs", "Runs per $"]
    rows = []
    for t in report["tiers"]:
        econ = t.get("economics")
        if not econ:
            continue
        rows.append([t["key"], f"{econ['runs_per_hour']:,.1f}",
                     f"${econ['cost_per_1k_runs']:,.4f}", f"{econ['runs_per_dollar']:,.1f}"])
    pricing = report["pricing"]
    monthly = pricing.get("price_per_month")
    source = pricing.get("source")
    subtitle = dim(f"${price:.5f}/hr ~ ${monthly:,.2f}/mo  (source: {source})")
    return bold("Cost of compute") + "  " + subtitle + "\n" + _table(headers, rows, "lrrr")


def render_optimization_value(report: dict) -> str:
    val = report.get("optimization_value") or {}
    if not val:
        return ""
    speedup = val["optimization_speedup"]
    lines = [bold("Value of optimizing this workload on this hardware")]
    lines.append(f"  {val['baseline_tier']} -> {val['best_tier']}: "
                 f"{val['baseline_seconds']:.3f}s -> {val['best_seconds']:.3f}s  = "
                 + cyan(f"{speedup:.2f}x faster"))
    levers = val.get("lever_speedups") or {}
    for name, factor in levers.items():
        lines.append(f"    {name:<22} {factor:>6.2f}x")
    if val.get("parallel_efficiency_percent") is not None:
        eff = val["parallel_efficiency_percent"]
        tag = green(f"{eff}%") if eff >= 70 else yellow(f"{eff}%")
        lines.append(f"    {'parallel efficiency':<22} {tag:>6}")
    if "cost_reduction_percent" in val:
        drop = green(f"-{val['cost_reduction_percent']:.1f}%")
        effective = cyan(f"${val['effective_price_per_month']:,.2f}/mo")
        lines.append("")
        lines.append(f"  Cost per 1k runs   ${val['cost_per_1k_runs_baseline']:,.4f}"
                     f"  ->  ${val['cost_per_1k_runs_optimized']:,.4f}   ({drop})")
        lines.append("  For this workload the optimized code makes the VM behave like a "
                     + effective + " machine.")
    return "\n".join(lines)


def render_integrity(report: dict) -> str:
    lines = [bold("Result integrity")]
    rt = report.get("runtime") or {}
    steal = rt.get("steal_percent")
    if steal is None:
        steal_txt = dim("unavailable")
    elif steal < 1:
        steal_txt = green(f"{steal:.2f}%")
    elif steal < 5:
        steal_txt = yellow(f"{steal:.2f}% - noisy host, treat results as soft")
    else:
        steal_txt = red(f"{steal:.2f}% - host heavily oversubscribed, results unreliable")
    lines.append(f"  Hypervisor steal     {steal_txt}")
    match = report.get("cross_tier_digest_match")
    lines.append(f"  All tiers agree      "
                 + (green("yes - identical digits of pi") if match else red("NO - tiers disagree")))
    method = report.get("verification")
    if method:
        lines.append("  Digit verification   "
                     + (green(method) if method.startswith("full") else yellow(method)))
    noisy = [t["key"] for t in report["tiers"] if t.get("noisy")]
    lines.append(f"  Run-to-run variance  "
                 + (yellow("high in: " + ", ".join(noisy)) if noisy else green("within 5% on every tier")))
    for w in report.get("environment_warnings", []):
        lines.append(f"  {yellow('!')} {w}")
    for w in report.get("measurement_warnings", []):
        lines.append(f"  {yellow('!')} {w}")
    for w in report.get("pricing_warnings", []):
        lines.append(f"  {yellow('!')} {w}")
    return "\n".join(lines)


def render_report(report: dict) -> str:
    sections = [
        render_environment(report),
        render_workload(report),
        render_tiers(report),
        render_optimization_value(report),
        render_economics(report),
        render_integrity(report),
    ]
    body = "\n\n".join(s for s in sections if s)
    return f"{_rule()}\n{body}\n{_rule()}"


def render_comparison_markdown(comparison: dict) -> str:
    rows = comparison["rows"]
    if not rows:
        return "_No comparable results found._"
    has_price = any(r.get("runs_per_dollar") for r in rows)
    head = ["Machine", "Arch", "vCPU", "Phys cores", "SMT", "Time", "Runs/hr"]
    if has_price:
        head += ["$/month", "Runs per $", "Value vs base"]
    head += ["Steal", "Opt. speedup"]

    lines = ["| " + " | ".join(head) + " |",
             "|" + "|".join(["---"] * len(head)) + "|"]
    for r in rows:
        cells = [
            str(r["label"]), r["arch"], str(r["vcpus"]),
            str(r.get("physical_cores") or "?"),
            "yes" if r.get("smt") else "no",
            f"{r['seconds']:.3f}s", f"{r['runs_per_hour']:,.1f}",
        ]
        if has_price:
            cells += [
                f"${r['price_per_month']:,.2f}" if r.get("price_per_month") else "-",
                f"{r['runs_per_dollar']:,.1f}" if r.get("runs_per_dollar") else "-",
                ("baseline" if r.get("is_baseline")
                 else f"{r['value_delta_percent']:+.1f}%" if r.get("value_delta_percent") is not None
                 else "-"),
            ]
        cells += [
            f"{r['steal_percent']:.2f}%" if r.get("steal_percent") is not None else "-",
            f"{r['optimization_speedup']:.2f}x" if r.get("optimization_speedup") else "-",
        ]
        lines.append("| " + " | ".join(cells) + " |")

    notes = [""]
    notes.append(f"_Tier compared: `{comparison['tier']}` using `{comparison['metric']}`. "
                 f"Baseline machine: {comparison['baseline']}._")
    if not comparison.get("comparable"):
        notes.append("")
        notes.append("> **Warning:** these runs are not directly comparable - "
                     "the digit targets differ or the computed results do not match. "
                     "Re-run every machine with the same `--size`.")
    elif comparison.get("digests_match"):
        notes.append("")
        notes.append("_Every machine produced a bit-identical result "
                     "(matching SHA-256 of the digit string), so the work performed was identical._")
    return "\n".join(lines + notes)
