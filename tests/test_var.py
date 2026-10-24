import numpy as np
import pandas as pd
import pytest

from riskengine.portfolio import Market, load_book, value_book
from riskengine.var import (delta_normal_var, historical_var, monte_carlo_var, reval_pnl,
                            var_es)


@pytest.fixture(scope="module")
def data():
    book = load_book("data/sample_book.csv")
    mkt = Market.from_csv("data/market.csv", "2026-10-23")
    rets = pd.read_csv("data/returns.csv", index_col=0, parse_dates=True)
    dvol = pd.read_csv("data/vol_changes.csv", index_col=0, parse_dates=True)
    return book, mkt, rets, dvol


def test_var_es_simple():
    pnl = np.arange(-50, 50)  # 100 equally likely outcomes
    v, es = var_es(pnl, 0.95)
    assert v == pytest.approx(45.05, abs=0.1)
    assert es >= v


def test_reval_matches_value_book(data):
    book, mkt, rets, dvol = data
    day = rets.iloc[[-1]]
    vday = dvol.iloc[[-1]]
    fast = reval_pnl(book, mkt, day, vday)[0]
    # slow path, one underlying at a time isn't possible for vol so just
    # check spot only against value_book
    fast_spot = reval_pnl(book, mkt, day)[0]
    slow = value_book(book, mkt, spot_shift=day.iloc[0].to_dict()).sum() - value_book(book, mkt).sum()
    assert fast_spot == pytest.approx(slow, rel=1e-9)
    assert np.isfinite(fast)


def test_methods_same_ballpark(data):
    book, mkt, rets, dvol = data
    h = historical_var(book, mkt, rets, dvol)["var"]
    mc = monte_carlo_var(book, mkt, rets, dvol, n_sims=5000)["var"]
    dn = delta_normal_var(book, mkt, rets)["var"]
    assert 0.3 < mc / h < 3
    assert 0.2 < dn / h < 5


def test_t_tails_fatter(data):
    book, mkt, rets, _ = data
    n = monte_carlo_var(book, mkt, rets, n_sims=20000, seed=1)
    t = monte_carlo_var(book, mkt, rets, n_sims=20000, dof=4, seed=1)
    assert t["es"] / t["var"] > n["es"] / n["var"]
