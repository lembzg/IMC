import math
from collections import defaultdict
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent
PRODUCT = "HYDROGEL_PACK"
LIMIT = 200
LOOKBACK = 800
ENTRY_Z = 2.0
TARGET = 200


def load_data():
    data = {}
    for day in (1, 2, 3):
        prices = pd.read_csv(ROOT / "data/prices" / f"prices_round_4_day_{day}.csv", sep=";")
        hydro = prices[prices["product"] == PRODUCT].sort_values("timestamp").reset_index(drop=True)
        trades = pd.read_csv(ROOT / "data/trades" / f"trades_round_4_day_{day}.csv", sep=";")
        hydro_trades = trades[trades["symbol"] == PRODUCT]

        by_ts = defaultdict(list)
        for _, row in hydro_trades.iterrows():
            by_ts[int(row.timestamp)].append((row.buyer, row.seller, int(row.quantity)))

        rows = []
        for _, row in hydro.iterrows():
            bids = []
            asks = []
            for level in (1, 2, 3):
                bid_price = row.get(f"bid_price_{level}")
                ask_price = row.get(f"ask_price_{level}")
                if not pd.isna(bid_price):
                    bids.append((int(bid_price), int(abs(row[f"bid_volume_{level}"]))))
                if not pd.isna(ask_price):
                    asks.append((int(ask_price), int(abs(row[f"ask_volume_{level}"]))))
            rows.append((int(row.timestamp), bids, asks, float(row.mid_price)))

        data[day] = (rows, by_ts, [row[3] for row in rows])
    return data


def rolling_z_values(mids):
    out = [0.0] * len(mids)
    rolling_sum = sum(mids[:LOOKBACK])
    rolling_sum_sq = sum(x * x for x in mids[:LOOKBACK])
    for i in range(LOOKBACK, len(mids)):
        mean = rolling_sum / LOOKBACK
        variance = rolling_sum_sq / LOOKBACK - mean * mean
        out[i] = 0.0 if variance <= 0 else (mids[i] - mean) / math.sqrt(variance)
        old = mids[i - LOOKBACK]
        new = mids[i]
        rolling_sum += new - old
        rolling_sum_sq += new * new - old * old
    return out


def cross_to_target(bids, asks, cash, pos, target):
    if target > pos:
        need = min(target - pos, LIMIT - pos)
        for price, volume in asks:
            qty = min(need, volume)
            cash -= qty * price
            pos += qty
            need -= qty
            if need <= 0:
                break
    elif target < pos:
        need = min(pos - target, LIMIT + pos)
        for price, volume in bids:
            qty = min(need, volume)
            cash += qty * price
            pos -= qty
            need -= qty
            if need <= 0:
                break
    return cash, pos


def simulate(jump=1, passive_mode="skew"):
    data = load_data()
    total = 0.0
    day_pnl = {}
    fills = 0
    qty_sum = 0

    for day, (rows, trades_by_ts, mids) in data.items():
        z_values = rolling_z_values(mids)
        cash = 0.0
        pos = 0

        for i, (ts, bids, asks, mid) in enumerate(rows):
            z = z_values[i]
            target = pos
            if z >= ENTRY_Z:
                target = -TARGET
            elif z <= -ENTRY_Z:
                target = TARGET
            cash, pos = cross_to_target(bids, asks, cash, pos, target)

            if not bids or not asks:
                continue
            bid_quote = bids[0][0] + jump
            ask_quote = asks[0][0] - jump
            allow_buy = pos < LIMIT
            allow_sell = pos > -LIMIT

            if passive_mode == "skew":
                if z <= -ENTRY_Z:
                    allow_sell = False
                elif z >= ENTRY_Z:
                    allow_buy = False

            for buyer, seller, qty in trades_by_ts.get(ts, []):
                if buyer == "Mark 38" and allow_sell and pos - qty >= -LIMIT:
                    cash += qty * ask_quote
                    pos -= qty
                    fills += 1
                    qty_sum += qty
                elif seller == "Mark 38" and allow_buy and pos + qty <= LIMIT:
                    cash -= qty * bid_quote
                    pos += qty
                    fills += 1
                    qty_sum += qty

        pnl = cash + pos * mids[-1]
        day_pnl[day] = pnl
        total += pnl

    return total, day_pnl, fills, qty_sum


def main():
    for jump in (0, 1, 2):
        total, day_pnl, fills, qty_sum = simulate(jump=jump)
        print(f"jump={jump} total={total:.0f} worst={min(day_pnl.values()):.0f} fills={fills} qty={qty_sum} days={day_pnl}")


if __name__ == "__main__":
    main()
