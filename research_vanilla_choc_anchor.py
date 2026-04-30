"""
Replace VANILLA's fair value with K - CHOCOLATE_mid (where K = rolling SUM mean).

Rationale: SUM = VANILLA + CHOCOLATE has std ~30-50 (range ~150) — extremely stable.
So predicting VANILLA = K - CHOCOLATE is far sharper than snackpack-mean fair.

Strategy: trade VANILLA against this prediction with rolling z-score on (VANILLA - predicted).
"""

import pandas as pd
import numpy as np
import math
from pathlib import Path

DATA_DIR = Path("data/round5")
DAYS = [2, 3, 4]
HALF_SPREAD = 1
SIZE = 10
POS_LIMIT = 10


def load_data():
    frames = [pd.read_csv(DATA_DIR / f"prices_round_5_day_{d}.csv", sep=";") for d in DAYS]
    df = pd.concat(frames, ignore_index=True)
    products = ["SNACKPACK_VANILLA", "SNACKPACK_CHOCOLATE"]
    sub = df[df["product"].isin(products)]
    pivot = sub.pivot_table(index=["day", "timestamp"], columns="product", values="mid_price")
    pivot.columns = [c.replace("SNACKPACK_", "") for c in pivot.columns]
    return pivot.sort_index()


def simulate(pivot, k_window=400, entry=10, exit=3, size=SIZE, half_spread=HALF_SPREAD, verbose=True):
    """
    Predict VANILLA from CHOCOLATE: predicted_van = K - cho, where K = rolling mean of (van+cho).
    Trade VANILLA based on residual.
    """
    van = pivot["VANILLA"]
    cho = pivot["CHOCOLATE"]
    sumvc = van + cho
    K = sumvc.rolling(k_window, min_periods=k_window).mean()

    predicted = K - cho
    residual = van - predicted  # positive = VANILLA expensive vs predicted

    pos = 0
    pnl = 0.0
    trades = 0
    results_by_day = {}
    prev_day = None
    day_pnl = 0.0

    for i in range(len(van)):
        day = pivot.index[i][0]
        if prev_day is not None and day != prev_day:
            results_by_day[prev_day] = day_pnl
            day_pnl = 0.0
        prev_day = day

        r = residual.iloc[i]
        if math.isnan(r):
            continue

        target = pos
        if r > entry:
            target = -size
        elif r < -entry:
            target = size
        elif abs(r) < exit:
            target = 0

        d_pos = target - pos
        if d_pos != 0:
            pnl -= abs(d_pos) * half_spread
            day_pnl -= abs(d_pos) * half_spread
            trades += 1
            pos = target

        if i + 1 < len(van):
            step = pos * (van.iloc[i + 1] - van.iloc[i])
            pnl += step
            day_pnl += step

    results_by_day[prev_day] = day_pnl

    if verbose:
        print(f"\nk_window={k_window}, entry={entry}, exit={exit}, size={size}")
        for d in DAYS:
            print(f"  Day {d}: {results_by_day.get(d, 0):>8.0f}")
        print(f"  TOTAL:  {pnl:>8.0f}  ({trades} trade events)")
    return pnl, results_by_day


def param_sweep(pivot):
    print("\n=== Parameter sweep (residual-band thresholds) ===")
    print(f"{'k_window':>9} {'entry':>6} {'exit':>5}  {'PnL':>10}  {'D2':>7} {'D3':>7} {'D4':>7}")
    best = (-1e9, None)
    for k_window in [200, 400, 800, 1500]:
        for entry in [5, 10, 15, 20, 30, 50]:
            for exit in [1, 3, 5, 10]:
                if exit >= entry:
                    continue
                pnl, by_day = simulate(pivot, k_window=k_window, entry=entry, exit=exit, verbose=False)
                d2 = by_day.get(2, 0); d3 = by_day.get(3, 0); d4 = by_day.get(4, 0)
                print(f"{k_window:>9} {entry:>6} {exit:>5}  {pnl:>10.0f}  {d2:>7.0f} {d3:>7.0f} {d4:>7.0f}")
                if pnl > best[0]:
                    best = (pnl, (k_window, entry, exit))
    print(f"\nBest: pnl={best[0]:.0f}  params={best[1]}")
    return best


if __name__ == "__main__":
    pivot = load_data()
    print(f"Loaded {len(pivot)} ticks")

    print(f"\n=== Default (k_window=400, entry=10, exit=3) ===")
    simulate(pivot)

    best = param_sweep(pivot)

    print(f"\n=== Best per-day breakdown ===")
    kw, e, x = best[1]
    simulate(pivot, k_window=kw, entry=e, exit=x)
