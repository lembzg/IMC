from datamodel import Order, TradingState
from typing import Dict, List

CIRCLE   = "MICROCHIP_CIRCLE"
TRIANGLE = "MICROCHIP_TRIANGLE"
LIMIT    = 10
ENTRY    = 75
EXIT     = 25


class Trader:
    def bid(self, state=None) -> int:
        return 0

    def run(self, state: TradingState):
        result: Dict[str, List[Order]] = {}

        c_od = state.order_depths.get(CIRCLE)
        t_od = state.order_depths.get(TRIANGLE)
        if not c_od or not t_od or not c_od.buy_orders or not c_od.sell_orders or not t_od.buy_orders or not t_od.sell_orders:
            return {CIRCLE: [], TRIANGLE: []}, 0, ""

        c_bid = max(c_od.buy_orders)
        c_ask = min(c_od.sell_orders)
        t_bid = max(t_od.buy_orders)
        t_ask = min(t_od.sell_orders)
        c_mid = (c_bid + c_ask) / 2
        t_mid = (t_bid + t_ask) / 2

        pair_mean = (c_mid + t_mid) / 2
        # positive = that product is expensive relative to the other
        c_dev = c_mid - pair_mean

        c_pos = state.position.get(CIRCLE, 0)
        t_pos = state.position.get(TRIANGLE, 0)

        c_orders: List[Order] = []
        t_orders: List[Order] = []

        # Exit: deviation has collapsed back
        if c_pos > 0 and c_dev >= -EXIT:
            c_orders.append(Order(CIRCLE, c_bid, -min(LIMIT + c_pos, c_pos)))
        elif c_pos < 0 and c_dev <= EXIT:
            c_orders.append(Order(CIRCLE, c_ask, min(LIMIT - c_pos, -c_pos)))

        if t_pos > 0 and c_dev <= EXIT:
            t_orders.append(Order(TRIANGLE, t_bid, -min(LIMIT + t_pos, t_pos)))
        elif t_pos < 0 and c_dev >= -EXIT:
            t_orders.append(Order(TRIANGLE, t_ask, min(LIMIT - t_pos, -t_pos)))

        # Entry: circle expensive -> sell circle, buy triangle
        if c_dev > ENTRY:
            sell_room = LIMIT + c_pos
            buy_room  = LIMIT - t_pos
            if sell_room > 0:
                c_orders.append(Order(CIRCLE, c_bid, -sell_room))
            if buy_room > 0:
                t_orders.append(Order(TRIANGLE, t_ask, buy_room))
        # triangle expensive -> buy circle, sell triangle
        elif c_dev < -ENTRY:
            buy_room  = LIMIT - c_pos
            sell_room = LIMIT + t_pos
            if buy_room > 0:
                c_orders.append(Order(CIRCLE, c_ask, buy_room))
            if sell_room > 0:
                t_orders.append(Order(TRIANGLE, t_bid, -sell_room))

        result[CIRCLE]   = c_orders
        result[TRIANGLE] = t_orders
        return result, 0, ""
