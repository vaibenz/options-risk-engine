"""Runs the VBA modules in LibreOffice (VBA compatibility mode) and checks
them against the Python engine. Not part of the normal pytest run because it
needs LibreOffice installed:

    python excel/tests/test_vba.py

What it checks
  * every BS_* function against riskengine.pricing on a grid of inputs
  * BuildMorningReport runs on the csvs in out/ (run the python report first)
  * LoadWhatIfBook's live formula totals match position_greeks() exactly
"""
import itertools
import os
import sys

import numpy as np
from scipy.stats import norm

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

from lo_harness import LO  # noqa: E402
from riskengine.pricing import bs_greeks, bs_price  # noqa: E402
from riskengine.portfolio import Market, load_book, position_greeks  # noqa: E402


def check_udfs(lo):
    worst = {"NormCDF": max(abs(lo.call("BlackScholes", "NormCDF", float(x)) - norm.cdf(x))
                            for x in np.linspace(-8, 8, 161))}
    grid = itertools.product([80.0, 100.0, 125.0], [0.02, 0.5, 2.0], [0.1, 0.3], ["C", "P"])
    for S, T, v, cp in grid:
        K, r, q, c = 100.0, 0.03, 0.01, cp == "C"
        g = bs_greeks(S, K, T, r, q, v, c)
        got = {
            "BS_PRICE": (lo.call("BlackScholes", "BS_PRICE", S, K, T, r, q, v, cp), bs_price(S, K, T, r, q, v, c)),
            "BS_DELTA": (lo.call("BlackScholes", "BS_DELTA", S, K, T, r, q, v, cp), g["delta"]),
            "BS_GAMMA": (lo.call("BlackScholes", "BS_GAMMA", S, K, T, r, q, v), g["gamma"]),
            "BS_VEGA": (lo.call("BlackScholes", "BS_VEGA", S, K, T, r, q, v), g["vega"]),
            "BS_THETA": (lo.call("BlackScholes", "BS_THETA", S, K, T, r, q, v, cp), g["theta"]),
        }
        for k, (a, b) in got.items():
            worst[k] = max(worst.get(k, 0.0), abs(a - float(b)))
        # implied vol only where the price actually carries vol information
        if float(g["vega"]) > 1e-3:
            px = float(bs_price(S, K, T, r, q, v, c))
            worst["BS_IMPLIED_VOL"] = max(worst.get("BS_IMPLIED_VOL", 0.0),
                                          abs(lo.call("BlackScholes", "BS_IMPLIED_VOL", px, S, K, T, r, q, cp) - v))
    for k, w in worst.items():
        print(f"  {k:15s} max abs diff vs python {w:.1e}")
        assert w < (1e-6 if k == "BS_IMPLIED_VOL" else 1e-10), k


def check_report_and_whatif(lo, doc):
    lo.call("MorningReport", "BuildMorningReport")
    rep = doc.Sheets.getByName("Report")
    assert rep.getCellRangeByName("A1").String.startswith("Options book risk report")
    print("  BuildMorningReport ok, headline:", rep.getCellRangeByName("B7").String)

    lo.call("MorningReport", "LoadWhatIfBook")
    doc.calculateAll()
    w = doc.Sheets.getByName("WhatIf")
    totals = None
    for r in range(80):
        if w.getCellByPosition(0, r).String == "TOTAL":
            totals = [w.getCellByPosition(c, r).Value for c in range(10, 14)]
    py = position_greeks(load_book(os.path.join(ROOT, "data/sample_book.csv")),
                         Market.from_csv(os.path.join(ROOT, "data/market.csv"), "2026-10-23"))
    expect = py[["delta_1pct", "gamma_1pct", "vega", "theta"]].sum().to_numpy()
    print("  WhatIf totals (excel):", np.round(totals, 0), " python:", np.round(expect, 0))
    assert np.allclose(totals, expect, rtol=1e-9)


if __name__ == "__main__":
    lo = LO()
    doc = lo.open()
    try:
        doc.Sheets.getByIndex(0).Name = "Settings"
        doc.Sheets.insertNewByName("Report", 1)   # LibreOffice's Worksheets.Add is flaky, Excel is fine
        doc.Sheets.insertNewByName("WhatIf", 2)
        doc.Sheets.getByName("Settings").getCellRangeByName("B1").String = ROOT
        lo.add_module("BlackScholes", os.path.join(ROOT, "excel/BlackScholes.bas"))
        lo.add_module("MorningReport", os.path.join(ROOT, "excel/MorningReport.bas"))
        print("UDFs")
        check_udfs(lo)
        print("macros")
        check_report_and_whatif(lo, doc)
        print("all VBA checks passed")
    finally:
        lo.close()
