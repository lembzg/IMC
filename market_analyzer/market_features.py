"""
market_features.py
------------------
Per-product market-structure features. Pure functions on a prices DataFrame.

Inputs:  prices DF with standard IMC columns (bid/ask L1-L3, mid_price).
Outputs: the same DF with additional columns: best_bid, best_ask, spread,
         weighted_mid, microprice, bid_depth, ask_depth, obi, ret, realized_vol,
         rolling_spread, vwap (if trades supplied).

Trading decision informed:
  * spread / depth  -> can we make markets, or must we take?
  * OBI             -> directional pressure signal candidate
  * microprice      -> candidate fair-value
  * realized vol    -> sizing, risk appetite, strategy family choice
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd


def _safe(col: pd.Series) -> pd.Series:
    return col.fillna(0.0)


def compute_market_features(
    prices: pd.DataFrame,
    trades: Optional[pd.DataFrame] = None,
    vol_window: int = 100,
) -> pd.DataFrame:
    """Return a copy of ``prices`` with features added."""
    df = prices.copy()

    # Best quotes (level 1).
    df["best_bid"] = df["bid_price_1"]
    df["best_ask"] = df["ask_price_1"]
    df["best_bid_vol"] = df["bid_volume_1"]
    df["best_ask_vol"] = df["ask_volume_1"]
    df["spread"] = df["best_ask"] - df["best_bid"]

    # Mid (fallback to provided mid_price if L1 missing).
    book_mid = (df["best_bid"] + df["best_ask"]) / 2.0
    df["mid"] = book_mid.where(book_mid.notna(), df.get("mid_price"))

    # Weighted mid (volume-weighted toward heavier side).
    bv, av = _safe(df["best_bid_vol"]), _safe(df["best_ask_vol"])
    denom = (bv + av).replace(0, np.nan)
    df["weighted_mid"] = (df["best_bid"] * av + df["best_ask"] * bv) / denom
    # Microprice: classic definition (tilts toward side with less volume, which
    # tends to predict short-term direction better than mid).
    df["microprice"] = (df["best_ask"] * bv + df["best_bid"] * av) / denom

    # Depth (sum of L1..L3).
    bid_vol_cols = [c for c in ("bid_volume_1", "bid_volume_2", "bid_volume_3") if c in df]
    ask_vol_cols = [c for c in ("ask_volume_1", "ask_volume_2", "ask_volume_3") if c in df]
    df["bid_depth"] = df[bid_vol_cols].fillna(0).sum(axis=1)
    df["ask_depth"] = df[ask_vol_cols].fillna(0).sum(axis=1)

    # Order book imbalance: L1 pressure in [-1, 1]. Decision: directional tilt.
    l1_sum = (bv + av).replace(0, np.nan)
    df["obi_l1"] = (bv - av) / l1_sum
    total_sum = (df["bid_depth"] + df["ask_depth"]).replace(0, np.nan)
    df["obi_total"] = (df["bid_depth"] - df["ask_depth"]) / total_sum

    # Returns + realized vol (std of log returns over window).
    df["ret"] = df["mid"].pct_change()
    df["log_ret"] = np.log(df["mid"] / df["mid"].shift(1))
    df["realized_vol"] = df["log_ret"].rolling(vol_window, min_periods=10).std()
    df["rolling_spread"] = df["spread"].rolling(vol_window, min_periods=5).mean()

    # VWAP from trades (if given).
    if trades is not None and len(trades) > 0:
        df = _attach_vwap(df, trades, window=vol_window)
    else:
        df["vwap"] = np.nan
        df["trade_count"] = 0
        df["trade_volume"] = 0

    return df


def _attach_vwap(prices: pd.DataFrame, trades: pd.DataFrame, window: int) -> pd.DataFrame:
    """Attach rolling VWAP and trade activity to a prices frame.

    Assumption: trades timestamps align to price timestamps on the same tick
    grid. We bucket trades by timestamp, sum volume and pv, then forward-fill
    through ticks with no trades.
    """
    t = trades.copy()
    t["pv"] = t["price"] * t["quantity"]
    grp = t.groupby("timestamp").agg(pv=("pv", "sum"),
                                     vol=("quantity", "sum"),
                                     n=("quantity", "size"))
    grp = grp.reindex(prices["timestamp"].values, fill_value=0)
    pv_roll = grp["pv"].rolling(window, min_periods=1).sum()
    vol_roll = grp["vol"].rolling(window, min_periods=1).sum().replace(0, np.nan)
    prices = prices.copy()
    prices["vwap"] = (pv_roll / vol_roll).values
    prices["trade_count"] = grp["n"].values
    prices["trade_volume"] = grp["vol"].values
    return prices


def summarize(features: pd.DataFrame) -> dict:
    """One-line fingerprint for the report layer.

    Decision informed: is this product quiet/stable or noisy/illiquid?
    """
    mid = features["mid"].dropna()
    return {
        "n_ticks": int(len(features)),
        "mid_mean": float(mid.mean()) if len(mid) else np.nan,
        "mid_std": float(mid.std()) if len(mid) else np.nan,
        "mid_min": float(mid.min()) if len(mid) else np.nan,
        "mid_max": float(mid.max()) if len(mid) else np.nan,
        "spread_mean": float(features["spread"].mean()),
        "spread_median": float(features["spread"].median()),
        "bid_depth_mean": float(features["bid_depth"].mean()),
        "ask_depth_mean": float(features["ask_depth"].mean()),
        "trade_count_total": int(features["trade_count"].sum()) if "trade_count" in features else 0,
        "trade_volume_total": int(features["trade_volume"].sum()) if "trade_volume" in features else 0,
        "realized_vol_mean": float(features["realized_vol"].mean()),
    }
