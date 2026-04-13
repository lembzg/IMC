"""
regime_analysis.py
------------------
Condition results on observable market regime (vol, spread). Phase-2 lite.

Inputs:  fills_df (annotated with adverse_h* from execution_analysis), market_df.
Outputs: DataFrame of PnL stats by regime bucket per product.

Trading decision informed: if the strategy only wins in low-vol / tight-spread
regimes, gate it behind that regime instead of running it always.
"""
from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd


def _regime_series(market: pd.DataFrame, n_buckets: int = 3) -> pd.DataFrame:
    if market.empty:
        return pd.DataFrame()
    rows = []
    for prod, m in market.groupby("product"):
        m = m.sort_values("ts").copy()
        m["spread"] = (m["best_ask"] - m["best_bid"]).astype(float)
        m["ret"] = m["mid"].pct_change()
        m["vol"] = m["ret"].rolling(100, min_periods=10).std()
        try:
            m["vol_bucket"] = pd.qcut(m["vol"], n_buckets, labels=["low", "mid", "high"],
                                      duplicates="drop")
        except ValueError:
            m["vol_bucket"] = "unknown"
        try:
            m["spread_bucket"] = pd.qcut(m["spread"], n_buckets,
                                         labels=["tight", "normal", "wide"],
                                         duplicates="drop")
        except ValueError:
            m["spread_bucket"] = "unknown"
        rows.append(m[["ts", "product", "vol_bucket", "spread_bucket"]])
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def performance_by_regime(fills_annotated: pd.DataFrame, market: pd.DataFrame,
                          horizon: int = 10) -> pd.DataFrame:
    if fills_annotated.empty or market.empty:
        return pd.DataFrame()
    regimes = _regime_series(market)
    if regimes.empty:
        return pd.DataFrame()
    merged = pd.merge_asof(
        fills_annotated.sort_values("ts"),
        regimes.sort_values("ts"),
        on="ts", by="product", direction="backward",
    )
    adv_col = f"adverse_h{horizon}"
    if adv_col not in merged.columns:
        return pd.DataFrame()
    merged["forward_pnl"] = -merged[adv_col]
    g = merged.groupby(["product", "vol_bucket", "spread_bucket"], dropna=False).agg(
        n=("forward_pnl", "size"),
        mean_forward_pnl=("forward_pnl", "mean"),
        win_rate=("forward_pnl", lambda x: float((x > 0).mean())),
    ).reset_index()
    return g
