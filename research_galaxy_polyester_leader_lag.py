"""
GALAXY_SOUNDS_BLACK_HOLES vs SLEEP_POD_POLYESTER leader-lag research.

Hypothesis: one product leads the other — when the leader's mid moves,
the laggard follows within a few ticks. We trade the laggard in the
direction of the leader's recent move.

Strategy:
  - Compute leader's price change over `lookback` ticks
  - If leader moved up by > threshold → buy laggard (expect it to follow)
  - If leader moved down by > threshold → sell laggard
  - Exit when laggard has moved enough (exit_threshold) or position > max_hold ticks

Run:
  python3 research_galaxy_polyester_leader_lag.py
"""

import pandas as pd
import numpy as np
import math
from pathlib import Path

DATA_DIR = Path("data/round5")
DAYS = [2, 3, 4]

LOOKBACK = 100       # ticks to measure leader move
ENTRY_THRESH = 10    # leader must move this much to trigger
EXIT_THRESH = 5      # exit laggard when it has moved this much in our favour
MAX_HOLD = 200       # max ticks to hold before forced exit
SIZE = 10
HALF_SPREAD = 1      # assumed 1-tick transaction cost per leg


def load_data():
    frames = [pd.read_csv(DATA_DIR / f"prices_round_5_day_{d}.csv", sep=";") for d in DAYS]
    df = pd.concat(frames, ignore_index=True)
    products = ["GALAXY_SOUNDS_BLACK_HOLES", "SLEEP_POD_POLYESTER"]
    sub = df[df["product"].isin(products)]
    pivot = sub.pivot_table(index=["day", "timestamp"], columns="product", values="mid_price")
    pivot = pivot.sort_index()
    return pivot


def check_lead_lag(pivot):
    """Cross-correlation: which product leads?"""
    print("\n=== Cross-correlation analysis ===")
    bh = pivot["GALAXY_SOUNDS_BLACK_HOLES"].dropna()
    sp = pivot["SLEEP_POD_POLYESTER"].dropna()

    bh_ret = bh.diff()
    sp_ret = sp.diff()

    lags = range(-20, 21)
    corrs = {}
    for lag in lags:
        if lag > 0:
            corrs[lag] = bh_ret.corr(sp_ret.shift(lag))   # BH leads SP by `lag`
        elif lag < 0:
            corrs[lag] = sp_ret.corr(bh_ret.shift(-lag))  # SP leads BH by `-lag`
        else:
            corrs[lag] = bh_ret.corr(sp_ret)

    best_lag = max(corrs, key=lambda k: abs(corrs[k]))
    print(f"  lag=0 corr: {corrs[0]:.4f}")
    for lag in [-5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5]:
        marker = " <-- best" if lag == best_lag else ""
        print(f"  lag={lag:+d}: {corrs[lag]:.4f}{marker}")
    print(f"\n  Best lag: {best_lag:+d}  (positive → BH leads SP, negative → SP leads BH)")
    return best_lag


