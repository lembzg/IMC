from datamodel import Order, TradingState
from typing import Dict, List
import json


TARGET = "PANEL_1X2"
SIGNAL = "PANEL_1X4"
PRODUCTS = (TARGET, SIGNAL)
LIMIT = 10

WINDOW = 3000
WARMUP = 500
ENTRY_Z = 1.5
EXIT_Z = 0.1
ORDER_SIZE = 1
HISTORY_KEY = "panel_1x_sum"


class Trader:
    def bid(self, state=None) -> int:
        return 0

    def run(self, state: TradingState):
        history = self._load_history(state.traderData)
        orders = self._trade_panel_sum(state, history)
        trader_data = json.dumps({HISTORY_KEY: history[-WINDOW:]}, separators=(",", ":"))
        return orders, 0, trader_data

    def _trade_panel_sum(self, state: TradingState, history: List[float]) -> Dict[str, List[Order]]:
        depths = {}
        mids = {}
        for product in PRODUCTS:
            od = state.order_depths.get(product)
            if od is None or not od.buy_orders or not od.sell_orders:
                return {TARGET: []}
            best_bid = max(od.buy_orders)
            best_ask = min(od.sell_orders)
            depths[product] = (best_bid, best_ask)
            mids[product] = (best_bid + best_ask) / 2.0

        panel_sum = mids[TARGET] + mids[SIGNAL]
        history.append(panel_sum)
        if len(history) > WINDOW:
            del history[:-WINDOW]

        if len(history) < WARMUP:
            return {TARGET: []}

        mean = sum(history) / len(history)
        variance = sum((value - mean) ** 2 for value in history) / max(1, len(history) - 1)
        stdev = variance ** 0.5
        if stdev < 1:
            return {TARGET: []}

        z = (panel_sum - mean) / stdev
        best_bid, best_ask = depths[TARGET]
        position = state.position.get(TARGET, 0)
        buy_room = LIMIT - position
        sell_room = LIMIT + position
        orders: List[Order] = []

        if abs(z) <= EXIT_Z:
            if position > 0 and sell_room > 0:
                qty = min(ORDER_SIZE, sell_room, position)
                orders.append(Order(TARGET, best_bid, -qty))
                sell_room -= qty
            elif position < 0 and buy_room > 0:
                qty = min(ORDER_SIZE, buy_room, -position)
                orders.append(Order(TARGET, best_ask, qty))
                buy_room -= qty

        if z <= -ENTRY_Z and buy_room > 0:
            orders.append(Order(TARGET, best_ask, min(ORDER_SIZE, buy_room)))
        elif z >= ENTRY_Z and sell_room > 0:
            orders.append(Order(TARGET, best_bid, -min(ORDER_SIZE, sell_room)))

        return {TARGET: orders}

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
