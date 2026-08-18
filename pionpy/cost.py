"""Cost model: converts benchmark time into money.

Two questions are answered separately, because conflating them is what makes
ARM migration numbers unconvincing:

  1. "What does this hardware cost me per unit of work?"      -> cost efficiency
  2. "What did optimizing the code buy me on this hardware?"  -> optimization value

The second is expressed as an *effective price*: if optimization makes the
workload 8x faster, the VM behaves as though it cost 1/8th as much for that
workload. That is the number a finance conversation actually needs.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

HOURS_PER_MONTH = 730  # Azure/AWS billing convention
PRICE_STALE_DAYS = 120


def load_pricing(path: Path) -> dict:
    if not path.exists():
        return {"as_of": None, "currency": "USD", "skus": {}}
    with path.open() as f:
        return json.load(f)


def resolve_price(pricing: dict, sku: str | None,
                  price_per_hour: float | None,
                  price_per_month: float | None) -> dict:
    """Resolve an hourly price from an explicit flag or the SKU table."""
    if price_per_hour is not None:
        return {"price_per_hour": price_per_hour, "source": "--price-per-hour", "sku": sku}
    if price_per_month is not None:
        return {"price_per_hour": price_per_month / HOURS_PER_MONTH,
                "source": "--price-per-month", "sku": sku}
    if sku and sku in pricing.get("skus", {}):
        entry = pricing["skus"][sku]
        hourly = entry.get("price_per_hour")
        if hourly is None and entry.get("price_per_month") is not None:
            hourly = entry["price_per_month"] / HOURS_PER_MONTH
        return {"price_per_hour": hourly, "source": f"pricing.json:{sku}",
                "sku": sku, "region": entry.get("region"),
                "vcpus": entry.get("vcpus"), "notes": entry.get("notes")}
    return {"price_per_hour": None, "source": None, "sku": sku}


def price_warnings(pricing: dict, resolved: dict) -> list[str]:
    out = []
    if resolved.get("price_per_hour") is None:
        out.append(
            "No price supplied: cost metrics are omitted. Pass --cpu to use the "
            "price in pricing.json, or --price-per-month for an explicit figure."
        )
        return out
    as_of = pricing.get("as_of")
    if resolved.get("source", "").startswith("pricing.json"):
        if not as_of:
            out.append("pricing.json has no 'as_of' date; re-verify prices before publishing.")
        else:
            try:
                age = (date.today() - datetime.strptime(as_of, "%Y-%m-%d").date()).days
                if age > PRICE_STALE_DAYS:
                    out.append(f"pricing.json is {age} days old (as_of {as_of}); re-verify prices.")
            except ValueError:
                out.append(f"pricing.json 'as_of' value {as_of!r} is not YYYY-MM-DD.")
    return out


def economics(seconds_per_iteration: float, price_per_hour: float | None) -> dict:
    """Throughput and cost for one fixed-size iteration."""
    if seconds_per_iteration <= 0:
        return {}
    per_hour = 3600.0 / seconds_per_iteration
    out = {"iterations_per_hour": round(per_hour, 2)}
    if price_per_hour is not None:
        out["cost_per_1k_iterations"] = round(price_per_hour / per_hour * 1000, 6)
        out["iterations_per_dollar"] = round(per_hour / price_per_hour, 2)
    return out


def annotate(report: dict, resolved: dict) -> dict:
    """Attach pricing and throughput economics to a run, in place."""
    price = resolved.get("price_per_hour")
    report["pricing"] = dict(resolved)
    if price is not None:
        report["pricing"]["price_per_month"] = round(price * HOURS_PER_MONTH, 2)
    report["economics"] = economics(report["run"]["seconds_per_iteration"], price)
    return report


def summarize(reports: list[dict]) -> list[dict]:
    """One row per saved run, in load order and unranked."""
    rows = []
    for rep in reports:
        env = rep["environment"]
        run = rep["run"]
        econ = rep.get("economics") or {}
        price = (rep.get("pricing") or {}).get("price_per_hour")
        rows.append({
            "label": rep.get("label") or env["cpu"].get("model") or env["hostname"],
            "arch": env["cpu"]["arch"],
            "model": env["cpu"].get("model"),
            "mode": rep["mode"],
            "gmp": run.get("gmp"),
            "workers": run.get("workers"),
            "digits": rep["digits"],
            "iterations": run["iterations"],
            "total_seconds": run["total_seconds"],
            "seconds_per_iteration": run["seconds_per_iteration"],
            "iterations_per_hour": econ.get("iterations_per_hour"),
            "cost_per_1k_iterations": econ.get("cost_per_1k_iterations"),
            "price_per_hour": price,
            "price_per_month": round(price * HOURS_PER_MONTH, 2) if price else None,
            "verified": run.get("verified"),
            "noisy": run.get("noisy"),
            "digest": run.get("digest"),
            "steal_percent": (rep.get("runtime") or {}).get("steal_percent"),
        })
    return rows


def integrity(reports: list[dict]) -> dict:
    """Whether these runs are eligible to be compared at all."""
    digests = {rep["run"]["digest"] for rep in reports if rep["run"].get("digest")}
    sizes = {rep["digits"] for rep in reports}
    return {
        "digests_match": len(digests) <= 1,
        "same_size": len(sizes) == 1,
        "digits": sorted(sizes),
    }
