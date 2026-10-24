"""Limit checks.

limits.json looks like
{
  "book":       {"var_99": 150000, "stress_worst": 600000, "vega": 400000},
  "underlying": {"NKY": {"delta_1pct": 120000, "vega": 250000}, ...}
}
All limits are absolute values in USD. A line is flagged as a warning when
usage is above `warn_at` (default 80%) and as a breach above 100%.
"""
import json

import pandas as pd


def load_limits(path):
    with open(path) as f:
        return json.load(f)


def _row(scope, metric, value, limit, warn_at):
    usage = abs(value) / limit if limit else float("nan")
    status = "BREACH" if usage > 1 else "WARN" if usage > warn_at else "ok"
    return {"scope": scope, "metric": metric, "value": round(value, 0), "limit": limit,
            "usage_pct": round(usage * 100, 1), "status": status}


def check_limits(agg_greeks, book_metrics, limits, warn_at=0.8):
    """agg_greeks:   output of portfolio.aggregate(..., by=("underlying",))
    book_metrics: dict of book level numbers, e.g. {"var_99": .., "vega": ..}
    """
    rows = []
    for metric, limit in limits.get("book", {}).items():
        if metric in book_metrics:
            rows.append(_row("BOOK", metric, book_metrics[metric], limit, warn_at))
    for und, lims in limits.get("underlying", {}).items():
        if und not in agg_greeks.index:
            continue
        for metric, limit in lims.items():
            rows.append(_row(und, metric, float(agg_greeks.loc[und, metric]), limit, warn_at))

    out = pd.DataFrame(rows, columns=["scope", "metric", "value", "limit", "usage_pct", "status"])
    order = {"BREACH": 0, "WARN": 1, "ok": 2}
    return out.sort_values("status", key=lambda s: s.map(order), kind="stable").reset_index(drop=True)
