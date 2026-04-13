"""
execution_analysis.py
---------------------
Slippage, adverse selection, fill-quality diagnostics.

Inputs:  fills_df, market_df, horizons.
Outputs: per-fill DataFrame with mid_at_fill, mid_after_h, slippage,
         adverse_h cols + summary dict.

Trading decision informed:
  * Fills with positive immediate adverse selection (mid moves against us
    after our buys) -> we are toxic-flow taking; widen edge or quote less
    aggressively.
  * Slippage > 0 on takes -> we are crossing too far; tighten edge or use
    smaller size.
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd


def annotate_fills(fills: pd.DataFrame, market: pd.DataFrame,
                   horizons: List[int]) -> pd.DataFrame:
    if fills.empty:
        return fills.copy()
    out = fills.copy().sort_values(["product", "ts"]).reset_index(drop=True)
    if market.empty:
        return out
    pieces = []
    for prod, f in out.groupby("product"):
        m = market[market["product"] == prod].sort_values("ts").reset_index(drop=True)
        m_idx = m.set_index("ts")["mid"]
        # mid at fill = last mid <= ts
        mid_at = pd.merge_asof(f.sort_values("ts"), m[["ts", "mid"]],
                               on="ts", direction="backward")
        f = f.copy()
        f["mid_at_fill"] = mid_at["mid"].values
        # slippage in price-units relative to mid (positive = paid more than mid for buy / sold below mid).
        f["slippage"] = (f["price"] - f["mid_at_fill"]) * f["side"]
        # forward mid at horizons: index by ts -> shift would skip gaps; use merge_asof per horizon.
        ts_arr = m["ts"].values
        for h in horizons:
            shifted_ts = f["ts"].values + h * 100  # IMC ticks = 100ms apart
            # find next-mid at-or-after shifted_ts (forward). Use searchsorted.
            idx = np.searchsorted(ts_arr, shifted_ts, side="left")
            idx = np.clip(idx, 0, len(ts_arr) - 1)
            f[f"mid_h{h}"] = m["mid"].values[idx]
            # adverse: positive when market moved against our side after the fill
            #   buy -> bad if mid drops; sell -> bad if mid rises
            f[f"adverse_h{h}"] = -f["side"] * (f[f"mid_h{h}"] - f["mid_at_fill"])
        pieces.append(f)
    return pd.concat(pieces, ignore_index=True)


def execution_summary(annotated: pd.DataFrame, horizons: List[int]) -> Dict[str, Dict]:
    if annotated.empty:
        return {}
    summary: Dict[str, Dict] = {}
    for prod, f in annotated.groupby("product"):
        d = {
            "n_fills": int(len(f)),
            "buys": int((f["side"] > 0).sum()),
            "sells": int((f["side"] < 0).sum()),
            "mean_slippage": float(f["slippage"].mean()) if "slippage" in f else float("nan"),
            "median_slippage": float(f["slippage"].median()) if "slippage" in f else float("nan"),
        }
        for h in horizons:
            col = f"adverse_h{h}"
            if col in f:
                d[f"mean_adverse_h{h}"] = float(f[col].mean())
                d[f"pct_adverse_h{h}"] = float((f[col] > 0).mean())
        summary[prod] = d
    return summary
