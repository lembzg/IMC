"""
IMC Prosperity 4 - Modular Trading Algorithm
=============================================
Architecture:
- Each product gets its own strategy method
- State persistence via traderData (JSON serialized, max 50k chars)
- Position-aware order generation that respects limits
- Easy to add new products each round

Key rules to remember:
- sell_orders quantities are NEGATIVE in OrderDepth
- If aggregated buy/sell orders would exceed position limit, ALL orders are rejected
- Orders execute instantaneously against bot quotes
- Unmatched order remainder becomes a quote that bots may trade against
- traderData max 50,000 characters
- 900ms timeout per run() call
"""

from datamodel import OrderDepth, UserId, TradingState, Order
from typing import List, Dict, Any
import json
import math
import numpy as np


# ============================================================
# CONFIGURATION - Update these per round
# ============================================================
POSITION_LIMITS = {
    # Update with actual limits from the wiki Rounds page
    "RAINFOREST_RESIN": 50,   # Example stable product
    "KELP": 50,               # Example volatile product
    # Add new products each round
}

# Strategy parameters - tune via backtesting
PARAMS = {
    "RAINFOREST_RESIN": {
        "fair_value": 10000,       # Known stable price
        "spread": 2,               # Half-spread for market making
        "max_order_size": 20,      # Max per order
    },
    "KELP": {
        "ema_alpha": 0.3,          # EMA smoothing factor (higher = more responsive)
        "spread": 2,               # Half-spread for market making
        "max_order_size": 10,
    },
}


