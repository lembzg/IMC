from datamodel import OrderDepth, UserId, TradingState, Order
from typing import List, Tuple, Dict
import json
from collections import defaultdict
# import jsonpckle

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
        result = defaultdict(list)
        conversions = 0
        root_data = {}
        # Execute individual product strategies, passing state to each
        result['ASH_COATED_OSMIUM'], ash_data = self.ash(state)
        # result['INTARIAN_PEPPER_ROOT'], root_data = self.root(state)
        
        # Combine the respective data dictionaries into a single payload
        traderData = json.dumps({"ash_data": ash_data, "root_data": root_data})
        
        # Flush logger using the properly constructed traderData
        logger.flush(state, dict(result), conversions, traderData)
        
        return dict(result), conversions, traderData
    
    def ash(self, state: TradingState):
        result = []
        symbol = "ASH_COATED_OSMIUM"
        sma_window = 5
        z_window = 20
        z_threshold = 2.25
        active_lim = 10
        pos_limit = 80
        ask_threshold = 10003

        ash_data = {"bid_hist": [], "ask_hist": [], "mid_hist": []}

        if state.traderData:
            try:
                parsed_data = json.loads(state.traderData)
                if "ash_data" in parsed_data:
                    ash_data = parsed_data["ash_data"]
            except json.JSONDecodeError:
                pass

        if "mid_hist" not in ash_data:
            ash_data["mid_hist"] = []

        if symbol not in state.order_depths:
            return result, ash_data

        order_depth = state.order_depths[symbol]

        # Forward-filled best bid / ask for history
        curr_best_bid = max(order_depth.buy_orders.keys()) if order_depth.buy_orders else None
        curr_best_ask = min(order_depth.sell_orders.keys()) if order_depth.sell_orders else None

        hist_best_bid = curr_best_bid if curr_best_bid is not None else (
            ash_data["bid_hist"][-1] if ash_data["bid_hist"] else None
        )
        hist_best_ask = curr_best_ask if curr_best_ask is not None else (
            ash_data["ask_hist"][-1] if ash_data["ask_hist"] else None
        )

        # Update histories
        if hist_best_bid is not None:
            ash_data["bid_hist"].append(hist_best_bid)
        if hist_best_ask is not None:
            ash_data["ask_hist"].append(hist_best_ask)
        if hist_best_bid is not None and hist_best_ask is not None:
            ash_data["mid_hist"].append((hist_best_bid + hist_best_ask) / 2.0)

        if len(ash_data["bid_hist"]) > sma_window:
            ash_data["bid_hist"].pop(0)
        if len(ash_data["ask_hist"]) > sma_window:
            ash_data["ask_hist"].pop(0)
        if len(ash_data["mid_hist"]) > z_window:
            ash_data["mid_hist"].pop(0)

        # Warm-up for fair value
        if len(ash_data["bid_hist"]) < sma_window or len(ash_data["ask_hist"]) < sma_window:
            return result, ash_data


        # Fair value from SMA
        bid_sma = sum(ash_data["bid_hist"]) / sma_window
        ask_sma = sum(ash_data["ask_hist"]) / sma_window
        sma_fv = (bid_sma + ask_sma) / 2.0
        stable_fv = 9999.0
        fair_value = 0.5 * sma_fv + 0.5 * stable_fv

        # Current visible book
        bids = sorted(order_depth.buy_orders.keys(), reverse=True)
        asks = sorted(order_depth.sell_orders.keys())

        best_bid = bids[0] if bids else round(bid_sma)
        best_ask = asks[0] if asks else round(ask_sma)
        spread = best_ask - best_bid

        # Z-score on recent mid prices
        zscore = 0.0
        if len(ash_data["mid_hist"]) >= z_window:
            mean_mid = sum(ash_data["mid_hist"]) / len(ash_data["mid_hist"])
            var_mid = sum((x - mean_mid) ** 2 for x in ash_data["mid_hist"]) / len(ash_data["mid_hist"])
            std_mid = var_mid ** 0.5
            if std_mid > 0:
                current_mid = (best_bid + best_ask) / 2.0
                zscore = (current_mid - mean_mid) / std_mid

        pos = state.position.get(symbol, 0)
        buy_capacity = pos_limit - pos
        sell_capacity = pos_limit + pos
        logger.print("fv", fair_value, "z", zscore, "z_th", z_threshold, "spread", spread)

        # Buying dip in Ask
        if curr_best_ask <= ask_threshold and sell_capacity > 20:
            vol = min(active_lim, abs(order_depth.sell_orders[curr_best_ask]))
            if vol > 0:
                result.append(Order(symbol, curr_best_ask, vol))
                buy_capacity -= vol
                # Take back from spike
                result.append(Order(symbol, curr_best_ask + 6, -vol))


        # ACTIVE TAKING: normal FV trigger OR z-score stretch trigger
        if asks:
            ask_px = asks[0]
            buy_signal = (ask_px <= fair_value) or (zscore < -z_threshold and ask_px <= fair_value + 1)

            if buy_signal and buy_capacity > 0 and pos <= 40:
                vol = min(active_lim, buy_capacity, abs(order_depth.sell_orders[ask_px]))
                if vol > 0:
                    result.append(Order(symbol, ask_px, vol))
                    buy_capacity -= vol

        if bids:
            bid_px = bids[0]
            sell_signal = (bid_px >= fair_value) or (zscore > z_threshold and bid_px >= fair_value - 1)

            if sell_signal and sell_capacity > 0 and pos >= -40:
                vol = min(active_lim, sell_capacity, order_depth.buy_orders[bid_px])
                if vol > 0:
                    result.append(Order(symbol, bid_px, -vol))
                    sell_capacity -= vol

        # PASSIVE MAKING:
        passive_bid = next((p for p in bids if p + 1 <= fair_value), None) if fair_value is not None else best_bid
        if passive_bid is None and best_bid is not None and (fair_value is None or best_bid + 1 <= fair_value):
            passive_bid = best_bid

        passive_ask = next((p for p in asks if p - 1 >= fair_value), None) if fair_value is not None else best_ask
        if passive_ask is None and best_ask is not None and (fair_value is None or best_ask - 1 >= fair_value):
            passive_ask = best_ask

        if passive_bid is not None and buy_capacity != 0:
            result.append(Order(symbol, passive_bid + 1, buy_capacity))

        if passive_ask is not None and sell_capacity != 0:
            result.append(Order(symbol, passive_ask - 1, -sell_capacity))

        return result, ash_data