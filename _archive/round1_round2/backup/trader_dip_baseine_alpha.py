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
        # Alpha overlay params (dip signal)
        # ---------------------------
        alpha_bid_px = 10003
        alpha_entry_size = 10
        alpha_pos_cap = 10          # max alpha-owned inventory at any time
        alpha_edge = 6              # floor = fill_price + alpha_edge
        alpha_pos_gate = 40         # stop alpha entries when overall pos >= this

        drift_tolerance = 3

        ash_data = {
            "bid_hist": [],
            "ask_hist": [],
            "mid_hist": [],
            "alpha_lots": [],
            "seen_fills": [],
            "pending_alpha_bid_qty": 0,
            "pending_alpha_exit_orders": {},
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
        ash_data.setdefault("alpha_lots", [])
        ash_data.setdefault("seen_fills", [])
        ash_data.setdefault("pending_alpha_bid_qty", 0)
        ash_data.setdefault("pending_alpha_exit_orders", {})
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
        # ---------------------------
        seen = ash_data["seen_fills"]
        seen_set = set(seen)

        pending_alpha_bid_qty = int(ash_data.get("pending_alpha_bid_qty", 0))
        pending_alpha_exit_orders = {
            int(px): int(qty)
            for px, qty in ash_data.get("pending_alpha_exit_orders", {}).items()
        }
        pending_baseline_buy_orders = {
            int(px): int(qty)
            for px, qty in ash_data.get("pending_baseline_buy_orders", {}).items()
        }
        pending_baseline_sell_orders = {
            int(px): int(qty)
            for px, qty in ash_data.get("pending_baseline_sell_orders", {}).items()
        }

        alpha_lots = [
            {"px": int(lot["px"]), "qty": int(lot["qty"])}
            for lot in ash_data.get("alpha_lots", [])
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
                if pending_alpha_bid_qty > 0 and px <= alpha_bid_px and qty > 0:
                    matched = min(qty, pending_alpha_bid_qty)
                    alpha_lots.append({"px": px, "qty": matched})
                    pending_alpha_bid_qty -= matched
                    qty -= matched

                if qty > 0 and px in pending_baseline_buy_orders and pending_baseline_buy_orders[px] > 0:
                    matched = min(qty, pending_baseline_buy_orders[px])
                    pending_baseline_buy_orders[px] -= matched
                    qty -= matched

            else:
                if px in pending_alpha_exit_orders and pending_alpha_exit_orders[px] > 0 and qty > 0:
                    matched = min(qty, pending_alpha_exit_orders[px])
                    pending_alpha_exit_orders[px] -= matched
                    qty -= matched

                    remaining = matched
                    while remaining > 0 and alpha_lots:
                        lot = alpha_lots[0]
                        take = min(lot["qty"], remaining)
                        lot["qty"] -= take
                        remaining -= take
                        if lot["qty"] == 0:
                            alpha_lots.pop(0)

                if qty > 0 and px in pending_baseline_sell_orders and pending_baseline_sell_orders[px] > 0:
                    matched = min(qty, pending_baseline_sell_orders[px])
                    pending_baseline_sell_orders[px] -= matched
                    qty -= matched

        if len(seen) > 100:
            ash_data["seen_fills"] = seen[-100:]
        else:
            ash_data["seen_fills"] = seen

        alpha_lots = [lot for lot in alpha_lots if lot["qty"] > 0]
        alpha_inv = sum(lot["qty"] for lot in alpha_lots)

        # ---------------------------
        # Drift reconciliation
        # ---------------------------
        pos = state.position.get(symbol, 0)

        if alpha_inv > max(0, pos):
            target = max(0, pos)
            logger.print(
                "BIG DRIFT alpha>pos",
                "ts", state.timestamp,
                "pos", pos,
                "alpha_inv", alpha_inv,
                "target", target
            )
            excess = alpha_inv - target
            while excess > 0 and alpha_lots:
                lot = alpha_lots[0]
                take = min(lot["qty"], excess)
                lot["qty"] -= take
                excess -= take
                if lot["qty"] == 0:
                    alpha_lots.pop(0)
            alpha_inv = sum(lot["qty"] for lot in alpha_lots)

        drift = pos - alpha_inv
        if abs(drift) > pos_limit:
            logger.print(
                "BIG DRIFT impossible",
                "ts", state.timestamp,
                "pos", pos,
                "alpha_inv", alpha_inv,
                "implied_baseline", drift
            )

        ash_data["alpha_lots"] = alpha_lots

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
        baseline_effective_pos = pos - alpha_inv

        buy_capacity = max(0, pos_limit - pos)
        sell_capacity = max(0, pos_limit + baseline_effective_pos)

        logger.print(
            "fv", fair_value,
            "z", zscore,
            "spread", spread,
            "pos", pos,
            "alpha_inv", alpha_inv,
            "baseline_eff_pos", baseline_effective_pos
        )

        # ==========================================================
        # ALPHA OVERLAY
        # ==========================================================

        # 1) Alpha entry: gated on overall pos to prevent runaway accumulation
        new_pending_alpha_bid_qty = 0
        alpha_entry_room = max(0, alpha_pos_cap - alpha_inv)
        alpha_entry_room = min(alpha_entry_room, buy_capacity)

        # GATE: stop new alpha entries when overall position is already long
        if pos >= alpha_pos_gate:
            alpha_entry_room = 0

        if alpha_entry_room > 0:
            alpha_bid_qty = min(alpha_entry_size, alpha_entry_room)
            if alpha_bid_qty > 0:
                result.append(Order(symbol, alpha_bid_px, alpha_bid_qty))
                new_pending_alpha_bid_qty = alpha_bid_qty

        # 2) Alpha exits: unchanged, always allowed so existing lots can unwind
        new_pending_alpha_exit_orders = {}

        if curr_best_ask is not None and curr_best_bid is not None and alpha_lots:
            exit_qty_by_px = {}

            for lot in alpha_lots:
                floor = lot["px"] + alpha_edge
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
                new_pending_alpha_exit_orders[str(px)] = qty

        reserved_buy_prices = set()
        if new_pending_alpha_bid_qty > 0:
            reserved_buy_prices.add(alpha_bid_px)
        reserved_sell_prices = {int(px) for px in new_pending_alpha_exit_orders.keys()}

        baseline_buy_capacity = max(0, buy_capacity - new_pending_alpha_bid_qty)
        baseline_sell_capacity = sell_capacity

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

        # Middle-ground active sell: post at ask - 1 instead of hitting bid
        if bids and asks:
            bid_px = bids[0]
            ask_px = asks[0]
            sell_signal = (bid_px >= fair_value) or (zscore > z_threshold and bid_px >= fair_value - 1)

            if (
                sell_signal
                and baseline_sell_capacity > 0
                and baseline_effective_pos >= -40
            ):
                sell_px = ask_px - 1
                if sell_px <= bid_px:
                    sell_px = ask_px

                if sell_px not in reserved_sell_prices:
                    vol = min(active_lim, baseline_sell_capacity)
                    if vol > 0:
                        result.append(Order(symbol, sell_px, -vol))
                        new_pending_baseline_sell_orders[str(sell_px)] = (
                            new_pending_baseline_sell_orders.get(str(sell_px), 0) + vol
                        )
                        baseline_sell_capacity -= vol

        passive_bid = next((p for p in bids if p + 1 <= fair_value), None) if fair_value is not None else best_bid
        if passive_bid is None and best_bid is not None and (fair_value is None or best_bid + 1 <= fair_value):
            passive_bid = best_bid

        passive_ask = next((p for p in asks if p - 1 >= fair_value), None) if fair_value is not None else best_ask
        if passive_ask is None and best_ask is not None and (fair_value is None or best_ask - 1 >= fair_value):
            passive_ask = best_ask

        if passive_bid is not None and baseline_buy_capacity > 0:
            px = passive_bid + 1
            if px not in reserved_buy_prices:
                result.append(Order(symbol, px, baseline_buy_capacity))
                new_pending_baseline_buy_orders[str(px)] = (
                    new_pending_baseline_buy_orders.get(str(px), 0) + baseline_buy_capacity
                )

        if passive_ask is not None and baseline_sell_capacity > 0:
            px = passive_ask - 1
            if px not in reserved_sell_prices:
                result.append(Order(symbol, px, -baseline_sell_capacity))
                new_pending_baseline_sell_orders[str(px)] = (
                    new_pending_baseline_sell_orders.get(str(px), 0) + baseline_sell_capacity
                )

        # ---------------------------
        # Save pending orders for next-tick attribution
        # ---------------------------
        ash_data["pending_alpha_bid_qty"] = new_pending_alpha_bid_qty
        ash_data["pending_alpha_exit_orders"] = new_pending_alpha_exit_orders
        ash_data["pending_baseline_buy_orders"] = new_pending_baseline_buy_orders
        ash_data["pending_baseline_sell_orders"] = new_pending_baseline_sell_orders

        return result, ash_data