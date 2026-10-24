"""Full revaluation stress grids.

The grid is the main thing a risk analyst checks every morning: what does
the book make or lose if spot moves X% and vols move Y points at the same
time. Greeks only tell you the local picture, the grid shows the shape
(e.g. short gamma books lose on both sides).
"""
import numpy as np
import pandas as pd

from .portfolio import value_book

DEFAULT_SPOT = [-0.15, -0.10, -0.05, -0.02, 0.0, 0.02, 0.05, 0.10, 0.15]
DEFAULT_VOL = [-0.10, -0.05, 0.0, 0.05, 0.10, 0.20]


def spot_vol_grid(book, market, underlying=None, spot_moves=DEFAULT_SPOT, vol_moves=DEFAULT_VOL):
    """P&L (USD) under each combination of spot and vol shock.

    If underlying is given only that underlying is shocked and only its
    lines are revalued, otherwise every underlying moves together.
    Rows are vol shocks, columns spot shocks.
    """
    if underlying is not None:
        book = book[book["underlying"] == underlying]
    base = value_book(book, market).sum()

    out = np.empty((len(vol_moves), len(spot_moves)))
    for i, dv in enumerate(vol_moves):
        for j, ds in enumerate(spot_moves):
            out[i, j] = value_book(book, market, spot_shift=ds, vol_shift=dv).sum() - base

    return pd.DataFrame(
        out,
        index=pd.Index([f"{v * 100:+.0f}v" for v in vol_moves], name="vol"),
        columns=pd.Index([f"{s * 100:+.0f}%" for s in spot_moves], name="spot"),
    )


def worst_case(grid):
    idx = np.unravel_index(np.argmin(grid.to_numpy()), grid.shape)
    return grid.index[idx[0]], grid.columns[idx[1]], float(grid.iat[idx])


# a few named scenarios, loosely based on real moves
HISTORICAL_STRESS = {
    "covid_crash_mar20": {"spot": {"NKY": -0.18, "HSI": -0.12, "TWSE": -0.20}, "vol": 0.25},
    "aug24_yen_unwind": {"spot": {"NKY": -0.12, "HSI": -0.03, "TWSE": -0.08}, "vol": 0.15},
    "china_stimulus_sep24": {"spot": {"NKY": 0.03, "HSI": 0.15, "TWSE": 0.04}, "vol": 0.05},
    "vol_crush": {"spot": {}, "vol": -0.06},
}


def named_stress(book, market, scenarios=HISTORICAL_STRESS):
    base = value_book(book, market).sum()
    rows = []
    for name, sc in scenarios.items():
        pnl = value_book(book, market, spot_shift=sc["spot"], vol_shift=sc["vol"]).sum() - base
        rows.append({"scenario": name, "pnl_usd": pnl})
    return pd.DataFrame(rows).set_index("scenario").round(0)
