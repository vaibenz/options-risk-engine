import numpy as np
import pandas as pd
import pytest

from data.fetch_history import build_history, check_closes


def test_build_history_aligns_and_has_negative_spot_vol():
    rng = np.random.default_rng(0)
    idx = pd.bdate_range("2024-01-01", periods=300)
    r = rng.standard_normal((300, 3)) * 0.01
    # make vol jump after big down days so the EWMA proxy picks it up
    closes = pd.DataFrame(100 * np.exp(np.cumsum(r, axis=0)), index=idx, columns=["NKY", "HSI", "TWSE"])
    closes.iloc[50, 1] = np.nan           # an HSI holiday
    rets, dvol = build_history(closes)
    assert idx[50] not in rets.index      # dropped, not filled
    assert list(rets.columns) == ["NKY", "HSI", "TWSE"]
    assert rets.index.equals(dvol.index)
    assert not rets.isna().any().any() and not dvol.isna().any().any()
    # a big down day should push the vol proxy up
    big_down = rets["NKY"].idxmin()
    assert dvol.loc[big_down, "NKY"] > 0


def test_check_closes_names_the_missing_market():
    idx = pd.bdate_range("2024-01-01", periods=5)
    closes = pd.DataFrame({"NKY": 1.0, "HSI": 1.0, "TWSE": np.nan}, index=idx)
    with pytest.raises(SystemExit, match="TWSE"):
        check_closes(closes)


def test_check_closes_passes_good_data():
    idx = pd.bdate_range("2024-01-01", periods=5)
    check_closes(pd.DataFrame({"NKY": 1.0, "HSI": 1.0, "TWSE": 1.0}, index=idx))
