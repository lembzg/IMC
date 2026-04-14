"""
reversion_tests.py
------------------
Statistical evidence for whether a product reverts, trends, is pinned to an
anchor, or is dominated by bid-ask microstructure noise.

The previous version classified nearly every discrete-price product as
``mean_reverting`` because:
  * AR(1) of returns is strongly negative on any tick-grid with sparse moves
    (bid-ask bounce), and
  * variance_ratio on returns then falls well below 1,
both of which were (wrongly) taken as price-level mean reversion.

The fix is to look at the **price level**, not the return tape, for level
mean-reversion evidence; keep the return-level statistics only as descriptors.

Labels produced:
  * ``fixed_anchored``       — price sits at a constant value, almost no moves
  * ``mean_reverting_level`` — AR(1) on de-drifted mid in (0, 1), reasonable
                                half-life, Hurst below 0.5
  * ``trending``             — Hurst > 0.55 and variance_ratio > 1.2 on levels
  * ``microstructure_noise`` — negative return autocorrelation dominates while
                                the level looks like a near-random-walk
  * ``random_or_mixed``      — no confident signal either way
  * ``unknown``              — not enough data to decide
"""
from __future__ import annotations

import logging
from typing import Dict, List

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Low-level estimators
# ---------------------------------------------------------------------------

def _ar1(x: np.ndarray) -> float:
    x = x[~np.isnan(x)]
    if len(x) < 20:
        return float("nan")
    x0, x1 = x[:-1], x[1:]
    x0 = x0 - x0.mean()
    x1 = x1 - x1.mean()
    denom = (x0 ** 2).sum()
    return float((x0 * x1).sum() / denom) if denom else float("nan")


def _half_life_from_phi(phi: float) -> float:
    if not np.isfinite(phi) or phi <= 0 or phi >= 1:
        return float("nan")
    return float(-np.log(2) / np.log(phi))


def _hurst(series: np.ndarray, max_lag: int = 50) -> float:
    """Variance-of-lagged-diffs Hurst. Guarded to return NaN when unreliable."""
    s = series[~np.isnan(series)]
    if len(s) < max_lag * 3:
        return float("nan")
    lags = np.arange(2, max_lag)
    tau = np.array([np.std(s[lag:] - s[:-lag]) for lag in lags])
    # If the series is near-constant the taus are tiny and the log-log slope
    # is numerically meaningless. Require a non-trivial spread of taus.
    mask = tau > 0
    if mask.sum() < 5 or tau[mask].max() < 1e-6:
        return float("nan")
    slope, _ = np.polyfit(np.log(lags[mask]), np.log(tau[mask]), 1)
    # Clamp to valid Hurst domain; if clearly outside, treat as unreliable.
    if not np.isfinite(slope) or slope < -0.2 or slope > 1.2:
        return float("nan")
    return float(max(0.0, min(1.0, slope)))


def _variance_ratio(x: np.ndarray, k: int) -> float:
    """Lo-MacKinlay variance ratio. 1.0 = random walk, <1 revert, >1 trend."""
    x = x[~np.isnan(x)]
    if len(x) < k * 5:
        return float("nan")
    var1 = x.var()
    agg = np.array([x[i:i + k].sum() for i in range(len(x) - k + 1)])
    vark = agg.var() / k
    return float(vark / var1) if var1 > 0 else float("nan")


# ---------------------------------------------------------------------------
# Metric bundle
# ---------------------------------------------------------------------------

