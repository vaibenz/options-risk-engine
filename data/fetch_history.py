"""Pull real index history to replace the synthetic GARCH data.

    pip install yfinance
    python data/fetch_history.py                 # last 3 years
    python -m riskengine.report --returns data/returns_real.csv --vols data/vol_changes_real.csv

Writes data/returns_real.csv and data/vol_changes_real.csv in the same
format as the synthetic files, so everything else just works.

Spot: daily closes for the Nikkei 225 (^N225), Hang Seng (^HSI) and TAIEX
(^TWII). The three markets have different holidays, so returns are only
kept on days all three traded, which is the honest choice for a joint VaR.

Vol: I couldn't find free daily history for the Nikkei VI, VHSI and the
Taiwan vol index that all line up, so ATM vol moves are proxied by the day
on day change in a 21 day EWMA realised vol. It's not implied vol, but it
keeps the real spot/vol relationship (vol up when spot falls) instead of
the made up -0.35 from the synthetic generator.
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

TICKERS = {"NKY": "^N225", "HSI": "^HSI", "TWSE": "^TWII"}
HERE = Path(__file__).resolve().parent


def build_history(closes, lam=0.94, warmup=21):
    """closes: DataFrame of daily closes, one column per underlying.
    Returns (returns, vol_changes) on dates where every market traded."""
    closes = closes.dropna(how="any").sort_index()
    rets = closes.pct_change().dropna(how="any")

    # EWMA variance of log returns, annualised vol
    lr = np.log1p(rets)
    var = lr.iloc[:warmup].var()
    vols = []
    for _, row in lr.iterrows():
        var = lam * var + (1 - lam) * row**2
        vols.append(np.sqrt(var * 252))
    vol = pd.DataFrame(vols, index=lr.index)
    dvol = vol.diff()

    rets, dvol = rets.iloc[warmup:], dvol.iloc[warmup:]
    return rets.round(6), dvol.round(6)


def download(years):
    import yfinance as yf

    end = pd.Timestamp.today().normalize()
    start = end - pd.DateOffset(years=years)
    raw = yf.download(list(TICKERS.values()), start=start, end=end, auto_adjust=False, progress=False)
    closes = raw["Close"].rename(columns={v: k for k, v in TICKERS.items()})
    return closes[list(TICKERS)]


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--years", type=int, default=3)
    a = p.parse_args(argv)

    closes = download(a.years)
    rets, dvol = build_history(closes)
    rets.rename_axis("date").to_csv(HERE / "returns_real.csv")
    dvol.rename_axis("date").to_csv(HERE / "vol_changes_real.csv")
    print(f"{len(rets)} common trading days {rets.index[0].date()} to {rets.index[-1].date()}")
    print("annualised vol:", (rets.std() * np.sqrt(252)).round(3).to_dict())
    print("corr:\n", rets.corr().round(2))
    print("spot/vol corr:", {k: round(rets[k].corr(dvol[k]), 2) for k in rets})


if __name__ == "__main__":
    main()
