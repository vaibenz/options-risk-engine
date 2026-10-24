"""Generates the synthetic market history used for VaR and backtests.

Real index data would be better but I didn't want to commit vendor data.
This uses a simple GARCH(1,1) per underlying with correlated t shocks so
there is vol clustering and fat tails, which is what makes VaR backtesting
interesting. ATM vol changes are driven off the same shocks with a
negative spot/vol correlation.

    python data/make_history.py
"""
import numpy as np
import pandas as pd

rng = np.random.default_rng(2024)
N = 760
und = ["NKY", "HSI", "TWSE"]
corr = np.array([[1.0, 0.55, 0.65], [0.55, 1.0, 0.6], [0.65, 0.6, 1.0]])
L = np.linalg.cholesky(corr)

omega = np.array([2e-6, 4e-6, 2.5e-6])
a, b = 0.08, 0.90
var = omega / (1 - a - b)
nu = 5

rets = np.zeros((N, 3))
dvol = np.zeros((N, 3))
for t in range(N):
    z = L @ rng.standard_t(nu, 3) * np.sqrt((nu - 2) / nu)
    rets[t] = np.sqrt(var) * z
    # vol goes up when spot goes down, plus some noise of its own
    dvol[t] = -0.35 * rets[t] + 0.004 * rng.standard_normal(3)
    var = omega + a * rets[t] ** 2 + b * var

dates = pd.bdate_range(end="2026-10-23", periods=N)
pd.DataFrame(rets.round(6), index=dates, columns=und).rename_axis("date").to_csv("data/returns.csv")
pd.DataFrame(dvol.round(6), index=dates, columns=und).rename_axis("date").to_csv("data/vol_changes.csv")
print(f"wrote {N} days")
