"""
order_lifecycle.py
------------------
Match our emitted quotes to realized fills and label each quote as filled /
unfilled (partially when same-timestamp fill size < quoted size).

Inputs:  Run.orders_df(), Run.fills_df(), Run.market_df().
Outputs: DataFrame one-row-per-order with filled_size, fill_price,
         was_passive, was_aggressive.

Trading decision informed:
  * Low fill rate on passive bids while spread is tight -> too passive,
    tighten quotes.
  * High fill rate on takes followed by adverse move -> taking into toxic
    flow, widen the edge.
"""
from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd


def build_lifecycle(run_orders: pd.DataFrame, run_fills: pd.DataFrame,
                    run_market: pd.DataFrame) -> pd.DataFrame:
    if run_orders.empty:
        return pd.DataFrame()

    # Classify each emitted order as quote vs take using the market snapshot
    # at the same timestamp (if available).
    orders = run_orders.copy()
    if not run_market.empty:
        m = run_market.rename(columns={"ts": "ts"})[["ts", "product", "best_bid", "best_ask"]]
        orders = orders.merge(m, on=["ts", "product"], how="left")
        cross_buy = (orders["side"] > 0) & (orders["price"] >= orders["best_ask"])
        cross_sell = (orders["side"] < 0) & (orders["price"] <= orders["best_bid"])
        orders["was_aggressive"] = (cross_buy | cross_sell).fillna(False)
    else:
        orders["best_bid"] = np.nan
        orders["best_ask"] = np.nan
        orders["was_aggressive"] = False

    # Match fills to orders by (ts, product, side, price).
    if run_fills.empty:
        orders["filled_size"] = 0
        orders["fill_price"] = np.nan
        return orders

    fills_grp = (run_fills.groupby(["ts", "product", "side", "price"])
                 .agg(filled_size=("size", "sum")).reset_index())
    orders = orders.merge(fills_grp, on=["ts", "product", "side", "price"],
                          how="left")
    orders["filled_size"] = orders["filled_size"].fillna(0).astype(int)
    orders["fill_fraction"] = np.where(orders["size"] > 0,
                                       orders["filled_size"] / orders["size"], 0.0)
    orders["fill_price"] = np.where(orders["filled_size"] > 0, orders["price"], np.nan)
    orders["was_passive"] = ~orders["was_aggressive"].fillna(False)
    return orders


def fill_rate_summary(lifecycle: pd.DataFrame) -> pd.DataFrame:
    """Fill rate by product × side × (passive|aggressive) × tag."""
    if lifecycle.empty:
        return pd.DataFrame()
    grp_cols = ["product", "side"]
    if "tag" in lifecycle:
        grp_cols.append("tag")
    grp_cols.append("was_passive")
    g = lifecycle.groupby(grp_cols, dropna=False).agg(
        orders=("size", "count"),
        total_quoted=("size", "sum"),
        total_filled=("filled_size", "sum"),
    ).reset_index()
    g["fill_rate"] = np.where(g["total_quoted"] > 0,
                              g["total_filled"] / g["total_quoted"], 0.0)
    return g
