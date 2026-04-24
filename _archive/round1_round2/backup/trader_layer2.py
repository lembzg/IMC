from datamodel import OrderDepth, UserId, TradingState, Order
from typing import List
import json
from collections import defaultdict
import jsonpickle


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


def clamp(val, lo, hi):
    return max(lo, min(hi, val))


class Trader:
    # ── ACO constants ────────────────────────────────────────
    ACO_BASE_FV       = 10_000
    ACO_BASE_SPREAD   = 11      # ticks each side (inside bot's ±8)
    ACO_POS_LIMIT     = 50      # update from wiki if different
    ACO_EMA_ALPHA     = 0.1     # fast EMA for FV tracking
    ACO_SLOW_ALPHA    = 0.005   # slow EMA for macro wave
    ACO_ROLL_WINDOW   = 50      # z-score rolling window
    ACO_FV_CAP        = 5       # max ±ticks FV can deviate from base
    # OBI bucket → FV shift map (bucket 0 = heavy ask side, 3 = heavy bid side)
    ACO_OBI_MAP       = {0: -3, 1: 0, 2: 2, 3: 4}

    # ─────────────────────────────────────────────────────────

    def run(self, state: TradingState):
        result = defaultdict(list)
        conversions = 0

        # ── Load persisted state ─────────────────────────────
        sd = {}
        if state.traderData and state.traderData != "":
            try:
                sd = jsonpickle.decode(state.traderData)
            except Exception:
                sd = {}

        # ── Trade each product ───────────────────────────────
        result['ASH_COATED_OSMIUM'], sd = self.ash(state, sd)

        # ── Persist state ────────────────────────────────────
        traderData = jsonpickle.encode(sd)

        logger.flush(state, result, conversions, traderData)
        return result, conversions, traderData

    # ══════════════════════════════════════════════════════════
    #  ASH_COATED_OSMIUM  –  passive market-making with
    #  OBI shift  ·  z-score reversion  ·  macro wave tilt
    # ══════════════════════════════════════════════════════════
    def ash(self, state: TradingState, sd: dict) -> tuple:
        product = "ASH_COATED_OSMIUM"
        pos = state.position.get(product, 0)
        pos_lim = self.ACO_POS_LIMIT

        if product not in state.order_depths:
            return [], sd

        od = state.order_depths[product]
        bids = od.buy_orders
        asks = od.sell_orders

        if not bids or not asks:
            return [], sd

        bid_prices = sorted(bids.keys(), reverse=True)
        ask_prices = sorted(asks.keys())

        best_bid = bid_prices[0]
        best_ask = ask_prices[0]
        mid = (best_bid + best_ask) / 2.0
        spread = best_ask - best_bid

        # Update rolling mid-price window
        mid_hist = sd.get("aco_mid_hist", [])
        mid_hist.append(mid)
        if len(mid_hist) > self.ACO_ROLL_WINDOW:
            mid_hist = mid_hist[-self.ACO_ROLL_WINDOW:]
        sd["aco_mid_hist"] = mid_hist

        # Populated book-level fair value anchor
        pop_bid = max(bids.keys(), key=lambda p: bids[p])
        pop_ask = max(asks.keys(), key=lambda p: abs(asks[p]))
        fv = float(round((pop_bid + pop_ask) / 2))

        # Z-score skew
        if len(mid_hist) >= 10:
            roll_mean = sum(mid_hist) / len(mid_hist)
            roll_var = sum((m - roll_mean) ** 2 for m in mid_hist) / len(mid_hist)
            roll_std = roll_var ** 0.5
            if roll_std > 0:
                z = (mid - roll_mean) / roll_std
                z_shift = -clamp(round(z * 1.5), -3, 3)
                fv += z_shift

        # Inventory skew
        ratio = pos / pos_lim
        fv -= round(ratio * 3)
        fv = round(fv)

        # Dynamic size
        abs_ratio = abs(ratio)
        if abs_ratio < 0.5:
            size = 12
        elif abs_ratio < 0.75:
            size = 8
        else:
            size = 4

        buy_room = pos_lim - pos
        sell_room = pos_lim + pos

        buy_qty = min(size, buy_room)
        sell_qty = min(size, sell_room)

        orders: List[Order] = []

        # ---- Opportunistic taking, but only with clear edge ----
        take_edge = 2

        if buy_qty > 0 and pos < pos_lim - 10:
            for ask_px in ask_prices:
                if ask_px <= fv - take_edge:
                    qty = min(buy_qty, abs(asks[ask_px]))
                    if qty > 0:
                        orders.append(Order(product, ask_px, qty))
                        buy_qty -= qty
                    break

        if sell_qty > 0 and pos > -pos_lim + 10:
            for bid_px in bid_prices:
                if bid_px >= fv + take_edge:
                    qty = min(sell_qty, bids[bid_px])
                    if qty > 0:
                        orders.append(Order(product, bid_px, -qty))
                        sell_qty -= qty
                    break

        # ---- Passive quotes, but more competitive ----
        bid_price = fv - self.ACO_BASE_SPREAD
        ask_price = fv + self.ACO_BASE_SPREAD

        # Step inside spread when there is room, while staying passive
        if spread >= 3:
            bid_price = max(bid_price, best_bid + 1)
            ask_price = min(ask_price, best_ask - 1)
        else:
            bid_price = min(bid_price, best_ask - 1)
            ask_price = max(ask_price, best_bid + 1)

        if bid_price < ask_price:
            if buy_qty > 0:
                orders.append(Order(product, bid_price, buy_qty))
            if sell_qty > 0:
                orders.append(Order(product, ask_price, -sell_qty))

        return orders, sd