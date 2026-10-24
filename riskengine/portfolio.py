"""Book representation and risk aggregation.

A book is a DataFrame of positions, one row per line:
    id, underlying, kind (call/put/future), strike, expiry, qty, multiplier, vol

Futures are treated as delta one hedges marked relative to today's spot,
so their value is 0 at base and qty * multiplier * dS under a shock.

Market data is a small DataFrame indexed by underlying with
    spot, rate, div_yield, ccy, usd_per_unit

All currency amounts (values, cash greeks) come out in USD so the book can
be summed across markets.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .pricing import bs_greeks, bs_price

REQUIRED_COLS = ["id", "underlying", "kind", "strike", "expiry", "qty", "multiplier", "vol"]
GREEKS = ["delta", "gamma", "vega", "theta", "rho"]


@dataclass
class Market:
    spots: pd.Series
    rates: pd.Series
    divs: pd.Series
    fx: pd.Series
    asof: pd.Timestamp

    @classmethod
    def from_csv(cls, path, asof):
        df = pd.read_csv(path).set_index("underlying")
        return cls(df["spot"], df["rate"], df["div_yield"], df["usd_per_unit"], pd.Timestamp(asof))


def load_book(path):
    book = pd.read_csv(path, parse_dates=["expiry"])
    missing = set(REQUIRED_COLS) - set(book.columns)
    if missing:
        raise ValueError(f"book is missing columns: {sorted(missing)}")
    book["kind"] = book["kind"].str.lower().str.strip()
    bad = ~book["kind"].isin(["call", "put", "future"])
    if bad.any():
        raise ValueError(f"unknown kind in rows {book.index[bad].tolist()}")
    return book


def year_frac(asof, expiry):
    days = (pd.to_datetime(expiry) - asof).dt.days.fillna(0).to_numpy()
    return np.maximum(days / 365.0, 0.0)


def _inputs(book, market, spot_shift=None, vol_shift=0.0, days_forward=0):
    """Pull pricing inputs out of the book, optionally shocked.

    spot_shift: dict/Series of relative spot moves per underlying (0.05 = +5%),
                or a single float applied to every underlying
    vol_shift:  absolute vol move (0.02 = +2 vol points)
    """
    spots = market.spots.copy()
    if spot_shift is not None:
        if isinstance(spot_shift, (dict, pd.Series)):
            spot_shift = pd.Series(spot_shift).reindex(spots.index).fillna(0.0)
        spots = spots * (1 + spot_shift)
    S = book["underlying"].map(spots).to_numpy(dtype=float)
    asof = market.asof + pd.Timedelta(days=days_forward)
    T = year_frac(asof, book["expiry"])
    r = book["underlying"].map(market.rates).to_numpy(dtype=float)
    q = book["underlying"].map(market.divs).to_numpy(dtype=float)
    vol = np.maximum(book["vol"].fillna(0.0).to_numpy(dtype=float) + vol_shift, 0.01)
    return S, T, r, q, vol


def value_book(book, market, **shocks):
    """Mark to model value of each line (in currency, so qty * multiplier included)."""
    S, T, r, q, vol = _inputs(book, market, **shocks)
    K = book["strike"].to_numpy(dtype=float)
    is_fut = (book["kind"] == "future").to_numpy()
    is_call = (book["kind"] == "call").to_numpy()
    S0 = book["underlying"].map(market.spots).to_numpy(dtype=float)
    opt = bs_price(S, np.where(is_fut, S, K), T, r, q, vol, is_call)
    unit = np.where(is_fut, S - S0, opt)
    fx = book["underlying"].map(market.fx).to_numpy(dtype=float)
    return unit * book["qty"].to_numpy() * book["multiplier"].to_numpy() * fx


def position_greeks(book, market):
    S, T, r, q, vol = _inputs(book, market)
    K = book["strike"].to_numpy(dtype=float)
    is_fut = (book["kind"] == "future").to_numpy()
    g = bs_greeks(S, np.where(is_fut, S, K), T, r, q, vol, (book["kind"] == "call").to_numpy())

    fx = book["underlying"].map(market.fx).to_numpy(dtype=float)
    scale = book["qty"].to_numpy() * book["multiplier"].to_numpy()
    out = book[["id", "underlying", "kind", "strike", "expiry"]].copy()
    # delta and gamma stay in units of the underlying (index points),
    # vega / theta / rho are converted to USD
    for name in GREEKS:
        raw = np.where(is_fut, 1.0 if name == "delta" else 0.0, g[name]) * scale
        out[name] = raw if name in ("delta", "gamma") else raw * fx

    # cash versions are what the desk actually looks at
    # delta in currency for a 1% spot move
    out["delta_1pct"] = out["delta"] * S / 100 * fx
    out["gamma_1pct"] = 0.5 * out["gamma"] * (0.01 * S) ** 2 * fx
    out["value"] = value_book(book, market)
    return out


def aggregate(greeks, by=("underlying",)):
    cols = ["value", "delta", "delta_1pct", "gamma_1pct", "vega", "theta", "rho"]
    g = greeks.copy()
    if "expiry" in by:
        g["expiry"] = g["expiry"].dt.strftime("%Y-%m").fillna("futures")
    return g.groupby(list(by))[cols].sum().round(2)
