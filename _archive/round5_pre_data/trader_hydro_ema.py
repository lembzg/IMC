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

        result['HYDROGEL_PACK'], hydro_data = self.hydro(state, shared)
        #result['VELVETFRUIT_EXTRACT'], vev_data = self.vev(state, shared)

        traderData = json.dumps({**hydro_data})
        logger.flush(state, result, conversions, traderData)
        return result, conversions, traderData


    
    def hydro(self, state: TradingState, shared: dict):
        product = "HYDROGEL_PACK"
        result = []
        pos_lim = 200

        if product not in state.order_depths:
            return result, shared

        order_depth = state.order_depths[product]
        bids = sorted(order_depth.buy_orders.keys(), reverse=True)
        asks = sorted(order_depth.sell_orders.keys())

        if not bids or not asks:
            return result, shared

        best_bid = bids[0]
        best_ask = asks[0]
        mid = (best_bid + best_ask) / 2
        pos = state.position.get(product, 0)
        buy_room = pos_lim - pos
        sell_room = pos_lim + pos

        # EMA fair value — alpha=0.2 per analyze.py winning params
        alpha = 0.2
        prev_ema = shared.get("hydro_ema", mid)
        ema = alpha * mid + (1 - alpha) * prev_ema
        shared["hydro_ema"] = ema

        EDGE = 0.5
        SIZE = 10  # match benchmark exactly first, then scale

        # Buy when ask is below EMA by edge
        if best_ask <= ema - EDGE and buy_room > 0:
            ask_qty = -order_depth.sell_orders[best_ask]
            qty = min(ask_qty, buy_room, SIZE)
            result.append(Order(product, best_ask, qty))

        # Sell when bid is above EMA by edge
        if best_bid >= ema + EDGE and sell_room > 0:
            bid_qty = order_depth.buy_orders[best_bid]
            qty = min(bid_qty, sell_room, SIZE)
            result.append(Order(product, best_bid, -qty))

        return result, shared