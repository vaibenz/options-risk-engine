# excel

VBA side of the risk engine, for people who live in Excel.

| module | what's in it |
|---|---|
| `BlackScholes.bas` | worksheet functions `BS_PRICE`, `BS_DELTA`, `BS_GAMMA`, `BS_VEGA`, `BS_THETA`, `BS_IMPLIED_VOL`, `NormCDF`. Same conventions as `riskengine/pricing.py` (vega per vol point, theta per day). |
| `MorningReport.bas` | `BuildMorningReport` lays the python report's csvs out as one sheet: headline VaR / ES / worst stress, limit usage with breaches red and warnings amber, greeks by underlying, the spot x vol grid as a heat map, named scenarios. `LoadWhatIfBook` loads the sample book with live `BS_*` formulas so you can bump a spot or vol and watch the greeks move. |

The modules are kept as `.bas` text files so they diff properly in git. A `.xlsm` is a zip and shows up as one opaque binary change.

## Setting it up

1. From the repo root run `python -m riskengine.report` once so `out/` has the csvs.
2. Open a new workbook in Excel, `Alt + F11`, then File > Import File and import both `.bas` files.
3. Save it as `excel/RiskReport.xlsm` (macro enabled). It looks for `out/` and `data/` one folder up from the workbook. To point it somewhere else, add a sheet called `Settings` with the repo path in `B1`.
4. `Alt + F8` and run `BuildMorningReport` or `LoadWhatIfBook`.

## Tests

`tests/test_vba.py` runs both modules inside LibreOffice in VBA compatibility mode and checks them against the python engine:

* every `BS_*` function against `riskengine.pricing`, max difference about 2e-14
* `LoadWhatIfBook`'s formula totals for delta, gamma, vega and theta match `position_greeks()` exactly

```
python excel/tests/test_vba.py      # needs LibreOffice installed
```

One thing I found: deep in the money options close to expiry are almost pure intrinsic, so many vols give the same price and `BS_IMPLIED_VOL` can't recover the vol there. The test only checks implied vol where vega is meaningful.
