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
    complete = val.get("optimization_complete", val.get("best_tier") == "optimized")
    heading = ("Value of optimizing this workload on this hardware" if complete else
               "Value of available optimizations on this hardware")
    lines = [bold(heading)]
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
        code_label = "optimized code" if complete else "best available tier"
        lines.append(f"  For this workload the {code_label} makes the VM behave like a "
                     + effective + " machine.")
    if not complete:
        lines.append("  " + yellow("! Full optimization result unavailable; install gmpy2/GMP and re-run."))
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


def _md_table(head: list[str], rows: list[list[str]]) -> str:
    return "\n".join(["| " + " | ".join(head) + " |",
                      "|" + "|".join(["---"] * len(head)) + "|",
                      *["| " + " | ".join(r) + " |" for r in rows]])


def render_results_matrix(rows: list[dict], metric: str = "median_seconds") -> str:
    if not rows:
        return "_No results found._"
    has_price = any(r.get("cost_per_1k_runs") for r in rows)
    head = ["Machine", "Arch", "Tier", "Cores", "Time", "vs baseline", "Runs/hr"]
    if has_price:
        head += ["Cost / 1k runs", "Runs per $"]

    body = []
    for r in rows:
        if r["status"] != "ok":
            cells = [r["label"], r["arch"], f"`{r['tier']}`", "-",
                     r.get("skipped_reason") or r["status"], "-", "-"]
            cells += ["-", "-"] if has_price else []
        else:
            cells = [
                r["label"], r["arch"], f"`{r['tier']}`", str(r.get("workers") or "-"),
                f"{r['seconds']:.3f}s",
                f"{r['vs_baseline']:.2f}x" if r.get("vs_baseline") else "-",
                f"{r['runs_per_hour']:,.1f}",
            ]
            if has_price:
                cells += [f"${r['cost_per_1k_runs']:,.4f}",
                          f"{r['runs_per_dollar']:,.1f}"]
        body.append(cells)

    note = (f"_Timing metric: `{metric}`. `vs baseline` compares each machine "
            "against its own baseline tier, not against another machine._")
    return _md_table(head, body) + "\n\n" + note


def render_machines_markdown(machines: list[dict]) -> str:
    if not machines:
        return ""
    head = ["Machine", "Arch", "CPU", "vCPU", "Phys cores", "SMT", "GMP",
            "$/hour", "$/month", "Steal"]
    body = []
    for m in machines:
        body.append([
            m["label"], m["arch"], m.get("model") or "unknown",
            str(m["vcpus"]), str(m.get("physical_cores") or "?"),
            "yes" if m.get("smt") else "no",
            m.get("gmp") or "none",
            f"${m['price_per_hour']:.5f}" if m.get("price_per_hour") else "-",
            f"${m['price_per_month']:,.2f}" if m.get("price_per_month") else "-",
            f"{m['steal_percent']:.2f}%" if m.get("steal_percent") is not None else "-",
        ])
    return _md_table(head, body)
