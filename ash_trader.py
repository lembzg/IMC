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
        traderData=""
        #result['EMERALDS']=self.emeralds(state)
        result['ASH_COATED_OSMIUM'] = self.ash(state)
        logger.flush(state, result, conversions, traderData)
        return result, conversions, traderData
    
    def ash(self,state: TradingState):
        result=[]
        pos_lim=80
        quote_lim=10
        if 'ASH_COATED_OSMIUM' not in state.order_depths:
            return result
        order_depth=state.order_depths['ASH_COATED_OSMIUM']
        bids=sorted(order_depth.buy_orders,reverse=True)
        asks=sorted(order_depth.sell_orders)
        if len(bids)<1 or len(asks)<1:
            return result
        else:
            vwap_bid = sum(p * order_depth.buy_orders[p] for p in bids) / sum(order_depth.buy_orders[p] for p in bids)
            vwap_ask = sum(p * abs(order_depth.sell_orders[p]) for p in asks) / sum(abs(order_depth.sell_orders[p]) for p in asks)
            fair_value = round((vwap_bid + vwap_ask) / 2)
            buy_px = fair_value - 8
            sell_px = fair_value + 8
            pos = state.position.get('ASH_COATED_OSMIUM', 0)
            buy_qty = min(quote_lim, pos_lim - pos)
            sell_qty = min(quote_lim, pos_lim + pos)
        #FV Taking to reduce position
        if pos>0 and fair_value in order_depth.buy_orders:
            fv_qty=min(pos, order_depth.buy_orders[fair_value])
            result.append(Order('ASH_COATED_OSMIUM', fair_value, -fv_qty))
        if pos<0 and fair_value in order_depth.sell_orders:
            fv_qty=min(-pos, abs(order_depth.sell_orders[fair_value]))
            result.append(Order('ASH_COATED_OSMIUM', fair_value, fv_qty))
        if buy_qty!=0:
            result.append(Order('ASH_COATED_OSMIUM', buy_px, buy_qty))
        if sell_qty!=0:
            result.append(Order('ASH_COATED_OSMIUM', sell_px, -sell_qty))
        return result