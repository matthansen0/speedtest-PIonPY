#!/usr/bin/env python3
"""One-time environment preparation for the Pi-on-Py benchmark.

    python3 prepare_benchmark.py
    python3 run_benchmark.py --sku azure_d2ps_v6

Creates ./venv, installs dependencies, and verifies that the benchmark
produces correct digits of pi before you spend time collecting numbers.

gmpy2 must compile against the platform's GMP. That is deliberate: the
"native math library" tier exists to measure what an architecture-tuned
numeric stack is worth, so it has to be a real build for this CPU.
"""
from __future__ import annotations

import platform
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
VENV_DIR = PROJECT_ROOT / "venv"
REQ_FILE = PROJECT_ROOT / "requirements.txt"

BUILD_DEPS_HINT = {
    "debian": "sudo apt update && sudo apt install -y python3-dev python3-venv "
              "libgmp-dev libmpfr-dev libmpc-dev build-essential",
    "rhel": "sudo dnf install -y python3-devel gmp-devel mpfr-devel libmpc-devel gcc",
}


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    print(f"[prep] $ {' '.join(cmd)}")
    return subprocess.run(cmd)


def venv_python() -> Path:
    return VENV_DIR / "bin" / "python"


def ensure_python_version() -> None:
    if sys.version_info < (3, 9):
        print(f"[error] Python 3.9+ required, found {platform.python_version()}.")
        sys.exit(1)


def create_venv() -> None:
    if VENV_DIR.exists():
        print(f"[prep] reusing venv at {VENV_DIR}")
        return
    print(f"[prep] creating venv at {VENV_DIR}")
    if _run([sys.executable, "-m", "venv", str(VENV_DIR)]).returncode != 0:
        print("[error] could not create the virtual environment.")
        print("        Debian/Ubuntu: sudo apt install -y python3-venv")
        sys.exit(1)


def install_requirements() -> bool:
    py = venv_python()
    if not py.exists():
        print("[error] venv python missing after creation.")
        sys.exit(1)
    _run([str(py), "-m", "pip", "install", "--quiet", "--upgrade", "pip"])
    if _run([str(py), "-m", "pip", "install", "--quiet", "-r", str(REQ_FILE)]).returncode == 0:
        return True

    print("\n[warn] dependency install failed. gmpy2 usually needs GMP headers:")
    for name, hint in BUILD_DEPS_HINT.items():
        print(f"       {name:<7} {hint}")
    print("\n[prep] retrying without gmpy2 so the other tiers still work...")
    ok = _run([str(py), "-m", "pip", "install", "--quiet", "mpmath>=1.3.0"]).returncode == 0
    if ok:
        print("[warn] the native-acceleration tier will be skipped on this machine,")
        print("       which removes the most architecture-sensitive measurement.")
    return ok


SELF_TEST = """
from pionpy import kernels as K
d = 5000
values = [K.pi_linear(d), K.pi_binary_splitting(d)]
try:
    import gmpy2
    values.append(K.pi_binary_splitting(d, use_gmp=True))
    gmp = gmpy2.mp_version()
except ImportError:
    gmp = None
assert all(K.verify(v, d) for v in values), 'digit verification failed'
assert len(set(values)) == 1, 'kernels disagree with each other'
print('[prep] self-test passed:', K.verification_method(d), '| GMP:', gmp or 'not available')
"""


def self_test() -> bool:
    """Prove the benchmark computes real digits of pi before anyone trusts it."""
    print("[prep] $ python -c <self-test: verify pi digits across all kernels>")
    return subprocess.run([str(venv_python()), "-c", SELF_TEST]).returncode == 0


def main() -> int:
    print("[prep] preparing Pi-on-Py benchmark environment")
    ensure_python_version()
    create_venv()
    if not install_requirements():
        print("[error] could not install dependencies.")
        return 1
    if not self_test():
        print("[error] self-test failed; do not trust results from this environment.")
        return 1
    print("\n[prep] ready.")
    print("[next] python3 run_benchmark.py --sku azure_d2ps_v6")
    print("       (list SKUs in pricing.json, or pass --price-per-month)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
