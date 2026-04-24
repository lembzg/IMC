from datamodel import OrderDepth, UserId, TradingState, Order
from typing import List
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
        conversions = 0
        shared = {}
        if state.traderData:
            try:
                shared = json.loads(state.traderData)
            except json.JSONDecodeError:
                pass

        result['ASH_COATED_OSMIUM'], ov = self.ash(state, shared.get("ov", {}))
        traderData = json.dumps({"ov": ov})
        logger.flush(state, result, conversions, traderData)
        return result, conversions, traderData

    def ash(self, state: TradingState, ov: dict):
        product = 'ASH_COATED_OSMIUM'
        result = []
        pos_lim = 80
        entry_size = 2
        long_entry_px  = 10003
        short_entry_px = 10005

        ov.setdefault("long_inv",  0);  ov.setdefault("long_entry_px_pend",  0);  ov.setdefault("long_entry_qty_pend",  0)
        ov.setdefault("short_inv", 0);  ov.setdefault("short_entry_px_pend", 0);  ov.setdefault("short_entry_qty_pend", 0)
        ov.setdefault("long_exit_px_pend",  0);  ov.setdefault("long_exit_qty_pend",  0)
        ov.setdefault("short_exit_px_pend", 0);  ov.setdefault("short_exit_qty_pend", 0)
        ov.setdefault("seen", [])

        if product not in state.order_depths:
            return result, ov

        od = state.order_depths[product]
        bids = sorted(od.buy_orders, reverse=True)
        asks = sorted(od.sell_orders)

        if not bids or not asks:
            return result, ov

        best_bid = bids[0]
        best_ask = asks[0]
        pos = state.position.get(product, 0)

        # ── Fill attribution ─────────────────────────────────────────────────
        seen = list(ov["seen"])
        seen_set = set(seen)

        for t in state.own_trades.get(product, []):
            sig = f"{t.timestamp}|{t.price}|{t.quantity}|{t.buyer}|{t.seller}"
            if sig in seen_set:
                continue
            seen.append(sig)
            seen_set.add(sig)

            px  = int(t.price)
            qty = abs(int(t.quantity))
            is_buy = (t.buyer == "SUBMISSION")

            if is_buy:
                if ov["long_entry_qty_pend"] > 0 and px == ov["long_entry_px_pend"]:
                    filled = min(qty, ov["long_entry_qty_pend"])
                    ov["long_inv"]            += filled
                    ov["long_entry_qty_pend"] -= filled
                elif ov["short_exit_qty_pend"] > 0 and px == ov["short_exit_px_pend"]:
                    filled                    = min(qty, ov["short_exit_qty_pend"])
                    ov["short_inv"]           = max(0, ov["short_inv"] - filled)
                    ov["short_exit_qty_pend"] -= filled
            else:
                if ov["short_entry_qty_pend"] > 0 and px == ov["short_entry_px_pend"]:
                    filled = min(qty, ov["short_entry_qty_pend"])
                    ov["short_inv"]            += filled
                    ov["short_entry_qty_pend"] -= filled
                elif ov["long_exit_qty_pend"] > 0 and px == ov["long_exit_px_pend"]:
                    filled                   = min(qty, ov["long_exit_qty_pend"])
                    ov["long_inv"]           = max(0, ov["long_inv"] - filled)
                    ov["long_exit_qty_pend"] -= filled

        ov["seen"] = seen[-200:]

        ov["long_entry_px_pend"]  = 0;  ov["long_entry_qty_pend"]  = 0
        ov["long_exit_px_pend"]   = 0;  ov["long_exit_qty_pend"]   = 0
        ov["short_entry_px_pend"] = 0;  ov["short_entry_qty_pend"] = 0
        ov["short_exit_px_pend"]  = 0;  ov["short_exit_qty_pend"]  = 0

        # ── Orders ───────────────────────────────────────────────────────────

        # Long exit — sell at best_ask - 1
        if ov["long_inv"] > 0:
            exit_px = best_ask - 1
            if exit_px > best_bid:
                result.append(Order(product, exit_px, -ov["long_inv"]))
                ov["long_exit_px_pend"]  = exit_px
                ov["long_exit_qty_pend"] = ov["long_inv"]

        # Short exit — buy at best_bid + 1
        if ov["short_inv"] > 0:
            exit_px = best_bid + 1
            if exit_px < best_ask:
                result.append(Order(product, exit_px, ov["short_inv"]))
                ov["short_exit_px_pend"]  = exit_px
                ov["short_exit_qty_pend"] = ov["short_inv"]

        # Long entry — passive bid at 10003
        if ov["long_inv"] == 0:
            room = max(0, pos_lim - pos)
            sz = min(entry_size, room)
            if sz > 0 and long_entry_px < best_ask:
                result.append(Order(product, long_entry_px, sz))
                ov["long_entry_px_pend"]  = long_entry_px
                ov["long_entry_qty_pend"] = sz

        # Short entry — passive ask at 10005
        if ov["short_inv"] == 0:
            room = max(0, pos_lim + pos)
            sz = min(entry_size, room)
            if sz > 0 and short_entry_px > best_bid:
                result.append(Order(product, short_entry_px, -sz))
                ov["short_entry_px_pend"]  = short_entry_px
                ov["short_entry_qty_pend"] = sz

        logger.print("l_inv", ov["long_inv"], "s_inv", ov["short_inv"],
                     "bid", best_bid, "ask", best_ask)

        return result, ov
