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

        #result['HYDROGEL_PACK'], hydro_data = self.hydro(state, shared)
        result['VELVETFRUIT_EXTRACT'], vev_data = self.vev(state, shared)

        traderData = json.dumps({**vev_data})
        logger.flush(state, result, conversions, traderData)
        return result, conversions, traderData

    def vev(self, state: TradingState, shared: dict):
        product = 'VELVETFRUIT_EXTRACT'
        result = []
        pos_lim = 200
        quote_size = 30
        alpha = 0.05
        take_edge = 3

        if product not in state.order_depths:
            return result, shared.get('vev_state', {})

        order_depth = state.order_depths[product]
        bids = sorted(order_depth.buy_orders, reverse=True)
        asks = sorted(order_depth.sell_orders)

        if not bids or not asks:
            return result, shared.get('vev_state', {})

        best_bid = bids[0]
        best_ask = asks[0]
        mid = (best_bid + best_ask) / 2.0

        # EMA fair value
        ema = shared.get('vev_ema', mid)
        ema = alpha * mid + (1 - alpha) * ema

        pos = state.position.get(product, 0)
        buy_room = pos_lim - pos
        sell_room = pos_lim + pos

        # Take when price deviates from EMA by more than take_edge
        for ask_px in asks:
            if ask_px <= ema - take_edge and buy_room > 0:
                qty = min(abs(order_depth.sell_orders[ask_px]), buy_room)
                if qty > 0:
                    result.append(Order(product, ask_px, qty))
                    buy_room -= qty
            else:
                break

        for bid_px in bids:
            if bid_px >= ema + take_edge and sell_room > 0:
                qty = min(order_depth.buy_orders[bid_px], sell_room)
                if qty > 0:
                    result.append(Order(product, bid_px, -qty))
                    sell_room -= qty
            else:
                break

        # Passive making
        spread = best_ask - best_bid
        passive_bid = best_bid + 1 if spread >= 3 else best_bid
        passive_ask = best_ask - 1 if spread >= 3 else best_ask

        if buy_room > 0 and passive_bid < ema:
            result.append(Order(product, passive_bid, min(quote_size, buy_room)))
        if sell_room > 0 and passive_ask > ema:
            result.append(Order(product, passive_ask, -min(quote_size, sell_room)))

        return result, {'vev_ema': ema}