"""VaR backtesting.

Rolls through history, computes a 1 day historical VaR each day from the
previous `window` days, then checks it against the P&L the (static) book
would have made on the next day. Simplification: the book and the market
levels are held at today's values, only the moves are replayed, so this is
a hypothetical P&L backtest, not an actual P&L one.
"""
import numpy as np
import pandas as pd
from scipy.stats import chi2

from .var import reval_pnl, var_es


def rolling_backtest(book, market, returns, vol_changes=None, alpha=0.99, window=250, test_days=250):
    all_pnl = reval_pnl(book, market, returns, vol_changes)
    all_pnl = pd.Series(all_pnl, index=returns.index)

    rows = []
    start = len(returns) - test_days
    if start < window:
        raise ValueError("not enough history for that window + test length")
    for t in range(start, len(returns)):
        hist = all_pnl.iloc[t - window:t]
        v, _ = var_es(hist.to_numpy(), alpha)
        rows.append({"date": returns.index[t], "var": v, "pnl": all_pnl.iloc[t]})

    df = pd.DataFrame(rows).set_index("date")
    df["exception"] = df["pnl"] < -df["var"]
    return df


def kupiec_pof(n_exceptions, n_obs, alpha=0.99):
    """Kupiec proportion of failures likelihood ratio test.

    H0: the true exception rate is 1 - alpha. Returns (LR stat, p value).
    """
    p = 1 - alpha
    x, n = n_exceptions, n_obs
    if x == 0:
        lr = -2 * n * np.log(1 - p)
    elif x == n:
        lr = -2 * n * np.log(p)
    else:
        phat = x / n
        lr = -2 * ((n - x) * np.log(1 - p) + x * np.log(p)
                   - (n - x) * np.log(1 - phat) - x * np.log(phat))
    return lr, 1 - chi2.cdf(lr, df=1)


def christoffersen_independence(exceptions):
    """Tests whether exceptions cluster (an exception today makes one tomorrow
    more likely). Returns (LR stat, p value)."""
    e = np.asarray(exceptions, dtype=int)
    prev, curr = e[:-1], e[1:]
    n00 = np.sum((prev == 0) & (curr == 0))
    n01 = np.sum((prev == 0) & (curr == 1))
    n10 = np.sum((prev == 1) & (curr == 0))
    n11 = np.sum((prev == 1) & (curr == 1))

    def ll(n_stay, n_move, p):
        if p <= 0 or p >= 1:
            return 0.0
        return n_stay * np.log(1 - p) + n_move * np.log(p)

    pi0 = n01 / max(n00 + n01, 1)
    pi1 = n11 / max(n10 + n11, 1)
    pi = (n01 + n11) / max(n00 + n01 + n10 + n11, 1)
    lr = -2 * (ll(n00 + n10, n01 + n11, pi) - ll(n00, n01, pi0) - ll(n10, n11, pi1))
    return lr, 1 - chi2.cdf(lr, df=1)


def basel_zone(n_exceptions, n_obs=250):
    # Basel traffic light, defined for 250 observations at 99%
    scaled = n_exceptions * 250 / n_obs
    if scaled <= 4:
        return "green"
    if scaled <= 9:
        return "yellow"
    return "red"


def summarise(bt, alpha=0.99):
    n, x = len(bt), int(bt["exception"].sum())
    lr, p = kupiec_pof(x, n, alpha)
    lr_i, p_i = christoffersen_independence(bt["exception"])
    return {
        "days": n,
        "exceptions": x,
        "expected": round(n * (1 - alpha), 1),
        "kupiec_lr": round(float(lr), 3),
        "kupiec_p": round(float(p), 3),
        "independence_p": round(float(p_i), 3),
        "basel_zone": basel_zone(x, n),
    }
