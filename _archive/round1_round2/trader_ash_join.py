from datamodel import Order, TradingState
from collections import defaultdict
import json


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
    def run(self, state: TradingState):
        result = defaultdict(list)
        shared = {}
        if state.traderData:
            try:
                shared = json.loads(state.traderData)
            except json.JSONDecodeError:
                pass
        result["ASH_COATED_OSMIUM"], ash_data = self.ash(state, shared)
        result["INTARIAN_PEPPER_ROOT"], root_data = self.root(state, shared)
        trader_data = json.dumps({**ash_data, **root_data})
        logger.flush(state, result, 0, trader_data)
        return result, 0, trader_data

    def root(self, state: TradingState, shared: dict):
        product = "INTARIAN_PEPPER_ROOT"
        result = []
        pos = state.position.get(product, 0)
        pos_lim = 80
        first_ask = shared.get("first_ask")
        if product not in state.order_depths or not state.order_depths[product].sell_orders:
            return result, {"first_ask": first_ask}
        od = state.order_depths[product]
        best_ask = min(od.sell_orders)
        if first_ask is None:
            first_ask = best_ask
        if pos < 76 and (best_ask <= first_ask + 2 or state.timestamp >= 2000):
            qty = min(76 - pos, abs(od.sell_orders[best_ask]))
            if qty > 0:
                result.append(Order(product, best_ask, qty))
        elif pos < pos_lim and od.buy_orders:
            result.append(Order(product, max(od.buy_orders) + 1, pos_lim - pos))
        return result, {"first_ask": first_ask}

    def ash(self, state: TradingState, shared: dict):
        product = "ASH_COATED_OSMIUM"
        result = []
        pos_lim = 80
        quote_lim = 20
        sma_window = 5

        bid_hist = shared.get("bid_hist", [])
        ask_hist = shared.get("ask_hist", [])
        if product not in state.order_depths:
            return result, {"bid_hist": bid_hist, "ask_hist": ask_hist}
        od = state.order_depths[product]
        bids = sorted(od.buy_orders, reverse=True)
        asks = sorted(od.sell_orders)
        curr_best_bid = bids[0] if bids else None
        curr_best_ask = asks[0] if asks else None
        best_bid = curr_best_bid if curr_best_bid is not None else (bid_hist[-1] if bid_hist else None)
        best_ask = curr_best_ask if curr_best_ask is not None else (ask_hist[-1] if ask_hist else None)
        if best_bid is not None:
            bid_hist.append(best_bid)
        if best_ask is not None:
            ask_hist.append(best_ask)
        bid_hist = bid_hist[-sma_window:]
        ask_hist = ask_hist[-sma_window:]
        if len(bid_hist) < sma_window or len(ask_hist) < sma_window:
            return result, {"bid_hist": bid_hist, "ask_hist": ask_hist}

        fair_value = (sum(bid_hist) / sma_window + sum(ask_hist) / sma_window) / 2.0
        pos = state.position.get(product, 0)
        buy_qty = min(quote_lim, pos_lim - pos)
        sell_qty = min(quote_lim, pos_lim + pos)

        buy_threshold = fair_value + (1 if pos < -15 else 0)
        sell_threshold = fair_value - (1 if pos > 15 else 0)
        for ask_px in asks:
            if ask_px <= buy_threshold and buy_qty > 0 and pos <= 40:
                result.append(Order(product, ask_px, buy_qty))
                buy_qty = 0
                break
        for bid_px in bids:
            if bid_px >= sell_threshold and sell_qty > 0 and pos >= -40:
                result.append(Order(product, bid_px, -sell_qty))
                sell_qty = 0
                break

        # Join the public bot's bid/ask prints instead of pennying inside.
        passive_bid = next((p for p in bids if p <= fair_value), None)
        passive_ask = next((p for p in asks if p >= fair_value), None)
        if passive_bid is not None and buy_qty > 0:
            result.append(Order(product, passive_bid, buy_qty))
        if passive_ask is not None and sell_qty > 0:
            result.append(Order(product, passive_ask, -sell_qty))
        return result, {"bid_hist": bid_hist, "ask_hist": ask_hist}
