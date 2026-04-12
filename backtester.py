"""
Local Backtester for IMC Prosperity 4
======================================
Replays historical CSV data through your Trader class.
Usage:
    python backtester.py --prices data/prices_round_0_day_0.csv --trades data/trades_round_0_day_0.csv

Note: This backtester simulates order matching but cannot perfectly replicate
the competition engine (bot reactions to your quotes are not simulated).
It's useful for testing that your code runs without errors and for rough PnL estimates.
"""

import csv
import json
import argparse
import sys
from collections import defaultdict
from datamodel import (
    Listing, OrderDepth, Trade, TradingState, Order, Observation
)
from trader import Trader


def parse_prices_csv(filepath: str) -> dict:
    """
    Parse the market orders/prices CSV.
    Expected columns: day;timestamp;product;bid_price_1;bid_volume_1;
                      ask_price_1;ask_volume_1;bid_price_2;bid_volume_2;...
    Adjust parsing based on actual CSV format from Prosperity.
    """
    timestamps = defaultdict(dict)  # {timestamp: {product: OrderDepth}}

    with open(filepath, 'r') as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            ts = int(row.get('timestamp', 0))
            product = row.get('product', '')

            buy_orders = {}
            sell_orders = {}

            # Parse up to 3 price levels (adjust based on actual CSV format)
            for i in range(1, 4):
                bp_key = f'bid_price_{i}'
                bv_key = f'bid_volume_{i}'
                ap_key = f'ask_price_{i}'
                av_key = f'ask_volume_{i}'

                if bp_key in row and row[bp_key]:
                    try:
                        price = int(float(row[bp_key]))
                        vol = int(float(row[bv_key]))
                        if vol > 0:
                            buy_orders[price] = buy_orders.get(price, 0) + vol
                    except (ValueError, KeyError):
                        pass

                if ap_key in row and row[ap_key]:
                    try:
                        price = int(float(row[ap_key]))
                        vol = int(float(row[av_key]))
                        if vol > 0:
                            sell_orders[price] = sell_orders.get(price, 0) - vol  # Negative!
                    except (ValueError, KeyError):
                        pass

            if product:
                od = OrderDepth()
                od.buy_orders = buy_orders
                od.sell_orders = sell_orders
                timestamps[ts][product] = od

    return dict(sorted(timestamps.items()))


def parse_trades_csv(filepath: str) -> dict:
    """Parse historical trades CSV."""
    timestamps = defaultdict(lambda: defaultdict(list))

    with open(filepath, 'r') as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            ts = int(row.get('timestamp', 0))
            product = row.get('symbol', row.get('product', ''))
            price = int(float(row.get('price', 0)))
            quantity = int(float(row.get('quantity', 0)))
            buyer = row.get('buyer', '')
            seller = row.get('seller', '')

            trade = Trade(product, price, quantity, buyer, seller, ts)
            timestamps[ts][product].append(trade)

    return dict(timestamps)


def match_orders(orders: list, order_depth: OrderDepth, position: int,
                 limit: int) -> tuple:
    """
    Simulate order matching against the order book.
    Returns: (trades, new_position, pnl)
    """
    trades = []
    pnl = 0

    # Check if total order quantity would breach limits
    total_buy = sum(o.quantity for o in orders if o.quantity > 0)
    total_sell = sum(abs(o.quantity) for o in orders if o.quantity < 0)

    if position + total_buy > limit or position - total_sell < -limit:
        return [], position, 0  # All orders rejected

    for order in orders:
        if order.quantity > 0:  # Buy order
            remaining = order.quantity
            for ask_price in sorted(order_depth.sell_orders.keys()):
                if ask_price <= order.price and remaining > 0:
                    available = abs(order_depth.sell_orders[ask_price])
                    fill = min(remaining, available)
                    trades.append(Trade(order.symbol, ask_price, fill,
                                       "SUBMISSION", "", 0))
                    position += fill
                    pnl -= ask_price * fill
                    remaining -= fill

        elif order.quantity < 0:  # Sell order
            remaining = abs(order.quantity)
            for bid_price in sorted(order_depth.buy_orders.keys(), reverse=True):
                if bid_price >= order.price and remaining > 0:
                    available = order_depth.buy_orders[bid_price]
                    fill = min(remaining, available)
                    trades.append(Trade(order.symbol, bid_price, fill,
                                       "", "SUBMISSION", 0))
                    position -= fill
                    pnl += bid_price * fill
                    remaining -= fill

    return trades, position, pnl


def run_backtest(prices_file: str, trades_file: str = None):
    """Run the full backtest."""
    from trader import Trader, POSITION_LIMITS

    trader = Trader()
    price_data = parse_prices_csv(prices_file)
    trade_data = parse_trades_csv(trades_file) if trades_file else {}

    positions = defaultdict(int)
    total_pnl = defaultdict(float)
    trader_data = ""
    products = set()

    timestamps = sorted(price_data.keys())
    print(f"Running backtest over {len(timestamps)} timestamps...")

    for i, ts in enumerate(timestamps):
        order_depths = price_data[ts]
        products.update(order_depths.keys())

        # Build listings
        listings = {p: Listing(p, p, "XIRECS") for p in order_depths}

        # Get market trades for this timestamp
        market_trades = {}
        for p in order_depths:
            market_trades[p] = trade_data.get(ts, {}).get(p, [])

        # Build state
        state = TradingState(
            traderData=trader_data,
            timestamp=ts,
            listings=listings,
            order_depths=order_depths,
            own_trades={p: [] for p in order_depths},
            market_trades=market_trades,
            position=dict(positions),
            observations=Observation({}, {})
        )

        # Run trader
        try:
            result, conversions, trader_data = trader.run(state)
        except Exception as e:
            print(f"  ERROR at ts={ts}: {e}")
            continue

        # Match orders
        for product, orders in result.items():
            if product in order_depths:
                limit = POSITION_LIMITS.get(product, 20)
                trades, new_pos, pnl = match_orders(
                    orders, order_depths[product],
                    positions[product], limit
                )
                positions[product] = new_pos
                total_pnl[product] += pnl

    # Final PnL includes mark-to-market of remaining positions
    print("\n" + "=" * 60)
    print("BACKTEST RESULTS")
    print("=" * 60)

    grand_total = 0
    for product in sorted(products):
        realized = total_pnl[product]
        pos = positions[product]
        # Mark remaining position at last midprice
        last_ts = timestamps[-1]
        if product in price_data[last_ts]:
            od = price_data[last_ts][product]
            if od.buy_orders and od.sell_orders:
                mid = (max(od.buy_orders.keys()) + min(od.sell_orders.keys())) / 2
                mtm = pos * mid
            else:
                mtm = 0
        else:
            mtm = 0

        total = realized + mtm
        grand_total += total
        print(f"  {product:25s}  Realized: {realized:>10.0f}  Position: {pos:>4d}  "
              f"MtM: {mtm:>10.0f}  Total: {total:>10.0f}")

    print(f"\n  {'GRAND TOTAL':25s}  {grand_total:>52.0f}")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prosperity 4 Backtester")
    parser.add_argument("--prices", required=True, help="Path to prices/orders CSV")
    parser.add_argument("--trades", default=None, help="Path to trades CSV")
    args = parser.parse_args()

    run_backtest(args.prices, args.trades)
