from datamodel import TradingState, Order
from typing import List, Dict, Tuple
import json


PRODUCT = "VELVETFRUIT_EXTRACT"

VELVET_POS_LIM = 200
VELVET_STEP_SIZE = 20
VELVET_MAX_SPREAD = 8

VELVET_BUY_TIERS = [
    (5225, 100),
    (5230, 80),
    (5235, 60),
    (5245, 40),
]

VELVET_SELL_TIERS = [
    (5270, 100),
    (5265, 80),
    (5260, 60),
    (5255, 40),
]

VELVET_MAKER_SIZE = 12
VELVET_MAKER_MAX_POS = 20


class Logger:
    def __init__(self):
        self.logs = ""

    def print(self, *objects, sep=" ", end="\n"):
        self.logs += sep.join(map(str, objects)) + end

    def flush(self, state: TradingState, orders: dict, conversions: int, trader_data: str):
        print(json.dumps([
            [
                state.timestamp,
                state.traderData,
                [[l.symbol, l.product, l.denomination] for l in state.listings.values()],
                {s: [od.buy_orders, od.sell_orders] for s, od in state.order_depths.items()},
                [[t.symbol, t.price, t.quantity, t.buyer, t.seller, t.timestamp] for trades in state.own_trades.values() for t in trades],
                [[t.symbol, t.price, t.quantity, t.buyer, t.seller, t.timestamp] for trades in state.market_trades.values() for t in trades],
                dict(state.position),
                [state.observations.plainValueObservations, {
                    p: [o.bidPrice, o.askPrice, o.transportFees, o.exportTariff, o.importTariff, o.sugarPrice, o.sunlightIndex]
                    for p, o in state.observations.conversionObservations.items()
                }],
            ],
            [[o.symbol, o.price, o.quantity] for arr in orders.values() for o in arr],
            conversions,
            trader_data,
            self.logs,
        ], separators=(",", ":")))
        self.logs = ""


logger = Logger()


class Trader:
    def run(self, state: TradingState) -> Tuple[Dict[str, List[Order]], int, str]:
        result: Dict[str, List[Order]] = {}
        conversions = 0

        orders = self.velvet_strategy(state)

        if orders:
            result[PRODUCT] = orders

        trader_data = state.traderData if state.traderData else "{}"

        logger.flush(state, result, conversions, trader_data)
        return result, conversions, trader_data

    def velvet_strategy(self, state: TradingState) -> List[Order]:
        od = state.order_depths.get(PRODUCT)

        if od is None or not od.buy_orders or not od.sell_orders:
            return []

        best_bid = max(od.buy_orders)
        best_ask = min(od.sell_orders)
        spread = best_ask - best_bid

        if spread <= 0 or spread > VELVET_MAX_SPREAD:
            return []

        mid = (best_bid + best_ask) / 2
        pos = state.position.get(PRODUCT, 0)

        buy_room = VELVET_POS_LIM - pos
        sell_room = VELVET_POS_LIM + pos

        orders: List[Order] = []

        if mid < 5190 and pos > 0:
            return [Order(PRODUCT, best_bid, -pos)]

        if mid > 5290 and pos < 0:
            return [Order(PRODUCT, best_ask, -pos)]

        # Macro buy tiers
        for threshold, target in VELVET_BUY_TIERS:
            if mid < threshold:
                qty = min(VELVET_STEP_SIZE, target - pos, buy_room, -od.sell_orders[best_ask])
                if qty > 0:
                    orders.append(Order(PRODUCT, best_ask, qty))
                    buy_room -= qty
                break

        # Macro sell tiers
        for threshold, target in VELVET_SELL_TIERS:
            if mid > threshold:
                qty = min(VELVET_STEP_SIZE, pos + target, sell_room, od.buy_orders[best_bid])
                if qty > 0:
                    orders.append(Order(PRODUCT, best_bid, -qty))
                    sell_room -= qty
                break

        # Passive maker runs alongside macro, but only when near flat
        if abs(pos) <= VELVET_MAKER_MAX_POS:
            quote_bid = best_bid + 1
            quote_ask = best_ask - 1

            if quote_bid < quote_ask:
                if buy_room > 0:
                    qty = min(VELVET_MAKER_SIZE, buy_room)
                    if qty > 0:
                        orders.append(Order(PRODUCT, quote_bid, qty))

                if sell_room > 0:
                    qty = min(VELVET_MAKER_SIZE, sell_room)
                    if qty > 0:
                        orders.append(Order(PRODUCT, quote_ask, -qty))

        return orders