def simulate(pivot, leader, laggard, lookback=LOOKBACK, entry_thresh=ENTRY_THRESH,
             exit_thresh=EXIT_THRESH, max_hold=MAX_HOLD, size=SIZE, verbose=True):
    ldr = pivot[leader].ffill()
    lag = pivot[laggard].ffill()

    pos = 0
    entry_lag_price = None
    hold_count = 0
    pnl = 0.0
    trades = 0
    results_by_day = {}
    prev_day = None
    day_pnl = 0.0

    for i in range(lookback, len(ldr)):
        day = pivot.index[i][0]
        if prev_day is not None and day != prev_day:
            # forced close at day end
            if pos != 0:
                close_price = lag.iloc[i]
                pnl += pos * (close_price - entry_lag_price) - abs(pos) * HALF_SPREAD
                day_pnl += pos * (close_price - entry_lag_price) - abs(pos) * HALF_SPREAD
                pos = 0
                entry_lag_price = None
                hold_count = 0
            results_by_day[prev_day] = day_pnl
            day_pnl = 0.0
        prev_day = day

        ldr_now = ldr.iloc[i]
        ldr_past = ldr.iloc[i - lookback]
        lag_now = lag.iloc[i]

        if math.isnan(ldr_now) or math.isnan(ldr_past) or math.isnan(lag_now):
            continue

        ldr_move = ldr_now - ldr_past

        # Exit logic
        if pos != 0:
            hold_count += 1
            lag_move = lag_now - entry_lag_price
            profit = pos * lag_move - abs(pos) * HALF_SPREAD
            forced_exit = hold_count >= max_hold
            target_exit = (pos > 0 and lag_move >= exit_thresh) or (pos < 0 and lag_move <= -exit_thresh)

            if forced_exit or target_exit:
                pnl += profit
                day_pnl += profit
                trades += 1
                pos = 0
                entry_lag_price = None
                hold_count = 0
                continue

        # Entry logic (only if flat)
        if pos == 0:
            if ldr_move > entry_thresh:
                pos = size
                entry_lag_price = lag_now
                pnl -= HALF_SPREAD
                day_pnl -= HALF_SPREAD
                hold_count = 0
            elif ldr_move < -entry_thresh:
                pos = -size
                entry_lag_price = lag_now
                pnl -= HALF_SPREAD
                day_pnl -= HALF_SPREAD
                hold_count = 0

    # final day
    if pos != 0 and entry_lag_price is not None:
        close_price = lag.iloc[-1]
        profit = pos * (close_price - entry_lag_price) - abs(pos) * HALF_SPREAD
        pnl += profit
        day_pnl += profit
        pos = 0
    results_by_day[prev_day] = day_pnl

    if verbose:
        print(f"\nlookback={lookback}, entry_thresh={entry_thresh}, exit_thresh={exit_thresh}, max_hold={max_hold}")
        print(f"  Leader={leader}, Laggard={laggard}")
        for d in DAYS:
            print(f"  Day {d}: {results_by_day.get(d, 0):>8.0f}")
        print(f"  TOTAL:  {pnl:>8.0f}  ({trades} trade events)")
    return pnl


def param_sweep(pivot, leader, laggard):
    print(f"\n=== Param sweep (leader={leader}) ===")
    print(f"{'lookback':>9} {'entry':>7} {'exit':>6} {'hold':>6}  {'PnL':>10}")
    best = (-1e9, None)
    for lookback in [50, 100, 200]:
        for entry_thresh in [5, 10, 20, 40]:
            for exit_thresh in [3, 5, 10]:
                for max_hold in [100, 200, 500]:
                    p = simulate(pivot, leader, laggard,
                                 lookback=lookback, entry_thresh=entry_thresh,
                                 exit_thresh=exit_thresh, max_hold=max_hold,
                                 verbose=False)
                    print(f"{lookback:>9} {entry_thresh:>7} {exit_thresh:>6} {max_hold:>6}  {p:>10.0f}")
                    if p > best[0]:
                        best = (p, (lookback, entry_thresh, exit_thresh, max_hold))
    print(f"\nBest: pnl={best[0]:.0f}  params={best[1]}")
    return best


if __name__ == "__main__":
    pivot = load_data()
    pivot.columns.name = None

    print("=== Data summary ===")
    for prod in ["GALAXY_SOUNDS_BLACK_HOLES", "SLEEP_POD_POLYESTER"]:
        s = pivot[prod].dropna()
        print(f"  {prod}: n={len(s)}  range=[{s.min():.0f}, {s.max():.0f}]  std={s.std():.1f}")

    best_lag = check_lead_lag(pivot)

    # Determine leader based on cross-correlation
    if best_lag >= 0:
        leader = "GALAXY_SOUNDS_BLACK_HOLES"
        laggard = "SLEEP_POD_POLYESTER"
    else:
        leader = "SLEEP_POD_POLYESTER"
        laggard = "GALAXY_SOUNDS_BLACK_HOLES"

    print(f"\n=== Default test (lookback={LOOKBACK}) ===")
    simulate(pivot, leader, laggard)

    print(f"\n=== Also test reverse direction ===")
    simulate(pivot, laggard, leader)

    best_fwd = param_sweep(pivot, leader, laggard)
    best_rev = param_sweep(pivot, laggard, leader)

    print(f"\n=== Summary ===")
    print(f"  Forward  ({leader} leads): best pnl={best_fwd[0]:.0f}  params={best_fwd[1]}")
    print(f"  Reverse  ({laggard} leads): best pnl={best_rev[0]:.0f}  params={best_rev[1]}")
