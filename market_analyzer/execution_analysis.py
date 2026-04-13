"""
execution_analysis.py
---------------------
Where do trades actually occur, and how often are quotes at best filled?

Inputs:  features DF + trades DF.
Outputs: dict of execution statistics.

Trading decision informed:
  * % trades at bid/ask/inside -> will our passive quotes get filled, or will
    everyone else be passive too?
  * Time between trades -> can we run a market-making strategy that needs
    frequent fills?
  * Spread-time distribution -> what is a realistic quote width?
"""
from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd


def analyse_execution(features: pd.DataFrame, trades: pd.DataFrame) -> Dict[str, float]:
    stats: Dict[str, float] = {}
    if len(trades) == 0:
        return {
            "trades_total": 0.0,
            "trades_per_tick": 0.0,
            "pct_at_bid": float("nan"),
            "pct_at_ask": float("nan"),
            "pct_inside_spread": float("nan"),
            "pct_outside_spread": float("nan"),
            "spread_mean": float(features["spread"].mean()),
            "spread_median": float(features["spread"].median()),
            "spread_p90": float(features["spread"].quantile(0.90)),
            "mean_time_between_trades": float("nan"),
        }
    merged = pd.merge_asof(
        trades.sort_values("timestamp"),
        features[["timestamp", "best_bid", "best_ask"]].sort_values("timestamp"),
        on="timestamp",
        direction="backward",
    )
    at_bid = (merged["price"] <= merged["best_bid"]).mean()
    at_ask = (merged["price"] >= merged["best_ask"]).mean()
    inside = ((merged["price"] > merged["best_bid"]) & (merged["price"] < merged["best_ask"])).mean()
    outside = ((merged["price"] < merged["best_bid"]) | (merged["price"] > merged["best_ask"])).mean()

    dts = np.diff(trades["timestamp"].sort_values().values)
    stats.update({
        "trades_total": float(len(trades)),
        "trades_per_tick": float(len(trades) / max(1, len(features))),
        "pct_at_bid": float(at_bid),
        "pct_at_ask": float(at_ask),
        "pct_inside_spread": float(inside),
        "pct_outside_spread": float(outside),
        "spread_mean": float(features["spread"].mean()),
        "spread_median": float(features["spread"].median()),
        "spread_p90": float(features["spread"].quantile(0.90)),
        "mean_time_between_trades": float(dts.mean()) if len(dts) else float("nan"),
        "median_trade_size": float(trades["quantity"].median()),
    })
    return stats
