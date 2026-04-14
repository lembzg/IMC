"""
fair_value_models.py
--------------------
Fair-value candidates and their out-of-sample error against future mid.

Every candidate carries an explicit ``causal`` flag. A causal FV uses only
information available at time t; a non-causal ("oracle") FV may peek at the
entire sample and serves purely as a reference lower-bound. Non-causal
models are kept out of the ranking used by downstream recommendations.

Trading decision informed:
  * Which *causal* signal best predicts future mid? That is the reference
    price to build a market-maker or taker around.
  * Large error across all causal models -> product is too random for
    FV-based strategies; rely on OBI / spread capture instead.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class FVCandidate:
    name: str
    series: pd.Series
    causal: bool   # False = uses full-sample / future info; excluded from decisions.


def build_fair_value_candidates(
    features: pd.DataFrame,
    ema_alphas: List[float],
    roll_windows: List[int],
) -> Dict[str, FVCandidate]:
    """Return a dict of FV candidates keyed by name.

    Causal (live-usable):
      - mid, weighted_mid, microprice (current-tick book features)
      - expanding_mean (causal running mean of mid)
      - rolling_mean_W (causal)
      - ema_A (causal)
      - vwap (causal, if available)

    Non-causal (reference only):
      - constant_mean_oracle (full-sample mean; look-ahead bias; kept solely
        to show the achievable floor on MAE for a perfectly-stationary price).
    """
    mid = features["mid"]
    out: Dict[str, FVCandidate] = {}

    # Current-tick book features are causal (computed from the t book only).
    out["mid"] = FVCandidate("mid", mid, causal=True)
    if "weighted_mid" in features:
        out["weighted_mid"] = FVCandidate("weighted_mid", features["weighted_mid"], causal=True)
    if "microprice" in features:
        out["microprice"] = FVCandidate("microprice", features["microprice"], causal=True)

    # Causal expanding mean replaces the non-causal constant_mean.
    out["expanding_mean"] = FVCandidate(
        "expanding_mean", mid.expanding(min_periods=20).mean(), causal=True,
    )

    for w in roll_windows:
        out[f"rolling_mean_{w}"] = FVCandidate(
            f"rolling_mean_{w}",
            mid.rolling(w, min_periods=max(2, w // 5)).mean(),
            causal=True,
        )
    for a in ema_alphas:
        out[f"ema_{a:g}"] = FVCandidate(
            f"ema_{a:g}",
            mid.ewm(alpha=a, adjust=False).mean(),
            causal=True,
        )
    if "vwap" in features and features["vwap"].notna().any():
        out["vwap"] = FVCandidate("vwap", features["vwap"], causal=True)

    # Non-causal oracle: full-sample mean. Kept as a floor reference, never
    # recommended for strategy use.
    out["constant_mean_oracle"] = FVCandidate(
        "constant_mean_oracle",
        pd.Series(np.full(len(mid), mid.mean()), index=mid.index),
        causal=False,
    )
    return out


def evaluate_fair_values(
    fv_candidates: Dict[str, FVCandidate],
    features: pd.DataFrame,
    horizons: List[int],
) -> pd.DataFrame:
    """MAE / RMSE of each FV vs mid(t+h), with a ``causal`` column per row."""
    mid = features["mid"]
    rows = []
    for name, cand in fv_candidates.items():
        fv = cand.series.reindex(mid.index)
        for h in horizons:
            future = mid.shift(-h)
            err = (fv - future).dropna()
            if len(err) == 0:
                continue
            rows.append({
                "model": name,
                "causal": bool(cand.causal),
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


def best_causal_fair_value(eval_table: pd.DataFrame, horizon: int = 5) -> Tuple[str, float]:
    """Top *causal* FV at a given horizon. Returns (name, mae) or (mid, NaN)."""
    if eval_table.empty:
        return ("mid", float("nan"))
    sub = eval_table[(eval_table["horizon"] == horizon) & (eval_table["causal"])]
    if sub.empty:
        return ("mid", float("nan"))
    row = sub.sort_values("mae").iloc[0]
    return (str(row["model"]), float(row["mae"]))


# -- Backwards-compatibility shim --------------------------------------------
# Old callers did: dict[name] -> pd.Series. Provide a helper for them.

def as_series_dict(candidates: Dict[str, FVCandidate]) -> Dict[str, pd.Series]:
    return {name: c.series for name, c in candidates.items()}
