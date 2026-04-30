"""
MICROCHIP OVAL-RECTANGLE pairs trade research.

Observation: RECTANGLE inversely mirrors OVAL — when OVAL falls, RECT rises
(Day 4: OVAL -1800, RECT +800 while their SUM stays ~stable at 14.5k).

The OVAL-RECT DIFF is mean-reverting on a rolling z-score basis.
Strategy: z-score on rolling(200) of (OVAL - RECT), entry ±1.0, exit ±0.3.
  z > +1.0 → OVAL overpriced vs RECT → short OVAL (+10), long RECT (-10)... wait:
    short OVAL means pos_oval = -10, long RECT means pos_rect = +10
  z < -1.0 → OVAL underpriced → long OVAL, short RECT

Run:
  python3 research_chip_oval_rect.py
"""

import pandas as pd
import numpy as np
import math
from pathlib import Path

DATA_DIR = Path("data/round5")
DAYS = [2, 3, 4]
WINDOW = 600
MIN_HISTORY = 600
ENTRY_Z = 0.75
EXIT_Z = 0.1
SIZE = 10
HALF_SPREAD = 1  # assume 1-tick cost per trade per product


def load_data():
    frames = [pd.read_csv(DATA_DIR / f"prices_round_5_day_{d}.csv", sep=";") for d in DAYS]
    df = pd.concat(frames, ignore_index=True)
    products = ["MICROCHIP_OVAL", "MICROCHIP_RECTANGLE"]
    sub = df[df["product"].isin(products)]
    pivot = sub.pivot_table(index=["day", "timestamp"], columns="product", values="mid_price")
    pivot.columns = [c.replace("MICROCHIP_", "") for c in pivot.columns]
    return pivot


def rolling_z(series, window, min_history):
    mean = series.rolling(window, min_periods=min_history).mean()
    std = series.rolling(window, min_periods=min_history).std()
    return (series - mean) / std.clip(lower=0.01)


def simulate(pivot, window=WINDOW, entry_z=ENTRY_Z, exit_z=EXIT_Z, size=SIZE, verbose=True):
    oval = pivot["OVAL"]
    rect = pivot["RECTANGLE"]
    diff = oval - rect

    z = rolling_z(diff, window, window)

    pos_oval = 0  # current position in OVAL
    pos_rect = 0  # current position in RECT
    pnl = 0.0
    trades = 0

    results_by_day = {}

    prev_day = None
    day_pnl = 0.0

    for i in range(len(diff)):
        day = pivot.index[i][0]
        if prev_day is not None and day != prev_day:
            results_by_day[prev_day] = day_pnl
            day_pnl = 0.0
        prev_day = day

        zi = z.iloc[i]
        if math.isnan(zi):
            continue

        target_oval = 0
        target_rect = 0

        if zi > entry_z:
            # OVAL high vs RECT → short OVAL, long RECT
            target_oval = -size
            target_rect = size
        elif zi < -entry_z:
            # OVAL low vs RECT → long OVAL, short RECT
            target_oval = size
            target_rect = -size
        elif abs(zi) < exit_z:
            target_oval = 0
            target_rect = 0
        else:
            target_oval = pos_oval
            target_rect = pos_rect

        # Execute delta
        delta_oval = target_oval - pos_oval
        delta_rect = target_rect - pos_rect

        if delta_oval != 0:
            cost = abs(delta_oval) * HALF_SPREAD
            pnl -= cost
            day_pnl -= cost
            trades += 1
            pos_oval = target_oval

        if delta_rect != 0:
            cost = abs(delta_rect) * HALF_SPREAD
            pnl -= cost
            day_pnl -= cost
            trades += 1
            pos_rect = target_rect

        # Mark-to-market on next tick
        if i + 1 < len(diff):
            next_oval = oval.iloc[i + 1]
            next_rect = rect.iloc[i + 1]
            pnl += pos_oval * (next_oval - oval.iloc[i])
            pnl += pos_rect * (next_rect - rect.iloc[i])
            day_pnl += pos_oval * (next_oval - oval.iloc[i])
            day_pnl += pos_rect * (next_rect - rect.iloc[i])

    results_by_day[prev_day] = day_pnl

    if verbose:
        print(f"\nwindow={window}, entry_z={entry_z}, exit_z={exit_z}, size={size}")
        for d in DAYS:
            print(f"  Day {d}: {results_by_day.get(d, 0):>8.0f}")
        print(f"  TOTAL:  {pnl:>8.0f}  ({trades} trade events)")
    return pnl


def param_sweep(pivot):
    print("\n=== Parameter sweep ===")
    print(f"{'window':>8} {'entry_z':>8} {'exit_z':>7}  {'PnL':>10}")
    best = (-1e9, None)
    for window in [100, 200, 400, 600]:
        for entry_z in [0.75, 1.0, 1.25, 1.5, 2.0]:
            for exit_z in [0.1, 0.3, 0.5]:
                pnl = simulate(pivot, window=window, entry_z=entry_z, exit_z=exit_z, verbose=False)
                print(f"{window:>8} {entry_z:>8.2f} {exit_z:>7.1f}  {pnl:>10.0f}")
                if pnl > best[0]:
                    best = (pnl, (window, entry_z, exit_z))
    print(f"\nBest: pnl={best[0]:.0f}  params={best[1]}")


if __name__ == "__main__":
    pivot = load_data()

    print("=== OVAL vs RECTANGLE summary ===")
    print(f"Overall corr: {pivot['OVAL'].corr(pivot['RECTANGLE']):.4f}")
    for d in DAYS:
        sub = pivot.xs(d, level="day")
        c = sub["OVAL"].corr(sub["RECTANGLE"])
        diff = sub["OVAL"] - sub["RECTANGLE"]
        print(f"  Day {d}: corr={c:.3f}  OVAL-RECT range=[{diff.min():.0f}, {diff.max():.0f}]  std={diff.std():.0f}")

    print("\n=== Default strategy (window=200, entry_z=1.0, exit_z=0.3) ===")
    simulate(pivot)

    param_sweep(pivot)
