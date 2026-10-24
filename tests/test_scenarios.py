import numpy as np

from riskengine.portfolio import Market, load_book
from riskengine.scenarios import named_stress, spot_vol_grid, worst_case


def setup():
    return load_book("data/sample_book.csv"), Market.from_csv("data/market.csv", "2026-10-23")


def test_grid_centre_is_zero():
    book, mkt = setup()
    grid = spot_vol_grid(book, mkt)
    assert abs(grid.loc["+0v", "+0%"]) < 1e-6


def test_single_underlying_grid_ignores_others():
    book, mkt = setup()
    full = spot_vol_grid(book[book.underlying == "HSI"], mkt)
    only = spot_vol_grid(book, mkt, underlying="HSI")
    assert np.allclose(full.to_numpy(), only.to_numpy())


def test_long_straddle_grid_is_convex():
    import pandas as pd
    book = pd.DataFrame({
        "id": ["c", "p"], "underlying": "HSI", "kind": ["call", "put"], "strike": 17800.0,
        "expiry": pd.to_datetime("2027-01-15"), "qty": 10, "multiplier": 50, "vol": 0.25,
    })
    _, mkt = setup()
    grid = spot_vol_grid(book, mkt, vol_moves=[0.0])
    row = grid.iloc[0].to_numpy()
    assert row[0] > row[4] and row[-1] > row[4]
    assert worst_case(grid)[1] in ("+0%", "-2%", "+2%")


def test_named_stress_runs():
    book, mkt = setup()
    out = named_stress(book, mkt)
    assert "covid_crash_mar20" in out.index