def run_reversion_tests(
    features: pd.DataFrame,
    ret_lags: List[int] = (1, 2, 5, 10, 20),
) -> Dict[str, float]:
    mid = features["mid"].to_numpy()
    ret = features["log_ret"].to_numpy()

    # Level (mid) statistics — the honest place to look for reversion.
    # Detrend mid with a slow rolling mean before measuring AR(1) to remove
    # any linear drift bias; then AR(1) near 0 means reversion is fast, AR(1)
    # near 1 means the level is a random walk.
    mid_s = pd.Series(mid)
    slow = mid_s.rolling(500, min_periods=50).mean()
    dev = (mid_s - slow).to_numpy()
    phi_level = _ar1(dev)
    half_life_level = _half_life_from_phi(phi_level)

    # Return-level descriptors (kept for context; NOT used for the label).
    phi_ret = _ar1(ret)

    # Sign continuation fixed: divide by nonzero-predecessor pairs only.
    s = pd.Series(ret).dropna().to_numpy()
    if len(s) > 1:
        sign = np.sign(s)
        prev, nxt = sign[:-1], sign[1:]
        nonzero_prev = prev != 0
        sign_cont = float((prev[nonzero_prev] == nxt[nonzero_prev]).mean()) \
            if nonzero_prev.any() else float("nan")
        # Also report the fraction of non-moving ticks for context.
        nonzero_frac = float((sign != 0).mean())
    else:
        sign_cont = float("nan")
        nonzero_frac = float("nan")

    stats: Dict[str, float] = {
        # Level evidence (used by classifier).
        "ar1_mid_detrended": phi_level,
        "half_life_level": half_life_level,
        "ar1_mid": _ar1(mid),
        "hurst_mid": _hurst(mid),
        "variance_ratio_5": _variance_ratio(ret, 5),
        "variance_ratio_20": _variance_ratio(ret, 20),
        # Return-level descriptors (context only).
        "ar1_ret": phi_ret,
        "sign_continuation_prob": sign_cont,
        "nonzero_return_frac": nonzero_frac,
        # Mid-range descriptors: how much the price actually moves.
        "mid_range": float(np.nanmax(mid) - np.nanmin(mid)),
        "mid_std": float(np.nanstd(mid)),
    }
    # Return autocorrelation at lags.
    rs = pd.Series(ret).dropna()
    for lag in ret_lags:
        stats[f"ret_autocorr_lag{lag}"] = (
            float(rs.autocorr(lag)) if len(rs) > lag else float("nan")
        )
    return stats


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------

def classify(stats: Dict[str, float]) -> str:
    """Evidence-based regime label; conservative — defaults to random_or_mixed.

    Decision rules (in order):
      1. If the price barely moves (very small std relative to level and low
         nonzero-return fraction) -> fixed_anchored.
      2. If Hurst > 0.55 and variance ratio on returns > 1.2 -> trending.
      3. If ar1_mid_detrended in (0.5, 0.999), half-life in (2, 500) ticks,
         and Hurst < 0.5 (or NaN) -> mean_reverting_level.
      4. If return AR(1) is strongly negative (< -0.2) but the level looks
         like a random walk (ar1_mid near 1 and Hurst near 0.5) ->
         microstructure_noise.
      5. Otherwise -> random_or_mixed / unknown.
    """
    mid_std = stats.get("mid_std", float("nan"))
    nonzero = stats.get("nonzero_return_frac", float("nan"))
    h = stats.get("hurst_mid", float("nan"))
    ar1_mid = stats.get("ar1_mid", float("nan"))
    ar1_dev = stats.get("ar1_mid_detrended", float("nan"))
    hl = stats.get("half_life_level", float("nan"))
    vr = stats.get("variance_ratio_20", float("nan"))
    ar1_r = stats.get("ar1_ret", float("nan"))

    # 1. Fixed / anchored: almost no movement.
    if np.isfinite(mid_std) and mid_std < 1.0 and \
            np.isfinite(nonzero) and nonzero < 0.05:
        return "fixed_anchored"

    # 2. Trending: both level Hurst and return VR agree.
    if np.isfinite(h) and h > 0.55 and np.isfinite(vr) and vr > 1.2:
        return "trending"

    # 3. Level-based mean reversion.
    level_reverts = (
        np.isfinite(ar1_dev) and 0.5 < ar1_dev < 0.999
        and np.isfinite(hl) and 2.0 < hl < 500.0
        and (not np.isfinite(h) or h < 0.5)
    )
    if level_reverts:
        return "mean_reverting_level"

    # 4. Microstructure-noise (return autocorrelation is negative but the
    #    level is indistinguishable from a random walk).
    level_rw_like = (
        (not np.isfinite(h) or 0.4 <= h <= 0.6)
        and (not np.isfinite(ar1_mid) or abs(ar1_mid) > 0.95)
    )
    if np.isfinite(ar1_r) and ar1_r < -0.2 and level_rw_like:
        return "microstructure_noise"

    if not np.isfinite(h) and not np.isfinite(ar1_mid):
        return "unknown"
    return "random_or_mixed"
