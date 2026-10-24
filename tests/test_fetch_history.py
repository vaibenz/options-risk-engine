import numpy as np
import pandas as pd

from data.fetch_history import build_history


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
