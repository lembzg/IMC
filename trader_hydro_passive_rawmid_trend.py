from datamodel import OrderDepth, UserId, TradingState, Order
from typing import List
import json
from collections import defaultdict


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
    def bid(self):
        return 1

    def run(self, state: TradingState):
        result = defaultdict(list)
        conversions = 0
        shared = {}
        if state.traderData:
            try:
                shared = json.loads(state.traderData)
            except json.JSONDecodeError:
                pass

        result["HYDROGEL_PACK"], hydro_data = self.hydro(state, shared)

        traderData = json.dumps(hydro_data)
        logger.flush(state, result, conversions, traderData)
        return result, conversions, traderData

    # HYDROGEL_PACK — passive maker with inventory skew and trend filter
    def hydro(self, state: TradingState, shared: dict):
        product = "HYDROGEL_PACK"
        result = []

        pos_lim = 200
        quote_size = 6
        skew = 0.15
        edge = 0.75
        trend_thresh = 3

        if product not in state.order_depths:
            return result, shared

        order_depth = state.order_depths[product]
        bids = sorted(order_depth.buy_orders.keys(), reverse=True)
        asks = sorted(order_depth.sell_orders.keys())

        if not bids or not asks:
            return result, shared

        best_bid = bids[0]
        best_ask = asks[0]
        spread = best_ask - best_bid
        mid = (best_bid + best_ask) / 2.0
        fair_value = mid

        prev_mid = shared.get("hydro_prev_mid", mid)
        trend = mid - prev_mid
        shared["hydro_prev_mid"] = mid

        pos = state.position.get(product, 0)
        buy_room = pos_lim - pos
        sell_room = pos_lim + pos

        fair_value -= pos * skew

        bid_price = best_bid + 1 if spread >= 3 else best_bid
        ask_price = best_ask - 1 if spread >= 3 else best_ask

        if buy_room > 0 and bid_price <= fair_value - edge:
            if trend > -trend_thresh:
                result.append(Order(product, int(bid_price), min(quote_size, buy_room)))

        if sell_room > 0 and ask_price >= fair_value + edge:
            if trend < trend_thresh:
                result.append(Order(product, int(ask_price), -min(quote_size, sell_room)))

        return result, shared
