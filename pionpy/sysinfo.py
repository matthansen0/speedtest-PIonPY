"""Environment fingerprinting.

Cloud benchmark numbers are only defensible if you can prove what you were
actually running on. In particular this captures the three things that most
often invalidate an ARM-vs-x86 comparison:

  1. vCPU != core. An x86 vCPU is usually an SMT sibling; an ARM vCPU is
     usually a whole physical core. Comparing "2 vCPU vs 2 vCPU" without
     saying so is the single most common mistake.
  2. cgroup CPU quota. In containers the usable CPU budget is often lower
     than the visible CPU count.
  3. Steal time. On shared cloud hosts a noisy neighbour silently inflates
     wall-clock time. Measured across the run, not just sampled once.
"""
from __future__ import annotations

import os
import platform
import re
import sys
from pathlib import Path


def _read(path: str) -> str | None:
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def _read_int(path: str) -> int | None:
    raw = _read(path)
    try:
        return int(raw) if raw is not None else None
    except ValueError:
        return None


def usable_cpus() -> int:
    """CPUs this process is actually allowed to run on, honouring affinity."""
    try:
        return len(os.sched_getaffinity(0))
    except AttributeError:
        return os.cpu_count() or 1


def cgroup_cpu_limit() -> float | None:
    """Effective CPU limit from cgroup v2 or v1, in whole-CPU units."""
    v2 = _read("/sys/fs/cgroup/cpu.max")
    if v2:
        parts = v2.split()
        if len(parts) == 2 and parts[0] != "max":
            try:
                return int(parts[0]) / int(parts[1])
            except (ValueError, ZeroDivisionError):
                pass
    quota = _read_int("/sys/fs/cgroup/cpu/cpu.cfs_quota_us")
    period = _read_int("/sys/fs/cgroup/cpu/cpu.cfs_period_us")
    if quota and period and quota > 0:
        return quota / period
    return None


def topology() -> dict:
    """Physical core count and SMT factor from sysfs topology."""
    cores: set[tuple[str, str]] = set()
    online = 0
    base = Path("/sys/devices/system/cpu")
    try:
        cpu_dirs = sorted(base.glob("cpu[0-9]*"))
    except OSError:
        cpu_dirs = []
    for cpu_dir in cpu_dirs:
        core_id = _read(str(cpu_dir / "topology/core_id"))
        pkg_id = _read(str(cpu_dir / "topology/physical_package_id"))
        if core_id is None:
            continue
        online += 1
        cores.add((pkg_id or "0", core_id))
    logical = online or (os.cpu_count() or 1)
    physical = len(cores) or None
    smt = round(logical / physical, 2) if physical else None
    return {
        "logical_cpus": logical,
        "physical_cores": physical,
        "threads_per_core": smt,
        "smt_enabled": bool(smt and smt > 1),
    }


def cpu_identity() -> dict:
    """Human-readable CPU identification for x86 and ARM."""
    info: dict = {"arch": platform.machine(), "model": None, "vendor": None}
    text = _read("/proc/cpuinfo") or ""

    m = re.search(r"^model name\s*:\s*(.+)$", text, re.M)
    if m:
        info["model"] = m.group(1).strip()
    m = re.search(r"^vendor_id\s*:\s*(.+)$", text, re.M)
    if m:
        info["vendor"] = m.group(1).strip()

    if info["model"] is None:
        # ARM exposes implementer/part codes instead of a model string.
        impl = re.findall(r"^CPU implementer\s*:\s*(\S+)$", text, re.M)
        part = re.findall(r"^CPU part\s*:\s*(\S+)$", text, re.M)
        implementers = {
            "0x41": "ARM", "0x42": "Broadcom", "0x43": "Cavium",
            "0x46": "Fujitsu", "0x48": "HiSilicon", "0x4e": "NVIDIA",
            "0x50": "Ampere", "0x51": "Qualcomm", "0x61": "Apple",
            "0x6d": "Microsoft", "0xc0": "Ampere",
        }
        parts = {
            "0xd0c": "Neoverse-N1", "0xd49": "Neoverse-N2",
            "0xd40": "Neoverse-V1", "0xd4f": "Neoverse-V2",
            "0xd8e": "Neoverse-N3", "0xd83": "Neoverse-V3",
            "0xd03": "Cortex-A53", "0xd08": "Cortex-A72",
            "0xd0b": "Cortex-A76", "0xd44": "Cortex-X1",
        }
        if impl:
            info["vendor"] = implementers.get(impl[0].lower(), impl[0])
        if part:
            uniq = sorted(set(p.lower() for p in part))
            info["model"] = "/".join(parts.get(p, p) for p in uniq)
            info["heterogeneous_cores"] = len(uniq) > 1

    freq = _read_int("/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq")
    info["max_freq_mhz"] = round(freq / 1000) if freq else None
    info["page_size_kb"] = os.sysconf("SC_PAGE_SIZE") // 1024
    return info


