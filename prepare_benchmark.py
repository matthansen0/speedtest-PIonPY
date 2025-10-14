#!/usr/bin/env python3
"""One-shot preparation script for Pi-on-Py benchmark (no flags required).

Run this first:
    python3 prepare_benchmark.py
Then run the benchmark:
    python3 run_benchmark.py

What this script does:
  * Creates (or reuses) a local Python virtual environment at ./venv
  * Installs required Python dependencies (requirements.txt)
  * Optionally suggests installing PyPy for JIT speedups (Intel/AMD) – actual PyPy usage
    is handled automatically by run_benchmark.py via a separate local .pypy_venv.
  * Leaves your shell environment unchanged (no activation needed) because run_benchmark.py
    will auto re-exec inside ./venv if you forget to activate it.

Safe to re-run; it will only update what is missing.
"""
from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
VENV_DIR = PROJECT_ROOT / 'venv'
REQ_FILE = PROJECT_ROOT / 'requirements.txt'


def _run(cmd, **kwargs):
    print(f"[prep] $ {' '.join(cmd)}")
    return subprocess.run(cmd, **kwargs)


def ensure_python_version():
    if sys.version_info < (3, 8):
        print(f"[error] Python 3.8+ required, found {sys.version}. Please upgrade.")
        sys.exit(1)


def create_or_reuse_venv():
    if VENV_DIR.exists():
        print(f"[prep] Reusing existing venv at {VENV_DIR}")
    else:
        print(f"[prep] Creating venv at {VENV_DIR} ...")
        res = _run([sys.executable, '-m', 'venv', str(VENV_DIR)])
        if res.returncode != 0:
            print('[error] Failed to create virtual environment.')
            sys.exit(1)


def venv_python() -> Path:
    return VENV_DIR / 'bin' / 'python'


def ensure_requirements():
    py = venv_python()
    if not py.exists():
        print('[error] venv python not found after creation.')
        sys.exit(1)
    if not REQ_FILE.exists():
        print(f"[warn] requirements.txt not found at {REQ_FILE}, skipping dependency install.")
        return
    print('[prep] Installing/Updating Python dependencies...')
    cmd = [str(py), '-m', 'pip', 'install', '--upgrade', 'pip']
    _run(cmd)
    cmd = [str(py), '-m', 'pip', 'install', '-r', str(REQ_FILE)]
    res = _run(cmd)
    if res.returncode != 0:
        print('[error] Failed to install requirements.')
        sys.exit(1)


def suggest_pypy():
    arch = platform.machine().lower()
    if arch in ('x86_64', 'amd64'):
        # Only suggest if pypy3 not already available
        from shutil import which
        if which('pypy3') is None:
            print('[hint] Optional: Install PyPy for additional JIT speedups (Intel/AMD).')
            print('       Debian/Ubuntu: sudo apt update && sudo apt install pypy3 pypy3-venv -y')
            print('       After installing rerun the benchmark; it will auto-create .pypy_venv.')
        else:
            print('[prep] PyPy detected; benchmark may auto-use it via local .pypy_venv.')


def main():
    print('[prep] Starting environment preparation...')
    ensure_python_version()
    create_or_reuse_venv()
    ensure_requirements()
    suggest_pypy()
    print('\n[prep] Preparation complete.')
    print('[next] Run:  python3 run_benchmark.py')
    print('[info] (You do not need to activate the venv; the benchmark will auto re-exec inside it.)')
    print('[info] To inspect the environment manually: source venv/bin/activate')


if __name__ == '__main__':
    main()
