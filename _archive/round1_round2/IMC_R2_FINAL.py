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
    def bid(self):
        return 1
    def run(self, state: TradingState):
        result=defaultdict(list)
        conversions=0
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
        peak_price = shared.get("peak_price")
        exited = shared.get("exited", False)

        root_data = {"first_ask": first_ask, "peak_price": peak_price, "exited": exited}

        if product not in state.order_depths:
            return result, root_data

        order_depth = state.order_depths[product]
        best_bid = max(order_depth.buy_orders.keys()) if order_depth.buy_orders else None
        best_ask = min(order_depth.sell_orders.keys()) if order_depth.sell_orders else None

        # Update peak and trailing stop guard
        if best_bid is not None and best_ask is not None:
            mid_price = (best_bid + best_ask) / 2.0
            if peak_price is None:
                peak_price = mid_price
            else:
                peak_price = max(peak_price, mid_price)
            if not exited and mid_price < peak_price - 50:
                exited = True
            elif exited and mid_price > peak_price - 25:
                exited = False
            root_data = {"first_ask": first_ask, "peak_price": peak_price, "exited": exited}

        if exited:
            # Sell available volume at best bid only
            if best_bid is not None and pos > 0:
                sell_qty = min(order_depth.buy_orders[best_bid], pos)
                if sell_qty > 0:
                    result.append(Order(product, best_bid, -sell_qty))
            return result, root_data

        if best_ask is None:
            return result, root_data

        if first_ask is None:
            first_ask = best_ask
            root_data["first_ask"] = first_ask

        # sweep to 76 using best ask within first_ask + 2, or fallback after ts 2000
        if pos < 76 and (best_ask <= first_ask + 2 or state.timestamp >= 2000):
            qty = min(76 - pos, abs(order_depth.sell_orders[best_ask]))
            if qty > 0:
                result.append(Order(product, best_ask, qty))
        # penny jump to fill remaining capacity
        elif pos < pos_lim:
            if best_bid is not None:
                result.append(Order(product, best_bid + 1, pos_lim - pos))

        return result, root_data
    
    def ash(self, state: TradingState, shared: dict):
        result=[]
        pos_lim=80
        quote_lim=10
        sma_window=5
        # Deserialize SMA history
        bid_hist=shared.get("bid_hist", [])
        ask_hist=shared.get("ask_hist", [])
        if 'ASH_COATED_OSMIUM' not in state.order_depths:
            return result, {"bid_hist": bid_hist, "ask_hist": ask_hist}
        order_depth=state.order_depths['ASH_COATED_OSMIUM']
        bids=sorted(order_depth.buy_orders,reverse=True)
        asks=sorted(order_depth.sell_orders)
        curr_best_bid = bids[0] if len(bids)>=1 else None
        curr_best_ask = asks[0] if len(asks)>=1 else None
        # Forward fill from history
        best_bid = curr_best_bid if curr_best_bid is not None else (bid_hist[-1] if bid_hist else None)
        best_ask = curr_best_ask if curr_best_ask is not None else (ask_hist[-1] if ask_hist else None)
        # Update SMA history
        if best_bid is not None:
            bid_hist.append(best_bid)
        if best_ask is not None:
            ask_hist.append(best_ask)
        if len(bid_hist) > sma_window:
            bid_hist.pop(0)
        if len(ask_hist) > sma_window:
            ask_hist.pop(0)
        # Warmup — skip first 4 ticks
        if len(bid_hist) < sma_window or len(ask_hist) < sma_window:
            return result, {"bid_hist": bid_hist, "ask_hist": ask_hist}
        # SMA-5 fair value — float, not rounded
        bid_sma = sum(bid_hist) / sma_window
        ask_sma = sum(ask_hist) / sma_window
        fair_value = (bid_sma + ask_sma) / 2.0
        pos = state.position.get('ASH_COATED_OSMIUM', 0)
        buy_qty = min(quote_lim, pos_lim - pos)
        sell_qty = min(quote_lim, pos_lim + pos)
        # One-sided book fallback to last known best bid/ask
        best_bid = curr_best_bid if curr_best_bid is not None else (bid_hist[-1] if bid_hist else None)
        best_ask = curr_best_ask if curr_best_ask is not None else (ask_hist[-1] if ask_hist else None)
        if fair_value is not None:
            #active taking — relax threshold by 1 tick when position beyond ±15 to flatten
            buy_threshold = fair_value + (1 if pos < -15 else 0)
            sell_threshold = fair_value - (1 if pos > 15 else 0)
            for ask_px in asks:
                if ask_px<=buy_threshold and buy_qty!=0 and pos<=40:
                    result.append(Order('ASH_COATED_OSMIUM',ask_px,buy_qty))
                    buy_qty=0
                    break
            for bid_px in bids:
                if bid_px>=sell_threshold and sell_qty!=0 and pos>=-40:
                    result.append(Order('ASH_COATED_OSMIUM', bid_px, -sell_qty))
                    sell_qty=0
                    break
        #Passive making — step down/up through book to find best level within FV, fallback to last known
        passive_bid = next((p for p in bids if p+1<=fair_value), None) if fair_value is not None else best_bid
        if passive_bid is None and best_bid is not None and (fair_value is None or best_bid+1<=fair_value):
            passive_bid = best_bid
        passive_ask = next((p for p in asks if p-1>=fair_value), None) if fair_value is not None else best_ask
        if passive_ask is None and best_ask is not None and (fair_value is None or best_ask-1>=fair_value):
            passive_ask = best_ask
        if passive_bid is not None and buy_qty!=0:
            result.append(Order('ASH_COATED_OSMIUM', passive_bid+1, buy_qty))
        if passive_ask is not None and sell_qty!=0:
            result.append(Order('ASH_COATED_OSMIUM', passive_ask-1, -sell_qty))
        return result, {"bid_hist": bid_hist, "ask_hist": ask_hist}