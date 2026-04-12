"""
Round Data Explorer - IMC Prosperity 4
=======================================
Run this immediately when a new round drops to understand the data.

Usage:
    python analyze.py data/prices_round_1_day_0.csv
    python analyze.py data/prices_round_1_day_0.csv data/trades_round_1_day_0.csv

Outputs: price plots, correlation heatmap, basic stats, and initial strategy suggestions.
"""

import csv
import sys
import json
import math
from collections import defaultdict
from statistics import mean, stdev, median


def load_prices(filepath: str) -> dict:
    """Load prices CSV into {product: [(timestamp, best_bid, best_ask, mid)]}"""
    data = defaultdict(list)

    with open(filepath, 'r') as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            product = row.get('product', '')
            ts = int(row.get('timestamp', 0))

            # Get best bid and ask
            bid = None
            ask = None
            for i in range(1, 4):
                bp = row.get(f'bid_price_{i}', '')
                ap = row.get(f'ask_price_{i}', '')
                if bp and bid is None:
                    try:
                        bid = float(bp)
                    except ValueError:
                        pass
                if ap and ask is None:
                    try:
                        ask = float(ap)
                    except ValueError:
                        pass

            if bid is not None and ask is not None:
                mid = (bid + ask) / 2
                data[product].append((ts, bid, ask, mid))

    return dict(data)


def load_trades(filepath: str) -> dict:
    """Load trades CSV into {product: [(timestamp, price, quantity, buyer, seller)]}"""
    data = defaultdict(list)

    with open(filepath, 'r') as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            product = row.get('symbol', row.get('product', ''))
            ts = int(row.get('timestamp', 0))
            price = float(row.get('price', 0))
            qty = int(float(row.get('quantity', 0)))
            buyer = row.get('buyer', '')
            seller = row.get('seller', '')
            data[product].append((ts, price, qty, buyer, seller))

    return dict(data)


def analyze_product(product: str, prices: list):
    """Compute key statistics for a product."""
    mids = [p[3] for p in prices]
    spreads = [p[2] - p[1] for p in prices]

    returns = [(mids[i] - mids[i-1]) / mids[i-1] if mids[i-1] != 0 else 0
               for i in range(1, len(mids))]

    stats = {
        "n_observations": len(mids),
        "mean_price": mean(mids),
        "std_price": stdev(mids) if len(mids) > 1 else 0,
        "min_price": min(mids),
        "max_price": max(mids),
        "price_range": max(mids) - min(mids),
        "mean_spread": mean(spreads),
        "median_spread": median(spreads),
        "cv": stdev(mids) / mean(mids) if mean(mids) != 0 and len(mids) > 1 else 0,
    }

    if returns:
        stats["mean_return"] = mean(returns)
        stats["std_return"] = stdev(returns) if len(returns) > 1 else 0
        stats["max_return"] = max(returns)
        stats["min_return"] = min(returns)

    return stats


def detect_product_type(product: str, stats: dict) -> str:
    """Suggest what type of product this is based on statistics."""
    cv = stats["cv"]
    price_range = stats["price_range"]
    mean_price = stats["mean_price"]

    if cv < 0.001:
        return "STABLE (like Rainforest Resin) → Market make around fixed fair value"
    elif cv < 0.01:
        return "LOW VOLATILITY → Market make with EMA fair value"
    elif cv < 0.05:
        return "MODERATE VOLATILITY → EMA + wider spreads + inventory skew"
    else:
        return "HIGH VOLATILITY → Trend following or wider EMA"


def compute_correlation(prices_a: list, prices_b: list) -> float:
    """Compute correlation between two products' midprices."""
    # Align by timestamp
    ts_a = {p[0]: p[3] for p in prices_a}
    ts_b = {p[0]: p[3] for p in prices_b}
    common = sorted(set(ts_a.keys()) & set(ts_b.keys()))

    if len(common) < 10:
        return float('nan')

    a = [ts_a[t] for t in common]
    b = [ts_b[t] for t in common]

    mean_a, mean_b = mean(a), mean(b)
    std_a, std_b = stdev(a), stdev(b)

    if std_a == 0 or std_b == 0:
        return 0.0

    cov = sum((a[i] - mean_a) * (b[i] - mean_b) for i in range(len(a))) / (len(a) - 1)
    return cov / (std_a * std_b)


