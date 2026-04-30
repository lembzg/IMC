from datamodel import TradingState, Order
import json
from collections import defaultdict

POS_LIM = 200

FAIR = 10000
THRESH = 10   # test 20, 30, 40

NORMAL_MAIN_QTY = 6
NORMAL_SMALL_QTY = 2

DIRECTIONAL_QTY = 10


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
            mid = (best_bid + best_ask) / 2

            pos = state.position.get(product, 0)

            buy_room = POS_LIM - pos
            sell_room = POS_LIM + pos

            orders = []

            # -----------------------------
            # 1. CHEAP ZONE: bias long
            # -----------------------------
            if mid < FAIR - THRESH:
                buy_qty = min(DIRECTIONAL_QTY, buy_room)

                if buy_qty > 0:
                    orders.append(Order(product, buy_price, buy_qty))

            # -----------------------------
            # 2. EXPENSIVE ZONE: bias short
            # -----------------------------
            elif mid > FAIR + THRESH:
                sell_qty = min(DIRECTIONAL_QTY, sell_room)

                if sell_qty > 0:
                    orders.append(Order(product, sell_price, -sell_qty))

            # -----------------------------
            # 3. NORMAL ZONE: your 20k MM edge
            # -----------------------------
            else:
                if pos > 0:
                    sell_qty = min(NORMAL_MAIN_QTY, sell_room)
                    buy_qty = min(NORMAL_SMALL_QTY, buy_room)

                    if sell_qty > 0:
                        orders.append(Order(product, sell_price, -sell_qty))
                    if buy_qty > 0:
                        orders.append(Order(product, buy_price, buy_qty))

                elif pos < 0:
                    buy_qty = min(NORMAL_MAIN_QTY, buy_room)
                    sell_qty = min(NORMAL_SMALL_QTY, sell_room)

                    if buy_qty > 0:
                        orders.append(Order(product, buy_price, buy_qty))
                    if sell_qty > 0:
                        orders.append(Order(product, sell_price, -sell_qty))

                else:
                    buy_qty = min(NORMAL_MAIN_QTY, buy_room)
                    sell_qty = min(NORMAL_MAIN_QTY, sell_room)

                    if buy_qty > 0:
                        orders.append(Order(product, buy_price, buy_qty))
                    if sell_qty > 0:
                        orders.append(Order(product, sell_price, -sell_qty))

            result[product] = orders

        trader_data = ""
        logger.flush(state, result, 0, trader_data)
        return result, 0, trader_data