class Trader:
    """
    Modular trader for IMC Prosperity 4.
    Add a method `trade_PRODUCTNAME(self, state, product)` for each product.
    """

    def bid(self):
        """Required for Round 2 auction. Update when Round 2 spec is released."""
        return 0

    def run(self, state: TradingState):
        # ---- Load persisted state ----
        trader_state = self._load_state(state.traderData)

        # ---- Generate orders for each product ----
        result: Dict[str, List[Order]] = {}

        for product in state.order_depths:
            orders = self._trade_product(product, state, trader_state)
            if orders:
                result[product] = orders

        # ---- Persist state ----
        trader_data = self._save_state(trader_state)
        conversions = 0

        return result, conversions, trader_data

    # ============================================================
    # STRATEGY ROUTER
    # ============================================================
    def _trade_product(self, product: str, state: TradingState,
                       trader_state: dict) -> List[Order]:
        """Route each product to its strategy."""
        # Map product names to strategy functions
        strategy_map = {
            "RAINFOREST_RESIN": self._trade_stable,
            "KELP": self._trade_volatile_ema,
            # Add new products here each round:
            # "NEW_PRODUCT": self._trade_pairs,
        }

        strategy = strategy_map.get(product)
        if strategy:
            return strategy(product, state, trader_state)

        # Default: skip unknown products (or use a generic strategy)
        return []

    # ============================================================
    # STRATEGY: STABLE PRODUCT (Market Making around known fair value)
    # ============================================================
    def _trade_stable(self, product: str, state: TradingState,
                      trader_state: dict) -> List[Order]:
        """
        For products with a known, fixed fair value (like Rainforest Resin at 10,000).
        Strategy: Aggressively take any mispriced orders, then place passive quotes.
        """
        params = PARAMS.get(product, {})
        fair_value = params.get("fair_value", 10000)
        spread = params.get("spread", 2)
        max_size = params.get("max_order_size", 20)

        order_depth = state.order_depths[product]
        position = state.position.get(product, 0)
        limit = POSITION_LIMITS.get(product, 20)

        orders: List[Order] = []

        # Phase 1: Take any mispriced orders (aggressive)
        buy_room = limit - position
        sell_room = limit + position

        # Buy anything offered below fair value
        if order_depth.sell_orders:
            for ask_price in sorted(order_depth.sell_orders.keys()):
                if ask_price < fair_value and buy_room > 0:
                    ask_vol = abs(order_depth.sell_orders[ask_price])
                    qty = min(ask_vol, buy_room)
                    orders.append(Order(product, ask_price, qty))
                    buy_room -= qty

        # Sell into any bids above fair value
        if order_depth.buy_orders:
            for bid_price in sorted(order_depth.buy_orders.keys(), reverse=True):
                if bid_price > fair_value and sell_room > 0:
                    bid_vol = order_depth.buy_orders[bid_price]
                    qty = min(bid_vol, sell_room)
                    orders.append(Order(product, bid_price, -qty))
                    sell_room -= qty

        # Phase 2: Place passive market-making quotes
        buy_price = fair_value - spread
        sell_price = fair_value + spread

        # Skew sizes based on inventory to mean-revert position
        buy_size = min(max_size, buy_room)
        sell_size = min(max_size, sell_room)

        # Inventory adjustment: reduce size on the side we're overweight
        if position > limit * 0.5:
            buy_size = max(1, buy_size // 2)
        elif position < -limit * 0.5:
            sell_size = max(1, sell_size // 2)

        if buy_size > 0:
            orders.append(Order(product, buy_price, buy_size))
        if sell_size > 0:
            orders.append(Order(product, sell_price, -sell_size))

        return orders

    # ============================================================
    # STRATEGY: VOLATILE PRODUCT (EMA-based market making)
    # ============================================================
    def _trade_volatile_ema(self, product: str, state: TradingState,
                           trader_state: dict) -> List[Order]:
        """
        For volatile products without a known fair value.
        Uses EMA to estimate fair value, then market-makes around it.
        """
        params = PARAMS.get(product, {})
        alpha = params.get("ema_alpha", 0.3)
        spread = params.get("spread", 2)
        max_size = params.get("max_order_size", 10)

        order_depth = state.order_depths[product]
        position = state.position.get(product, 0)
        limit = POSITION_LIMITS.get(product, 20)

        # Calculate current midprice
        mid = self._get_midprice(order_depth)
        if mid is None:
            return []

        # Update EMA
        ema_key = f"{product}_ema"
        if ema_key in trader_state and trader_state[ema_key] is not None:
            ema = alpha * mid + (1 - alpha) * trader_state[ema_key]
        else:
            ema = mid
        trader_state[ema_key] = ema

        fair_value = round(ema)

        orders: List[Order] = []
        buy_room = limit - position
        sell_room = limit + position

        # Phase 1: Take mispriced orders
        if order_depth.sell_orders:
            for ask_price in sorted(order_depth.sell_orders.keys()):
                if ask_price < fair_value and buy_room > 0:
                    ask_vol = abs(order_depth.sell_orders[ask_price])
                    qty = min(ask_vol, buy_room)
                    orders.append(Order(product, ask_price, qty))
                    buy_room -= qty

        if order_depth.buy_orders:
            for bid_price in sorted(order_depth.buy_orders.keys(), reverse=True):
                if bid_price > fair_value and sell_room > 0:
                    bid_vol = order_depth.buy_orders[bid_price]
                    qty = min(bid_vol, sell_room)
                    orders.append(Order(product, bid_price, -qty))
                    sell_room -= qty

        # Phase 2: Passive quotes with inventory skew
        # Widen spread slightly based on position to encourage mean reversion
        inv_skew = int(position * 0.5)  # Shift fair value away from our position
        adj_fair = fair_value - inv_skew

        buy_price = adj_fair - spread
        sell_price = adj_fair + spread

        buy_size = min(max_size, buy_room)
        sell_size = min(max_size, sell_room)

        if buy_size > 0:
            orders.append(Order(product, int(buy_price), buy_size))
        if sell_size > 0:
            orders.append(Order(product, int(sell_price), -sell_size))

        return orders

    # ============================================================
    # STRATEGY: PAIRS / SPREAD TRADING (Template for correlated products)
    # ============================================================
    def _trade_spread(self, product: str, state: TradingState,
                      trader_state: dict) -> List[Order]:
        """
        Template for spread/pairs trading between correlated products.
        E.g., ETF vs its components, or two correlated assets.
        Implement when such products appear in later rounds.
        """
        # TODO: Implement when correlated products are introduced
        # Key steps:
        # 1. Calculate spread = price_A - hedge_ratio * price_B
        # 2. Compute z-score of spread using rolling mean/std
        # 3. If z-score > threshold, sell A and buy B (spread is high)
        # 4. If z-score < -threshold, buy A and sell B (spread is low)
        return []

    # ============================================================
    # HELPER METHODS
    # ============================================================
    def _get_midprice(self, order_depth: OrderDepth) -> float:
        """Calculate midprice from order book."""
        if not order_depth.buy_orders or not order_depth.sell_orders:
            return None
        best_bid = max(order_depth.buy_orders.keys())
        best_ask = min(order_depth.sell_orders.keys())
        return (best_bid + best_ask) / 2

    def _get_microprice(self, order_depth: OrderDepth) -> float:
        """Volume-weighted midprice - better fair value estimate."""
        if not order_depth.buy_orders or not order_depth.sell_orders:
            return None
        best_bid = max(order_depth.buy_orders.keys())
        best_ask = min(order_depth.sell_orders.keys())
        bid_vol = order_depth.buy_orders[best_bid]
        ask_vol = abs(order_depth.sell_orders[best_ask])
        # Microprice weights toward the side with more volume
        return (best_bid * ask_vol + best_ask * bid_vol) / (bid_vol + ask_vol)

    def _get_vwap(self, order_depth: OrderDepth, side: str = "both") -> float:
        """Volume-weighted average price across all levels."""
        total_value = 0
        total_volume = 0

        if side in ("buy", "both"):
            for price, vol in order_depth.buy_orders.items():
                total_value += price * vol
                total_volume += vol

        if side in ("sell", "both"):
            for price, vol in order_depth.sell_orders.items():
                total_value += price * abs(vol)
                total_volume += abs(vol)

        return total_value / total_volume if total_volume > 0 else None

    def _load_state(self, trader_data: str) -> dict:
        """Deserialize persisted state from traderData string."""
        if trader_data and trader_data.strip():
            try:
                return json.loads(trader_data)
            except (json.JSONDecodeError, TypeError):
                pass
        return {}

    def _save_state(self, trader_state: dict) -> str:
        """Serialize state to traderData string (max 50k chars)."""
        try:
            s = json.dumps(trader_state)
            if len(s) > 49000:  # Leave margin
                # If too large, keep only essential state
                essential = {k: v for k, v in trader_state.items()
                            if k.endswith("_ema") or k.endswith("_prices")}
                s = json.dumps(essential)
            return s
        except (TypeError, ValueError):
            return ""
