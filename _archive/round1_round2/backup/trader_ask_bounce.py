from datamodel import OrderDepth, TradingState, Order
from typing import Dict, List, Tuple
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

        result["ASH_COATED_OSMIUM"], ash_data = self.ash(state)

        traderData = json.dumps({
            "ash_data": ash_data
        })

        logger.flush(state, dict(result), conversions, traderData)
        return dict(result), conversions, traderData

    def ash(self, state: TradingState):
        result = []
        symbol = "ASH_COATED_OSMIUM"

        resting_bid_px = 10003
        min_bounce_trigger = 6     # only start exiting if best ask has recovered by 6
        entry_size = 10
        pos_limit = 80
        dip_pos_cap = 10

        ash_data = {
            "dip_lots": [],
            "seen_fills": []
        }

        # ---------------------------
        # Load persistent state
        # ---------------------------
        if state.traderData:
            try:
                parsed_data = json.loads(state.traderData)
                if "ash_data" in parsed_data:
                    ash_data = parsed_data["ash_data"]
            except json.JSONDecodeError:
                pass

        ash_data.setdefault("dip_lots", [])
        ash_data.setdefault("seen_fills", [])

        if symbol not in state.order_depths:
            return result, ash_data

        order_depth = state.order_depths[symbol]
        curr_best_bid = max(order_depth.buy_orders.keys()) if order_depth.buy_orders else None
        curr_best_ask = min(order_depth.sell_orders.keys()) if order_depth.sell_orders else None

        # ---------------------------
        # Read new fills from own_trades
        # ---------------------------
        seen = ash_data["seen_fills"]
        seen_set = set(seen)

        for t in state.own_trades.get(symbol, []):
            sig = f"{t.timestamp}|{t.price}|{t.quantity}|{t.buyer}|{t.seller}"
            if sig in seen_set:
                continue

            seen.append(sig)
            seen_set.add(sig)

            px = int(t.price)
            qty = abs(int(t.quantity))

            # Entry fills
            if px <= resting_bid_px:
                ash_data["dip_lots"].append({"price": px, "qty": qty})

            # Exit fills
            else:
                remaining = qty
                while remaining > 0 and ash_data["dip_lots"]:
                    lot = ash_data["dip_lots"][0]
                    take = min(lot["qty"], remaining)
                    lot["qty"] -= take
                    remaining -= take
                    if lot["qty"] == 0:
                        ash_data["dip_lots"].pop(0)

        # bound memory
        if len(seen) > 50:
            ash_data["seen_fills"] = seen[-50:]
        else:
            ash_data["seen_fills"] = seen

        ash_data["dip_lots"] = [lot for lot in ash_data["dip_lots"] if lot["qty"] > 0]

        # ---------------------------
        # Capacity / position
        # ---------------------------
        pos = state.position.get(symbol, 0)
        buy_capacity = max(0, pos_limit - pos)
        sell_capacity = max(0, pos_limit + pos)

        open_dip_qty = sum(lot["qty"] for lot in ash_data["dip_lots"])

        logger.print(
            "best_bid", curr_best_bid,
            "best_ask", curr_best_ask,
            "pos", pos,
            "open_dip_qty", open_dip_qty
        )

        # ==========================================================
        # 1) ALWAYS keep a resting bid at 10003
        # ==========================================================
        if open_dip_qty < dip_pos_cap and buy_capacity > 0:
            bid_qty = min(entry_size, dip_pos_cap - open_dip_qty, buy_capacity)
            if bid_qty > 0:
                result.append(Order(symbol, resting_bid_px, bid_qty))

        # ==========================================================
        # 2) After actual fill, exit at best_ask - 1
        #    BUT only after enough bounce
        # ==========================================================
        if (
            curr_best_ask is not None
            and curr_best_bid is not None
            and sell_capacity > 0
            and ash_data["dip_lots"]
        ):
            exit_qty_by_px = {}
            remaining_sell_capacity = sell_capacity

            for lot in ash_data["dip_lots"]:
                if remaining_sell_capacity <= 0:
                    break

                # only try exiting if ask has bounced enough from this lot's entry
                if curr_best_ask >= lot["price"] + min_bounce_trigger:
                    qty = min(lot["qty"], remaining_sell_capacity)
                    if qty > 0:
                        # target exit = best ask - 1
                        exit_px = curr_best_ask - 1

                        # make sure it is still a valid passive-ish ask
                        # if spread is only 1, this becomes best ask instead
                        if exit_px <= curr_best_bid:
                            exit_px = curr_best_bid + 1

                        if exit_px > curr_best_ask:
                            exit_px = curr_best_ask

                        exit_qty_by_px[exit_px] = exit_qty_by_px.get(exit_px, 0) + qty
                        remaining_sell_capacity -= qty

            for px, qty in exit_qty_by_px.items():
                result.append(Order(symbol, px, -qty))

        return result, ash_data