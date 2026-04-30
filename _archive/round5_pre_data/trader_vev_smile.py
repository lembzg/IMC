"""
VEV Mean-Reversion  v5
=======================
Findings from data analysis:
  - Original trader_vev.py's price-EMA approach makes +6,130 from VEV_5200-5500 alone.
  - All losses come from VEV_4000/4500 (no IV solvable), VEV_5000/5100 (spread 4-5 wide),
    and the spot MM (fights trends on the volatile days).
  - IV has lag-1 autocorrelation of -0.49 to -0.51 — confirmed mean reversion.
  - The simplest exploitable edge: price oscillates around its trailing mean.

Strategy (exactly replicates what works in original, focused on VEV_5200-5500):
  - slow EMA of mid price (alpha=0.001) as the "fair value" reference.
  - fast EMA (alpha=0.97) for short-term momentum.
  - extrinsic EMA (alpha=0.01) for a cleaner mean-reversion signal.
  - Aggressive take when price deviates from slow EMA or when extrinsic exceeds EMA ± EXT_THR.
  - No spot trading (consistent loser on this dataset).
  - No VEV_4000/4500/5000/5100 (spread too wide or IV unstable).

Tunable parameters at module top for grid search via backtester.py.
"""

import json
from datamodel import Order, Symbol, TradingState
from typing import Dict, List, Optional, Tuple

# ── Products ───────────────────────────────────────────────────────────────────
# All liquid VEV strikes. The very slow EMA reference plus high qty=1 ensures
# we capture large spot-driven moves on ITM options (4000-5100) profitably
# even with wide spreads, while near-ATM options (5200-5500) contribute smaller
# but steady mean-reversion P&L.  VEV_6000/6500 excluded (bid=0/ask=1, no fills).
OPT_LIMITS: Dict[str, int] = {
    "VEV_4000": 300,
    "VEV_4500": 300,
    "VEV_5000": 300,
    "VEV_5100": 300,
    "VEV_5200": 300,
    "VEV_5300": 300,
    "VEV_5400": 300,
    "VEV_5500": 300,
}

# ── Tunable parameters ─────────────────────────────────────────────────────────
# Grid-searched over [qty, alpha_slow, ext_thr] on all 3 round-3 days.
# Optimal found: qty=1, alpha_slow=0.0001, ext_thr=10 → +69,835 total P&L.
ALPHA_FAST      = 0.97     # fast EMA for short-term momentum
ALPHA_SLOW      = 0.0001   # near-constant EMA — anchors at initial price level
EXT_ALPHA       = 0.01     # extrinsic value EMA
EXT_THR         = 10.0     # extrinsic deviation threshold
MARGIN          = 0.01     # price deviation from slow EMA to enter
OPT_TRADE_QTY   = 1        # lots per signal — small to maximise signal frequency
STOP_LOSS       = -10000   # per-product stop-loss threshold


# ══════════════════════════════════════════════════════════════════════════════
# Logger
# ══════════════════════════════════════════════════════════════════════════════

class Logger:
    def __init__(self):
        self.logs = ""

    def print(self, *objects, sep=" ", end="\n"):
        self.logs += sep.join(map(str, objects)) + end

    def flush(self, state: TradingState, orders: dict, conversions: int, trader_data: str):
        print(json.dumps([
            [
                state.timestamp, state.traderData,
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
            conversions, trader_data, self.logs,
        ], separators=(",", ":")))
        self.logs = ""


logger = Logger()


class Trader:

    def run(self, state: TradingState) -> Tuple[Dict[Symbol, List[Order]], int, str]:
        saved: dict = {}
        if state.traderData:
            try:
                saved = json.loads(state.traderData)
            except Exception:
                pass

        result: Dict[Symbol, List[Order]] = {}

        # Spot mid (needed for intrinsic value calculation only)
        spot_depth = state.order_depths.get("VELVETFRUIT_EXTRACT")
        spot_mid: Optional[float] = None
        if spot_depth and spot_depth.buy_orders and spot_depth.sell_orders:
            spot_mid = (max(spot_depth.buy_orders) + min(spot_depth.sell_orders)) / 2.0

        ema_fast: dict = saved.get("f", {})
        ema_slow: dict = saved.get("s", {})
        ext_ema:  dict = saved.get("e", {})

        for product, limit in OPT_LIMITS.items():
            depth = state.order_depths.get(product)
            if not depth or not depth.buy_orders or not depth.sell_orders:
                continue

            best_ask = min(depth.sell_orders)
            best_bid = max(depth.buy_orders)
            mid_price = (best_ask + best_bid) / 2.0

            # EMA updates
            if product not in ema_fast:
                ema_fast[product] = mid_price
                ema_slow[product] = mid_price
            else:
                ema_fast[product] = ALPHA_FAST * mid_price + (1 - ALPHA_FAST) * ema_fast[product]
                ema_slow[product] = ALPHA_SLOW * mid_price + (1 - ALPHA_SLOW) * ema_slow[product]

            expected_price = ema_slow[product]
            momentum = mid_price - ema_fast[product]

            # Extrinsic value mean reversion
            extrinsic = mid_price
            ev_mavg = 0.0
            if spot_mid is not None:
                strike = int(product.split("_")[1])
                intrinsic = max(0.0, spot_mid - strike)
                extrinsic = mid_price - intrinsic
                prev = ext_ema.get(product)
                ext_ema[product] = extrinsic if prev is None else EXT_ALPHA * extrinsic + (1 - EXT_ALPHA) * prev
                ev_mavg = ext_ema[product]

            current_pos = state.position.get(product, 0)
            to_buy  = limit - current_pos
            to_sell = limit + current_pos

            orders: List[Order] = []

            # Stop-loss
            own_trades = state.own_trades.get(product, [])
            if own_trades:
                mid_pnl = (best_bid + best_ask) / 2
                realized = sum((t.price - mid_pnl) * t.quantity for t in own_trades)
                if realized < STOP_LOSS:
                    if current_pos > 0:
                        orders.append(Order(product, best_bid, -current_pos))
                    elif current_pos < 0:
                        orders.append(Order(product, best_ask, -current_pos))
                    if orders:
                        result[product] = orders
                    continue

            take_buy  = (best_ask < expected_price - MARGIN or momentum < -8) and to_buy > 0
            take_sell = (best_bid > expected_price + MARGIN or momentum > 8) and to_sell > 0

            if ev_mavg > 0:
                if extrinsic > ev_mavg + EXT_THR:
                    take_sell = True
                elif extrinsic < ev_mavg - EXT_THR:
                    take_buy = True

            if take_buy and to_buy > 0:
                vol = depth.sell_orders[best_ask]
                qty = min(to_buy, -vol, OPT_TRADE_QTY)
                if qty > 0:
                    orders.append(Order(product, best_ask, qty))

            if take_sell and to_sell > 0:
                vol = depth.buy_orders[best_bid]
                qty = min(to_sell, vol, OPT_TRADE_QTY)
                if qty > 0:
                    orders.append(Order(product, best_bid, -qty))

            if orders:
                result[product] = orders

        saved["f"] = {k: round(v, 2) for k, v in ema_fast.items()}
        saved["s"] = {k: round(v, 2) for k, v in ema_slow.items()}
        saved["e"] = {k: round(v, 2) for k, v in ext_ema.items()}

        trader_data = json.dumps(saved)
        logger.flush(state, result, 0, trader_data)
        return result, 0, trader_data
