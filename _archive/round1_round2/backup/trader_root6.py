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


class Trader:
    def run(self, state: TradingState):
        result=defaultdict(list)
        conversions=0
        #result['EMERALDS']=self.emeralds(state)
        result['ASH_COATED_OSMIUM'], traderData = self.ash(state)
        logger.flush(state, result, conversions, traderData)
        return result, conversions, traderData
    
    def ash(self,state: TradingState):
        result=[]
        pos_lim=80
        quote_lim=10
        last_bid=None
        last_ask=None
        if state.traderData:
            try:
                ash_data=json.loads(state.traderData)
                last_bid=ash_data.get("last_bid")
                last_ask=ash_data.get("last_ask")
            except json.JSONDecodeError:
                pass
        if 'ASH_COATED_OSMIUM' not in state.order_depths:
            return result, json.dumps({"last_bid": last_bid, "last_ask": last_ask})
        order_depth=state.order_depths['ASH_COATED_OSMIUM']
        bids=sorted(order_depth.buy_orders,reverse=True)
        asks=sorted(order_depth.sell_orders)
        curr_best_bid = bids[0] if len(bids)>=1 else None
        curr_best_ask = asks[0] if len(asks)>=1 else None
        best_bid = curr_best_bid if curr_best_bid is not None else last_bid
        best_ask = curr_best_ask if curr_best_ask is not None else last_ask
        pos = state.position.get('ASH_COATED_OSMIUM', 0)
        buy_qty = min(quote_lim, pos_lim - pos)
        sell_qty = min(quote_lim, pos_lim + pos)
        pop_bid = max(bids, key=lambda p: order_depth.buy_orders[p]) if bids else None
        pop_ask = max(asks, key=lambda p: abs(order_depth.sell_orders[p])) if asks else None
        fv_bid = pop_bid if pop_bid is not None else last_bid
        fv_ask = pop_ask if pop_ask is not None else last_ask
        fair_value = None
        if fv_bid is not None and fv_ask is not None:
            fair_value = round((fv_bid + fv_ask) / 2)
            #active taking
            for ask_px in asks:
                if ask_px<=fair_value and buy_qty!=0 and pos<=40:
                    result.append(Order('ASH_COATED_OSMIUM',ask_px,buy_qty))
                    buy_qty=0
                    break
            for bid_px in bids:
                if bid_px>=fair_value and sell_qty!=0 and pos>=-40:
                    result.append(Order('ASH_COATED_OSMIUM', bid_px, -sell_qty))
                    sell_qty=0
                    break
        #Passive making
        if best_bid is not None and buy_qty!=0 and (fair_value is None or best_bid+1<=fair_value):
            result.append(Order('ASH_COATED_OSMIUM', best_bid+1, buy_qty))
        if best_ask is not None and sell_qty!=0 and (fair_value is None or best_ask-1>=fair_value):
            result.append(Order('ASH_COATED_OSMIUM', best_ask-1, -sell_qty))
        return result, json.dumps({"last_bid": best_bid, "last_ask": best_ask})
    
    def root(self, state: TradingState):
            product = "INTARIAN_PEPPER_ROOT"
            pos = state.position.get(product, 0)
            pos_lim = 80
            res = []

            root_data = {}

            if product not in state.order_depths:
                return res, root_data

            order_depth = state.order_depths[product]

            if not order_depth.buy_orders or not order_depth.sell_orders:
                return res, root_data

            best_bid = max(order_depth.buy_orders.keys())
            best_ask = min(order_depth.sell_orders.keys())

            remaining = pos_lim - pos
            if remaining <= 0:
                return res, root_data

            # hard cap: only buy if ask is at or below this level
            price_cap = 12007

            if best_ask <= price_cap:
                for ask_px in sorted(order_depth.sell_orders.keys()):
                    if remaining <= 0:
                        break

                    # do not buy above the cap
                    if ask_px > price_cap:
                        break

                    ask_vol = abs(order_depth.sell_orders[ask_px])
                    qty = min(remaining, ask_vol)

                    if qty > 0:
                        res.append(Order(product, ask_px, qty))
                        remaining -= qty

            return res, root_data