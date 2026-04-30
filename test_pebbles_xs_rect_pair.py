from datamodel import Order, TradingState
from typing import Dict, List
import json


PEBBLES_XS = "PEBBLES_XS"
RECTANGLE = "MICROCHIP_RECTANGLE"
TRADES = (PEBBLES_XS, RECTANGLE)
LIMIT = 10

WINDOW = 1000
WARMUP = 200
ENTRY_Z = 1.75
EXIT_Z = 0.05
ORDER_SIZE = 3
HISTORY_KEY = "xs_rect_spread"


class Trader:
    def bid(self, state=None) -> int:
        return 0

    def run(self, state: TradingState):
        history = self._load_history(state.traderData)
        result = self._trade_spread(state, history)
        trader_data = json.dumps({HISTORY_KEY: history[-WINDOW:]}, separators=(",", ":"))
        return result, 0, trader_data

    def _trade_spread(self, state: TradingState, history: List[float]) -> Dict[str, List[Order]]:
        depths = {}
        mids = {}
        for product in TRADES:
            order_depth = state.order_depths.get(product)
            if order_depth is None or not order_depth.buy_orders or not order_depth.sell_orders:
                return {p: [] for p in TRADES}
            best_bid = max(order_depth.buy_orders)
            best_ask = min(order_depth.sell_orders)
            depths[product] = (best_bid, best_ask)
            mids[product] = (best_bid + best_ask) / 2.0

        spread = mids[PEBBLES_XS] - mids[RECTANGLE]
        history.append(spread)
        if len(history) > WINDOW:
            del history[:-WINDOW]

        if len(history) < WARMUP:
            return {p: [] for p in TRADES}

        mean = sum(history) / len(history)
        variance = sum((value - mean) ** 2 for value in history) / max(1, len(history) - 1)
        stdev = variance ** 0.5
        if stdev < 1:
            return {p: [] for p in TRADES}

        z = (spread - mean) / stdev
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

            if z >= ENTRY_Z:
                if product == PEBBLES_XS and sell_room > 0:
                    orders.append(Order(product, best_bid, -min(ORDER_SIZE, sell_room)))
                elif product == RECTANGLE and buy_room > 0:
                    orders.append(Order(product, best_ask, min(ORDER_SIZE, buy_room)))
            elif z <= -ENTRY_Z:
                if product == PEBBLES_XS and buy_room > 0:
                    orders.append(Order(product, best_ask, min(ORDER_SIZE, buy_room)))
                elif product == RECTANGLE and sell_room > 0:
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
