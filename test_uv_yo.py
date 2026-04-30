from datamodel import Order, TradingState
from typing import Dict, List

RED     = "UV_VISOR_YELLOW"
MAGENTA = "UV_VISOR_ORANGE"
TRADES  = (RED, MAGENTA)
LIMIT   = 10
ENTRY   = 700
EXIT    = 150


class Trader:
    def bid(self, state=None) -> int:
        return 0

    def run(self, state: TradingState):
        depths = {}
        mids = {}
        for product in TRADES:
            od = state.order_depths.get(product)
            if od is None or not od.buy_orders or not od.sell_orders:
                return {p: [] for p in TRADES}, 0, ""
            best_bid = max(od.buy_orders)
            best_ask = min(od.sell_orders)
            depths[product] = (best_bid, best_ask)
            mids[product] = (best_bid + best_ask) / 2.0

        pair_mean = (mids[RED] + mids[MAGENTA]) / 2.0
        red_dev = mids[RED] - pair_mean  # positive = red expensive

        result: Dict[str, List[Order]] = {}
        for product in TRADES:
            best_bid, best_ask = depths[product]
            position  = state.position.get(product, 0)
            buy_room  = LIMIT - position
            sell_room = LIMIT + position
            orders: List[Order] = []
            is_red = product == RED

            if position > 0 and abs(red_dev) <= EXIT and sell_room > 0:
                orders.append(Order(product, best_bid, -min(sell_room, position)))
            elif position < 0 and abs(red_dev) <= EXIT and buy_room > 0:
                orders.append(Order(product, best_ask, min(buy_room, -position)))

            if red_dev > ENTRY:
                if is_red and sell_room > 0:
                    orders.append(Order(product, best_bid, -sell_room))
                elif not is_red and buy_room > 0:
                    orders.append(Order(product, best_ask, buy_room))
            elif red_dev < -ENTRY:
                if is_red and buy_room > 0:
                    orders.append(Order(product, best_ask, buy_room))
                elif not is_red and sell_room > 0:
                    orders.append(Order(product, best_bid, -sell_room))

            result[product] = orders
        return result, 0, ""
