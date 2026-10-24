import numpy as np
import pandas as pd
import pytest

from riskengine.portfolio import Market, aggregate, load_book, position_greeks, value_book

ASOF = "2026-10-23"


@pytest.fixture
def book():
    return load_book("data/sample_book.csv")


@pytest.fixture
def market():
    return Market.from_csv("data/market.csv", ASOF)


def test_futures_are_zero_at_base(book, market):
    vals = value_book(book, market)
    assert np.allclose(vals[(book["kind"] == "future").to_numpy()], 0.0)


def test_delta_1pct_close_to_repricing(book, market):
    # delta_1pct should be close to a symmetric 1% repricing of the book
    g = aggregate(position_greeks(book, market))
    for und in market.spots.index:
        up = value_book(book, market, spot_shift={und: 0.01}).sum()
        dn = value_book(book, market, spot_shift={und: -0.01}).sum()
        fd = (up - dn) / 2
        assert fd == pytest.approx(g.loc[und, "delta_1pct"], rel=0.02)


def test_bad_kind_rejected(tmp_path):
    p = tmp_path / "b.csv"
    pd.DataFrame([["X1", "NKY", "swaption", 1, "2027-01-01", 1, 1, 0.2]],
                 columns=["id", "underlying", "kind", "strike", "expiry", "qty", "multiplier", "vol"]).to_csv(p, index=False)
    with pytest.raises(ValueError):
        load_book(p)
