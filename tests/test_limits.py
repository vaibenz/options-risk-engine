import pandas as pd

from riskengine.limits import check_limits


def test_status_and_ordering():
    agg = pd.DataFrame({"delta_1pct": [90.0, -130.0], "vega": [10.0, 5.0]}, index=["A", "B"])
    limits = {"book": {"var_99": 100}, "underlying": {"A": {"delta_1pct": 100}, "B": {"delta_1pct": 100, "vega": 50}}}
    out = check_limits(agg, {"var_99": 50}, limits)
    assert out.iloc[0]["scope"] == "B" and out.iloc[0]["status"] == "BREACH"   # abs value used
    assert out.loc[out.scope == "A", "status"].item() == "WARN"
    assert set(out["status"]) == {"BREACH", "WARN", "ok"}


def test_unknown_underlying_skipped():
    agg = pd.DataFrame({"vega": [1.0]}, index=["A"])
    out = check_limits(agg, {}, {"underlying": {"ZZZ": {"vega": 1}}})
    assert out.empty
