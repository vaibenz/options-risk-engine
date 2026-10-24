"""Morning risk report from the command line.

    python -m riskengine.report --asof 2026-10-23
"""
import argparse
from pathlib import Path

import pandas as pd

from .backtest import rolling_backtest, summarise
from .limits import check_limits, load_limits
from .portfolio import Market, aggregate, load_book, position_greeks
from .scenarios import named_stress, spot_vol_grid, worst_case
from .var import historical_var, monte_carlo_var


def build_report(book_path, market_path, returns_path, vols_path, limits_path, asof):
    book = load_book(book_path)
    mkt = Market.from_csv(market_path, asof)
    rets = pd.read_csv(returns_path, index_col=0, parse_dates=True)
    dvol = pd.read_csv(vols_path, index_col=0, parse_dates=True)

    greeks = position_greeks(book, mkt)
    by_und = aggregate(greeks)
    by_exp = aggregate(greeks, ("underlying", "expiry"))

    hist = historical_var(book, mkt, rets, dvol)
    mc = monte_carlo_var(book, mkt, rets, dvol, dof=5)
    grid = spot_vol_grid(book, mkt)
    worst = worst_case(grid)
    bt = summarise(rolling_backtest(book, mkt, rets, dvol))

    book_metrics = {
        "var_99": hist["var"], "es_99": hist["es"],
        "stress_worst": -worst[2], "vega": by_und["vega"].sum(),
    }
    lims = check_limits(by_und, book_metrics, load_limits(limits_path))
    return {
        "by_underlying": by_und, "by_expiry": by_exp, "grid": grid,
        "named_stress": named_stress(book, mkt), "worst": worst,
        "var": pd.DataFrame({"historical": [hist["var"], hist["es"]], "monte_carlo_t5": [mc["var"], mc["es"]]},
                            index=["VaR 99%", "ES 99%"]).round(0),
        "backtest": bt, "limits": lims,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description="options book risk report")
    p.add_argument("--book", default="data/sample_book.csv")
    p.add_argument("--market", default="data/market.csv")
    p.add_argument("--returns", default="data/returns.csv")
    p.add_argument("--vols", default="data/vol_changes.csv")
    p.add_argument("--limits", default="data/limits.json")
    p.add_argument("--asof", default="2026-10-23")
    p.add_argument("--out", default="out", help="folder for csv output")
    a = p.parse_args(argv)

    rep = build_report(a.book, a.market, a.returns, a.vols, a.limits, a.asof)
    pd.set_option("display.width", 160)
    pd.set_option("display.float_format", "{:,.0f}".format)

    print(f"\n=== risk report {a.asof} (USD) ===\n")
    print("greeks by underlying\n", rep["by_underlying"], "\n")
    print("VaR / ES (1 day)\n", rep["var"], "\n")
    print("spot x vol grid (USD 000s)\n", (rep["grid"] / 1000).round(0), "\n")
    v, s, pnl = rep["worst"]
    print(f"worst grid point: spot {s}, vol {v}, pnl {pnl:,.0f}\n")
    print("named stress\n", rep["named_stress"], "\n")
    print("backtest (last 250d)", rep["backtest"], "\n")
    print("limits\n", rep["limits"].to_string(index=False))

    out = Path(a.out)
    out.mkdir(exist_ok=True)
    for k in ("by_underlying", "by_expiry", "grid", "named_stress", "var", "limits"):
        rep[k].to_csv(out / f"{k}.csv")
    breaches = (rep["limits"]["status"] == "BREACH").sum()
    return 1 if breaches else 0


if __name__ == "__main__":
    raise SystemExit(main())