def main():
    if len(sys.argv) < 2:
        print("Usage: python analyze.py <prices_csv> [trades_csv]")
        sys.exit(1)

    prices_file = sys.argv[1]
    trades_file = sys.argv[2] if len(sys.argv) > 2 else None

    print("=" * 70)
    print("IMC PROSPERITY 4 - DATA ANALYSIS")
    print("=" * 70)

    # Load data
    prices = load_prices(prices_file)
    trades = load_trades(trades_file) if trades_file else {}

    products = sorted(prices.keys())
    print(f"\nProducts found: {', '.join(products)}")
    print(f"Total timestamps: {max(len(v) for v in prices.values())}")

    # Per-product analysis
    all_stats = {}
    for product in products:
        stats = analyze_product(product, prices[product])
        all_stats[product] = stats
        product_type = detect_product_type(product, stats)

        print(f"\n{'─' * 70}")
        print(f"  {product}")
        print(f"{'─' * 70}")
        print(f"  Observations:  {stats['n_observations']}")
        print(f"  Mean price:    {stats['mean_price']:.2f}")
        print(f"  Std dev:       {stats['std_price']:.2f}")
        print(f"  Range:         {stats['min_price']:.0f} - {stats['max_price']:.0f} "
              f"(width: {stats['price_range']:.0f})")
        print(f"  Mean spread:   {stats['mean_spread']:.2f}")
        print(f"  CV:            {stats['cv']:.6f}")
        if 'mean_return' in stats:
            print(f"  Mean return:   {stats['mean_return']:.8f}")
            print(f"  Return vol:    {stats['std_return']:.8f}")
        print(f"  → Type:        {product_type}")

        if product in trades:
            trade_list = trades[product]
            # Analyze unique traders
            buyers = set(t[3] for t in trade_list if t[3])
            sellers = set(t[4] for t in trade_list if t[4])
            all_traders = buyers | sellers
            print(f"  Trade count:   {len(trade_list)}")
            print(f"  Unique traders: {', '.join(sorted(all_traders)) if all_traders else 'N/A'}")

    # Correlation matrix
    if len(products) > 1:
        print(f"\n{'=' * 70}")
        print("CORRELATION MATRIX")
        print(f"{'=' * 70}")

        # Header
        header = f"{'':15s}" + "".join(f"{p:>15s}" for p in products)
        print(header)

        for p1 in products:
            row = f"{p1:15s}"
            for p2 in products:
                if p1 == p2:
                    corr = 1.0
                else:
                    corr = compute_correlation(prices[p1], prices[p2])
                row += f"{corr:15.4f}"
            print(row)

        # Flag high correlations
        print("\nHighly correlated pairs (|r| > 0.7):")
        found = False
        for i, p1 in enumerate(products):
            for p2 in products[i+1:]:
                corr = compute_correlation(prices[p1], prices[p2])
                if abs(corr) > 0.7:
                    print(f"  {p1} ↔ {p2}: r = {corr:.4f} → Consider PAIRS TRADING")
                    found = True
        if not found:
            print("  None found")

    # Strategy recommendations
    print(f"\n{'=' * 70}")
    print("STRATEGY RECOMMENDATIONS")
    print(f"{'=' * 70}")
    for product in products:
        stats = all_stats[product]
        product_type = detect_product_type(product, stats)
        print(f"\n  {product}: {product_type}")

        if stats['cv'] < 0.001:
            print(f"    → Set fair_value = {stats['mean_price']:.0f}")
            print(f"    → Spread = {max(1, int(stats['mean_spread']))}")
        else:
            print(f"    → Use EMA with alpha ~0.2-0.4")
            print(f"    → Spread = {max(1, int(stats['mean_spread'] * 0.8))}")

    print()


if __name__ == "__main__":
    main()
