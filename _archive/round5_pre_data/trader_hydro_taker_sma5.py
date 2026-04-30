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

        traderData = json.dumps({**hydro_data})
        logger.flush(state, result, conversions, traderData)
        return result, conversions, traderData

    def hydro(self, state: TradingState, shared: dict):
        product = 'HYDROGEL_PACK'
        result = []
        pos_lim = 200
        quote_lim = 10
        sma_window = 5

        bid_hist = shared.get("bid_hist", [])
        ask_hist = shared.get("ask_hist", [])

        if product not in state.order_depths:
            return result, {"bid_hist": bid_hist, "ask_hist": ask_hist}

        order_depth = state.order_depths[product]
        bids = sorted(order_depth.buy_orders, reverse=True)
        asks = sorted(order_depth.sell_orders)

        curr_best_bid = bids[0] if len(bids) >= 1 else None
        curr_best_ask = asks[0] if len(asks) >= 1 else None

        # Forward fill from history
        best_bid = curr_best_bid if curr_best_bid is not None else (bid_hist[-1] if bid_hist else None)
        best_ask = curr_best_ask if curr_best_ask is not None else (ask_hist[-1] if ask_hist else None)

        if best_bid is not None:
            bid_hist.append(best_bid)
        if best_ask is not None:
            ask_hist.append(best_ask)
        if len(bid_hist) > sma_window:
            bid_hist.pop(0)
        if len(ask_hist) > sma_window:
            ask_hist.pop(0)

        if len(bid_hist) < sma_window or len(ask_hist) < sma_window:
            return result, {"bid_hist": bid_hist, "ask_hist": ask_hist}

        bid_sma = sum(bid_hist) / sma_window
        ask_sma = sum(ask_hist) / sma_window
        fair_value = (bid_sma + ask_sma) / 2.0

        pos = state.position.get(product, 0)
        buy_qty = min(quote_lim, pos_lim - pos)
        sell_qty = min(quote_lim, pos_lim + pos)

        # Refresh to current best (post-history update)
        best_bid = curr_best_bid if curr_best_bid is not None else (bid_hist[-1] if bid_hist else None)
        best_ask = curr_best_ask if curr_best_ask is not None else (ask_hist[-1] if ask_hist else None)

        # Active taking — relax threshold by 1 tick when position beyond ±40 to flatten
        buy_threshold = fair_value + (1 if pos < -40 else 0)
        sell_threshold = fair_value - (1 if pos > 40 else 0)

        for ask_px in asks:
            if ask_px <= buy_threshold and buy_qty != 0 and pos <= 100:
                result.append(Order(product, ask_px, buy_qty))
                buy_qty = 0
                break

        for bid_px in bids:
            if bid_px >= sell_threshold and sell_qty != 0 and pos >= -100:
                result.append(Order(product, bid_px, -sell_qty))
                sell_qty = 0
                break

        # Passive making — penny-jump through book to best level within FV
        passive_bid = next((p for p in bids if p + 1 <= fair_value), None)
        if passive_bid is None and best_bid is not None and best_bid + 1 <= fair_value:
            passive_bid = best_bid

        passive_ask = next((p for p in asks if p - 1 >= fair_value), None)
        if passive_ask is None and best_ask is not None and best_ask - 1 >= fair_value:
            passive_ask = best_ask

        if passive_bid is not None and buy_qty != 0:
            result.append(Order(product, passive_bid + 1, buy_qty))
        if passive_ask is not None and sell_qty != 0:
            result.append(Order(product, passive_ask - 1, -sell_qty))

        return result, {"bid_hist": bid_hist, "ask_hist": ask_hist}
