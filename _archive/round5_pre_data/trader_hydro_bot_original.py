from datamodel import TradingState, Order
import json
from collections import defaultdict

POS_LIM = 200

MAIN_QTY = 6
SMALL_QTY = 2

class Logger:
    def __init__(self):
        self.logs = ""

    def print(self, *args, sep=" ", end="\n"):
        self.logs += sep.join(map(str, args)) + end

    def flush(self, state, orders, conversions, trader_data):
        print(json.dumps([
            [
                state.timestamp,
                state.traderData,
                [[l.symbol, l.product, l.denomination] for l in state.listings.values()],
                {s: [od.buy_orders, od.sell_orders] for s, od in state.order_depths.items()},
                [[t.symbol, t.price, t.quantity, t.buyer, t.seller, t.timestamp]
                 for trades in state.own_trades.values() for t in trades],
                [[t.symbol, t.price, t.quantity, t.buyer, t.seller, t.timestamp]
                 for trades in state.market_trades.values() for t in trades],
                dict(state.position),
                [
                    state.observations.plainValueObservations,
                    {
                        p: [
                            o.bidPrice,
                            o.askPrice,
                            o.transportFees,
                            o.exportTariff,
                            o.importTariff,
                            o.sugarPrice,
                            o.sunlightIndex,
                        ]
                        for p, o in state.observations.conversionObservations.items()
                    },
                ],
            ],
            [[o.symbol, o.price, o.quantity] for arr in orders.values() for o in arr],
            conversions,
            trader_data,
            self.logs,
        ], separators=(",", ":")))
        self.logs = ""


logger = Logger()


class Trader:
    def bid(self):
        return 1

    def run(self, state: TradingState):
        result = defaultdict(list)
        product = "HYDROGEL_PACK"

        od = state.order_depths.get(product)
        if od and od.buy_orders and od.sell_orders:
            best_bid = max(od.buy_orders)
            best_ask = min(od.sell_orders)

            buy_price = best_bid + 1
            sell_price = best_ask - 1

            pos = state.position.get(product, 0)
            small_qty=SMALL_QTY
            if abs(pos) > 120:
                small_qty = 0


            buy_room = POS_LIM - pos
            sell_room = POS_LIM + pos

            orders = []

            if pos > 0:
                # Long: mainly sell, but still leave a small buy quote
                sell_qty = min(MAIN_QTY, sell_room)
                buy_qty = min(small_qty, buy_room)

                if sell_qty > 0:
                    orders.append(Order(product, sell_price, -sell_qty))
                if buy_qty > 0:
                    orders.append(Order(product, buy_price, buy_qty))

            elif pos < 0:
                # Short: mainly buy, but still leave a small sell quote
                buy_qty = min(MAIN_QTY, buy_room)
                sell_qty = min(small_qty, sell_room)

                if buy_qty > 0:
                    orders.append(Order(product, buy_price, buy_qty))
                if sell_qty > 0:
                    orders.append(Order(product, sell_price, -sell_qty))

            else:
                # Flat: quote both sides equally
                buy_qty = min(MAIN_QTY, buy_room)
                sell_qty = min(MAIN_QTY, sell_room)

                if buy_qty > 0:
                    orders.append(Order(product, buy_price, buy_qty))
                if sell_qty > 0:
                    orders.append(Order(product, sell_price, -sell_qty))

            result[product] = orders

        trader_data = ""
        logger.flush(state, result, 0, trader_data)
        return result, 0, trader_data