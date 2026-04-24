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

        # ---------------------------
        # Baseline params
        # ---------------------------
        sma_window = 5
        z_window = 20
        z_threshold = 2.25
        active_lim = 10
        pos_limit = 80

        # ---------------------------
        # Alpha LONG overlay (dip buy)
        # ---------------------------
        alpha_long_enabled = True
        alpha_bid_px = 10003
        alpha_long_size = 10
        alpha_long_cap = 10
        alpha_long_edge = 6
        alpha_long_gate = 40

        # ---------------------------
        # Alpha SHORT overlay (spike short)
        # ---------------------------
        alpha_short_enabled = True
        alpha_ask_px = 10005
        alpha_short_size = 10
        alpha_short_cap = 10
        alpha_short_edge = 6
        alpha_short_gate = -40

        ash_data = {
            "bid_hist": [],
            "ask_hist": [],
            "mid_hist": [],
            "alpha_long_lots": [],
            "alpha_short_lots": [],
            "seen_fills": [],
            "pending_alpha_long_bid_qty": 0,
            "pending_alpha_long_exit_orders": {},
            "pending_alpha_short_ask_qty": 0,
            "pending_alpha_short_exit_orders": {},
            "pending_baseline_buy_orders": {},
            "pending_baseline_sell_orders": {}
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

        ash_data.setdefault("bid_hist", [])
        ash_data.setdefault("ask_hist", [])
        ash_data.setdefault("mid_hist", [])
        ash_data.setdefault("alpha_long_lots", [])
        ash_data.setdefault("alpha_short_lots", [])
        ash_data.setdefault("seen_fills", [])
        ash_data.setdefault("pending_alpha_long_bid_qty", 0)
        ash_data.setdefault("pending_alpha_long_exit_orders", {})
        ash_data.setdefault("pending_alpha_short_ask_qty", 0)
        ash_data.setdefault("pending_alpha_short_exit_orders", {})
        ash_data.setdefault("pending_baseline_buy_orders", {})
        ash_data.setdefault("pending_baseline_sell_orders", {})

        if symbol not in state.order_depths:
            return result, ash_data

        order_depth = state.order_depths[symbol]
        bids = sorted(order_depth.buy_orders.keys(), reverse=True)
        asks = sorted(order_depth.sell_orders.keys())

        curr_best_bid = bids[0] if bids else None
        curr_best_ask = asks[0] if asks else None

        # ---------------------------
        # Fill attribution
        # FIX: exact-price matching for alpha entries so they don't steal
        # fills that belong to alpha exits or baseline orders.
        # ---------------------------
        seen = ash_data["seen_fills"]
        seen_set = set(seen)

        pending_alpha_long_bid_qty = int(ash_data.get("pending_alpha_long_bid_qty", 0))
        pending_alpha_long_exit_orders = {
            int(px): int(qty)
            for px, qty in ash_data.get("pending_alpha_long_exit_orders", {}).items()
        }
        pending_alpha_short_ask_qty = int(ash_data.get("pending_alpha_short_ask_qty", 0))
        pending_alpha_short_exit_orders = {
            int(px): int(qty)
            for px, qty in ash_data.get("pending_alpha_short_exit_orders", {}).items()
        }
        pending_baseline_buy_orders = {
            int(px): int(qty)
            for px, qty in ash_data.get("pending_baseline_buy_orders", {}).items()
        }
        pending_baseline_sell_orders = {
            int(px): int(qty)
            for px, qty in ash_data.get("pending_baseline_sell_orders", {}).items()
        }

        alpha_long_lots = [
            {"px": int(lot["px"]), "qty": int(lot["qty"])}
            for lot in ash_data.get("alpha_long_lots", [])
            if int(lot.get("qty", 0)) > 0
        ]
        alpha_short_lots = [
            {"px": int(lot["px"]), "qty": int(lot["qty"])}
            for lot in ash_data.get("alpha_short_lots", [])
            if int(lot.get("qty", 0)) > 0
        ]

        for t in state.own_trades.get(symbol, []):
            sig = f"{t.timestamp}|{t.price}|{t.quantity}|{t.buyer}|{t.seller}"
            if sig in seen_set:
                continue

            seen.append(sig)
            seen_set.add(sig)

            px = int(t.price)
            raw_qty = int(t.quantity)
            qty = abs(raw_qty)

            is_buy = None
            if t.buyer == "SUBMISSION":
                is_buy = True
            elif t.seller == "SUBMISSION":
                is_buy = False
            else:
                is_buy = raw_qty > 0

            if is_buy:
                # 1) Alpha long entry: EXACT price match only
                if pending_alpha_long_bid_qty > 0 and px == alpha_bid_px and qty > 0:
                    matched = min(qty, pending_alpha_long_bid_qty)
                    alpha_long_lots.append({"px": px, "qty": matched})
                    pending_alpha_long_bid_qty -= matched
                    qty -= matched

                # 2) Alpha short exits: exact pending exit price
                if qty > 0 and px in pending_alpha_short_exit_orders and pending_alpha_short_exit_orders[px] > 0:
                    matched = min(qty, pending_alpha_short_exit_orders[px])
                    pending_alpha_short_exit_orders[px] -= matched
                    qty -= matched

                    remaining = matched
                    while remaining > 0 and alpha_short_lots:
                        lot = alpha_short_lots[0]
                        take = min(lot["qty"], remaining)
                        lot["qty"] -= take
                        remaining -= take
                        if lot["qty"] == 0:
                            alpha_short_lots.pop(0)

                # 3) Baseline buys: exact pending price
                if qty > 0 and px in pending_baseline_buy_orders and pending_baseline_buy_orders[px] > 0:
                    matched = min(qty, pending_baseline_buy_orders[px])
                    pending_baseline_buy_orders[px] -= matched
                    qty -= matched

            else:
                # 1) Alpha short entry: EXACT price match only
                if pending_alpha_short_ask_qty > 0 and px == alpha_ask_px and qty > 0:
                    matched = min(qty, pending_alpha_short_ask_qty)
                    alpha_short_lots.append({"px": px, "qty": matched})
                    pending_alpha_short_ask_qty -= matched
                    qty -= matched

                # 2) Alpha long exits: exact pending exit price
                if qty > 0 and px in pending_alpha_long_exit_orders and pending_alpha_long_exit_orders[px] > 0:
                    matched = min(qty, pending_alpha_long_exit_orders[px])
                    pending_alpha_long_exit_orders[px] -= matched
                    qty -= matched

                    remaining = matched
                    while remaining > 0 and alpha_long_lots:
                        lot = alpha_long_lots[0]
                        take = min(lot["qty"], remaining)
                        lot["qty"] -= take
                        remaining -= take
                        if lot["qty"] == 0:
                            alpha_long_lots.pop(0)

                # 3) Baseline sells: exact pending price
                if qty > 0 and px in pending_baseline_sell_orders and pending_baseline_sell_orders[px] > 0:
                    matched = min(qty, pending_baseline_sell_orders[px])
                    pending_baseline_sell_orders[px] -= matched
                    qty -= matched

        if len(seen) > 100:
            ash_data["seen_fills"] = seen[-100:]
        else:
            ash_data["seen_fills"] = seen

        alpha_long_lots = [lot for lot in alpha_long_lots if lot["qty"] > 0]
        alpha_short_lots = [lot for lot in alpha_short_lots if lot["qty"] > 0]
        alpha_long_inv = sum(lot["qty"] for lot in alpha_long_lots)
        alpha_short_inv = sum(lot["qty"] for lot in alpha_short_lots)

        # ---------------------------
        # Drift reconciliation
        # ---------------------------
        pos = state.position.get(symbol, 0)

        max_long_supported = max(0, pos + alpha_short_inv)
        if alpha_long_inv > max_long_supported:
            logger.print(
                "BIG DRIFT long>supported",
                "ts", state.timestamp,
                "pos", pos,
                "alpha_long_inv", alpha_long_inv,
                "alpha_short_inv", alpha_short_inv,
                "target", max_long_supported
            )
            excess = alpha_long_inv - max_long_supported
            while excess > 0 and alpha_long_lots:
                lot = alpha_long_lots[0]
                take = min(lot["qty"], excess)
                lot["qty"] -= take
                excess -= take
                if lot["qty"] == 0:
                    alpha_long_lots.pop(0)
            alpha_long_inv = sum(lot["qty"] for lot in alpha_long_lots)

        max_short_supported = max(0, -pos + alpha_long_inv)
        if alpha_short_inv > max_short_supported:
            logger.print(
                "BIG DRIFT short>supported",
                "ts", state.timestamp,
                "pos", pos,
                "alpha_long_inv", alpha_long_inv,
                "alpha_short_inv", alpha_short_inv,
                "target", max_short_supported
            )
            excess = alpha_short_inv - max_short_supported
            while excess > 0 and alpha_short_lots:
                lot = alpha_short_lots[0]
                take = min(lot["qty"], excess)
                lot["qty"] -= take
                excess -= take
                if lot["qty"] == 0:
                    alpha_short_lots.pop(0)
            alpha_short_inv = sum(lot["qty"] for lot in alpha_short_lots)

        alpha_net = alpha_long_inv - alpha_short_inv
        ash_data["alpha_long_lots"] = alpha_long_lots
        ash_data["alpha_short_lots"] = alpha_short_lots

        # ---------------------------
        # Forward-filled best bid / ask for history
        # ---------------------------
        hist_best_bid = curr_best_bid if curr_best_bid is not None else (
            ash_data["bid_hist"][-1] if ash_data["bid_hist"] else None
        )
        hist_best_ask = curr_best_ask if curr_best_ask is not None else (
            ash_data["ask_hist"][-1] if ash_data["ask_hist"] else None
        )

        if hist_best_bid is not None:
            ash_data["bid_hist"].append(hist_best_bid)
        if hist_best_ask is not None:
            ash_data["ask_hist"].append(hist_best_ask)
        if hist_best_bid is not None and hist_best_ask is not None:
            ash_data["mid_hist"].append((hist_best_bid + hist_best_ask) / 2.0)

        if len(ash_data["bid_hist"]) > sma_window:
            ash_data["bid_hist"].pop(0)
        if len(ash_data["ask_hist"]) > sma_window:
            ash_data["ask_hist"].pop(0)
        if len(ash_data["mid_hist"]) > z_window:
            ash_data["mid_hist"].pop(0)

        if len(ash_data["bid_hist"]) < sma_window or len(ash_data["ask_hist"]) < sma_window:
            bid_sma = hist_best_bid if hist_best_bid is not None else 9999.0
            ask_sma = hist_best_ask if hist_best_ask is not None else 9999.0
            fair_value = (bid_sma + ask_sma) / 2.0
            zscore = 0.0
        else:
            bid_sma = sum(ash_data["bid_hist"]) / sma_window
            ask_sma = sum(ash_data["ask_hist"]) / sma_window
            sma_fv = (bid_sma + ask_sma) / 2.0
            stable_fv = 9999.0
            fair_value = 0.5 * sma_fv + 0.5 * stable_fv

            zscore = 0.0
            if len(ash_data["mid_hist"]) >= z_window:
                mean_mid = sum(ash_data["mid_hist"]) / len(ash_data["mid_hist"])
                var_mid = sum((x - mean_mid) ** 2 for x in ash_data["mid_hist"]) / len(ash_data["mid_hist"])
                std_mid = var_mid ** 0.5
                if std_mid > 0:
                    best_bid_for_mid = curr_best_bid if curr_best_bid is not None else round(bid_sma)
                    best_ask_for_mid = curr_best_ask if curr_best_ask is not None else round(ask_sma)
                    current_mid = (best_bid_for_mid + best_ask_for_mid) / 2.0
                    zscore = (current_mid - mean_mid) / std_mid

        best_bid = curr_best_bid if curr_best_bid is not None else round(bid_sma)
        best_ask = curr_best_ask if curr_best_ask is not None else round(ask_sma)
        spread = best_ask - best_bid

        # ---------------------------
        # Capacities
        # ---------------------------
        baseline_effective_pos = pos - alpha_net

        buy_capacity = max(0, pos_limit - pos)
        sell_capacity_total = max(0, pos_limit + pos)
        baseline_sell_capacity = max(0, pos_limit + baseline_effective_pos)

        logger.print(
            "fv", fair_value,
            "z", zscore,
            "spread", spread,
            "pos", pos,
            "a_long", alpha_long_inv,
            "a_short", alpha_short_inv,
            "base_eff", baseline_effective_pos
        )

        # ==========================================================
        # ALPHA LONG OVERLAY (buy dip)
        # ==========================================================
        new_pending_alpha_long_bid_qty = 0
        if alpha_long_enabled:
            alpha_long_entry_room = max(0, alpha_long_cap - alpha_long_inv)
            alpha_long_entry_room = min(alpha_long_entry_room, buy_capacity)
            if pos >= alpha_long_gate:
                alpha_long_entry_room = 0

            if alpha_long_entry_room > 0:
                bid_qty = min(alpha_long_size, alpha_long_entry_room)
                if bid_qty > 0:
                    result.append(Order(symbol, alpha_bid_px, bid_qty))
                    new_pending_alpha_long_bid_qty = bid_qty

        new_pending_alpha_long_exit_orders = {}
        if alpha_long_enabled and curr_best_ask is not None and curr_best_bid is not None and alpha_long_lots:
            exit_qty_by_px = {}
            for lot in alpha_long_lots:
                floor = lot["px"] + alpha_long_edge
                if curr_best_ask >= floor:
                    exit_px = max(floor, curr_best_ask - 1)
                    if exit_px > curr_best_ask:
                        exit_px = curr_best_ask
                    if exit_px <= curr_best_bid:
                        exit_px = curr_best_bid + 1
                    if exit_px < floor:
                        continue
                    exit_qty_by_px[exit_px] = exit_qty_by_px.get(exit_px, 0) + lot["qty"]

            for px, qty in exit_qty_by_px.items():
                result.append(Order(symbol, px, -qty))
                new_pending_alpha_long_exit_orders[str(px)] = qty

        # ==========================================================
        # ALPHA SHORT OVERLAY (short spike)
        # ==========================================================
        new_pending_alpha_short_ask_qty = 0
        if alpha_short_enabled:
            alpha_short_entry_room = max(0, alpha_short_cap - alpha_short_inv)
            alpha_short_entry_room = min(alpha_short_entry_room, sell_capacity_total)
            if pos <= alpha_short_gate:
                alpha_short_entry_room = 0

            if alpha_short_entry_room > 0:
                ask_qty = min(alpha_short_size, alpha_short_entry_room)
                if ask_qty > 0:
                    result.append(Order(symbol, alpha_ask_px, -ask_qty))
                    new_pending_alpha_short_ask_qty = ask_qty

        new_pending_alpha_short_exit_orders = {}
        if alpha_short_enabled and curr_best_ask is not None and curr_best_bid is not None and alpha_short_lots:
            exit_qty_by_px = {}
            for lot in alpha_short_lots:
                ceiling = lot["px"] - alpha_short_edge
                if curr_best_bid <= ceiling:
                    exit_px = min(ceiling, curr_best_bid + 1)
                    if exit_px < curr_best_bid:
                        exit_px = curr_best_bid
                    if exit_px >= curr_best_ask:
                        exit_px = curr_best_ask - 1
                    if exit_px > ceiling:
                        continue
                    exit_qty_by_px[exit_px] = exit_qty_by_px.get(exit_px, 0) + lot["qty"]

            for px, qty in exit_qty_by_px.items():
                result.append(Order(symbol, px, qty))
                new_pending_alpha_short_exit_orders[str(px)] = qty

        # ---------------------------
        # Reserved prices
        # FIX: alpha entry prices are ALWAYS reserved (not just when we
        # post them this tick), so baseline can never post at those
        # exact prices. This keeps exact-price attribution unambiguous.
        # ---------------------------
        reserved_buy_prices = {alpha_bid_px}
        for px in new_pending_alpha_short_exit_orders.keys():
            reserved_buy_prices.add(int(px))

        reserved_sell_prices = {alpha_ask_px}
        for px in new_pending_alpha_long_exit_orders.keys():
            reserved_sell_prices.add(int(px))

        # ---------------------------
        # Adjust baseline capacities
        # TOTAL buys (alpha + baseline) must not exceed pos_limit - pos
        # TOTAL sells (alpha + baseline) must not exceed pos_limit + pos
        # Leave 1-unit safety buffer to avoid hitting limits exactly
        # ---------------------------
        safety = 1

        alpha_buy_total = (
            new_pending_alpha_long_bid_qty
            + sum(new_pending_alpha_short_exit_orders.values())
        )
        alpha_sell_total = (
            new_pending_alpha_short_ask_qty
            + sum(new_pending_alpha_long_exit_orders.values())
        )

        baseline_buy_capacity = max(0, buy_capacity - alpha_buy_total - safety)
        baseline_sell_capacity_adj = max(0, baseline_sell_capacity - alpha_sell_total - safety)

        # ==========================================================
        # BASELINE
        # ==========================================================
        new_pending_baseline_buy_orders = {}
        new_pending_baseline_sell_orders = {}

        if asks:
            ask_px = asks[0]
            buy_signal = (ask_px <= fair_value) or (zscore < -z_threshold and ask_px <= fair_value + 1)

            if (
                buy_signal
                and baseline_buy_capacity > 0
                and baseline_effective_pos <= 40
                and ask_px not in reserved_buy_prices
            ):
                vol = min(active_lim, baseline_buy_capacity, abs(order_depth.sell_orders[ask_px]))
                if vol > 0:
                    result.append(Order(symbol, ask_px, vol))
                    new_pending_baseline_buy_orders[str(ask_px)] = (
                        new_pending_baseline_buy_orders.get(str(ask_px), 0) + vol
                    )
                    baseline_buy_capacity -= vol

        if bids and asks:
            bid_px = bids[0]
            ask_px = asks[0]
            sell_signal = (bid_px >= fair_value) or (zscore > z_threshold and bid_px >= fair_value - 1)

            if (
                sell_signal
                and baseline_sell_capacity_adj > 0
                and baseline_effective_pos >= -40
            ):
                sell_px = ask_px - 1
                if sell_px <= bid_px:
                    sell_px = ask_px

                if sell_px not in reserved_sell_prices:
                    vol = min(active_lim, baseline_sell_capacity_adj)
                    if vol > 0:
                        result.append(Order(symbol, sell_px, -vol))
                        new_pending_baseline_sell_orders[str(sell_px)] = (
                            new_pending_baseline_sell_orders.get(str(sell_px), 0) + vol
                        )
                        baseline_sell_capacity_adj -= vol

        passive_bid = next((p for p in bids if p + 1 <= fair_value), None) if fair_value is not None else best_bid
        if passive_bid is None and best_bid is not None and (fair_value is None or best_bid + 1 <= fair_value):
            passive_bid = best_bid

        passive_ask = next((p for p in asks if p - 1 >= fair_value), None) if fair_value is not None else best_ask
        if passive_ask is None and best_ask is not None and (fair_value is None or best_ask - 1 >= fair_value):
            passive_ask = best_ask

        if passive_bid is not None and baseline_buy_capacity > 0:
            px = passive_bid + 1
            while px in reserved_buy_prices and px < best_ask - 1:
                px += 1
            if px not in reserved_buy_prices and (best_ask is None or px < best_ask):
                result.append(Order(symbol, px, baseline_buy_capacity))
                new_pending_baseline_buy_orders[str(px)] = (
                    new_pending_baseline_buy_orders.get(str(px), 0) + baseline_buy_capacity
                )

        if passive_ask is not None and baseline_sell_capacity_adj > 0:
            px = passive_ask - 1
            while px in reserved_sell_prices and px > best_bid + 1:
                px -= 1
            if px not in reserved_sell_prices and (best_bid is None or px > best_bid):
                result.append(Order(symbol, px, -baseline_sell_capacity_adj))
                new_pending_baseline_sell_orders[str(px)] = (
                    new_pending_baseline_sell_orders.get(str(px), 0) + baseline_sell_capacity_adj
                )

        # ---------------------------
        # Save pending orders
        # ---------------------------
        ash_data["pending_alpha_long_bid_qty"] = new_pending_alpha_long_bid_qty
        ash_data["pending_alpha_long_exit_orders"] = new_pending_alpha_long_exit_orders
        ash_data["pending_alpha_short_ask_qty"] = new_pending_alpha_short_ask_qty
        ash_data["pending_alpha_short_exit_orders"] = new_pending_alpha_short_exit_orders
        ash_data["pending_baseline_buy_orders"] = new_pending_baseline_buy_orders
        ash_data["pending_baseline_sell_orders"] = new_pending_baseline_sell_orders

        return result, ash_data