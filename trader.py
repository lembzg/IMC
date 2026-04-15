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
        
        # Execute individual product strategies, passing state to each
        result['ASH_COATED_OSMIUM'], ash_data = self.ash(state)
        result['INTARIAN_PEPPER_ROOT'], root_data = self.root(state)
        
        # Combine the respective data dictionaries into a single payload
        traderData = json.dumps({"ash_data": ash_data, "root_data":root_data})
        
        # Flush logger using the properly constructed traderData
        logger.flush(state, dict(result), conversions, traderData)
        
        return dict(result), conversions, traderData
    
    def ash(self, state: TradingState):
        result = []
        symbol = 'ASH_COATED_OSMIUM'
        sma_window = 10
        pos_limit = 80
        reasonable_range = 3
        # reduce_range = 1
        
        # 1. Deserialize state specific to INTARIAN_PEPPER_ROOT
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
        
        # 2. Extract best bid/ask and Forward Fill if missing
        curr_best_bid = max(order_depth.buy_orders.keys()) if len(order_depth.buy_orders) > 0 else None
        curr_best_ask = min(order_depth.sell_orders.keys()) if len(order_depth.sell_orders) > 0 else None
        
        best_bid = curr_best_bid if curr_best_bid is not None else (ash_data["bid_hist"][-1] if ash_data["bid_hist"] else None)
        best_ask = curr_best_ask if curr_best_ask is not None else (ash_data["ask_hist"][-1] if ash_data["ask_hist"] else None)
        
        # 3. Update History
        if best_bid is not None:
            ash_data["bid_hist"].append(best_bid)
        if best_ask is not None:
            ash_data["ask_hist"].append(best_ask)
            
        if len(ash_data["bid_hist"]) > sma_window:
            ash_data["bid_hist"].pop(0)
        if len(ash_data["ask_hist"]) > sma_window:
            ash_data["ask_hist"].pop(0)
            
        # If still warming up, return empty orders but save updated history
        if len(ash_data["bid_hist"]) < sma_window or len(ash_data["ask_hist"]) < sma_window:
            return result, ash_data
        
        # 4. Calculate indicators and risk metrics
        bid_sma = sum(ash_data["bid_hist"]) / sma_window
        ask_sma = sum(ash_data["ask_hist"]) / sma_window
        fair_value = (bid_sma + ask_sma) / 2.0
        
        pos = state.position.get(symbol, 0)
        buy_capacity = pos_limit - pos
        sell_capacity = pos_limit + pos
        
        # --- 5. EXECUTION TIER A: Reduce Position near Fair Value ---
        fv_true = round(fair_value)
        for fv_round in reversed([ fv_true - 1, fv_true, fv_true + 1]):
            if pos > 0 and fv_round in order_depth.buy_orders:
                vol = min(pos, order_depth.buy_orders[fv_round])
                result.append(Order(symbol, fv_round, -vol))
                sell_capacity -= vol
                pos -= vol
            
        fv_true = round(fair_value)
        for fv_round in [fv_true - 2, fv_true - 1, fv_true, fv_true + 1]:
            if pos < 0 and fv_round in order_depth.sell_orders:
                vol = min(abs(pos), abs(order_depth.sell_orders[fv_round]))
                result.append(Order(symbol, fv_round, vol))
                buy_capacity -= vol
                pos += vol
            
        # --- 6. EXECUTION TIER B: Active Taking for Mispricings ---
        for ask_px in sorted(order_depth.sell_orders.keys()):
            if ask_px < fair_value and buy_capacity > 0:
                vol = min(buy_capacity, abs(order_depth.sell_orders[ask_px]))
                result.append(Order(symbol, ask_px, vol))
                buy_capacity -= vol
                
        for bid_px in sorted(order_depth.buy_orders.keys(), reverse=True):
            if bid_px > fair_value and sell_capacity > 0:
                vol = min(sell_capacity, order_depth.buy_orders[bid_px])
                result.append(Order(symbol, bid_px, -vol))
                sell_capacity -= vol
                
        # --- 7. EXECUTION TIER C: Passive Market Making (Pennying) ---
        passive_size = 20

        if best_bid is not None and best_bid - bid_sma <= reasonable_range and buy_capacity > 0:
            my_bid = best_bid + 1
            if my_bid < fair_value:
                result.append(Order(symbol, my_bid, min(passive_size, buy_capacity)))
                    
        if best_ask is not None and ask_sma - best_ask <= reasonable_range and sell_capacity > 0:
            my_ask = best_ask - 1
            if my_ask > fair_value:
                result.append(Order(symbol, my_ask, -min(passive_size, sell_capacity)))
                
        
        return result, ash_data
        
    def root(self, state: TradingState):
        product = "INTARIAN_PEPPER_ROOT"
        pos = state.position.get(product, 0)
        pos_lim = 80

        if product not in state.order_depths:
            return []

        sell_orders = state.order_depths[product].sell_orders
        if not sell_orders:
            return []

        best_ask = min(sell_orders.keys())
        best_ask_vol = abs(sell_orders[best_ask])

        remaining = pos_lim - pos
        if remaining <= 0:
            return []

        if state.timestamp < 20_000:
            clip = 30
        elif state.timestamp < 60_000:
            clip = 20
        else:
            return []

        qty = min(clip, remaining, best_ask_vol)
        if qty > 0:
            return [Order(product, best_ask, qty)]

        return []