def _gmpy2_build() -> dict:
    """How gmpy2 was installed. A portable wheel bundles a generic GMP."""
    try:
        import importlib.metadata as md

        text = md.distribution("gmpy2").read_text("WHEEL") or ""
    except Exception:
        return {"tags": [], "portable_wheel": None}
    tags = [line.split(":", 1)[1].strip()
            for line in text.splitlines() if line.startswith("Tag:")]
    portable = any("manylinux" in t or "musllinux" in t for t in tags)
    return {"tags": tags, "portable_wheel": portable}


def interpreter_info() -> dict:
    info = {
        "implementation": platform.python_implementation(),
        "version": platform.python_version(),
        "executable": sys.executable,
    }
    try:
        import gmpy2

        info["gmpy2"] = gmpy2.version()
        info["gmp"] = gmpy2.mp_version()
        info["gmp_build"] = _gmpy2_build()
    except ImportError:
        info["gmpy2"] = None
        info["gmp"] = None
        info["gmp_build"] = None
    return info


class StealMonitor:
    """Measures hypervisor steal time and involuntary preemption over a run.

    High steal means the host was oversubscribed and the resulting timings
    should not be trusted for cost comparison.
    """

    def __init__(self) -> None:
        self._start = self._sample()
        self._ctx_start = self._ctx_switches()

    @staticmethod
    def _sample() -> list[int] | None:
        text = _read("/proc/stat")
        if not text:
            return None
        for line in text.splitlines():
            if line.startswith("cpu "):
                return [int(v) for v in line.split()[1:]]
        return None

    @staticmethod
    def _ctx_switches() -> int | None:
        text = _read(f"/proc/{os.getpid()}/status") or ""
        m = re.search(r"^nonvoluntary_ctxt_switches:\s*(\d+)$", text, re.M)
        return int(m.group(1)) if m else None

    def result(self) -> dict:
        end = self._sample()
        out: dict = {"steal_percent": None, "involuntary_ctx_switches": None}
        if self._start and end and len(end) >= 8 and len(self._start) >= 8:
            deltas = [e - s for e, s in zip(end, self._start)]
            total = sum(deltas)
            if total > 0:
                out["steal_percent"] = round(deltas[7] / total * 100, 3)
        ctx_end = self._ctx_switches()
        if ctx_end is not None and self._ctx_start is not None:
            out["involuntary_ctx_switches"] = ctx_end - self._ctx_start
        return out


def collect() -> dict:
    topo = topology()
    return {
        "cpu": cpu_identity(),
        "topology": topo,
        "usable_cpus": usable_cpus(),
        "cgroup_cpu_limit": cgroup_cpu_limit(),
        "interpreter": interpreter_info(),
        "os": f"{platform.system()} {platform.release()}",
        "hostname": platform.node(),
        "virtualization": _detect_virt(),
    }


def _detect_virt() -> str | None:
    for path in ("/sys/class/dmi/id/sys_vendor", "/sys/class/dmi/id/product_name"):
        val = _read(path)
        if val:
            return val
    text = _read("/proc/cpuinfo") or ""
    if "hypervisor" in text:
        return "hypervisor (unidentified)"
    return None


def warnings(env: dict) -> list[str]:
    """Conditions that would make a cost comparison misleading."""
    out = []
    topo = env["topology"]
    if topo.get("smt_enabled"):
        out.append(
            f"SMT is on ({topo['threads_per_core']} threads/core): "
            f"{topo['logical_cpus']} vCPUs = {topo['physical_cores']} physical cores. "
            "Compare against ARM on physical cores, not vCPU count."
        )
    limit = env.get("cgroup_cpu_limit")
    if limit is not None and limit < env["usable_cpus"]:
        out.append(
            f"cgroup limits this process to {limit} CPUs but {env['usable_cpus']} are visible; "
            "parallel tiers will be throttled."
        )
    if env["usable_cpus"] < topo["logical_cpus"]:
        out.append(
            f"CPU affinity restricts this process to {env['usable_cpus']} of "
            f"{topo['logical_cpus']} CPUs."
        )
    if env["interpreter"]["gmp"] is None:
        out.append("gmpy2/GMP not installed: optimized mode cannot run on this machine.")
    return out
