from datamodel import Order, TradingState
from typing import Dict, List
from collections import defaultdict
import csv
import json
import math
import statistics
import sys
from pathlib import Path


MOPPING = "ROBOT_MOPPING"
DISHES = "ROBOT_DISHES"
TRADES = (MOPPING, DISHES)
LIMIT = 10

WINDOW = 3000
WARMUP = 300
ENTRY_Z = 2.5
EXIT_Z = 0.75
ORDER_SIZE = 5


class Trader:
    def bid(self, state=None) -> int:
        return 0

    def run(self, state: TradingState):
        data = self._load(state.traderData)
        history = data.setdefault("mop_dish_sum", [])
        result = self._trade_pair(state, history)
        trader_data = json.dumps({"mop_dish_sum": history[-WINDOW:]}, separators=(",", ":"))
        return result, 0, trader_data

    def _trade_pair(self, state: TradingState, history: List[float]) -> Dict[str, List[Order]]:
        depths = {}
        mids = {}
        for product in TRADES:
            od = state.order_depths.get(product)
            if od is None or not od.buy_orders or not od.sell_orders:
                return {p: [] for p in TRADES}
            best_bid = max(od.buy_orders)
            best_ask = min(od.sell_orders)
            depths[product] = (best_bid, best_ask)
            mids[product] = (best_bid + best_ask) / 2.0

        pair_sum = mids[MOPPING] + mids[DISHES]
        history.append(pair_sum)
        if len(history) > WINDOW:
            del history[:-WINDOW]

        if len(history) < WARMUP:
            return {p: [] for p in TRADES}

        mean = sum(history) / len(history)
        variance = sum((x - mean) ** 2 for x in history) / max(1, len(history) - 1)
        stdev = math.sqrt(variance)
        if stdev < 1:
            return {p: [] for p in TRADES}

        z = (pair_sum - mean) / stdev
        result: Dict[str, List[Order]] = {}

        for product in TRADES:
            best_bid, best_ask = depths[product]
            position = state.position.get(product, 0)
            buy_room = LIMIT - position
            sell_room = LIMIT + position
            orders: List[Order] = []

            if abs(z) <= EXIT_Z:
                if position > 0 and sell_room > 0:
                    quantity = min(ORDER_SIZE, sell_room, position)
                    orders.append(Order(product, best_bid, -quantity))
                    sell_room -= quantity
                elif position < 0 and buy_room > 0:
                    quantity = min(ORDER_SIZE, buy_room, -position)
                    orders.append(Order(product, best_ask, quantity))
                    buy_room -= quantity

            if z <= -ENTRY_Z and buy_room > 0:
                quantity = min(ORDER_SIZE, buy_room)
                orders.append(Order(product, best_ask, quantity))
            elif z >= ENTRY_Z and sell_room > 0:
                quantity = min(ORDER_SIZE, sell_room)
                orders.append(Order(product, best_bid, -quantity))

            result[product] = orders

        return result

    def _load(self, trader_data: str) -> dict:
        if not trader_data:
            return {}
        try:
            data = json.loads(trader_data)
        except Exception:
            return {}
        if not isinstance(data, dict):
            return {}
        raw = data.get("mop_dish_sum", [])
        if not isinstance(raw, list):
            data["mop_dish_sum"] = []
            return data
        data["mop_dish_sum"] = [float(x) for x in raw[-WINDOW:]]
        return data


def load_prices(day: int):
    path = Path("data/round5") / f"prices_round_5_day_{day}.csv"
    rows = defaultdict(dict)
    with path.open() as f:
        for row in csv.DictReader(f, delimiter=";"):
            product = row["product"]
            if product not in TRADES:
                continue
            rows[int(row["timestamp"])][product] = {
                "mid": float(row["mid_price"]),
                "bid": int(row["bid_price_1"]) if row["bid_price_1"].strip() else None,
                "ask": int(row["ask_price_1"]) if row["ask_price_1"].strip() else None,
            }
    return rows


