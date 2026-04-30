"""
UV_VISOR_YELLOW vs UV_VISOR_ORANGE pairs trade research.

Strategy: rolling z-score on (YELLOW - ORANGE) spread.
  z > +entry → YELLOW expensive vs ORANGE → short YELLOW, long ORANGE
  z < -entry → ORANGE expensive vs YELLOW → long YELLOW, short ORANGE
  |z| < exit → flat

Note: trader.py already has a 1-sided UV_YO strategy that only trades ORANGE.
This research tests a bidirectional pairs approach.

Run:
  python3 research_uv_yo_pairs.py
"""

import pandas as pd
import numpy as np
import math
from pathlib import Path

DATA_DIR = Path("data/round5")
DAYS = [2, 3, 4]
HALF_SPREAD = 1
SIZE = 10


def load_data():
    frames = [pd.read_csv(DATA_DIR / f"prices_round_5_day_{d}.csv", sep=";") for d in DAYS]
    df = pd.concat(frames, ignore_index=True)
    products = ["UV_VISOR_YELLOW", "UV_VISOR_ORANGE"]
    sub = df[df["product"].isin(products)]
    pivot = sub.pivot_table(index=["day", "timestamp"], columns="product", values="mid_price")
    pivot.columns = [c.replace("UV_VISOR_", "") for c in pivot.columns]
    return pivot.sort_index()


def rolling_z(series, window, min_history):
    mean = series.rolling(window, min_periods=min_history).mean()
    std = series.rolling(window, min_periods=min_history).std()
    return (series - mean) / std.clip(lower=0.01)


def simulate(pivot, window=200, entry_z=1.0, exit_z=0.3, size=SIZE, verbose=True):
    yel = pivot["YELLOW"]
    org = pivot["ORANGE"]
    spread = yel - org
    z = rolling_z(spread, window, window)

    pos_y = 0
    pos_o = 0
    pnl = 0.0
    trades = 0
    results_by_day = {}
    prev_day = None
    day_pnl = 0.0

    for i in range(len(spread)):
        day = pivot.index[i][0]
        if prev_day is not None and day != prev_day:
            results_by_day[prev_day] = day_pnl
            day_pnl = 0.0
        prev_day = day

        zi = z.iloc[i]
        if math.isnan(zi):
            continue

        target_y = pos_y
        target_o = pos_o

        if zi > entry_z:
            target_y = -size
            target_o = size
        elif zi < -entry_z:
            target_y = size
            target_o = -size
        elif abs(zi) < exit_z:
            target_y = 0
            target_o = 0

        d_y = target_y - pos_y
        d_o = target_o - pos_o

        if d_y != 0:
            pnl -= abs(d_y) * HALF_SPREAD
            day_pnl -= abs(d_y) * HALF_SPREAD
            trades += 1
            pos_y = target_y
        if d_o != 0:
            pnl -= abs(d_o) * HALF_SPREAD
            day_pnl -= abs(d_o) * HALF_SPREAD
            trades += 1
            pos_o = target_o

        if i + 1 < len(spread):
            ny = yel.iloc[i + 1]
            no = org.iloc[i + 1]
            pnl_step = pos_y * (ny - yel.iloc[i]) + pos_o * (no - org.iloc[i])
            pnl += pnl_step
            day_pnl += pnl_step

    results_by_day[prev_day] = day_pnl

    if verbose:
        print(f"\nwindow={window}, entry_z={entry_z}, exit_z={exit_z}, size={size}")
        for d in DAYS:
            print(f"  Day {d}: {results_by_day.get(d, 0):>8.0f}")
        print(f"  TOTAL:  {pnl:>8.0f}  ({trades} trade events)")
    return pnl, results_by_day


def param_sweep(pivot):
    print("\n=== Parameter sweep ===")
    print(f"{'window':>8} {'entry_z':>8} {'exit_z':>7}  {'PnL':>10}")
    best = (-1e9, None)
    for window in [100, 200, 400, 600, 1000]:
        for entry_z in [0.75, 1.0, 1.25, 1.5, 2.0]:
            for exit_z in [0.1, 0.3, 0.5]:
                pnl, _ = simulate(pivot, window=window, entry_z=entry_z, exit_z=exit_z, verbose=False)
                print(f"{window:>8} {entry_z:>8.2f} {exit_z:>7.1f}  {pnl:>10.0f}")
                if pnl > best[0]:
                    best = (pnl, (window, entry_z, exit_z))
    print(f"\nBest: pnl={best[0]:.0f}  params={best[1]}")
    return best


if __name__ == "__main__":
    pivot = load_data()

    print("=== UV YELLOW vs ORANGE summary ===")
    print(f"Overall corr: {pivot['YELLOW'].corr(pivot['ORANGE']):.4f}")
    for d in DAYS:
        sub = pivot.xs(d, level="day")
        c = sub["YELLOW"].corr(sub["ORANGE"])
        spread = sub["YELLOW"] - sub["ORANGE"]
        print(f"  Day {d}: corr={c:.3f}  Y-O range=[{spread.min():.0f}, {spread.max():.0f}]  std={spread.std():.0f}")

    print("\n=== Default (window=200, entry_z=1.0, exit_z=0.3) ===")
    simulate(pivot)

    best = param_sweep(pivot)

    print(f"\n=== Best params per-day breakdown ===")
    w, ez, xz = best[1]
    simulate(pivot, window=w, entry_z=ez, exit_z=xz)
