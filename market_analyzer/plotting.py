"""
plotting.py
-----------
All matplotlib plots for a single product/day.

Inputs:  features DF, signal series, sweep tables, strategy result.
Outputs: PNGs written to ``plots_dir``.

Trading decision informed: visual sanity check — parameter heatmaps reveal
plateaus; strategy PnL curves reveal slow bleed vs consistent edge; z-score
overlays reveal whether thresholds would have triggered sensibly.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .strategies import SimResult


def _save(fig, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def plot_price_overview(features: pd.DataFrame, path: Path):
    # Exclude rows where mid is invalid so zero-spikes never appear in the plot.
    n_invalid = int(features["mid"].isna().sum())
    f = features[features["mid"].notna()]
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.plot(f["timestamp"], f["mid"], label="mid", lw=0.8)
    ax.plot(f["timestamp"], f["best_bid"], label="best_bid", lw=0.5, alpha=0.6)
    ax.plot(f["timestamp"], f["best_ask"], label="best_ask", lw=0.5, alpha=0.6)
    if f["weighted_mid"].notna().any():
        ax.plot(f["timestamp"], f["weighted_mid"], label="weighted_mid", lw=0.5, alpha=0.8)
    if "vwap" in f and f["vwap"].notna().any():
        ax.plot(f["timestamp"], f["vwap"], label="vwap", lw=0.8, alpha=0.8)
    title = "Price overview"
    if n_invalid:
        title += f"  ({n_invalid} invalid-mid snapshots excluded)"
    ax.set_title(title)
    ax.set_xlabel("timestamp")
    ax.legend(loc="best", fontsize=8)
    _save(fig, path)


def plot_spread_depth(features: pd.DataFrame, path: Path):
    # Drop rows where spread is NaN (invalid L1 snapshots) so zero-spikes
    # never appear in the spread panel.
    f = features[features["spread"].notna()]
    fig, axs = plt.subplots(2, 1, figsize=(11, 6), sharex=True)
    axs[0].plot(f["timestamp"], f["spread"], lw=0.6)
    axs[0].set_title("Spread")
    axs[1].plot(f["timestamp"], f["bid_depth"], lw=0.6, label="bid_depth")
    axs[1].plot(f["timestamp"], f["ask_depth"], lw=0.6, label="ask_depth")
    axs[1].set_title("Depth (sum L1-L3)")
    axs[1].legend(fontsize=8)
    _save(fig, path)


def plot_obi(features: pd.DataFrame, path: Path):
    fig, ax = plt.subplots(figsize=(11, 4))
    ax.plot(features["timestamp"], features["obi_l1"], lw=0.4, alpha=0.7, label="obi_l1")
    if "obi_total" in features:
        ax.plot(features["timestamp"], features["obi_total"], lw=0.4, alpha=0.7, label="obi_total")
    ax.axhline(0, color="k", lw=0.3)
    ax.set_title("Order book imbalance")
    ax.legend(fontsize=8)
    _save(fig, path)


def plot_zscore(features: pd.DataFrame, z: pd.Series, path: Path):
    fig, ax = plt.subplots(figsize=(11, 4))
    ax.plot(features["timestamp"], z, lw=0.5)
    for thr in (1.0, 2.0):
        ax.axhline(thr, color="r", lw=0.4, ls="--")
        ax.axhline(-thr, color="g", lw=0.4, ls="--")
    ax.set_title("Mid z-score")
    _save(fig, path)


def plot_return_autocorr(features: pd.DataFrame, path: Path, max_lag: int = 30):
    r = features["log_ret"].dropna()
    lags = range(1, max_lag + 1)
    acs = [r.autocorr(l) for l in lags]
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(list(lags), acs)
    ax.axhline(0, color="k", lw=0.4)
    ax.set_title("Return autocorrelation")
    ax.set_xlabel("lag")
    _save(fig, path)


def plot_return_distribution(features: pd.DataFrame, path: Path):
    r = features["log_ret"].dropna()
    r = r[np.isfinite(r)]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.hist(r, bins=60)
    ax.set_title("Return distribution")
    _save(fig, path)


def plot_rolling_vol_spread(features: pd.DataFrame, path: Path):
    # Both series are NaN at invalid-mid / invalid-spread ticks; drop them so
    # matplotlib draws clean lines without gaps caused by those bad snapshots.
    vol_valid = features["realized_vol"].notna()
    spr_valid = features["rolling_spread"].notna()
    fig, axs = plt.subplots(2, 1, figsize=(11, 5), sharex=True)
    axs[0].plot(features.loc[vol_valid, "timestamp"],
                features.loc[vol_valid, "realized_vol"], lw=0.7)
    axs[0].set_title("Rolling realized volatility")
    axs[1].plot(features.loc[spr_valid, "timestamp"],
                features.loc[spr_valid, "rolling_spread"], lw=0.7)
    axs[1].set_title("Rolling mean spread")
    _save(fig, path)


def plot_obi_vs_future_ret(obi_table: pd.DataFrame, path: Path):
    if obi_table.empty:
        return
    fig, ax = plt.subplots(figsize=(8, 4))
    for h, g in obi_table.groupby("horizon"):
        ax.plot(g["bucket"], g["mean_future_ret"], marker="o", label=f"h={h}")
    ax.axhline(0, color="k", lw=0.4)
    ax.set_title("Mean future return by OBI bucket")
    ax.set_xlabel("OBI bucket (low→high)")
    ax.legend(fontsize=8)
    _save(fig, path)


def plot_strategy_result(res: SimResult, features: pd.DataFrame, path: Path):
    fig, axs = plt.subplots(3, 1, figsize=(11, 8), sharex=True)
    valid_mid = features["mid"].notna()
    axs[0].plot(features.loc[valid_mid, "timestamp"], features.loc[valid_mid, "mid"], lw=0.6)
    if not res.fills.empty:
        buys = res.fills[res.fills["side"] > 0]
        sells = res.fills[res.fills["side"] < 0]
        axs[0].scatter(buys["ts"], buys["price"], c="g", s=6, label="buy")
        axs[0].scatter(sells["ts"], sells["price"], c="r", s=6, label="sell")
        axs[0].legend(fontsize=8)
    axs[0].set_title(f"{res.name} — PnL {res.summary['total_pnl']:.1f} / fills {res.summary['n_fills']}")
    axs[1].plot(res.position_series.index, res.position_series.values, lw=0.6)
    axs[1].set_title("Position")
    axs[2].plot(res.pnl_series.index, res.pnl_series.values, lw=0.8)
    axs[2].set_title("Cumulative PnL (mark-to-mid)")
    _save(fig, path)


def plot_param_heatmap(sweep: pd.DataFrame, xcol: str, ycol: str, path: Path,
                       title: str = ""):
    if sweep.empty or xcol not in sweep or ycol not in sweep:
        return
    try:
        pivot = sweep.pivot_table(index=ycol, columns=xcol, values="total_pnl", aggfunc="mean")
    except Exception:
        return
    fig, ax = plt.subplots(figsize=(8, 5))
    im = ax.imshow(pivot.values, origin="lower", aspect="auto")
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels([f"{c:g}" if isinstance(c, (int, float)) else str(c)
                         for c in pivot.columns], rotation=45)
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels([f"{r:g}" if isinstance(r, (int, float)) else str(r)
                         for r in pivot.index])
    ax.set_xlabel(xcol)
    ax.set_ylabel(ycol)
    ax.set_title(title or f"PnL heatmap: {ycol} × {xcol}")
    fig.colorbar(im, ax=ax)
    _save(fig, path)


def plot_cross_corr(corr: pd.DataFrame, path: Path, title: str):
    if corr.empty:
        return
    fig, ax = plt.subplots(figsize=(6, 5))
    im = ax.imshow(corr.values, vmin=-1, vmax=1, cmap="RdBu_r")
    ax.set_xticks(range(len(corr.columns)))
    ax.set_xticklabels(corr.columns, rotation=45)
    ax.set_yticks(range(len(corr.index)))
    ax.set_yticklabels(corr.index)
    ax.set_title(title)
    for i in range(len(corr.index)):
        for j in range(len(corr.columns)):
            ax.text(j, i, f"{corr.values[i,j]:.2f}", ha="center", va="center", fontsize=7)
    fig.colorbar(im, ax=ax)
    _save(fig, path)
