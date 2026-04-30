from datamodel import TradingState, Order
import json
from collections import defaultdict

POS_LIM   = 200
QUOTE_QTY = 6

class Logger:
    def __init__(self): self.logs = ""
    def print(self, *args, sep=" ", end="\n"): self.logs += sep.join(map(str, args)) + end
    def flush(self, state, orders, conversions, trader_data):
        print(json.dumps([[state.timestamp,state.traderData,[[l.symbol,l.product,l.denomination]for l in state.listings.values()],{s:[od.buy_orders,od.sell_orders]for s,od in state.order_depths.items()},[[t.symbol,t.price,t.quantity,t.buyer,t.seller,t.timestamp]for trades in state.own_trades.values()for t in trades],[[t.symbol,t.price,t.quantity,t.buyer,t.seller,t.timestamp]for trades in state.market_trades.values()for t in trades],dict(state.position),[state.observations.plainValueObservations,{p:[o.bidPrice,o.askPrice,o.transportFees,o.exportTariff,o.importTariff,o.sugarPrice,o.sunlightIndex]for p,o in state.observations.conversionObservations.items()}]],[[o.symbol,o.price,o.quantity]for arr in orders.values()for o in arr],conversions,trader_data,self.logs],separators=(",",":")))
        self.logs = ""

logger = Logger()


class Trader:
    def bid(self):
        return 1

    def run(self, state: TradingState):
        result = defaultdict(list)
        shared = {}
        if state.traderData:
            try: shared = json.loads(state.traderData)
            except: pass

        od = state.order_depths.get("HYDROGEL_PACK")
        if od and od.buy_orders and od.sell_orders:
            best_bid = max(od.buy_orders)
            best_ask = min(od.sell_orders)
            pos      = state.position.get("HYDROGEL_PACK", 0)
            prev_pos = shared.get("prev_pos", 0)
            last_dir = shared.get("last_dir", None)  # "buy" | "sell" | None

            # detect fill direction since last iteration
            if pos > prev_pos:
                last_dir = "buy"
            elif pos < prev_pos:
                last_dir = "sell"

            buy_room  = POS_LIM - pos
            sell_room = POS_LIM + pos

            if pos > 0:
                # long — must sell down to flat before buying again
                qty = min(pos, sell_room)
                result["HYDROGEL_PACK"].append(Order("HYDROGEL_PACK", best_ask - 1, -qty))

            elif pos < 0:
                # short — must buy back to flat before selling again
                qty = min(abs(pos), buy_room)
                result["HYDROGEL_PACK"].append(Order("HYDROGEL_PACK", best_bid + 1, qty))

            else:
                # flat — decide next side
                if last_dir is None:
                    # first tick: quote both sides
                    result["HYDROGEL_PACK"].append(Order("HYDROGEL_PACK", best_bid + 1,  min(QUOTE_QTY, buy_room)))
                    result["HYDROGEL_PACK"].append(Order("HYDROGEL_PACK", best_ask - 1, -min(QUOTE_QTY, sell_room)))
                elif last_dir == "buy":
                    # just finished a buy cycle → now sell
                    result["HYDROGEL_PACK"].append(Order("HYDROGEL_PACK", best_ask - 1, -min(QUOTE_QTY, sell_room)))
                else:
                    # just finished a sell cycle → now buy
                    result["HYDROGEL_PACK"].append(Order("HYDROGEL_PACK", best_bid + 1, min(QUOTE_QTY, buy_room)))

            shared["prev_pos"] = pos
            shared["last_dir"] = last_dir

        trader_data = json.dumps(shared)
        logger.flush(state, result, 0, trader_data)
        return result, 0, trader_data
