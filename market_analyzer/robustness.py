"""
robustness.py
-------------
Phase 2 stub: aggregate sweep results across days to detect plateaus vs spikes.

Inputs:  list of per-day sweep DataFrames for the same strategy.
Outputs: DataFrame keyed by parameter set with mean/std/min PnL across days,
         plus a "plateau_score" = mean / (1 + std) (higher = more robust).

Trading decision informed: prefer parameter sets with high plateau_score over
spiky single-day winners — those overfit.
"""
from __future__ import annotations

from typing import List

import pandas as pd


def aggregate_across_days(sweeps_by_day: List[pd.DataFrame], key_cols: List[str]) -> pd.DataFrame:
    if not sweeps_by_day:
        return pd.DataFrame()
    combined = pd.concat(sweeps_by_day, axis=0, ignore_index=True)
    grp = combined.groupby(key_cols)["total_pnl"]
    agg = grp.agg(["mean", "std", "min", "max", "count"]).reset_index()
    agg["plateau_score"] = agg["mean"] / (1.0 + agg["std"].fillna(0))
    return agg.sort_values("plateau_score", ascending=False)
