from datamodel import Order, TradingState
from typing import Dict, List
import json


MINT = "OXYGEN_SHAKE_MINT"
EVENING = "OXYGEN_SHAKE_EVENING_BREATH"
TRADES = (MINT, EVENING)
LIMIT = 10

WINDOW = 5000
WARMUP = 500
ENTRY_Z = 1.5
EXIT_Z = 0.1
ORDER_SIZE = 10
HISTORY_KEY = "mint_evening_sum"


class Trader:
    def bid(self, state=None) -> int:
        return 0

    def run(self, state: TradingState):
        history = self._load_history(state.traderData)
        result = self._trade_sum_reversion(state, history)
        trader_data = json.dumps({HISTORY_KEY: history[-WINDOW:]}, separators=(",", ":"))
        return result, 0, trader_data

    def _trade_sum_reversion(self, state: TradingState, history: List[float]) -> Dict[str, List[Order]]:
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

        pair_sum = mids[MINT] + mids[EVENING]
        history.append(pair_sum)
        if len(history) > WINDOW:
            del history[:-WINDOW]

        if len(history) < WARMUP:
            return {p: [] for p in TRADES}

        mean = sum(history) / len(history)
        variance = sum((value - mean) ** 2 for value in history) / max(1, len(history) - 1)
        stdev = variance ** 0.5
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
                    qty = min(ORDER_SIZE, sell_room, position)
                    orders.append(Order(product, best_bid, -qty))
                    sell_room -= qty
                elif position < 0 and buy_room > 0:
                    qty = min(ORDER_SIZE, buy_room, -position)
                    orders.append(Order(product, best_ask, qty))
                    buy_room -= qty

            if z <= -ENTRY_Z and buy_room > 0:
                orders.append(Order(product, best_ask, min(ORDER_SIZE, buy_room)))
            elif z >= ENTRY_Z and sell_room > 0:
                orders.append(Order(product, best_bid, -min(ORDER_SIZE, sell_room)))

            result[product] = orders

        return result

    def _load_history(self, trader_data: str) -> List[float]:
        if not trader_data:
            return []
        try:
            decoded = json.loads(trader_data)
        except Exception:
            return []
        values = decoded.get(HISTORY_KEY, []) if isinstance(decoded, dict) else []
        if not isinstance(values, list):
            return []
        return [float(value) for value in values[-WINDOW:]]
