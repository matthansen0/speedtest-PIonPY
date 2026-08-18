"""Deterministic, verifiable pi kernels used as the benchmark workload.

Every kernel computes floor(pi * 10**digits) and MUST return bit-identical
output for a given `digits` value on every machine and at every optimization
tier. That property is what makes cross-architecture comparison meaningful:
the work is fixed, only the time-to-complete varies.
"""
from __future__ import annotations

import sys
from functools import lru_cache
from typing import Callable, Sequence

# Chudnovsky constants.
_C = 640320
_C3_OVER_24 = _C**3 // 24
DIGITS_PER_TERM = 14.181647462725477  # log10(_C3_OVER_24 / 72)

# Guard digits dropped before returning, so the final digit is never a
# rounding artifact and the sha256 digest is stable across implementations.
GUARD_DIGITS = 16

# Number of leaf chunks the binary-splitting range is cut into. Fixed on
# purpose: total work must NOT depend on how many cores the machine has.
DEFAULT_CHUNKS = 128

PI_FIRST_100 = (
    "31415926535897932384626433832795028841971693993751"
    "05820974944592307816406286208998628034825342117067"
)

if hasattr(sys, "set_int_max_str_digits"):
    sys.set_int_max_str_digits(0)


def _int_ops(use_gmp: bool):
    """Return (to_int, isqrt) for the requested big-integer backend."""
    if use_gmp:
        import gmpy2

        return gmpy2.mpz, gmpy2.isqrt
    import math

    return int, math.isqrt


def terms_for_digits(digits: int) -> int:
    return int((digits + GUARD_DIGITS) / DIGITS_PER_TERM) + 2


# --------------------------------------------------------------------------
# Tier 0 kernel: naive linear summation (correct, but O(n * prec) bignum ops)
# --------------------------------------------------------------------------

