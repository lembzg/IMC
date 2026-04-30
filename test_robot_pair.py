from datamodel import Order, TradingState
from typing import Dict, List

LAUNDRY = "ROBOT_LAUNDRY"
DISHES  = "ROBOT_DISHES"
TRADES  = (LAUNDRY, DISHES)
LIMIT   = 10
PAIR_FAIR  = 19600
PAIR_ENTRY = 150
PAIR_EXIT  = 75


class Trader:
    def bid(self, state=None) -> int:
        return 0

    def run(self, state: TradingState):
        depths = {}
        mids   = {}
        for product in TRADES:
            od = state.order_depths.get(product)
            if od is None or not od.buy_orders or not od.sell_orders:
                return {p: [] for p in TRADES}, 0, ""
            best_bid = max(od.buy_orders)
            best_ask = min(od.sell_orders)
            depths[product] = (best_bid, best_ask)
            mids[product]   = (best_bid + best_ask) / 2.0

        pair_sum = mids[LAUNDRY] + mids[DISHES]
        result: Dict[str, List[Order]] = {}

        for product in TRADES:
            best_bid, best_ask = depths[product]
            position  = state.position.get(product, 0)
            buy_room  = LIMIT - position
            sell_room = LIMIT + position
            orders: List[Order] = []

            if position > 0 and PAIR_FAIR - PAIR_EXIT <= pair_sum <= PAIR_FAIR + PAIR_EXIT and sell_room > 0:
                orders.append(Order(product, best_bid, -min(sell_room, position)))
            elif position < 0 and PAIR_FAIR - PAIR_EXIT <= pair_sum <= PAIR_FAIR + PAIR_EXIT and buy_room > 0:
                orders.append(Order(product, best_ask, min(buy_room, -position)))

            if pair_sum <= PAIR_FAIR - PAIR_ENTRY and buy_room > 0:
                orders.append(Order(product, best_ask, buy_room))
            elif pair_sum >= PAIR_FAIR + PAIR_ENTRY and sell_room > 0:
                orders.append(Order(product, best_bid, -sell_room))

            result[product] = orders

        return result, 0, ""
