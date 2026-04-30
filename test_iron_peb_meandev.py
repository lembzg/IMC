from datamodel import Order, TradingState
from typing import Dict, List

IRONING = "ROBOT_IRONING"
PEBS    = "PEBBLES_S"
TRADES  = (IRONING, PEBS)
LIMIT   = 10
ENTRY   = 200
EXIT    = 50


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

        pair_mean = (mids[IRONING] + mids[PEBS]) / 2.0
        iron_dev = mids[IRONING] - pair_mean  # positive = ironing expensive

        result: Dict[str, List[Order]] = {}
        for product in TRADES:
            best_bid, best_ask = depths[product]
            position  = state.position.get(product, 0)
            buy_room  = LIMIT - position
            sell_room = LIMIT + position
            orders: List[Order] = []
            is_iron = product == IRONING

            if position > 0 and abs(iron_dev) <= EXIT and sell_room > 0:
                orders.append(Order(product, best_bid, -min(sell_room, position)))
            elif position < 0 and abs(iron_dev) <= EXIT and buy_room > 0:
                orders.append(Order(product, best_ask, min(buy_room, -position)))

            if iron_dev > ENTRY:
                if is_iron and sell_room > 0:
                    orders.append(Order(product, best_bid, -sell_room))
                elif not is_iron and buy_room > 0:
                    orders.append(Order(product, best_ask, buy_room))
            elif iron_dev < -ENTRY:
                if is_iron and buy_room > 0:
                    orders.append(Order(product, best_ask, buy_room))
                elif not is_iron and sell_room > 0:
                    orders.append(Order(product, best_bid, -sell_room))

            result[product] = orders
        return result, 0, ""
