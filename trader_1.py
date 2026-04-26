
import json
import math
from typing import List, Optional
from datamodel import Order, OrderDepth, TradingState


PRODUCT     = "HYDROGEL_PACK"
LIMIT       = 200
ANCHOR      = 9950.0   # hardcoded fair value

# z-score & sizing
STD_WINDOW  = 50        # ticks of price history kept for rolling stdev
STD_FLOOR   = 2.0       # never let stdev go below this (avoids div-by-zero)
K_POS       = 60        # position scale per unit of |z| (z=1 -> target ±60)
Z_TAKE      = 1.5       # |z| above this -> aggressively take liquidity
MAX_TAKE    = 40        # per-level cap on aggressive fills

# market-making
QUOTE_EDGE  = 8         # post passives at anchor ± QUOTE_EDGE
QUOTE_SIZE  = 10        # base passive size per side


def best_bid(od: OrderDepth) -> Optional[int]:
    return max(od.buy_orders) if od.buy_orders else None

def best_ask(od: OrderDepth) -> Optional[int]:
    return min(od.sell_orders) if od.sell_orders else None

def wall_mid(od: OrderDepth, levels: int = 3) -> Optional[float]:
    """Mid between the largest-size bid level and the largest-size ask level."""
    if not od.buy_orders or not od.sell_orders:
        return None
    bids = sorted(od.buy_orders.items(), reverse=True)[:levels]
    asks = sorted(od.sell_orders.items())[:levels]
    bid_wall = max(bids, key=lambda x: (x[1], x[0]))[0]
    ask_wall = min(asks, key=lambda x: (abs(x[1]), -x[0]))[0]
    if bid_wall >= ask_wall:
        return 0.5 * (best_bid(od) + best_ask(od))
    return 0.5 * (bid_wall + ask_wall)


class Trader:
    def run(self, state: TradingState):
        # restore deviation history
        try:
            mem = json.loads(state.traderData) if state.traderData else {}
        except Exception:
            mem = {}
        devs: List[float] = mem.get("devs", [])

        result = {PRODUCT: []}
        od = state.order_depths.get(PRODUCT)
        if od is None:
            return result, 0, json.dumps({"devs": devs})

        bb, ba = best_bid(od), best_ask(od)
        wm = wall_mid(od)
        if bb is None or ba is None or wm is None:
            return result, 0, json.dumps({"devs": devs})

        # rolling stdev of (wall_mid - anchor)
        deviation = wm - ANCHOR
        devs.append(deviation)
        devs = devs[-STD_WINDOW:]

        if len(devs) >= 5:
            mean_d = sum(devs) / len(devs)
            var_d  = sum((d - mean_d) ** 2 for d in devs) / len(devs)
            std    = max(STD_FLOOR, math.sqrt(var_d))
        else:
            std = STD_FLOOR

        z = deviation / std

        # mean-reversion target: long when price is below anchor, short when above
        target_pos = max(-LIMIT, min(LIMIT, int(round(-K_POS * z))))

        pos = state.position.get(PRODUCT, 0)
        orders: List[Order] = []
        buy_cap  = LIMIT - pos
        sell_cap = LIMIT + pos

        # ── Aggressive: when |z| big, take whatever liquidity exists in our direction
        if z >= Z_TAKE and sell_cap > 0:
            # price is high -> sell into bids
            for bx, v in sorted(od.buy_orders.items(), reverse=True):
                if sell_cap <= 0 or pos <= target_pos:
                    break
                if bx < ANCHOR:
                    break  # don't sell below anchor
                qty = min(v, sell_cap, MAX_TAKE, pos - target_pos)
                if qty > 0:
                    orders.append(Order(PRODUCT, bx, -qty))
                    sell_cap -= qty
                    pos -= qty

        if z <= -Z_TAKE and buy_cap > 0:
            # price is low -> lift offers
            for ax, v in sorted(od.sell_orders.items()):
                if buy_cap <= 0 or pos >= target_pos:
                    break
                if ax > ANCHOR:
                    break  # don't buy above anchor
                qty = min(abs(v), buy_cap, MAX_TAKE, target_pos - pos)
                if qty > 0:
                    orders.append(Order(PRODUCT, ax, qty))
                    buy_cap -= qty
                    pos += qty

        # ── Passive: post quotes at anchor ± QUOTE_EDGE
        bid_px = int(round(ANCHOR - QUOTE_EDGE))
        ask_px = int(round(ANCHOR + QUOTE_EDGE))

        # stay strictly inside the natural spread
        bid_px = min(bid_px, ba - 1)
        ask_px = max(ask_px, bb + 1)
        if bid_px >= ask_px:
            bid_px = ask_px - 1

        # size leans toward the target_pos: if we want to be longer, bigger bid
        gap = target_pos - pos
        bid_boost = 1.0 + max(0, gap) / LIMIT
        ask_boost = 1.0 + max(0, -gap) / LIMIT
        # shrink the side that would push past the limit
        long_pen  = max(0.2, 1.0 - max(0,  pos) / LIMIT)
        short_pen = max(0.2, 1.0 - max(0, -pos) / LIMIT)

        bs = min(buy_cap,  int(QUOTE_SIZE * bid_boost * long_pen))
        ss = min(sell_cap, int(QUOTE_SIZE * ask_boost * short_pen))
        if bs > 0:
            orders.append(Order(PRODUCT, bid_px, bs))
        if ss > 0:
            orders.append(Order(PRODUCT, ask_px, -ss))

        result[PRODUCT] = orders
        return result, 0, json.dumps({"devs": devs})