"""
fair_value_models.py
--------------------
Compute candidate fair-value series and evaluate them against future mid.

Inputs:  features DF (from market_features.compute_market_features).
Outputs: (fv_series_dict, eval_table). ``fv_series_dict`` maps model name ->
         pd.Series; ``eval_table`` is a DataFrame ranked by MAE at each horizon.

Trading decision informed:
  * Which signal (mid, wmid, microprice, EMA, VWAP) best *predicts* future
    mid? That is the fair value to build a market-maker or taker around.
  * Large error across all models -> product is too random for FV-based
    strategies; rely on OBI / spread capture instead.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np
import pandas as pd


def build_fair_value_candidates(
    features: pd.DataFrame,
    ema_alphas: List[float],
    roll_windows: List[int],
) -> Dict[str, pd.Series]:
    """All fair-value candidates as pd.Series aligned to ``features.index``."""
    mid = features["mid"]
    out: Dict[str, pd.Series] = {
        "mid": mid,
        "weighted_mid": features["weighted_mid"],
        "microprice": features["microprice"],
        "constant_mean": pd.Series(np.full(len(mid), mid.mean()), index=mid.index),
    }
    for w in roll_windows:
        out[f"rolling_mean_{w}"] = mid.rolling(w, min_periods=max(2, w // 5)).mean()
    for a in ema_alphas:
        out[f"ema_{a:g}"] = mid.ewm(alpha=a, adjust=False).mean()
    if "vwap" in features and features["vwap"].notna().any():
        out["vwap"] = features["vwap"]
    return out


def evaluate_fair_values(
    fv_candidates: Dict[str, pd.Series],
    features: pd.DataFrame,
    horizons: List[int],
) -> pd.DataFrame:
    """Return MAE / RMSE of each FV vs future mid at each horizon.

    For each horizon h we compare FV(t) to mid(t+h). A good fair value has low
    error across horizons.
    """
    mid = features["mid"]
    rows = []
    for name, fv in fv_candidates.items():
        fv = fv.reindex(mid.index)
        for h in horizons:
            future = mid.shift(-h)
            err = (fv - future).dropna()
            if len(err) == 0:
                continue
            rows.append({
                "model": name,
                "horizon": h,
                "mae": float(err.abs().mean()),
                "rmse": float(np.sqrt((err ** 2).mean())),
                "bias": float(err.mean()),
                "n": int(len(err)),
            })
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["horizon", "mae"]).reset_index(drop=True)
    return df


def best_fair_value(eval_table: pd.DataFrame, horizon: int = 5) -> Tuple[str, float]:
    """Return (model_name, mae) of best FV at given horizon."""
    sub = eval_table[eval_table["horizon"] == horizon]
    if sub.empty:
        return ("mid", float("nan"))
    row = sub.iloc[0]
    return (str(row["model"]), float(row["mae"]))
