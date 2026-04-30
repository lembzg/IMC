import json
from datamodel import Order, Symbol, TradingState
from typing import Dict, List, Tuple
import math


class Trader:
    def __init__(self):
        # Position limits for all 12 assets
        self.limits = {
            "HYDROGEL_PACK": 200,
            "VELVETFRUIT_EXTRACT": 200,
            "VEV_4000": 300,
            "VEV_4500": 300,
            "VEV_5000": 300,
            "VEV_5100": 300,
            "VEV_5200": 300,
            "VEV_5300": 300,
            "VEV_5400": 300,
            "VEV_5500": 300,
        }

        # Dual EMA Smoothing Factors
        self.alpha_fast = 0.15  # Short-term trend (reacts quickly to recent ticks)
        self.alpha_slow = 0.001  # Long-term trend (anchors the baseline fair value)

        # Margin of safety before making a trade
        self.margin = {
            "HYDROGEL_PACK": 16,
            "VELVETFRUIT_EXTRACT": 5.5,
            "VEV_4000": 21,
            "VEV_4500": 16,
            "VEV_5000": 6,
            "VEV_5100": 4,
            "VEV_5200": 3,
            "VEV_5300": 2,
            "VEV_5400": 1.5,
            "VEV_5500": 1.5,
        }

    def run(self, state: TradingState) -> Tuple[Dict[Symbol, List[Order]], int, str]:
        result = {}
        conversions = 0

        # 1. Deserialize memory for BOTH trends from the previous tick
        state_memory = {"fast": {}, "slow": {}}
        if state.traderData != "":
            try:
                state_memory = json.loads(state.traderData)
            except Exception:
                pass

        ema_fast = state_memory.get("fast", {})
        ema_slow = state_memory.get("slow", {})

        # 2. Iterate through all products to calculate trends and execute trades
        for product in self.limits.keys():
            if product in state.order_depths:
                depth = state.order_depths[product]
                orders: List[Order] = []
                current_position = state.position.get(product, 0)
                limit = self.limits[product]

                if len(depth.buy_orders) > 0 and len(depth.sell_orders) > 0:
                    best_ask = min(depth.sell_orders.keys())
                    best_bid = max(depth.buy_orders.keys())
                    mid_price = (best_ask + best_bid) / 2
                    if product in ema_fast:
                        ema_fast[product] = ema_fast[product] * (1 - self.alpha_fast) + mid_price * self.alpha_fast
                        ema_slow[product] = ema_slow[product] * (1 - self.alpha_slow) + mid_price * self.alpha_slow
                    else:
                        ema_fast[product] = mid_price
                        ema_slow[product] = mid_price

                if product in ema_slow:
                    expected_price = ema_slow[product] * 0.5 + ema_fast[product] * 0.5
                else:
                    continue

                margin = self.margin[product]
                for best_ask in depth.sell_orders.keys():
                    if best_ask < expected_price - margin:
                        best_ask_vol = depth.sell_orders[best_ask]
                        buy_vol = min(limit - current_position, -best_ask_vol)
                        if buy_vol > 0:
                            orders.append(Order(product, best_ask, buy_vol))
                            current_position += buy_vol

                for best_bid in depth.buy_orders.keys():
                    if best_bid > expected_price + margin:
                        best_bid_vol = depth.buy_orders[best_bid]
                        sell_vol = max(-limit - current_position, -best_bid_vol)
                        if sell_vol < 0:
                            orders.append(Order(product, best_bid, sell_vol))
                            current_position += sell_vol

                if orders:
                    result[product] = orders

        # 3. Re-pack both dictionaries into state_memory and serialize for the next tick
        state_memory["fast"] = ema_fast
        state_memory["slow"] = ema_slow
        new_trader_data = json.dumps(state_memory)

        return result, conversions, new_trader_data
