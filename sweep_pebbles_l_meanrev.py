"""
Mean reversion backtest for PEBBLES_L on Round 5 data.
Fair value = mean(PEBBLES_XS, PEBBLES_S, PEBBLES_M, PEBBLES_XL).
Buy when mid < fair - THRESHOLD, sell when mid > fair + THRESHOLD.
Exit when mid returns within EXIT_THRESHOLD of fair.
Position limit 10, market orders (execute at best ask/bid).
"""
import csv
from pathlib import Path
from collections import defaultdict

DATA_DIR = Path("/home/j39233pt/Desktop/IMC/data/round5")
DAYS = [2, 3, 4]
POSITION_LIMIT = 10
EXIT_THRESHOLD = 0  # exit when mid crosses fair value
FAIR_PRODUCTS = ["PEBBLES_XS", "PEBBLES_S", "PEBBLES_M", "PEBBLES_XL"]
TARGET = "PEBBLES_L"
THRESHOLDS = [50, 100, 150, 200, 250]


def load_day(day: int) -> list[dict]:
    """Load and group price rows by timestamp."""
    path = DATA_DIR / f"prices_round_5_day_{day}.csv"
    rows = []
    with open(path) as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            rows.append(row)
    return rows


def group_by_ts(rows: list[dict]) -> dict:
    """Group rows by timestamp, keyed by product."""
    ts_map = defaultdict(dict)
    for row in rows:
        ts = int(row["timestamp"])
        product = row["product"]
        ts_map[ts][product] = row
    return ts_map


def get_mid(row: dict) -> float | None:
    v = row.get("mid_price")
    if v and v.strip():
        return float(v)
    return None


def get_best_ask(row: dict) -> float | None:
    v = row.get("ask_price_1")
    if v and v.strip():
        return float(v)
    return None


def get_best_bid(row: dict) -> float | None:
    v = row.get("bid_price_1")
    if v and v.strip():
        return float(v)
    return None


def backtest_day(ts_map: dict, threshold: int) -> float:
    position = 0
    cash = 0.0

    for ts in sorted(ts_map.keys()):
        products = ts_map[ts]
        if TARGET not in products:
            continue

        # Compute fair value from other pebbles
        fair_vals = []
        for p in FAIR_PRODUCTS:
            if p in products:
                m = get_mid(products[p])
                if m is not None:
                    fair_vals.append(m)
        if not fair_vals:
            continue
        fair = sum(fair_vals) / len(fair_vals)

        target_row = products[TARGET]
        mid = get_mid(target_row)
        if mid is None:
            continue

        best_ask = get_best_ask(target_row)
        best_bid = get_best_bid(target_row)

        # --- Exit logic (close position when mid returns near fair) ---
        if position > 0:
            # Long: exit when mid >= fair - EXIT_THRESHOLD
            if mid >= fair - EXIT_THRESHOLD:
                if best_bid is not None:
                    cash += position * best_bid
                    position = 0
        elif position < 0:
            # Short: exit when mid <= fair + EXIT_THRESHOLD
            if mid <= fair + EXIT_THRESHOLD:
                if best_ask is not None:
                    cash += position * best_ask  # position is negative
                    position = 0

        # --- Entry logic ---
        if mid < fair - threshold:
            # Buy signal: buy up to limit
            room = POSITION_LIMIT - position
            if room > 0 and best_ask is not None:
                qty = room
                cash -= qty * best_ask
                position += qty
        elif mid > fair + threshold:
            # Sell signal: sell down to -limit
            room = POSITION_LIMIT + position  # how much we can sell
            if room > 0 and best_bid is not None:
                qty = room
                cash += qty * best_bid
                position -= qty

    # Mark to market at end of day using last mid
    # Find last available mid for target
    last_mid = None
    for ts in sorted(ts_map.keys(), reverse=True):
        if TARGET in ts_map[ts]:
            m = get_mid(ts_map[ts][TARGET])
            if m is not None:
                last_mid = m
                break

    if last_mid is not None and position != 0:
        cash += position * last_mid

    return cash


def main():
    print(f"{'Threshold':>10} | {'Day 2':>10} | {'Day 3':>10} | {'Day 4':>10} | {'Total':>10}")
    print("-" * 60)

    day_data = {}
    for day in DAYS:
        rows = load_day(day)
        day_data[day] = group_by_ts(rows)

    for threshold in THRESHOLDS:
        pnls = []
        for day in DAYS:
            pnl = backtest_day(day_data[day], threshold)
            pnls.append(pnl)
        total = sum(pnls)
        pnl_strs = " | ".join(f"{p:>10.0f}" for p in pnls)
        print(f"{threshold:>10} | {pnl_strs} | {total:>10.0f}")


if __name__ == "__main__":
    main()
