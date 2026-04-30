"""
SNACKPACK_VANILLA × SNACKPACK_CHOCOLATE pairs research.

Discovery: VANILLA and CHOCOLATE are -0.97 correlated (consistent across days).
Their SUM should be strongly mean-reverting around a constant.

Strategy: trade the SUM = VANILLA + CHOCOLATE on rolling z-score.
  z > entry → SUM expensive → short VANILLA + short CHOCOLATE
  z < -entry → SUM cheap → long VANILLA + long CHOCOLATE
  |z| < exit → flat
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
    products = ["SNACKPACK_VANILLA", "SNACKPACK_CHOCOLATE"]
    sub = df[df["product"].isin(products)]
    pivot = sub.pivot_table(index=["day", "timestamp"], columns="product", values="mid_price")
    pivot.columns = [c.replace("SNACKPACK_", "") for c in pivot.columns]
    return pivot.sort_index()


def rolling_z(series, window, min_history):
    mean = series.rolling(window, min_periods=min_history).mean()
    std = series.rolling(window, min_periods=min_history).std()
    return (series - mean) / std.clip(lower=0.01)


def simulate(pivot, window=200, entry_z=1.0, exit_z=0.3, size=SIZE, verbose=True):
    van = pivot["VANILLA"]
    cho = pivot["CHOCOLATE"]
    spread = van + cho  # SUM (since anti-correlated)
    z = rolling_z(spread, window, window)

    pos_v = 0
    pos_c = 0
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

        target_v = pos_v
        target_c = pos_c
        if zi > entry_z:
            target_v = -size
            target_c = -size
        elif zi < -entry_z:
            target_v = size
            target_c = size
        elif abs(zi) < exit_z:
            target_v = 0
            target_c = 0

        d_v = target_v - pos_v
        d_c = target_c - pos_c
        if d_v != 0:
            pnl -= abs(d_v) * HALF_SPREAD
            day_pnl -= abs(d_v) * HALF_SPREAD
            trades += 1
            pos_v = target_v
        if d_c != 0:
            pnl -= abs(d_c) * HALF_SPREAD
            day_pnl -= abs(d_c) * HALF_SPREAD
            trades += 1
            pos_c = target_c

        if i + 1 < len(spread):
            nv = van.iloc[i + 1]
            nc = cho.iloc[i + 1]
            step = pos_v * (nv - van.iloc[i]) + pos_c * (nc - cho.iloc[i])
            pnl += step
            day_pnl += step

    results_by_day[prev_day] = day_pnl

    if verbose:
        print(f"\nwindow={window}, entry_z={entry_z}, exit_z={exit_z}, size={size}")
        for d in DAYS:
            print(f"  Day {d}: {results_by_day.get(d, 0):>8.0f}")
        print(f"  TOTAL:  {pnl:>8.0f}  ({trades} trade events)")
    return pnl, results_by_day


def param_sweep(pivot):
    print("\n=== Parameter sweep on SUM (V+C) ===")
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
    print(f"Loaded {len(pivot)} ticks")
    print(f"\n=== SUM (VANILLA + CHOCOLATE) summary ===")
    for d in DAYS:
        sub = pivot.xs(d, level="day")
        s = sub["VANILLA"] + sub["CHOCOLATE"]
        print(f"  Day {d}: SUM mean={s.mean():.0f}  std={s.std():.1f}  range=[{s.min():.0f}, {s.max():.0f}]")

    print(f"\n=== Default (window=200, entry_z=1.0, exit_z=0.3) ===")
    simulate(pivot)
    best = param_sweep(pivot)

    print(f"\n=== Best params per-day ===")
    w, ez, xz = best[1]
    simulate(pivot, window=w, entry_z=ez, exit_z=xz)
