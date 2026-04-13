"""
signal_analysis.py
------------------
Effectiveness of strategy signals (Z, OBI, SHIFT, EMA) at fill times.

For each fill, look up the most-recent signal value for the same product
and compute forward mid moves at multiple horizons. Bucket signal values
and report mean forward PnL per bucket per side.

Inputs:  fills_df, signals_df, market_df, horizons.
Outputs: per-signal DataFrame and a summary dict.

Trading decision informed:
  * Forward return monotone in signal bucket -> signal is real; consider
    raising thresholds to keep only the strongest.
  * Forward return flat / inverted in some bucket -> filter that bucket out.
  * Buy fills with negative forward returns at high signal -> signal direction
    is correct but execution is too slow; tighten edge.
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd


def _signal_at_fills(fills: pd.DataFrame, signals: pd.DataFrame) -> pd.DataFrame:
    if fills.empty or signals.empty:
        return pd.DataFrame()
    pieces = []
    for (prod, name), s in signals.groupby(["product", "name"]):
        s = s[["ts", "value"]].sort_values("ts").rename(columns={"value": name})
        f = fills[fills["product"] == prod].sort_values("ts")
        if f.empty:
            continue
        merged = pd.merge_asof(f, s, on="ts", direction="backward")
        pieces.append(merged)
    if not pieces:
        return pd.DataFrame()
    # Merge all signal columns onto the same fill rows.
    base = fills.sort_values(["product", "ts"]).reset_index(drop=True)
    out = base.copy()
    for p in pieces:
        sig_col = [c for c in p.columns if c not in base.columns and c != "ts"]
        for c in sig_col:
            tmp = p[["ts", "product", c]]
            out = out.merge(tmp, on=["ts", "product"], how="left",
                            suffixes=("", f"_{c}_dup"))
            # drop duplicates from successive merges
            dup = [col for col in out.columns if col.endswith("_dup")]
            out = out.drop(columns=dup, errors="ignore")
    return out


def signal_effectiveness(fills: pd.DataFrame, signals: pd.DataFrame,
                         market: pd.DataFrame, horizons: List[int],
                         n_buckets: int = 5) -> Dict[str, pd.DataFrame]:
    if fills.empty or signals.empty:
        return {}
    fs = _signal_at_fills(fills, signals)
    if fs.empty:
        return {}
    # Attach forward mid PnL.
    if not market.empty:
        from .execution_analysis import annotate_fills
        ann = annotate_fills(fs, market, horizons)
    else:
        ann = fs.copy()
    out: Dict[str, pd.DataFrame] = {}
    sig_names = sorted(signals["name"].unique())
    for name in sig_names:
        if name not in ann.columns or ann[name].isna().all():
            continue
        for h in horizons:
            adv_col = f"adverse_h{h}"
            if adv_col not in ann.columns:
                continue
            sub = ann[["product", "side", name, adv_col]].dropna()
            if sub.empty:
                continue
            sub = sub.copy()
            try:
                sub["bucket"] = pd.qcut(sub[name], n_buckets, labels=False, duplicates="drop")
            except ValueError:
                continue
            # forward PnL = -adverse (favorable move for our side)
            sub["forward_pnl"] = -sub[adv_col]
            g = sub.groupby(["product", "side", "bucket"]).agg(
                n=("forward_pnl", "size"),
                mean_signal=(name, "mean"),
                mean_forward_pnl=("forward_pnl", "mean"),
                win_rate=("forward_pnl", lambda x: float((x > 0).mean())),
            ).reset_index()
            out[f"{name}_h{h}"] = g
    return out
