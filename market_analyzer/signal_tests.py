"""
signal_tests.py
---------------
Predictive power of z-score deviations and order book imbalance, with
guards that stop the report from overclaiming on degenerate data.
"""
from __future__ import annotations

import logging
from typing import Dict, List

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# A reporting-row is "too thin" if fewer than this many observations.
MIN_N = 50
# Two rows are near-duplicates if this Jaccard of their trigger masks is met.
DUP_JACCARD = 0.95


def zscore_series(features: pd.DataFrame, window: int) -> pd.Series:
    mid = features["mid"]
    mu = mid.rolling(window, min_periods=max(5, window // 5)).mean()
    sd = mid.rolling(window, min_periods=max(5, window // 5)).std().replace(0, np.nan)
    return (mid - mu) / sd


def _mask_hash(mask: pd.Series) -> np.ndarray:
    """Boolean mask as a packed uint64 fingerprint for fast Jaccard checks."""
    return np.packbits(mask.fillna(False).to_numpy(dtype=bool))


def _jaccard_packed(a: np.ndarray, b: np.ndarray) -> float:
    n = min(len(a), len(b))
    if n == 0:
        return 0.0
    # Bit-level approximation — exact Jaccard on the underlying boolean vectors
    # requires unpacking; but we only need a similarity score.
    inter = np.bitwise_and(a[:n], b[:n])
    union = np.bitwise_or(a[:n], b[:n])
    iw = int.from_bytes(inter.tobytes(), "little").bit_count()
    uw = int.from_bytes(union.tobytes(), "little").bit_count()
    return iw / uw if uw else 0.0


def zscore_predictive(
    features: pd.DataFrame,
    windows: List[int],
    thresholds: List[float],
    horizons: List[int],
) -> pd.DataFrame:
    """Conditional future-return stats for |z| > threshold.

    Post-processing:
      * rows with n < MIN_N are dropped (small sample);
      * near-duplicate rows (same window/side/horizon, different threshold but
        trigger mask overlap > DUP_JACCARD) are de-duplicated — only the
        tightest threshold survives, and a ``collapsed_thresholds`` column
        lists the thresholds that produced the same subset. This stops the
        report from printing the same 168-row subset 12 times across threshold
        grids when z rarely exceeds any threshold.
    """
    rows = []
    mid = features["mid"]

    for w in windows:
        z = zscore_series(features, w)
        for h in horizons:
            fut = (mid.shift(-h) - mid) / mid
            for thr in thresholds:
                for side in ("high", "low"):
                    mask = (z > thr) if side == "high" else (z < -thr)
                    r = fut[mask].dropna()
                    if len(r) < MIN_N:
                        continue
                    expect_sign = -1 if side == "high" else +1
                    rows.append({
                        "window": w,
                        "threshold": float(thr),
                        "horizon": h,
                        "side": side,
                        "n": int(len(r)),
                        "mean_future_ret": float(r.mean()),
                        "median_future_ret": float(r.median()),
                        "std_future_ret": float(r.std()),
                        "win_rate_reversion": float(((r * expect_sign) > 0).mean()),
                        "_mask_hash": _mask_hash(mask),
                    })

    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)

    # Deduplicate threshold rows within the same (window, side, horizon) whose
    # trigger masks overlap >= DUP_JACCARD. Keep the highest threshold (most
    # selective); record the others in collapsed_thresholds.
    kept: List[dict] = []
    for (w, side, h), grp in df.groupby(["window", "side", "horizon"],
                                         sort=False):
        grp = grp.sort_values("threshold", ascending=False).to_dict("records")
        used = [False] * len(grp)
        for i, row_i in enumerate(grp):
            if used[i]:
                continue
            collapsed = [row_i["threshold"]]
            for j in range(i + 1, len(grp)):
                if used[j]:
                    continue
                sim = _jaccard_packed(row_i["_mask_hash"], grp[j]["_mask_hash"])
                if sim >= DUP_JACCARD:
                    collapsed.append(grp[j]["threshold"])
                    used[j] = True
            row_i["collapsed_thresholds"] = (
                ",".join(f"{t:g}" for t in sorted(set(collapsed)))
            )
            kept.append(row_i)

    out = pd.DataFrame(kept).drop(columns=["_mask_hash"])
    return out.reset_index(drop=True)


def obi_predictive(
    features: pd.DataFrame,
    horizons: List[int],
    n_buckets: int = 10,
    col: str = "obi_l1",
) -> pd.DataFrame:
    """Conditional future return by OBI decile.

    Adds an ``n_buckets_effective`` column so downstream logic can tell when
    qcut collapsed to too few distinct buckets (e.g. 2 when 10 were asked
    for — the "monotonicity" claim is trivially true in that case).
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
    effective = int(buckets.dropna().nunique())
    if effective < 3:
        log.warning("OBI qcut on %s collapsed to %d buckets (asked for %d)",
                    col, effective, n_buckets)
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
                "n_buckets_effective": effective,
            })
    return pd.DataFrame(rows)


def obi_correlation(features: pd.DataFrame, horizons: List[int]) -> Dict[str, float]:
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
