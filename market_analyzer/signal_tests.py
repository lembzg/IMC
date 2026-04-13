"""
signal_tests.py
---------------
Predictive power of z-score deviations and order book imbalance.

Inputs:  features DF.
Outputs: dicts + DataFrames describing conditional future returns.

Trading decision informed:
  * Z-score: if future return conditional on |z|>thr has opposite sign and
    meaningful magnitude, a threshold-reversion strategy is viable.
  * OBI: if future returns rise monotonically across OBI deciles, OBI is a
    predictive directional tilt; can bias quotes/takes.
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd


def zscore_series(features: pd.DataFrame, window: int) -> pd.Series:
    mid = features["mid"]
    mu = mid.rolling(window, min_periods=max(5, window // 5)).mean()
    sd = mid.rolling(window, min_periods=max(5, window // 5)).std().replace(0, np.nan)
    return (mid - mu) / sd


def zscore_predictive(
    features: pd.DataFrame,
    windows: List[int],
    thresholds: List[float],
    horizons: List[int],
) -> pd.DataFrame:
    """Conditional future return stats for |z| > threshold.

    Expectation for reverting product: when z > thr, future return < 0
    (win_rate_negative > 0.5 and mean_future_ret < 0).
    """
    rows = []
    mid = features["mid"]
    for w in windows:
        z = zscore_series(features, w)
        for h in horizons:
            fut = (mid.shift(-h) - mid) / mid  # fractional
            for thr in thresholds:
                hi_mask = z > thr
                lo_mask = z < -thr
                for side, mask in (("high", hi_mask), ("low", lo_mask)):
                    r = fut[mask].dropna()
                    if len(r) < 20:
                        continue
                    expect_sign = -1 if side == "high" else 1
                    rows.append({
                        "window": w,
                        "threshold": thr,
                        "horizon": h,
                        "side": side,
                        "n": int(len(r)),
                        "mean_future_ret": float(r.mean()),
                        "median_future_ret": float(r.median()),
                        "std_future_ret": float(r.std()),
                        "win_rate_reversion": float(((r * expect_sign) > 0).mean()),
                    })
    return pd.DataFrame(rows)


def obi_predictive(
    features: pd.DataFrame,
    horizons: List[int],
    n_buckets: int = 10,
    col: str = "obi_l1",
) -> pd.DataFrame:
    """Conditional future return by OBI decile.

    Strong predictive OBI: mean_future_ret rises monotonically with OBI bucket.
    """
    rows = []
    if col not in features or features[col].isna().all():
        return pd.DataFrame(rows)
    obi = features[col]
    mid = features["mid"]
    try:
        buckets = pd.qcut(obi, n_buckets, labels=False, duplicates="drop")
    except ValueError:
        return pd.DataFrame(rows)
    for h in horizons:
        fut = (mid.shift(-h) - mid) / mid
        for b, g in fut.groupby(buckets):
            r = g.dropna()
            if len(r) < 20:
                continue
            rows.append({
                "horizon": h,
                "bucket": int(b),
                "n": int(len(r)),
                "mean_future_ret": float(r.mean()),
                "median_future_ret": float(r.median()),
                "obi_col": col,
            })
    return pd.DataFrame(rows)


def obi_correlation(features: pd.DataFrame, horizons: List[int]) -> Dict[str, float]:
    """Pearson corr(OBI_t, future_ret_{t,t+h}) per horizon & per OBI variant."""
    out: Dict[str, float] = {}
    mid = features["mid"]
    for col in ("obi_l1", "obi_total"):
        if col not in features:
            continue
        for h in horizons:
            fut = (mid.shift(-h) - mid) / mid
            joined = pd.concat([features[col], fut], axis=1).dropna()
            if len(joined) < 30:
                continue
            c = joined.corr().iloc[0, 1]
            out[f"corr_{col}_h{h}"] = float(c) if np.isfinite(c) else float("nan")
    return out
