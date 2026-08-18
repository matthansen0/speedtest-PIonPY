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
            "No price supplied: cost metrics are omitted. Pass --price-per-month "
            "or --sku to get cost-per-work numbers."
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


def tier_economics(seconds: float, price_per_hour: float | None) -> dict:
    """Throughput and cost for one tier. `seconds` is time per fixed work unit."""
    if seconds <= 0:
        return {}
    runs_per_hour = 3600.0 / seconds
    out = {"runs_per_hour": round(runs_per_hour, 3)}
    if price_per_hour is not None:
        out["cost_per_1k_runs"] = round(price_per_hour / runs_per_hour * 1000, 6)
        out["runs_per_dollar"] = round(runs_per_hour / price_per_hour, 3)
    return out


def annotate(report: dict, resolved: dict, metric: str = "median_seconds") -> dict:
    """Attach per-tier economics and the optimization-value summary in place."""
    price = resolved.get("price_per_hour")
    report["pricing"] = dict(resolved)
    if price is not None:
        report["pricing"]["price_per_month"] = round(price * HOURS_PER_MONTH, 2)
    report["cost_metric"] = metric

    tiers = {t["key"]: t for t in report["tiers"] if t["status"] == "ok"}
    for t in report["tiers"]:
        if t["status"] == "ok":
            t["economics"] = tier_economics(t[metric], price)

    baseline = tiers.get("baseline")
    best_key = min(tiers, key=lambda k: tiers[k][metric]) if tiers else None
    best = tiers.get(best_key) if best_key else None

    summary: dict = {}
    if baseline and best:
        speedup = baseline[metric] / best[metric]
        summary = {
            "baseline_tier": baseline["key"],
            "best_tier": best["key"],
            "optimization_complete": "optimized" in tiers,
            "baseline_seconds": round(baseline[metric], 4),
            "best_seconds": round(best[metric], 4),
            "optimization_speedup": round(speedup, 2),
        }
        if price is not None:
            base_cost = baseline["economics"]["cost_per_1k_runs"]
            best_cost = best["economics"]["cost_per_1k_runs"]
            summary["cost_per_1k_runs_baseline"] = base_cost
            summary["cost_per_1k_runs_optimized"] = best_cost
            summary["cost_reduction_percent"] = round((1 - best_cost / base_cost) * 100, 2)
            summary["effective_price_per_month"] = round(
                price * HOURS_PER_MONTH / speedup, 2)

        # Attribute the total gain to individual levers.
        levers = {}
        if "algorithm" in tiers:
            levers["algorithm"] = round(baseline[metric] / tiers["algorithm"][metric], 2)
        if "algorithm" in tiers and "native" in tiers:
            levers["native_math_library"] = round(
                tiers["algorithm"][metric] / tiers["native"][metric], 2)
        if "algorithm" in tiers and "parallel" in tiers:
            levers["parallelism"] = round(
                tiers["algorithm"][metric] / tiers["parallel"][metric], 2)
        summary["lever_speedups"] = levers

        workers = best.get("workers", 1)
        if "algorithm" in tiers and "parallel" in tiers and workers > 1:
            scaling = tiers["algorithm"][metric] / tiers["parallel"][metric]
            summary["parallel_efficiency_percent"] = round(scaling / workers * 100, 1)

    report["optimization_value"] = summary
    return report


def results_matrix(reports: list[dict], metric: str = "median_seconds",
                   tier_key: str | None = None) -> list[dict]:
    """Every machine at every tier, unranked and in run order.

    No machine is nominated as the reference and no tier is nominated as the
    result, so the reader chooses the pair that matches the question.
    """
    rows = []
    for rep in reports:
        env = rep["environment"]
        label = rep.get("label") or env["cpu"].get("model") or env["hostname"]
        price = (rep.get("pricing") or {}).get("price_per_hour")
        base = next((t for t in rep["tiers"]
                     if t["key"] == "baseline" and t["status"] == "ok"), None)
        for tier in rep["tiers"]:
            if tier_key and tier["key"] != tier_key:
                continue
            row = {
                "label": label,
                "arch": env["cpu"]["arch"],
                "tier": tier["key"],
                "lever": tier.get("lever"),
                "status": tier["status"],
                "skipped_reason": tier.get("skipped_reason"),
                "workers": tier.get("workers"),
                "noisy": tier.get("noisy"),
                "digest": tier.get("digest"),
                "digits": rep["digits"],
            }
            if tier["status"] == "ok":
                seconds = tier[metric]
                runs_per_hour = 3600.0 / seconds
                row["seconds"] = round(seconds, 4)
                row["runs_per_hour"] = round(runs_per_hour, 2)
                if base:
                    row["vs_baseline"] = round(base[metric] / seconds, 2)
                if price is not None:
                    row["cost_per_1k_runs"] = round(price / runs_per_hour * 1000, 6)
                    row["runs_per_dollar"] = round(runs_per_hour / price, 2)
            rows.append(row)
    return rows


def machines(reports: list[dict]) -> list[dict]:
    """One row per machine: what it is, and what it costs to rent."""
    out = []
    for rep in reports:
        env = rep["environment"]
        price = (rep.get("pricing") or {}).get("price_per_hour")
        out.append({
            "label": rep.get("label") or env["cpu"].get("model") or env["hostname"],
            "arch": env["cpu"]["arch"],
            "model": env["cpu"].get("model"),
            "vcpus": env["topology"]["logical_cpus"],
            "physical_cores": env["topology"].get("physical_cores"),
            "smt": env["topology"].get("smt_enabled"),
            "gmp": (env.get("interpreter") or {}).get("gmp"),
            "digits": rep["digits"],
            "price_per_hour": price,
            "price_per_month": round(price * HOURS_PER_MONTH, 2) if price else None,
            "steal_percent": (rep.get("runtime") or {}).get("steal_percent"),
        })
    return out


def integrity(reports: list[dict]) -> dict:
    """Whether these runs are eligible to be compared at all."""
    digests = {t["digest"] for rep in reports for t in rep["tiers"] if t.get("digest")}
    sizes = {rep["digits"] for rep in reports}
    return {
        "digests_match": len(digests) <= 1,
        "same_size": len(sizes) == 1,
        "digits": sorted(sizes),
    }
