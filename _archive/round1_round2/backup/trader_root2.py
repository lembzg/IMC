from datamodel import TradingState, Order
from typing import List, Tuple, Dict
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
                [[t.symbol, t.price, t.quantity, t.buyer, t.seller, t.timestamp]
                 for trades in state.own_trades.values() for t in trades],
                [[t.symbol, t.price, t.quantity, t.buyer, t.seller, t.timestamp]
                 for trades in state.market_trades.values() for t in trades],
                dict(state.position),
                [state.observations.plainValueObservations, {
                    p: [o.bidPrice, o.askPrice, o.transportFees, o.exportTariff,
                        o.importTariff, o.sugarPrice, o.sunlightIndex]
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
        result = defaultdict(list)
        conversions = 0
        root_data = {}

        result["ASH_COATED_OSMIUM"], ash_data = self.ash(state)

        traderData = json.dumps({
            "ash_data": ash_data,
            "root_data": root_data
        })

        logger.flush(state, dict(result), conversions, traderData)
        return dict(result), conversions, traderData

    def ash(self, state: TradingState):
        result = []
        symbol = "ASH_COATED_OSMIUM"

        sma_window = 5
        pos_limit = 80
        quote_lim = 10

        ash_data = {"bid_hist": [], "ask_hist": []}

        if state.traderData:
            try:
                parsed_data = json.loads(state.traderData)
                if "ash_data" in parsed_data:
                    ash_data = parsed_data["ash_data"]
            except json.JSONDecodeError:
                pass

        if symbol not in state.order_depths:
            return result, ash_data

        order_depth = state.order_depths[symbol]

        # Current best prices if they exist
        curr_best_bid = max(order_depth.buy_orders.keys()) if order_depth.buy_orders else None
        curr_best_ask = min(order_depth.sell_orders.keys()) if order_depth.sell_orders else None

        # Forward fill missing values using history
        best_bid_ffill = curr_best_bid if curr_best_bid is not None else (
            ash_data["bid_hist"][-1] if ash_data["bid_hist"] else None
        )
        best_ask_ffill = curr_best_ask if curr_best_ask is not None else (
            ash_data["ask_hist"][-1] if ash_data["ask_hist"] else None
        )

        # Update rolling history
        if best_bid_ffill is not None:
            ash_data["bid_hist"].append(best_bid_ffill)
        if best_ask_ffill is not None:
            ash_data["ask_hist"].append(best_ask_ffill)

        if len(ash_data["bid_hist"]) > sma_window:
            ash_data["bid_hist"].pop(0)
        if len(ash_data["ask_hist"]) > sma_window:
            ash_data["ask_hist"].pop(0)

        # Warm-up
        if len(ash_data["bid_hist"]) < sma_window or len(ash_data["ask_hist"]) < sma_window:
            return result, ash_data

        # Fair value from rolling SMA
        bid_sma = sum(ash_data["bid_hist"]) / sma_window
        ask_sma = sum(ash_data["ask_hist"]) / sma_window
        fair_value = (bid_sma + ask_sma) / 2.0

        bids = sorted(order_depth.buy_orders.keys(), reverse=True)
        asks = sorted(order_depth.sell_orders.keys())

        best_bid = bids[0] if bids else round(bid_sma)
        best_ask = asks[0] if asks else round(ask_sma)

        pos = state.position.get(symbol, 0)
        buy_capacity = pos_limit - pos
        sell_capacity = pos_limit + pos

        # ACTIVE TAKING FIRST
        for ask_px in asks:
            if ask_px <= fair_value and buy_capacity > 0 and pos <= 40:
                vol = min(buy_capacity, abs(order_depth.sell_orders[ask_px]))
                if vol > 0:
                    result.append(Order(symbol, ask_px, vol))
                    pos += vol
                    buy_capacity = pos_limit - pos
                    sell_capacity = pos_limit + pos

        for bid_px in bids:
            if bid_px >= fair_value and sell_capacity > 0 and pos >= -40:
                vol = min(sell_capacity, order_depth.buy_orders[bid_px])
                if vol > 0:
                    result.append(Order(symbol, bid_px, -vol))
                    pos -= vol
                    buy_capacity = pos_limit - pos
                    sell_capacity = pos_limit + pos

        # PASSIVE MAKING SECOND
        if best_bid is not None and best_ask is not None:
            spread = best_ask - best_bid

            if spread >= 3:
                passive_bid = best_bid + 1
                passive_ask = best_ask - 1

                if buy_capacity > 0 and passive_bid < fair_value:
                    result.append(Order(symbol, passive_bid, min(quote_lim, buy_capacity)))

                if sell_capacity > 0 and passive_ask > fair_value:
                    result.append(Order(symbol, passive_ask, -min(quote_lim, sell_capacity)))
        return result, ash_data