"""Streamlit dashboard for the risk engine.

    streamlit run app.py
"""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

from riskengine.limits import check_limits, load_limits
from riskengine.backtest import rolling_backtest, summarise
from riskengine.portfolio import Market, aggregate, load_book, position_greeks
from riskengine.scenarios import named_stress, spot_vol_grid, worst_case
from riskengine.var import delta_normal_var, historical_var, monte_carlo_var

st.set_page_config(page_title="Options risk", layout="wide")


@st.cache_data
def load(book_file, asof):
    book = load_book(book_file)
    mkt = Market.from_csv("data/market.csv", asof)
    rets = pd.read_csv("data/returns.csv", index_col=0, parse_dates=True)
    dvol = pd.read_csv("data/vol_changes.csv", index_col=0, parse_dates=True)
    return book, mkt, rets, dvol


with st.sidebar:
    st.header("Inputs")
    asof = st.date_input("As of", pd.Timestamp("2026-10-23"))
    uploaded = st.file_uploader("Book csv (optional)", type="csv")
    alpha = st.select_slider("Confidence", [0.95, 0.975, 0.99], value=0.99)
    window = st.slider("Historical window (days)", 250, 750, 500, step=50)
    dof = st.slider("MC student t dof (0 = normal)", 0, 10, 5)
    grid_und = st.selectbox("Grid underlying", ["All", "NKY", "HSI", "TWSE"])

book, mkt, rets, dvol = load(uploaded if uploaded else "data/sample_book.csv", str(asof))
greeks = position_greeks(book, mkt)
by_und = aggregate(greeks)

hist = historical_var(book, mkt, rets, dvol, alpha=alpha, window=window)
mc = monte_carlo_var(book, mkt, rets, dvol, alpha=alpha, dof=dof or None)
dn = delta_normal_var(book, mkt, rets, alpha=alpha)
grid = spot_vol_grid(book, mkt, underlying=None if grid_und == "All" else grid_und)
worst = worst_case(grid)

lims = check_limits(by_und, {"var_99": hist["var"], "es_99": hist["es"], "stress_worst": -worst[2],
                             "vega": by_und["vega"].sum()}, load_limits("data/limits.json"))
n_breach = (lims["status"] == "BREACH").sum()
n_warn = (lims["status"] == "WARN").sum()

st.title("Options book risk")
c = st.columns(5)
c[0].metric("Hist VaR", f"${hist['var']:,.0f}")
c[1].metric("Hist ES", f"${hist['es']:,.0f}")
c[2].metric("Vega / vol pt", f"${by_und['vega'].sum():,.0f}")
c[3].metric("Worst grid pnl", f"-${-worst[2]:,.0f}" if worst[2] < 0 else f"${worst[2]:,.0f}", f"{worst[1]} spot, {worst[0]}")
c[4].metric("Limits", f"{n_breach} breach", f"{n_warn} warn", delta_color="inverse")

tab_lim, tab_greeks, tab_grid, tab_var, tab_bt = st.tabs(["Limits", "Greeks", "Stress", "VaR", "Backtest"])

with tab_lim:
    def colour(row):
        c = {"BREACH": "background-color: #f8d7da", "WARN": "background-color: #fff3cd"}.get(row["status"], "")
        return [c] * len(row)
    st.dataframe(lims.style.apply(colour, axis=1).format({"value": "{:,.0f}", "limit": "{:,.0f}"}),
                 width="stretch")

with tab_greeks:
    st.subheader("By underlying (USD, delta in index units)")
    st.dataframe(by_und.style.format("{:,.0f}"), width="stretch")
    st.subheader("By underlying and expiry")
    st.dataframe(aggregate(greeks, ("underlying", "expiry")).style.format("{:,.0f}"), width="stretch")
    with st.expander("Position level"):
        st.dataframe(greeks, width="stretch")

with tab_grid:
    st.subheader("Spot x vol P&L (USD 000s)")
    g = grid / 1000
    lim = np.abs(g.to_numpy()).max()
    st.dataframe(g.style.format("{:,.0f}").background_gradient(cmap="RdYlGn", vmin=-lim, vmax=lim),
                 width="stretch")
    st.subheader("Named scenarios")
    st.dataframe(named_stress(book, mkt).style.format("{:,.0f}"))

with tab_var:
    st.dataframe(pd.DataFrame({
        "historical": [hist["var"], hist["es"]],
        f"monte carlo ({'t' + str(dof) if dof else 'normal'})": [mc["var"], mc["es"]],
        "delta normal": [dn["var"], dn["es"]],
    }, index=[f"VaR {alpha:.1%}", f"ES {alpha:.1%}"]).style.format("{:,.0f}"))

    fig, ax = plt.subplots(figsize=(8, 3))
    ax.hist(mc["pnl"], bins=100, alpha=0.6, density=True, label="monte carlo")
    ax.hist(hist["pnl"], bins=50, alpha=0.6, density=True, label="historical")
    ax.axvline(-hist["var"], color="k", ls="--", lw=1, label="hist VaR")
    ax.set_xlabel("1 day P&L (USD)")
    ax.legend()
    st.pyplot(fig)
    st.caption("Delta normal ignores gamma and vega, so the gap to the full reval numbers "
               "is roughly how much convexity the book is carrying.")

with tab_bt:
    bt = rolling_backtest(book, mkt, rets, dvol, alpha=alpha)
    st.json(summarise(bt, alpha))
    fig, ax = plt.subplots(figsize=(10, 3))
    ax.plot(bt.index, bt["pnl"], lw=0.8, label="hypothetical P&L")
    ax.plot(bt.index, -bt["var"], color="r", lw=1, label="-VaR")
    ex = bt[bt["exception"]]
    ax.scatter(ex.index, ex["pnl"], color="r", zorder=3, label="exception")
    ax.legend(loc="lower left")
    st.pyplot(fig)
