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


def _mode_description(report: dict) -> str:
    run = report["run"]
    if report["mode"] == "optimized":
        build = (report["environment"]["interpreter"].get("gmp_build") or {})
        origin = (yellow("generic prebuilt wheel") if build.get("portable_wheel")
                  else green("built on this machine"))
        # gmpy2.mp_version() already reads like "GMP 6.3.0".
        detail = f"{run['gmp']} ({origin})"
    else:
        detail = "stock CPython big integers"
    return f"{report['mode']}  |  {detail}  |  {run['workers']} worker(s)"


def render_header(report: dict) -> str:
    env = report["environment"]
    cpu, topo = env["cpu"], env["topology"]
    cores = f"{topo['logical_cpus']} vCPU"
    if topo.get("physical_cores"):
        cores += f" / {topo['physical_cores']} physical core(s)"
    cores += "  " + (yellow(f"SMT {topo['threads_per_core']}x")
                     if topo.get("smt_enabled") else green("no SMT"))

    lines = [
        f"{bold('Machine')}    {env['hostname']}  |  "
        f"{cpu.get('model') or 'unknown'} ({cpu['arch']})",
        f"{bold('Cores')}      {cores}",
        f"{bold('Mode')}       {_mode_description(report)}",
        f"{bold('Workload')}   {report['digits']:,} digits of pi  |  "
        f"{report['terms']:,} series terms",
    ]
    return "\n".join(lines)


def render_result(report: dict) -> str:
    run = report["run"]
    econ = report.get("economics") or {}
    pricing = report.get("pricing") or {}

    variance = f"variance {run['cv'] * 100:.1f}%"
    wall = report.get("wall_seconds")
    lines = [
        green(bold(f"Ran {run['iterations']:,} iterations in {run['total_seconds']:,.1f}s"))
        + (dim(f"   ({wall:,.1f}s including warm-up)") if wall else ""),
        "  " + cyan(f"{run['seconds_per_iteration']:.3f}s per iteration")
        + f"   (fastest {run['fastest_seconds']:.3f}s, "
        + f"slowest {run['slowest_seconds']:.3f}s, "
        + (yellow(variance) if run["noisy"] else variance) + ")",
    ]
    if econ.get("iterations_per_hour"):
        lines.append(f"  {econ['iterations_per_hour']:,.1f} iterations/hour")
    if econ.get("cost_per_1k_iterations") is not None:
        price = pricing.get("price_per_hour")
        monthly = pricing.get("price_per_month")
        lines.append(f"  ${econ['cost_per_1k_iterations']:,.4f} per 1,000 iterations"
                     + dim(f"   (${price:.5f}/hr ~ ${monthly:,.2f}/mo)"))
    return "\n".join(lines)


def render_integrity(report: dict) -> str:
    run = report["run"]
    lines = [bold("Verified") + "   "
             + (green("yes - matches the known digits of pi") if run["verified"]
                else red("NO"))]
    method = report.get("verification")
    if method:
        lines.append(dim(f"           {method}"))
    rt = report.get("runtime") or {}
    steal = rt.get("steal_percent")
    if steal is not None and steal >= 1:
        lines.append(f"  {yellow('!')} Hypervisor steal {steal:.2f}% - the host was shared.")
    for key in ("environment_warnings", "measurement_warnings", "pricing_warnings"):
        for w in report.get(key, []):
            lines.append(f"  {yellow('!')} {w}")
    return "\n".join(lines)


def render_report(report: dict) -> str:
    sections = [
        render_header(report),
        render_result(report),
        render_integrity(report),
    ]
    body = "\n\n".join(s for s in sections if s)
    return f"{_rule()}\n{body}\n{_rule()}"


def _md_table(head: list[str], rows: list[list[str]]) -> str:
    return "\n".join(["| " + " | ".join(head) + " |",
                      "|" + "|".join(["---"] * len(head)) + "|",
                      *["| " + " | ".join(r) + " |" for r in rows]])


def render_summary_markdown(rows: list[dict]) -> str:
    if not rows:
        return "_No results found._"
    has_price = any(r.get("cost_per_1k_iterations") is not None for r in rows)
    head = ["Machine", "Arch", "CPU", "Mode", "Workers", "Digits",
            "Iterations", "Total", "s / iteration", "Iterations/hr"]
    if has_price:
        head += ["$/month", "Cost / 1k iterations"]

    body = []
    for r in rows:
        cells = [
            r["label"], r["arch"], r.get("model") or "unknown",
            f"`{r['mode']}`", str(r.get("workers") or "-"),
            f"{r['digits']:,}", f"{r['iterations']:,}",
            f"{r['total_seconds']:,.1f}s",
            f"{r['seconds_per_iteration']:.3f}s",
            f"{r['iterations_per_hour']:,.1f}" if r.get("iterations_per_hour") else "-",
        ]
        if has_price:
            cells += [
                f"${r['price_per_month']:,.2f}" if r.get("price_per_month") else "-",
                f"${r['cost_per_1k_iterations']:,.4f}"
                if r.get("cost_per_1k_iterations") is not None else "-",
            ]
        body.append(cells)
    return _md_table(head, body)
