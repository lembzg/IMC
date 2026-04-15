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
    ACO_BASE_SPREAD   = 14
    ACO_POS_LIMIT     = 50
    ACO_ROLL_WINDOW   = 50
    ACO_SIZE_LO       = 15     # size when abs_ratio < 0.5
    ACO_SIZE_MID      = 12     # size when abs_ratio < 0.75
    ACO_SIZE_HI       = 6      # size when abs_ratio >= 0.75

    # ─────────────────────────────────────────────────────────

    def run(self, state: TradingState):
        result = defaultdict(list)
        conversions = 0

        sd = {}
        if state.traderData and state.traderData != "":
            try:
                sd = jsonpickle.decode(state.traderData)
            except Exception:
                sd = {}

        result['ASH_COATED_OSMIUM'], sd = self.ash(state, sd)
        #result["INTARIAN_PEPPER_ROOT"] = self.pepper(state)

        traderData = jsonpickle.encode(sd)

        logger.flush(state, result, conversions, traderData)
        return result, conversions, traderData

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

        # Populated book-level fair value anchor
        pop_bid = max(bids.keys(), key=lambda p: bids[p])
        pop_ask = max(asks.keys(), key=lambda p: abs(asks[p]))
        fv = float(round((pop_bid + pop_ask) / 2))
        
        

        # Inventory skew
        ratio = pos / pos_lim
        fv -= round(ratio * 6)
        fv = round(fv)

        # Dynamic size
        abs_ratio = abs(ratio)
        if abs_ratio < 0.5:
            size = self.ACO_SIZE_LO
        elif abs_ratio < 0.75:
            size = self.ACO_SIZE_MID
        else:
            size = self.ACO_SIZE_HI

        buy_room = pos_lim - pos
        sell_room = pos_lim + pos

        buy_qty = min(size, buy_room)
        sell_qty = min(size, sell_room)

        orders: List[Order] = []

        # ---- Opportunistic taking, but only with clear edge ----
        take_edge = 1

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
    
    
    # def pepper(self, state: TradingState):
    #     product = "INTARIAN_PEPPER_ROOT"
    #     pos = state.position.get(product, 0)
    #     pos_lim = 80

    #     if product not in state.order_depths:
    #         return []

    #     od = state.order_depths[product]
    #     bids = od.buy_orders
    #     asks = od.sell_orders

    #     if not asks:
    #         return []

    #     ask_prices = sorted(asks.keys())   
    #     orders = []

    #     remaining = pos_lim - pos
    #     if remaining <= 0:
    #         return []

    #     # Extremely aggressive front-loaded entry
    #     if state.timestamp < 20_000:
    #         target_clip = 40
    #         max_levels = 3
    #     elif state.timestamp < 60_000:
    #         target_clip = 30
    #         max_levels = 2
    #     else:
    #         return []   
    #     qty_left = min(target_clip, remaining)
    #     levels_used = 0

    #     for ask_px in ask_prices:
    #         if qty_left <= 0 or levels_used >= max_levels:
    #             break

    #         avail = abs(asks[ask_px])
    #         take_qty = min(qty_left, avail)

    #         if take_qty > 0:
    #             orders.append(Order(product, ask_px, take_qty))
    #             qty_left -= take_qty
    #             levels_used += 1

    #     return orders