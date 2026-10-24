import numpy as np
import pandas as pd
import pytest

from riskengine.backtest import basel_zone, kupiec_pof, rolling_backtest, summarise
from riskengine.portfolio import Market, load_book


def test_kupiec_at_expected_rate_not_rejected():
    lr, p = kupiec_pof(3, 250, 0.99)  # 2.5 expected
    assert p > 0.5


def test_kupiec_rejects_too_many():
    _, p = kupiec_pof(12, 250, 0.99)
    assert p < 0.01


def test_kupiec_zero_exceptions():
    lr, p = kupiec_pof(0, 250, 0.99)
    assert lr > 0 and 0 < p < 1


def test_basel_zones():
    assert basel_zone(4) == "green"
    assert basel_zone(7) == "yellow"
    assert basel_zone(10) == "red"


def test_rolling_backtest_runs():
    book = load_book("data/sample_book.csv")
    mkt = Market.from_csv("data/market.csv", "2026-10-23")
    rets = pd.read_csv("data/returns.csv", index_col=0, parse_dates=True)
    dvol = pd.read_csv("data/vol_changes.csv", index_col=0, parse_dates=True)
    bt = rolling_backtest(book, mkt, rets, dvol)
    assert len(bt) == 250
    s = summarise(bt)
    assert s["exceptions"] == bt["exception"].sum()
