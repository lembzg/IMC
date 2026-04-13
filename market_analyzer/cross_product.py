"""
cross_product.py
----------------
Phase 1: return & price correlation matrix across products on a given day.
Phase 2 (TODO): rolling correlation, lead-lag, cointegration (Engle-Granger),
                hedge-ratio estimates, spread z-score series.

Inputs:  mapping {product: features_df} for a single day.
Outputs: dict of DataFrames (price_corr, return_corr, lead_lag_stub).

Trading decision informed:
  * High correlation + stable hedge ratio -> pair trade candidate.
  * Significant lead-lag -> directional alpha on the lagger using the leader.
  * Low correlation -> independent risk (useful for diversifying exposure).
"""
from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd


def cross_product_report(features_by_product: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    if len(features_by_product) < 2:
        return {}
    # Align on timestamp.
    mids = {}
    rets = {}
    for prod, df in features_by_product.items():
        s = df.set_index("timestamp")["mid"]
        mids[prod] = s
        rets[prod] = df.set_index("timestamp")["log_ret"]
    mid_df = pd.concat(mids, axis=1).sort_index().ffill()
    ret_df = pd.concat(rets, axis=1).sort_index()

    out = {
        "price_correlation": mid_df.corr().round(4),
        "return_correlation": ret_df.corr().round(4),
        # Phase 2 stub: naive lead-lag via corr(ret_i[t], ret_j[t-1..+k]).
        "lead_lag_max5": _lead_lag(ret_df, max_lag=5),
    }
    return out


def _lead_lag(ret_df: pd.DataFrame, max_lag: int = 5) -> pd.DataFrame:
    """For each pair (i, j) find the lag (in ticks) at which corr is maximised.

    Positive lag means i leads j (shift j forward). Phase-2 candidate for
    building leader/lagger predictive strategies.
    """
    prods = list(ret_df.columns)
    rows = []
    for i in prods:
        for j in prods:
            if i == j:
                continue
            best_c, best_lag = 0.0, 0
            for lag in range(-max_lag, max_lag + 1):
                if lag == 0:
                    continue
                c = ret_df[i].corr(ret_df[j].shift(lag))
                if np.isfinite(c) and abs(c) > abs(best_c):
                    best_c, best_lag = float(c), lag
            rows.append({"leader": i, "follower": j, "best_lag": best_lag,
                         "best_corr": round(best_c, 4)})
    return pd.DataFrame(rows)