def pi_linear(digits: int, use_gmp: bool = False) -> int:
    """Straightforward term-by-term Chudnovsky in fixed-point arithmetic.

    This is the "wrote it the obvious way" baseline. It is numerically
    correct, unlike the previous benchmark's segmented approximation.
    """
    to_int, isqrt = _int_ops(use_gmp)
    prec = digits + GUARD_DIGITS
    one = to_int(10) ** prec
    c3_over_24 = to_int(_C3_OVER_24)

    a_k = one
    a_sum = one
    b_sum = to_int(0)
    k = 0
    while a_k != 0:
        k += 1
        a_k *= -(6 * k - 5) * (2 * k - 1) * (6 * k - 1)
        a_k //= k * k * k * c3_over_24
        a_sum += a_k
        b_sum += k * a_k

    total = 13591409 * a_sum + 545140134 * b_sum
    pi = (426880 * isqrt(10005 * one * one) * one) // total
    return int(pi // to_int(10) ** GUARD_DIGITS)


# --------------------------------------------------------------------------
# Tier 1+ kernel: binary splitting
# --------------------------------------------------------------------------

def _bs(a: int, b: int, to_int):
    """Exact binary splitting over term range [a, b). Returns (P, Q, T)."""
    if b - a == 1:
        if a == 0:
            p = q = to_int(1)
        else:
            p = to_int((6 * a - 5) * (2 * a - 1) * (6 * a - 1))
            q = to_int(a) * a * a * _C3_OVER_24
        t = p * (13591409 + 545140134 * a)
        if a & 1:
            t = -t
        return p, q, t
    m = (a + b) // 2
    p1, q1, t1 = _bs(a, m, to_int)
    p2, q2, t2 = _bs(m, b, to_int)
    return p1 * p2, q1 * q2, q2 * t1 + p1 * t2


def _combine(left, right):
    p1, q1, t1 = left
    p2, q2, t2 = right
    return p1 * p2, q1 * q2, q2 * t1 + p1 * t2


def chunk_bounds(digits: int, chunks: int) -> list[tuple[int, int]]:
    """Split the term range into `chunks` contiguous pieces.

    Deterministic and independent of CPU count, so every machine executes the
    exact same decomposition.
    """
    n = terms_for_digits(digits)
    chunks = max(1, min(chunks, n))
    base, extra = divmod(n, chunks)
    bounds = []
    start = 0
    for i in range(chunks):
        end = start + base + (1 if i < extra else 0)
        bounds.append((start, end))
        start = end
    return bounds


def compute_chunk(task):
    """Pool worker entry point. Returns (index, P, Q, T) with plain ints.

    gmpy2 mpz values are converted back to int for pickling so the parent
    does not need the same backend loaded.
    """
    index, a, b, use_gmp = task
    to_int, _ = _int_ops(use_gmp)
    p, q, t = _bs(a, b, to_int)
    return index, int(p), int(q), int(t)


def _reduce_tree(parts: Sequence[tuple]) -> tuple:
    """Order-preserving balanced reduction (keeps combine cost near-optimal)."""
    items = list(parts)
    while len(items) > 1:
        nxt = []
        for i in range(0, len(items) - 1, 2):
            nxt.append(_combine(items[i], items[i + 1]))
        if len(items) & 1:
            nxt.append(items[-1])
        items = nxt
    return items[0]


def finalize(pqt: tuple, digits: int, use_gmp: bool) -> int:
    to_int, isqrt = _int_ops(use_gmp)
    _, q, t = pqt
    q, t = to_int(q), to_int(t)
    prec = digits + GUARD_DIGITS
    one_sq = to_int(10) ** (2 * prec)
    sqrt_c = isqrt(to_int(10005) * one_sq)
    pi = (q * 426880 * sqrt_c) // t
    return int(pi // to_int(10) ** GUARD_DIGITS)


def pi_binary_splitting(
    digits: int,
    chunks: int = DEFAULT_CHUNKS,
    use_gmp: bool = False,
    mapper: Callable | None = None,
) -> int:
    """Binary-splitting Chudnovsky over a fixed chunk decomposition.

    `mapper` defaults to serial evaluation; pass a pool's map to parallelize.
    The chunk decomposition is identical either way, so serial-vs-parallel
    timings isolate parallel scaling with no algorithmic difference.
    """
    tasks = [(i, a, b, use_gmp) for i, (a, b) in enumerate(chunk_bounds(digits, chunks))]
    run = mapper if mapper is not None else map
    results = sorted(run(compute_chunk, tasks), key=lambda r: r[0])
    return finalize(_reduce_tree([(p, q, t) for _, p, q, t in results]), digits, use_gmp)


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

_LOG2_10 = 3.3219280948873626


@lru_cache(maxsize=4)
def reference_pi(digits: int) -> int | None:
    """floor(pi * 10**digits) from mpmath, used as an independent oracle.

    mpmath is a separate implementation with its own splitting and scaling, so
    agreement is a real cross-check rather than the benchmark grading itself.
    Returns None if mpmath is unavailable, in which case callers fall back to
    the published-prefix check.
    """
    try:
        from mpmath.libmp import pi_fixed
    except ImportError:
        return None
    bits = int((digits + 25) * _LOG2_10) + 64
    return (pi_fixed(bits) * 10**digits) >> bits


def verification_method(digits: int) -> str:
    return "full (mpmath oracle)" if reference_pi(digits) is not None else "prefix only"


def verify(value: int, digits: int) -> bool:
    """Reject any result that is not exactly the requested digits of pi.

    A fast-but-wrong kernel must never be able to win the benchmark, so this
    checks every digit when the oracle is available and at minimum the
    published leading expansion when it is not.
    """
    if len(str(value)) != digits + 1:
        return False
    reference = reference_pi(digits)
    if reference is not None:
        return value == reference
    prefix_len = min(len(PI_FIRST_100), digits + 1)
    return str(value)[:prefix_len] == PI_FIRST_100[:prefix_len]
