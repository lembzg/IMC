"""
reversion_tests.py
------------------
Statistical tests that classify a product as mean-reverting, trending, or
random.

Inputs:  features DF with ``mid`` and ``log_ret``.
Outputs: dict of scalar statistics.

Trading decision informed:
  * AR(1) > 0, Hurst > 0.5, positive autocorr -> trend-following candidate
  * AR(1) < 0, Hurst < 0.5, negative autocorr -> mean-reversion candidate
  * half-life short (<50 ticks) -> fast reversion; can use tight z-thresholds
  * half-life very long or noisy -> reversion strategies will take too long
    to monetize; skip.
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd


def _ar1(x: np.ndarray) -> float:
    """Ordinary AR(1) coefficient via lag-1 regression."""
    x = x[~np.isnan(x)]
    if len(x) < 20:
        return float("nan")
    x0, x1 = x[:-1], x[1:]
    x0 = x0 - x0.mean()
    x1 = x1 - x1.mean()
    denom = (x0 ** 2).sum()
    return float((x0 * x1).sum() / denom) if denom else float("nan")


def _half_life(phi: float) -> float:
    """Half-life of mean reversion in an AR(1) with coefficient ``phi``."""
    if not np.isfinite(phi) or phi <= 0 or phi >= 1:
        return float("nan")
    return float(-np.log(2) / np.log(phi))


def _hurst(series: np.ndarray, max_lag: int = 50) -> float:
    """Hurst exponent via rescaled-range-ish log-log slope of std-of-diffs.

    H > 0.5 trending, < 0.5 mean-reverting, ≈ 0.5 random walk.
    This is the cheap-and-cheerful variance-of-lagged-diffs estimator; fine
    for ranking products, not for publication.
    """
    s = series[~np.isnan(series)]
    if len(s) < max_lag * 3:
        return float("nan")
    lags = range(2, max_lag)
    tau = [np.std(s[lag:] - s[:-lag]) for lag in lags]
    tau = np.array(tau)
    lags_arr = np.array(list(lags))
    mask = tau > 0
    if mask.sum() < 5:
        return float("nan")
    slope, _ = np.polyfit(np.log(lags_arr[mask]), np.log(tau[mask]), 1)
    return float(slope)


def _variance_ratio(returns: np.ndarray, k: int = 5) -> float:
    """Lo-MacKinlay style variance ratio. 1.0 = random walk.

    VR < 1 → mean reversion; VR > 1 → momentum.
    """
    r = returns[~np.isnan(returns)]
    if len(r) < k * 5:
        return float("nan")
    var1 = r.var()
    agg = np.array([r[i:i + k].sum() for i in range(len(r) - k + 1)])
    vark = agg.var() / k
    return float(vark / var1) if var1 > 0 else float("nan")


def run_reversion_tests(
    features: pd.DataFrame,
    ret_lags: List[int] = (1, 2, 5, 10, 20),
) -> Dict[str, float]:
    mid = features["mid"].values
    ret = features["log_ret"].values
    phi = _ar1(ret)
    stats: Dict[str, float] = {
        "ar1_ret": phi,
        "half_life_ret": _half_life(phi) if phi > 0 else float("nan"),
        "ar1_mid": _ar1(mid),
        "hurst_mid": _hurst(mid),
        "variance_ratio_5": _variance_ratio(ret, 5),
        "variance_ratio_20": _variance_ratio(ret, 20),
    }
    # Return autocorrelation at multiple lags.
    s = pd.Series(ret).dropna()
    for lag in ret_lags:
        stats[f"ret_autocorr_lag{lag}"] = float(s.autocorr(lag)) if len(s) > lag else float("nan")
    # Directional persistence: P(sign(r_t+1) == sign(r_t)).
    sign = np.sign(s.values)
    pairs = (sign[:-1] == sign[1:]) & (sign[:-1] != 0)
    if len(pairs) > 0:
        stats["sign_continuation_prob"] = float(pairs.mean())
    return stats


def classify(stats: Dict[str, float]) -> str:
    """Coarse regime label for the report.

    Decision informed: which strategy family to prioritise.
    """
    h = stats.get("hurst_mid", float("nan"))
    a = stats.get("ar1_ret", float("nan"))
    vr = stats.get("variance_ratio_20", float("nan"))
    if np.isnan(h) and np.isnan(a):
        return "unknown"
    rev = (h < 0.45) or (a < -0.05) or (np.isfinite(vr) and vr < 0.8)
    trend = (h > 0.55) or (a > 0.05) or (np.isfinite(vr) and vr > 1.2)
    if rev and not trend:
        return "mean_reverting"
    if trend and not rev:
        return "trending"
    return "random_or_mixed"
