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
        result['ASH_COATED_OSMIUM'], ash_data = self.ash(state, shared)
        result['INTARIAN_PEPPER_ROOT'], root_data = self.root(state, shared)
        traderData = json.dumps({**ash_data, **root_data})
        logger.flush(state, result, conversions, traderData)
        return result, conversions, traderData

    def root(self, state: TradingState, shared: dict):
        product = 'INTARIAN_PEPPER_ROOT'
        result = []
        pos = state.position.get(product, 0)
        pos_lim = 80
        first_ask = shared.get("first_ask")

        if product not in state.order_depths:
            return result, {"first_ask": first_ask}

        order_depth = state.order_depths[product]

        if not order_depth.sell_orders:
            return result, {"first_ask": first_ask}

        best_ask = min(order_depth.sell_orders.keys())

        if first_ask is None:
            first_ask = best_ask

        if pos < 76 and (best_ask <= first_ask + 2 or state.timestamp >= 2000):
            qty = min(76 - pos, abs(order_depth.sell_orders[best_ask]))
            if qty > 0:
                result.append(Order(product, best_ask, qty))
        elif pos < pos_lim:
            if order_depth.buy_orders:
                best_bid = max(order_depth.buy_orders.keys())
                result.append(Order(product, best_bid + 1, pos_lim - pos))

        return result, {"first_ask": first_ask}

    def ash(self, state: TradingState, shared: dict):
        product = 'ASH_COATED_OSMIUM'
        result = []
        pos_lim        = 80
        ov_pos_lim     = 2   # overlay gets 2 units (1 long + 1 short)
        base_pos_lim   = pos_lim - ov_pos_lim  # baseline gets 78
        quote_lim      = 10
        sma_window     = 5
        entry_size     = 1
        long_entry_px  = 10003
        short_entry_px = 10005
        long_exit_px   = 10008
        short_exit_px  = 9995

        bid_hist = shared.get("bid_hist", [])
        ask_hist = shared.get("ask_hist", [])
        ov = shared.get("ov", {})
        ov.setdefault("long_inv",  0)
        ov.setdefault("short_inv", 0)
        ov.setdefault("long_entry_px_pend",  0);  ov.setdefault("long_entry_qty_pend",  0)
        ov.setdefault("long_exit_px_pend",   0);  ov.setdefault("long_exit_qty_pend",   0)
        ov.setdefault("short_entry_px_pend", 0);  ov.setdefault("short_entry_qty_pend", 0)
        ov.setdefault("short_exit_px_pend",  0);  ov.setdefault("short_exit_qty_pend",  0)
        ov.setdefault("seen", [])

        if product not in state.order_depths:
            return result, {"bid_hist": bid_hist, "ask_hist": ask_hist, "ov": ov}

        order_depth = state.order_depths[product]
        bids = sorted(order_depth.buy_orders, reverse=True)
        asks = sorted(order_depth.sell_orders)

        curr_best_bid = bids[0] if bids else None
        curr_best_ask = asks[0] if asks else None

        best_bid = curr_best_bid if curr_best_bid is not None else (bid_hist[-1] if bid_hist else None)
        best_ask = curr_best_ask if curr_best_ask is not None else (ask_hist[-1] if ask_hist else None)

        if best_bid is not None:
            bid_hist.append(best_bid)
        if best_ask is not None:
            ask_hist.append(best_ask)
        if len(bid_hist) > sma_window:
            bid_hist.pop(0)
        if len(ask_hist) > sma_window:
            ask_hist.pop(0)

        ash_data = {"bid_hist": bid_hist, "ask_hist": ask_hist, "ov": ov}

        if len(bid_hist) < sma_window or len(ask_hist) < sma_window:
            return result, ash_data

        bid_sma = sum(bid_hist) / sma_window
        ask_sma = sum(ask_hist) / sma_window
        fv = (bid_sma + ask_sma) / 2.0

        pos = state.position.get(product, 0)

        # fill attributes
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

        if best_ask is None or best_bid is None:
            return result, ash_data

        # ov_net = overlay's own contribution to pos; base_pos = baseline's clean position
        ov_net   = ov["long_inv"] - ov["short_inv"]
        base_pos = pos - ov_net

        # ── Overlay (2 units, fully independent) ─────────────────────────────
        ov_orders = []

        if ov["long_inv"] > 0:
            if long_exit_px > best_bid:
                ov_orders.append(Order(product, long_exit_px, -ov["long_inv"]))
                ov["long_exit_px_pend"]  = long_exit_px
                ov["long_exit_qty_pend"] = ov["long_inv"]
        else:
            if sz := min(entry_size, max(0, pos_lim - pos)):
                ov_orders.append(Order(product, long_entry_px, sz))
                ov["long_entry_px_pend"]  = long_entry_px
                ov["long_entry_qty_pend"] = sz

        if ov["short_inv"] > 0:
            if short_exit_px < best_ask:
                ov_orders.append(Order(product, short_exit_px, ov["short_inv"]))
                ov["short_exit_px_pend"]  = short_exit_px
                ov["short_exit_qty_pend"] = ov["short_inv"]
        else:
            if sz := min(entry_size, max(0, pos_lim + pos)):
                ov_orders.append(Order(product, short_entry_px, -sz))
                ov["short_entry_px_pend"]  = short_entry_px
                ov["short_entry_qty_pend"] = sz

        logger.print("fv", round(fv, 1),
                     "l_inv", ov["long_inv"], "s_inv", ov["short_inv"], "base_pos", base_pos)

        # ── Baseline (78 units, sees only its own clean position) ────────────
        buy_qty  = min(quote_lim, max(0, base_pos_lim - base_pos))
        sell_qty = min(quote_lim, max(0, base_pos_lim + base_pos))

        buy_threshold  = fv + (1 if base_pos < -15 else 0)
        sell_threshold = fv - (1 if base_pos > 15 else 0)

        for ask_px in asks:
            if ask_px <= buy_threshold and buy_qty > 0 and base_pos <= 40:
                result.append(Order(product, ask_px, buy_qty))
                buy_qty = 0
                break

        for bid_px in bids:
            if bid_px >= sell_threshold and sell_qty > 0 and base_pos >= -40:
                result.append(Order(product, bid_px, -sell_qty))
                sell_qty = 0
                break

        passive_bid = next((p for p in bids if p + 1 <= fv), None)
        if passive_bid is None and best_bid is not None and best_bid + 1 <= fv:
            passive_bid = best_bid

        passive_ask = next((p for p in asks if p - 1 >= fv), None)
        if passive_ask is None and best_ask is not None and best_ask - 1 >= fv:
            passive_ask = best_ask

        if passive_bid is not None and buy_qty > 0:
            result.append(Order(product, passive_bid + 1, buy_qty))

        if passive_ask is not None and sell_qty > 0:
            result.append(Order(product, passive_ask - 1, -sell_qty))


        return ov_orders + result, ash_data
