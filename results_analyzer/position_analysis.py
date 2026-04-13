"""
position_analysis.py
--------------------
Reconstruct position series from fills (fallback when POS snapshots are
absent) and compute inventory stress metrics.

Inputs:  fills DF, (optional) positions DF, products list.
Outputs: position_df(ts, product, position), inventory_stats dict.

Trading decision informed:
  * Max |position| near limit -> sizing/limit logic too loose.
  * Average |inventory| large relative to limit -> under-recycling; strategy
    is getting stuck in trades.
  * Time-at-limit > small threshold -> likely missing fills on the release
    side because quotes are too passive.
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd


def reconstruct_positions(fills: pd.DataFrame, products: List[str]) -> pd.DataFrame:
    if fills.empty:
        return pd.DataFrame(columns=["ts", "product", "position"])
    rows = []
    for prod in products:
        f = fills[fills["product"] == prod].sort_values("ts")
        if f.empty:
            continue
        signed = f["side"] * f["size"]
        pos = signed.cumsum().astype(int)
        rows.append(pd.DataFrame({"ts": f["ts"].values,
                                  "product": prod,
                                  "position": pos.values}))
    if not rows:
        return pd.DataFrame(columns=["ts", "product", "position"])
    return pd.concat(rows, ignore_index=True)


def inventory_stats(positions: pd.DataFrame, position_limit: int = 20) -> Dict[str, Dict]:
    out: Dict[str, Dict] = {}
    if positions.empty:
        return out
    for prod, g in positions.groupby("product"):
        p = g["position"].astype(float).values
        abs_p = np.abs(p)
        out[prod] = {
            "max_long": int(p.max()) if len(p) else 0,
            "max_short": int(p.min()) if len(p) else 0,
            "avg_abs_position": float(abs_p.mean()),
            "pct_time_at_limit": float((abs_p >= position_limit).mean()),
            "pct_time_flat": float((abs_p == 0).mean()),
            "n_snaps": int(len(p)),
        }
    return out