def backtest(day_rows, window, warmup, entry_z, exit_z, order_size):
    history = []
    rolling_sum = 0.0
    rolling_sq_sum = 0.0
    pos = {MOPPING: 0, DISHES: 0}
    cash = 0.0
    trades = 0

    for ts in sorted(day_rows):
        row = day_rows[ts]
        if MOPPING not in row or DISHES not in row:
            continue

        pair_sum = row[MOPPING]["mid"] + row[DISHES]["mid"]
        history.append(pair_sum)
        rolling_sum += pair_sum
        rolling_sq_sum += pair_sum * pair_sum
        if len(history) > window:
            old = history.pop(0)
            rolling_sum -= old
            rolling_sq_sum -= old * old
        if len(history) < warmup:
            continue

        count = len(history)
        mean = rolling_sum / count
        variance = max(0.0, (rolling_sq_sum - rolling_sum * rolling_sum / count) / max(1, count - 1))
        stdev = math.sqrt(variance)
        if stdev < 1:
            continue
        z = (pair_sum - mean) / stdev

        for product in TRADES:
            quote = row[product]
            position = pos[product]
            if abs(z) <= exit_z:
                if position > 0 and quote["bid"] is not None:
                    qty = min(order_size, position)
                    cash += qty * quote["bid"]
                    pos[product] -= qty
                    trades += 1
                elif position < 0 and quote["ask"] is not None:
                    qty = min(order_size, -position)
                    cash -= qty * quote["ask"]
                    pos[product] += qty
                    trades += 1

        if z <= -entry_z:
            for product in TRADES:
                quote = row[product]
                room = LIMIT - pos[product]
                if room > 0 and quote["ask"] is not None:
                    qty = min(order_size, room)
                    cash -= qty * quote["ask"]
                    pos[product] += qty
                    trades += 1
        elif z >= entry_z:
            for product in TRADES:
                quote = row[product]
                room = LIMIT + pos[product]
                if room > 0 and quote["bid"] is not None:
                    qty = min(order_size, room)
                    cash += qty * quote["bid"]
                    pos[product] -= qty
                    trades += 1

    for ts in sorted(day_rows, reverse=True):
        row = day_rows[ts]
        if MOPPING in row and DISHES in row:
            cash += pos[MOPPING] * row[MOPPING]["mid"]
            cash += pos[DISHES] * row[DISHES]["mid"]
            break

    return cash, trades


def describe(day_rows):
    mops = []
    dishes = []
    for ts in sorted(day_rows):
        row = day_rows[ts]
        if MOPPING in row and DISHES in row:
            mops.append(row[MOPPING]["mid"])
            dishes.append(row[DISHES]["mid"])
    sums = [a + b for a, b in zip(mops, dishes)]
    ret_m = [mops[i] - mops[i - 1] for i in range(1, len(mops))]
    ret_d = [dishes[i] - dishes[i - 1] for i in range(1, len(dishes))]
    corr = statistics.correlation(mops, dishes) if len(mops) > 1 else 0.0
    ret_corr = statistics.correlation(ret_m, ret_d) if len(ret_m) > 1 else 0.0
    return statistics.mean(sums), statistics.pstdev(sums), corr, ret_corr


def main():
    days = [2, 3, 4]
    day_data = {day: load_prices(day) for day in days}
    for day in days:
        mean_sum, sd_sum, corr, ret_corr = describe(day_data[day])
        print(
            f"day {day}: sum_mean={mean_sum:.1f} sum_sd={sd_sum:.1f} "
            f"level_corr={corr:.3f} ret_corr={ret_corr:.3f}"
        )

    windows = [1000, 2000, 3000, 5000]
    entries = [1.5, 1.75, 2.0, 2.25, 2.5]
    exits = [0.25, 0.35, 0.5, 0.75]
    sizes = [2, 5, 10]
    results = []
    for window in windows:
        warmup = min(500, max(100, window // 10))
        for entry_z in entries:
            for exit_z in exits:
                if exit_z >= entry_z:
                    continue
                for size in sizes:
                    pnls = []
                    trade_counts = []
                    for day in days:
                        pnl, trades = backtest(day_data[day], window, warmup, entry_z, exit_z, size)
                        pnls.append(pnl)
                        trade_counts.append(trades)
                    results.append((sum(pnls), min(pnls), window, warmup, entry_z, exit_z, size, pnls, trade_counts))

    results.sort(reverse=True)
    print("\nTop configs:")
    for total, worst, window, warmup, entry_z, exit_z, size, pnls, trade_counts in results[:15]:
        print(
            f"total={total:9.0f} worst={worst:8.0f} window={window:4d} warmup={warmup:3d} "
            f"entry={entry_z:.2f} exit={exit_z:.2f} size={size:2d} "
            f"D2={pnls[0]:8.0f} D3={pnls[1]:8.0f} D4={pnls[2]:8.0f} "
            f"trades={sum(trade_counts):4d}"
        )

    robust = sorted(results, key=lambda x: (x[1], x[0]), reverse=True)
    print("\nBest worst-day configs:")
    for total, worst, window, warmup, entry_z, exit_z, size, pnls, trade_counts in robust[:10]:
        print(
            f"total={total:9.0f} worst={worst:8.0f} window={window:4d} warmup={warmup:3d} "
            f"entry={entry_z:.2f} exit={exit_z:.2f} size={size:2d} "
            f"D2={pnls[0]:8.0f} D3={pnls[1]:8.0f} D4={pnls[2]:8.0f} "
            f"trades={sum(trade_counts):4d}"
        )

    if len(sys.argv) > 1 and sys.argv[1] == "--fixed":
        pnls = [backtest(day_data[day], WINDOW, WARMUP, ENTRY_Z, EXIT_Z, ORDER_SIZE)[0] for day in days]
        print(f"\nFixed Trader constants: D2={pnls[0]:.0f} D3={pnls[1]:.0f} D4={pnls[2]:.0f} total={sum(pnls):.0f}")


if __name__ == "__main__":
    main()
