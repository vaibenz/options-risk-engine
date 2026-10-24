"""Value at Risk and Expected Shortfall.

Three flavours so they can be compared against each other:
  * delta normal    quick, linear, ignores gamma and vega convexity
  * historical      full revaluation of the book under each past day's moves
  * monte carlo     full revaluation under simulated correlated moves

VaR is reported as a positive number (the loss), for a 1 day horizon
unless stated otherwise.
"""
import numpy as np
import pandas as pd
from scipy.stats import norm

from .portfolio import position_greeks, year_frac
from .pricing import bs_price


def reval_pnl(book, market, spot_rets, vol_moves=None):
    """Full revaluation P&L (USD) for many scenarios at once.

    spot_rets: DataFrame (n_scenarios x underlyings) of relative spot moves
    vol_moves: same shape, absolute ATM vol moves applied to every line on
               that underlying (parallel shift of the smile). None = no vol move
    Returns an array of length n_scenarios.
    """
    und = book["underlying"].to_numpy()
    cols = list(spot_rets.columns)
    idx = np.array([cols.index(u) for u in und])

    S0 = book["underlying"].map(market.spots).to_numpy(dtype=float)
    rets = spot_rets.to_numpy()[:, idx]                       # n x positions
    S = S0 * (1 + rets)

    vol0 = book["vol"].fillna(0.0).to_numpy(dtype=float)
    dv = 0.0 if vol_moves is None else vol_moves[cols].to_numpy()[:, idx]
    vol = np.maximum(vol0 + dv, 0.01)

    K = book["strike"].to_numpy(dtype=float)
    T = year_frac(market.asof, book["expiry"])
    r = book["underlying"].map(market.rates).to_numpy(dtype=float)
    q = book["underlying"].map(market.divs).to_numpy(dtype=float)
    fx = book["underlying"].map(market.fx).to_numpy(dtype=float)
    is_call = (book["kind"] == "call").to_numpy()
    is_fut = (book["kind"] == "future").to_numpy()
    scale = book["qty"].to_numpy() * book["multiplier"].to_numpy() * fx

    base = np.where(is_fut, 0.0, bs_price(S0, np.where(is_fut, S0, K), T, r, q, vol0, is_call))
    shocked = np.where(is_fut, S - S0, bs_price(S, np.where(is_fut, S, K), T, r, q, vol, is_call))
    return ((shocked - base) * scale).sum(axis=1)


def var_es(pnl, alpha=0.99):
    """Empirical VaR and ES from a P&L sample. Both returned as positive losses."""
    pnl = np.sort(np.asarray(pnl))
    cutoff = np.quantile(pnl, 1 - alpha)
    tail = pnl[pnl <= cutoff]
    return -cutoff, -tail.mean()


def historical_var(book, market, returns, vol_changes=None, alpha=0.99, window=500):
    rets = returns.iloc[-window:]
    vols = None if vol_changes is None else vol_changes.loc[rets.index]
    pnl = reval_pnl(book, market, rets, vols)
    v, es = var_es(pnl, alpha)
    return {"var": v, "es": es, "pnl": pd.Series(pnl, index=rets.index)}


def ewma_cov(returns, lam=0.94):
    """RiskMetrics style EWMA covariance, most recent day weighted most."""
    x = returns.to_numpy()
    w = lam ** np.arange(len(x))[::-1]
    w = w / w.sum()
    xc = x - (w[:, None] * x).sum(axis=0)
    return pd.DataFrame((w[:, None] * xc).T @ xc, index=returns.columns, columns=returns.columns)


def monte_carlo_var(book, market, returns, vol_changes=None, alpha=0.99, n_sims=20000,
                    dof=None, lam=0.94, seed=0):
    """Simulate correlated 1 day moves and fully revalue.

    dof: if set, use a multivariate student t with that many degrees of
         freedom (scaled to the same covariance) to get fatter tails.
    Spot and vol moves are simulated jointly so the negative spot/vol
    correlation in the history carries through.
    """
    rng = np.random.default_rng(seed)
    hist = returns if vol_changes is None else pd.concat(
        [returns, vol_changes.add_suffix("_vol")], axis=1).dropna()
    cov = ewma_cov(hist, lam)
    L = np.linalg.cholesky(cov.to_numpy() + 1e-12 * np.eye(len(cov)))

    z = rng.standard_normal((n_sims, len(cov)))
    if dof:
        chi = rng.chisquare(dof, size=(n_sims, 1))
        z = z * np.sqrt((dof - 2) / chi)
    sims = pd.DataFrame(z @ L.T, columns=cov.columns)

    und = list(returns.columns)
    spot = sims[und]
    vols = None if vol_changes is None else sims[[u + "_vol" for u in und]].set_axis(und, axis=1)
    pnl = reval_pnl(book, market, spot, vols)
    v, es = var_es(pnl, alpha)
    return {"var": v, "es": es, "pnl": pnl}


def delta_normal_var(book, market, returns, alpha=0.99, lam=0.94):
    g = position_greeks(book, market)
    d = g.groupby("underlying")["delta_1pct"].sum().reindex(returns.columns).fillna(0.0) * 100
    cov = ewma_cov(returns, lam)
    sd = float(np.sqrt(d.to_numpy() @ cov.to_numpy() @ d.to_numpy()))
    z = norm.ppf(alpha)
    return {"var": z * sd, "es": sd * norm.pdf(z) / (1 - alpha)}


def scale_horizon(v, days):
    # square root of time, only really ok for short horizons and linear books
    return v * np.sqrt(days)
