# options-risk-engine

A small market risk engine for an options market making book. I built it to understand what a risk analyst at a market maker actually looks at every morning: the greeks, how the book behaves when spot and vol move together, VaR and whether that VaR can be trusted, and which limits are close to being hit.

The sample book is synthetic: 27 lines of index options and futures hedges on NKY, HSI and TWSE across four expiries, with a skew baked into the vols. Market history is also synthetic (GARCH(1,1) with correlated student t shocks, see `data/make_history.py`) so I could commit it without vendor data.

## What it does

**Pricing and greeks** (`riskengine/pricing.py`)
Black Scholes Merton with dividend yield, vectorised over the whole book. Delta, gamma, vega (per vol point), theta (per day) and rho, all checked against finite difference bumps in the tests.

**Aggregation** (`riskengine/portfolio.py`)
Position greeks scaled by qty, multiplier and FX so everything sums in USD. Rolled up by underlying and by underlying x expiry. Cash delta and gamma are shown for a 1% move since that is easier to reason about than raw delta across three different index levels.

**Stress** (`riskengine/scenarios.py`)
Full revaluation spot x vol grid (spot -15% to +15%, vol -10 to +20 points) plus a few named scenarios loosely shaped on real moves (Mar 2020, the Aug 2024 yen carry unwind, the Sep 2024 China stimulus rally, a vol crush).

**VaR and ES** (`riskengine/var.py`)
* historical simulation, full reval of the book under each of the last 500 days of spot and vol moves
* Monte Carlo with an EWMA covariance (lambda 0.94) over spot and vol jointly, normal or student t shocks
* delta normal as a sanity check, the gap between this and the full reval numbers is roughly the convexity in the book

**Backtesting** (`riskengine/backtest.py`)
Rolling 250 day backtest of 1 day 99% historical VaR against hypothetical P&L, with the Kupiec proportion of failures test, the Christoffersen independence test (are exceptions clustering?) and the Basel traffic light zone.

**Limits** (`riskengine/limits.py`)
Book and per underlying limits from `data/limits.json`, warn at 80% usage, breach above 100%.

## Running it

```
pip install -r requirements.txt
python -m pytest
python -m riskengine.report          # prints the morning report, writes csvs to out/
streamlit run app.py                 # dashboard
```

`report` exits with code 1 if any limit is in breach, so it could sit in a cron job and alert.

Sample output on the included book:

```
VaR / ES (1 day)
          historical  monte_carlo_t5
VaR 99%     101,119          83,358
ES 99%      117,129         110,925

backtest (last 250d) {'days': 250, 'exceptions': 3, 'expected': 2.5, 'kupiec_p': 0.758, 'basel_zone': 'green'}

limits
 scope       metric   value  limit  usage_pct status
 BOOK stress_worst 514,378 500000        103 BREACH
  HSI   delta_1pct -40,680  40000        102 BREACH
 BOOK       var_99 101,119 120000         84   WARN
 TWSE         vega  36,042  40000         90   WARN
```

The grid shows the book is long vol overall but loses in the low vol / spot down corner, which is the stress limit breach.

## Things I simplified

* vol moves are parallel shifts of each underlying's smile, no skew or term structure moves
* the backtest replays historical moves on today's book (hypothetical P&L), not actual P&L with intraday trading
* no early exercise, everything is priced European
* rates and dividends are flat per underlying

Next I'd like to add sticky strike vs sticky delta vol dynamics and a proper vol surface per underlying (see my vol-surface-svi repo).

---

If something here is unclear, broken, or just wrong, feel free to open an issue. I'm always happy to chat about it.
