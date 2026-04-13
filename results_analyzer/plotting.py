"""
plotting.py
-----------
Plots for one run / product.

Trading decision informed: visual confirmation of every numerical claim in
the report (fill locations on the price chart, drawdown over time, PnL
attribution, signal-bucket forward PnL).
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def _save(fig, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def plot_price_with_fills(market: pd.DataFrame, fills: pd.DataFrame, path: Path,
                          product: str):
    m = market[market["product"] == product]
    f = fills[fills["product"] == product] if not fills.empty else fills
    if m.empty:
        return
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.plot(m["ts"], m["mid"], lw=0.6, label="mid")
    if not f.empty:
        b = f[f["side"] > 0]
        s = f[f["side"] < 0]
        ax.scatter(b["ts"], b["price"], c="g", s=10, label="buy fill")
        ax.scatter(s["ts"], s["price"], c="r", s=10, label="sell fill")
    ax.set_title(f"{product}: price with fills")
    ax.legend(fontsize=8)
    _save(fig, path)


def plot_pnl(pnl_series: pd.DataFrame, path: Path, product: str,
             authoritative: pd.DataFrame | None = None):
    g = pnl_series[pnl_series["product"] == product]
    if g.empty:
        return
    g = g.sort_values("ts")
    fig, axs = plt.subplots(2, 1, figsize=(11, 6), sharex=True)
    axs[0].plot(g["ts"], g["realized"], label="realized", lw=0.8)
    axs[0].plot(g["ts"], g["unrealized"], label="unrealized", lw=0.6, alpha=0.7)
    axs[0].plot(g["ts"], g["total"], label="total (MTM)", lw=0.9)
    if authoritative is not None and product in authoritative.columns:
        axs[0].plot(authoritative.index, authoritative[product], label="activities-log PnL",
                    lw=0.6, ls="--", alpha=0.7)
    axs[0].legend(fontsize=8)
    axs[0].set_title(f"{product}: PnL")
    running_max = np.maximum.accumulate(g["total"].values)
    dd = g["total"].values - running_max
    axs[1].plot(g["ts"], dd, lw=0.7, color="r")
    axs[1].set_title("Drawdown (MTM)")
    _save(fig, path)


def plot_position(positions: pd.DataFrame, path: Path, product: str):
    g = positions[positions["product"] == product].sort_values("ts")
    if g.empty:
        return
    fig, ax = plt.subplots(figsize=(11, 3.5))
    ax.step(g["ts"], g["position"], where="post", lw=0.7)
    ax.axhline(0, color="k", lw=0.3)
    ax.set_title(f"{product}: position over time")
    _save(fig, path)


def plot_trade_pnl_hist(round_trips: pd.DataFrame, path: Path, product: str):
    g = round_trips[round_trips["product"] == product]
    if g.empty:
        return
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.hist(g["pnl"], bins=40)
    ax.axvline(0, color="k", lw=0.5)
    ax.set_title(f"{product}: round-trip PnL distribution")
    _save(fig, path)


def plot_holding_time(round_trips: pd.DataFrame, path: Path, product: str):
    g = round_trips[round_trips["product"] == product]
    if g.empty:
        return
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.hist(g["holding_ticks"], bins=40)
    ax.set_title(f"{product}: holding time (ticks)")
    _save(fig, path)


def plot_mfe_mae(round_trips: pd.DataFrame, path: Path, product: str):
    g = round_trips[round_trips["product"] == product].dropna(subset=["mfe", "mae"])
    if g.empty:
        return
    fig, ax = plt.subplots(figsize=(6, 5))
    colors = np.where(g["pnl"] > 0, "g", "r")
    ax.scatter(g["mae"], g["mfe"], c=colors, s=10, alpha=0.7)
    ax.axhline(0, color="k", lw=0.3)
    ax.axvline(0, color="k", lw=0.3)
    ax.set_xlabel("MAE")
    ax.set_ylabel("MFE")
    ax.set_title(f"{product}: MFE vs MAE per round trip")
    _save(fig, path)


def plot_signal_buckets(signal_tables: dict, path: Path, product: str):
    """Bar-grid of mean forward PnL by signal bucket for each signal-horizon pair."""
    keys = [k for k, df in signal_tables.items()
            if not df.empty and (df["product"] == product).any()]
    if not keys:
        return
    n = len(keys)
    fig, axs = plt.subplots(n, 1, figsize=(8, max(2, 2 * n)))
    if n == 1:
        axs = [axs]
    for ax, k in zip(axs, keys):
        df = signal_tables[k]
        d = df[df["product"] == product]
        if d.empty:
            continue
        for side, sg in d.groupby("side"):
            ax.bar(sg["bucket"] + (0.2 if side > 0 else -0.2),
                   sg["mean_forward_pnl"], width=0.4,
                   label=f"side={side:+d}")
        ax.axhline(0, color="k", lw=0.3)
        ax.set_title(k)
        ax.legend(fontsize=7)
    _save(fig, path)


def plot_fill_rate_by_tag(fill_rate_df: pd.DataFrame, path: Path, product: str):
    g = fill_rate_df[fill_rate_df["product"] == product] if not fill_rate_df.empty else fill_rate_df
    if g.empty:
        return
    fig, ax = plt.subplots(figsize=(8, 4))
    labels = [f"side={s} pass={p}" + (f" tag={t}" if "tag" in g and pd.notna(t) else "")
              for s, p, t in zip(g.get("side", []), g.get("was_passive", []),
                                 g.get("tag", [None] * len(g)))]
    ax.bar(range(len(g)), g["fill_rate"])
    ax.set_xticks(range(len(g)))
    ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=7)
    ax.set_title(f"{product}: fill rate")
    _save(fig, path)
