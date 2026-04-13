"""
IMC Prosperity 4 - Comprehensive Market Data Analyzer
======================================================
Covers every critical dimension of market analysis needed to win.

Usage:
    python3 analyze.py <prices_csv> [trades_csv] [--plot] [--save]

    --plot   Show interactive charts
    --save   Save charts as PNG files (no display needed)

Examples:
    python3 analyze.py data/prices/prices_round_0_day_-1.csv
    python3 analyze.py data/prices/prices_round_0_day_-1.csv data/trades/trades_round_0_day_-1.csv --plot
    python3 analyze.py data/prices/prices_round_0_day_-1.csv --save

What this covers:
  Price structure   : mean, std, CV, skewness, kurtosis, range, VWAP
  Market microstructure: bid-ask spread, order book imbalance (OBI),
                        volume-weighted mid, book depth, Kyle's lambda,
                        Amihud illiquidity
  Time-series stats : Hurst exponent, AR(1) half-life, autocorrelogram,
                      rolling volatility, optimal EMA alpha
  Multi-product     : return & price correlation (seaborn heatmaps),
                      cointegration (Engle-Granger), pairs spread Z-score,
                      normalized price comparison
  Trade analysis    : VWAP, named trader signals, trade flow imbalance
  Strategy output   : data-driven parameter recommendations per product
"""

import csv
import sys
import math
from collections import defaultdict
from statistics import mean, stdev, median


# ══════════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ══════════════════════════════════════════════════════════════════════════════

def load_prices(filepath: str) -> dict:
    """
    Returns {product: [row_dict, ...]} where each row_dict has:
      ts, bid1-3, bvol1-3, ask1-3, avol1-3,
      mid, spread, obi, wmid, total_bid_vol, total_ask_vol
    """
    data = defaultdict(list)
    with open(filepath) as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            product = row.get('product', '').strip()
            if not product:
                continue
            ts = int(row.get('timestamp', 0))

            def fv(k):
                v = row.get(k, '').strip()
                return float(v) if v else None

            def iv(k):
                v = row.get(k, '').strip()
                return int(float(v)) if v else 0

            b1, bv1 = fv('bid_price_1'), iv('bid_volume_1')
            b2, bv2 = fv('bid_price_2'), iv('bid_volume_2')
            b3, bv3 = fv('bid_price_3'), iv('bid_volume_3')
            a1, av1 = fv('ask_price_1'), iv('ask_volume_1')
            a2, av2 = fv('ask_price_2'), iv('ask_volume_2')
            a3, av3 = fv('ask_price_3'), iv('ask_volume_3')

            if b1 is None or a1 is None:
                continue

            mid = (b1 + a1) / 2
            spread = a1 - b1
            total_bid = bv1 + bv2 + bv3
            total_ask = av1 + av2 + av3
            obi = (bv1 - av1) / (bv1 + av1) if (bv1 + av1) > 0 else 0.0
            # Volume-weighted mid: weighs best bid by ask liquidity and vice versa
            wmid = (b1 * av1 + a1 * bv1) / (bv1 + av1) if (bv1 + av1) > 0 else mid

            data[product].append({
                'ts': ts, 'mid': mid, 'spread': spread,
                'obi': obi, 'wmid': wmid,
                'bid1': b1, 'bvol1': bv1,
                'bid2': b2, 'bvol2': bv2,
                'bid3': b3, 'bvol3': bv3,
                'ask1': a1, 'avol1': av1,
                'ask2': a2, 'avol2': av2,
                'ask3': a3, 'avol3': av3,
                'total_bid_vol': total_bid,
                'total_ask_vol': total_ask,
            })
    return dict(data)


def load_trades(filepath: str) -> dict:
    """Returns {product: [(ts, price, qty, buyer, seller), ...]}"""
    data = defaultdict(list)
    with open(filepath) as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            product = row.get('symbol', row.get('product', '')).strip()
            if not product:
                continue
            ts = int(row.get('timestamp', 0))
            price = float(row.get('price', 0))
            qty = int(float(row.get('quantity', 0)))
            buyer = row.get('buyer', '').strip()
            seller = row.get('seller', '').strip()
            data[product].append((ts, price, qty, buyer, seller))
    return dict(data)


# ══════════════════════════════════════════════════════════════════════════════
# MATH UTILITIES
# ══════════════════════════════════════════════════════════════════════════════

def pearson_r(x: list, y: list) -> float:
    n = len(x)
    if n < 3:
        return float('nan')
    mx, my = sum(x) / n, sum(y) / n
    num = sum((x[i] - mx) * (y[i] - my) for i in range(n))
    dx = math.sqrt(sum((xi - mx) ** 2 for xi in x))
    dy = math.sqrt(sum((yi - my) ** 2 for yi in y))
    if dx == 0 or dy == 0:
        return 0.0
    return num / (dx * dy)


def ols(x: list, y: list) -> tuple:
    """Return (intercept, slope) for y = intercept + slope*x via OLS."""
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    denom = sum((xi - mx) ** 2 for xi in x)
    if denom == 0:
        return my, 0.0
    slope = sum((x[i] - mx) * (y[i] - my) for i in range(n)) / denom
    return my - slope * mx, slope


def ema(values: list, alpha: float) -> list:
    out = [values[0]]
    for v in values[1:]:
        out.append(alpha * v + (1 - alpha) * out[-1])
    return out


def rolling_mean_std(values: list, window: int):
    """Returns (means, stds) lists, each same length as values."""
    means, stds = [], []
    for i in range(len(values)):
        chunk = values[max(0, i - window + 1): i + 1]
        m = sum(chunk) / len(chunk)
        means.append(m)
        stds.append(math.sqrt(sum((x - m) ** 2 for x in chunk) / len(chunk)) if len(chunk) > 1 else 0.0)
    return means, stds


def skewness(values: list) -> float:
    n = len(values)
    if n < 3:
        return 0.0
    m = sum(values) / n
    s = math.sqrt(sum((x - m) ** 2 for x in values) / n)
    return (sum((x - m) ** 3 for x in values) / n) / s ** 3 if s > 0 else 0.0


def excess_kurtosis(values: list) -> float:
    n = len(values)
    if n < 4:
        return 0.0
    m = sum(values) / n
    s = math.sqrt(sum((x - m) ** 2 for x in values) / n)
    return ((sum((x - m) ** 4 for x in values) / n) / s ** 4 - 3) if s > 0 else 0.0


def autocorr(returns: list, lag: int) -> float:
    if len(returns) <= lag + 1:
        return float('nan')
    return pearson_r(returns[lag:], returns[:-lag])


def hurst_exponent(prices: list) -> float:
    """
    Variance-scaling Hurst exponent.
    H < 0.5 → mean-reverting
    H ≈ 0.5 → random walk
    H > 0.5 → trending / persistent
    """
    n = len(prices)
    if n < 64:
        return 0.5
    log_rets = [math.log(prices[i] / prices[i - 1])
                for i in range(1, n) if prices[i - 1] > 0 and prices[i] > 0]
    if len(log_rets) < 32:
        return 0.5

    lags = [2, 4, 8, 16, 32]
    pts = []
    for lag in lags:
        # Variance of lag-period cumulative returns
        chunks = [sum(log_rets[i:i + lag]) for i in range(0, len(log_rets) - lag + 1, lag)]
        if len(chunks) < 3:
            continue
        var = sum(c ** 2 for c in chunks) / len(chunks) - (sum(chunks) / len(chunks)) ** 2
        if var > 0:
            pts.append((math.log(lag), math.log(var)))

    if len(pts) < 3:
        return 0.5
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    _, slope = ols(xs, ys)
    return slope / 2  # Var ~ lag^(2H)


def halflife_ar1(series: list) -> float:
    """
    AR(1) mean reversion: Δy_t = α + β·y_{t-1} + ε
    Half-life = -ln(2) / ln(1+β)   (only meaningful when β < 0)
    Returns inf if series is non-mean-reverting.
    """
    n = len(series)
    if n < 20:
        return float('inf')
    y_lag = series[:-1]
    dy = [series[i + 1] - series[i] for i in range(n - 1)]
    _, beta = ols(y_lag, dy)
    if beta >= 0:
        return float('inf')
    return -math.log(2) / math.log(1 + beta)


def optimal_ema_alpha(mids: list) -> tuple:
    """Grid-search alpha in [0.01, 0.9] minimizing 1-step-ahead MSE."""
    best_alpha, best_mse = 0.1, float('inf')
    for alpha in [0.01, 0.03, 0.05, 0.08, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.7, 0.9]:
        e = ema(mids[:-1], alpha)
        mse = sum((mids[i + 1] - e[i]) ** 2 for i in range(len(e))) / len(e)
        if mse < best_mse:
            best_mse, best_alpha = mse, alpha
    return best_alpha, best_mse


# ══════════════════════════════════════════════════════════════════════════════
# TRADE MICROSTRUCTURE
# ══════════════════════════════════════════════════════════════════════════════

def kyles_lambda(trade_list: list, rows: list) -> float:
    """
    Kyle's λ: price impact per unit of signed order flow.
    Positive λ → buying moves price up (normal market).
    Estimated via OLS: Δmid_t = λ · signed_vol_t + ε
    """
    if len(trade_list) < 10 or len(rows) < 2:
        return float('nan')
    mid_map = {r['ts']: r['mid'] for r in rows}
    ts_sorted = sorted(mid_map.keys())
    ts_idx = {t: i for i, t in enumerate(ts_sorted)}

    signed_vols, price_changes = [], []
    for (ts, price, qty, buyer, seller) in trade_list:
        if ts not in mid_map:
            continue
        direction = 1 if price >= mid_map[ts] else -1
        idx = ts_idx.get(ts, -1)
        if idx < 0 or idx + 1 >= len(ts_sorted):
            continue
        dp = mid_map[ts_sorted[idx + 1]] - mid_map[ts]
        signed_vols.append(direction * qty)
        price_changes.append(dp)

    if len(signed_vols) < 5:
        return float('nan')
    _, lam = ols(signed_vols, price_changes)
    return lam


def amihud_illiquidity(trade_list: list) -> float:
    """
    Amihud (2002): mean(|Δprice| / volume) scaled by 1e6.
    Higher = less liquid (each unit of volume moves price more).
    """
    if len(trade_list) < 5:
        return float('nan')
    ratios = []
    for i in range(1, len(trade_list)):
        prev_p = trade_list[i - 1][1]
        cur_p = trade_list[i][1]
        qty = trade_list[i][2]
        if qty == 0 or prev_p == 0:
            continue
        ratios.append(abs(cur_p - prev_p) / prev_p / qty)
    return mean(ratios) * 1e6 if ratios else float('nan')


def trade_flow_imbalance(trade_list: list, mid_map: dict) -> float:
    """
    Net signed volume: buy_vol - sell_vol (buyer-initiated vs seller-initiated).
    Positive = net buying pressure.
    """
    buy_vol = sell_vol = 0
    for (ts, price, qty, buyer, seller) in trade_list:
        mid = mid_map.get(ts, price)
        if price >= mid:
            buy_vol += qty
        else:
            sell_vol += qty
    total = buy_vol + sell_vol
    return (buy_vol - sell_vol) / total if total > 0 else 0.0


def named_trader_analysis(trade_list: list) -> dict:
    """
    Track named bots (non-empty, non-SUBMISSION buyer/seller).
    Returns dict of trader → {buys, sells, buy_vol, sell_vol, net_vol, avg_buy_px, avg_sell_px}.
    """
    traders = defaultdict(lambda: {'buys': 0, 'sells': 0, 'buy_vol': 0, 'sell_vol': 0,
                                    'buy_px_sum': 0.0, 'sell_px_sum': 0.0})
    for (ts, price, qty, buyer, seller) in trade_list:
        for name, side in [(buyer, 'buy'), (seller, 'sell')]:
            if name and name not in ('', 'SUBMISSION'):
                if side == 'buy':
                    traders[name]['buys'] += 1
                    traders[name]['buy_vol'] += qty
                    traders[name]['buy_px_sum'] += price * qty
                else:
                    traders[name]['sells'] += 1
                    traders[name]['sell_vol'] += qty
                    traders[name]['sell_px_sum'] += price * qty

    result = {}
    for name, d in traders.items():
        result[name] = {
            'buys': d['buys'], 'sells': d['sells'],
            'buy_vol': d['buy_vol'], 'sell_vol': d['sell_vol'],
            'net_vol': d['buy_vol'] - d['sell_vol'],
            'avg_buy_px': d['buy_px_sum'] / d['buy_vol'] if d['buy_vol'] else None,
            'avg_sell_px': d['sell_px_sum'] / d['sell_vol'] if d['sell_vol'] else None,
        }
    return result


# ══════════════════════════════════════════════════════════════════════════════
# CORE PER-PRODUCT ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════

def analyze_product(product: str, rows: list, trade_list: list = None) -> dict:
    mids = [r['mid'] for r in rows]
    spreads = [r['spread'] for r in rows]
    obis = [r['obi'] for r in rows]
    wmids = [r['wmid'] for r in rows]
    total_bid_vols = [r['total_bid_vol'] for r in rows]
    total_ask_vols = [r['total_ask_vol'] for r in rows]

    n = len(mids)
    mu = mean(mids)
    sd = stdev(mids) if n > 1 else 0.0

    returns_pct = [(mids[i] - mids[i - 1]) / mids[i - 1] * 100
                   for i in range(1, n) if mids[i - 1] != 0]

    stats = {
        # ── Price basics ────────────────────────────────────────────────────
        'n': n,
        'mean': mu,
        'std': sd,
        'min': min(mids),
        'max': max(mids),
        'range': max(mids) - min(mids),
        'cv': sd / mu if mu else 0,
        'skew_price': skewness(mids),
        'kurt_price': excess_kurtosis(mids),
        # ── Spread ──────────────────────────────────────────────────────────
        'spread_mean': mean(spreads),
        'spread_median': median(spreads),
        'spread_std': stdev(spreads) if len(spreads) > 1 else 0,
        'spread_min': min(spreads),
        'spread_max': max(spreads),
        # ── Order book ──────────────────────────────────────────────────────
        'obi_mean': mean(obis),
        'obi_std': stdev(obis) if len(obis) > 1 else 0,
        'wmid_mean': mean(wmids),
        'wmid_vs_mid': mean(wmids) - mu,
        'avg_bid_depth': mean(total_bid_vols),
        'avg_ask_depth': mean(total_ask_vols),
        # ── Returns ─────────────────────────────────────────────────────────
        'ret_mean': mean(returns_pct) if returns_pct else 0,
        'ret_std': stdev(returns_pct) if len(returns_pct) > 1 else 0,
        'ret_skew': skewness(returns_pct) if returns_pct else 0,
        'ret_kurt': excess_kurtosis(returns_pct) if returns_pct else 0,
        # ── Time-series structure ────────────────────────────────────────────
        'hurst': hurst_exponent(mids),
        'halflife': halflife_ar1(mids),
        'ac1': autocorr(returns_pct, 1),
        'ac2': autocorr(returns_pct, 2),
        'ac5': autocorr(returns_pct, 5),
        'ac10': autocorr(returns_pct, 10),
    }

    # Optimal EMA
    opt_alpha, opt_mse = optimal_ema_alpha(mids)
    stats['opt_ema_alpha'] = opt_alpha
    stats['opt_ema_mse'] = opt_mse

    # OBI predictive power for next-period return
    if len(obis) > 2 and len(returns_pct) > 1:
        # Does OBI[t] predict return[t+1]?
        n_align = min(len(obis) - 1, len(returns_pct))
        stats['obi_pred_r'] = pearson_r(obis[:n_align], returns_pct[:n_align])
    else:
        stats['obi_pred_r'] = float('nan')

    # ── Trade analysis ───────────────────────────────────────────────────────
    if trade_list:
        qtys = [t[2] for t in trade_list]
        prices_t = [t[1] for t in trade_list]
        total_vol = sum(qtys)

        stats['trade_count'] = len(trade_list)
        stats['trade_volume'] = total_vol
        stats['vwap'] = sum(p * q for p, q in zip(prices_t, qtys)) / total_vol if total_vol else mu
        stats['vwap_vs_mid'] = stats['vwap'] - mu

        mid_map = {r['ts']: r['mid'] for r in rows}
        stats['flow_imbalance'] = trade_flow_imbalance(trade_list, mid_map)
        stats['kyles_lambda'] = kyles_lambda(trade_list, rows)
        stats['amihud'] = amihud_illiquidity(trade_list)
        stats['named_traders'] = named_trader_analysis(trade_list)

    return stats


# ══════════════════════════════════════════════════════════════════════════════
# MULTI-PRODUCT ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════

def build_return_matrix(prices: dict, products: list) -> tuple:
    """
    Aligns all products by timestamp, computes returns, builds correlation matrix.
    Returns (matrix dict {(p1,p2): corr}, common_timestamps list).
    """
    # Per-product timestamp → return
    ts_ret = {}
    for p in products:
        rows = prices[p]
        ts_mid = {r['ts']: r['mid'] for r in rows}
        timestamps = sorted(ts_mid.keys())
        rets = {}
        for i in range(1, len(timestamps)):
            t0, t1 = timestamps[i - 1], timestamps[i]
            if ts_mid[t0] != 0:
                rets[t1] = (ts_mid[t1] - ts_mid[t0]) / ts_mid[t0]
        ts_ret[p] = rets

    common = sorted(set.intersection(*[set(ts_ret[p].keys()) for p in products])) if len(products) > 1 else []

    matrix = {}
    for p1 in products:
        for p2 in products:
            if p1 == p2:
                matrix[(p1, p2)] = 1.0
            else:
                a = [ts_ret[p1][t] for t in common]
                b = [ts_ret[p2][t] for t in common]
                matrix[(p1, p2)] = pearson_r(a, b)
    return matrix, common


def cointegration_analysis(prices: dict, products: list) -> list:
    """
    Simplified Engle-Granger cointegration for all pairs.
    Regresses p1 on p2, checks if residuals are mean-reverting.
    """
    results = []
    for i, p1 in enumerate(products):
        for p2 in products[i + 1:]:
            ts1 = {r['ts']: r['mid'] for r in prices[p1]}
            ts2 = {r['ts']: r['mid'] for r in prices[p2]}
            common = sorted(set(ts1.keys()) & set(ts2.keys()))
            if len(common) < 50:
                continue
            a = [ts1[t] for t in common]
            b = [ts2[t] for t in common]
            intercept, beta = ols(b, a)  # a ≈ intercept + beta * b
            residuals = [a[i] - (intercept + beta * b[i]) for i in range(len(a))]
            hl = halflife_ar1(residuals)
            spread_std = stdev(residuals) if len(residuals) > 1 else 0
            results.append({
                'p1': p1, 'p2': p2,
                'beta': beta, 'intercept': intercept,
                'spread_mean': mean(residuals),
                'spread_std': spread_std,
                'halflife': hl,
                'residuals': residuals,
                'common_ts': common,
                'cointegrated': hl < 500 and hl != float('inf'),
            })
    return results


# ══════════════════════════════════════════════════════════════════════════════
# STRATEGY RECOMMENDATION
# ══════════════════════════════════════════════════════════════════════════════

def strategy_recommendation(stats: dict) -> tuple:
    h = stats['hurst']
    hl = stats['halflife']
    cv = stats['cv']
    ac1 = stats['ac1']
    spread = stats['spread_mean']

    if cv < 0.0005:
        strat = "FIXED FAIR VALUE MARKET MAKER"
        notes = [
            f"fair_value = {stats['mean']:.0f}  (barely drifts)",
            f"quote spread = {max(1, int(spread * 0.5))}-{max(2, int(spread * 0.7))}",
            "Aggressive inventory management — position limits hit fast",
        ]
    elif h < 0.45 and hl != float('inf') and hl < 300:
        strat = "MEAN-REVERSION MARKET MAKER"
        alpha = stats['opt_ema_alpha']
        notes = [
            f"EMA fair value, alpha = {alpha}",
            f"half-life ≈ {hl:.0f} ticks → flip inventory within {max(1, int(hl * 1.5))} ticks",
            f"quote spread = {max(1, int(spread * 0.6))}-{max(2, int(spread * 0.8))}",
            f"Z-score entry at ±1.5σ (σ = {stats['std']:.2f})",
        ]
    elif h > 0.55:
        strat = "TREND FOLLOWING / MOMENTUM"
        alpha = stats['opt_ema_alpha']
        notes = [
            f"EMA crossover signal, alpha = {alpha}",
            "Enter when fast EMA crosses slow EMA",
            "Do NOT market-make against trend",
            f"Volatility = {stats['ret_std']:.4f}% per tick → size positions accordingly",
        ]
    else:
        strat = "MARKET MAKER (near random walk)"
        alpha = stats['opt_ema_alpha']
        notes = [
            f"EMA fair value, alpha = {alpha}",
            f"quote spread = {max(1, int(spread * 0.7))}-{max(2, int(spread))}",
            "Use inventory skew to avoid one-sided fills",
        ]

    # OBI signal
    obi_r = stats.get('obi_pred_r', float('nan'))
    if not math.isnan(obi_r) and abs(obi_r) > 0.05:
        notes.append(f"Order book imbalance is predictive (r={obi_r:.3f}) → skew quotes toward OBI signal")

    # VWAP fair value
    if 'vwap' in stats:
        notes.append(f"VWAP = {stats['vwap']:.2f} (vs mid {stats['mean']:.2f}, diff {stats['vwap_vs_mid']:+.2f})")

    # Named trader signal
    if 'named_traders' in stats and stats['named_traders']:
        for trader, td in stats['named_traders'].items():
            if abs(td['net_vol']) > 0:
                direction = 'NET BUYER' if td['net_vol'] > 0 else 'NET SELLER'
                notes.append(f"Named trader {trader}: {direction}, net vol = {td['net_vol']}")

    # Flow imbalance
    if 'flow_imbalance' in stats and abs(stats['flow_imbalance']) > 0.1:
        notes.append(f"Trade flow imbalance = {stats['flow_imbalance']:+.3f} → structural buy/sell pressure")

    return strat, notes


# ══════════════════════════════════════════════════════════════════════════════
# PLOTS
# ══════════════════════════════════════════════════════════════════════════════

def plot_product(product: str, rows: list, trade_list: list, stats: dict, save: bool):
    import matplotlib.pyplot as plt
    import matplotlib.gridspec as gridspec
    import numpy as np

    ts = [r['ts'] for r in rows]
    mids = [r['mid'] for r in rows]
    bids = [r['bid1'] for r in rows]
    asks = [r['ask1'] for r in rows]
    spreads = [r['spread'] for r in rows]
    obis = [r['obi'] for r in rows]
    wmids = [r['wmid'] for r in rows]

    returns_pct = [(mids[i] - mids[i - 1]) / mids[i - 1] * 100
                   for i in range(1, len(mids)) if mids[i - 1] != 0]

    opt_alpha = stats['opt_ema_alpha']
    ema_opt = ema(mids, opt_alpha)
    ema_slow = ema(mids, 0.02)

    bb_window = 20
    bb_mean, bb_std_v = rolling_mean_std(mids, bb_window)
    bb_upper = [bb_mean[i] + 2 * bb_std_v[i] for i in range(len(mids))]
    bb_lower = [bb_mean[i] - 2 * bb_std_v[i] for i in range(len(mids))]
    z_score = [(mids[i] - bb_mean[i]) / bb_std_v[i] if bb_std_v[i] > 0 else 0 for i in range(len(mids))]

    hl_str = '∞' if stats['halflife'] == float('inf') else f"{stats['halflife']:.0f}"
    h_str = f"H={stats['hurst']:.3f}"
    ac1_str = f"AC1={stats['ac1']:.3f}" if not math.isnan(stats['ac1']) else "AC1=nan"

    fig = plt.figure(figsize=(16, 13))
    fig.suptitle(
        f"{product}  |  μ={stats['mean']:.2f}  σ={stats['std']:.2f}  "
        f"CV={stats['cv']:.5f}  {h_str}  HL={hl_str}  {ac1_str}",
        fontsize=12, fontweight='bold'
    )
    gs = gridspec.GridSpec(3, 2, figure=fig, hspace=0.52, wspace=0.35)

    # ── 1. Price + EMA + Bollinger + VWAP + trades ──────────────────────────
    ax1 = fig.add_subplot(gs[0, :])
    ax1.fill_between(ts, bids, asks, alpha=0.10, color='steelblue')
    ax1.fill_between(ts, bb_lower, bb_upper, alpha=0.07, color='purple', label='Bollinger ±2σ')
    ax1.plot(ts, mids, color='steelblue', lw=1.0, label='Mid')
    ax1.plot(ts, wmids, color='cyan', lw=0.7, linestyle='-.', alpha=0.7, label='Weighted mid')
    ax1.plot(ts, ema_opt, color='orange', lw=1.2, linestyle='--', label=f'EMA(α={opt_alpha})')
    ax1.plot(ts, ema_slow, color='red', lw=1.0, linestyle=':', label='EMA(α=0.02)')

    if trade_list:
        trade_ts = [t[0] for t in trade_list]
        trade_px = [t[1] for t in trade_list]
        trade_qty = [t[2] for t in trade_list]
        ax1.scatter(trade_ts, trade_px, s=[max(8, q * 4) for q in trade_qty],
                    color='limegreen', zorder=5, alpha=0.6, label='Trades')

        named = stats.get('named_traders', {})
        colors_named = ['gold', 'magenta', 'red', 'cyan', 'white']
        for ci, (trader, _) in enumerate(named.items()):
            nt_ts = [t[0] for t in trade_list if t[3] == trader or t[4] == trader]
            nt_px = [t[1] for t in trade_list if t[3] == trader or t[4] == trader]
            if nt_ts:
                ax1.scatter(nt_ts, nt_px, s=70, marker='^', zorder=7,
                            color=colors_named[ci % len(colors_named)], label=trader, edgecolors='black', linewidths=0.5)

    if 'vwap' in stats:
        ax1.axhline(stats['vwap'], color='gold', lw=1.5, linestyle='--',
                    label=f"VWAP {stats['vwap']:.2f}")

    ax1.set_title('Price  (Bollinger Bands + EMA + Weighted Mid + VWAP + Trades)')
    ax1.set_xlabel('Timestamp')
    ax1.set_ylabel('Price')
    ax1.legend(fontsize=7, loc='upper right', ncol=5)
    ax1.grid(True, alpha=0.25)

    # ── 2. Order Book Imbalance ─────────────────────────────────────────────
    ax2 = fig.add_subplot(gs[1, 0])
    bar_width = (ts[-1] - ts[0]) / len(ts) * 0.9 if len(ts) > 1 else 100
    colors_obi = ['tomato' if o < 0 else 'limegreen' for o in obis]
    ax2.bar(ts, obis, color=colors_obi, alpha=0.7, width=bar_width)
    ax2.axhline(0, color='black', lw=0.8)
    obi_r = stats.get('obi_pred_r', float('nan'))
    r_str = f"{obi_r:.3f}" if not math.isnan(obi_r) else "nan"
    ax2.axhline(mean(obis), color='darkred', lw=1.5, linestyle='--',
                label=f'Mean={mean(obis):.4f}  pred_r={r_str}')
    ax2.set_title('Order Book Imbalance  (green=buy pressure, red=sell)')
    ax2.set_xlabel('Timestamp')
    ax2.set_ylabel('OBI = (BidVol-AskVol)/(BidVol+AskVol)')
    ax2.legend(fontsize=8)
    ax2.grid(True, alpha=0.25)

    # ── 3. Z-Score vs Bollinger mean ────────────────────────────────────────
    ax3 = fig.add_subplot(gs[1, 1])
    ax3.plot(ts, z_score, color='mediumpurple', lw=0.9, label='Z-score')
    ax3.axhline(0, color='black', lw=0.8)
    ax3.axhline(2, color='red', lw=1, linestyle='--', alpha=0.7, label='±2σ')
    ax3.axhline(-2, color='red', lw=1, linestyle='--', alpha=0.7)
    ax3.axhline(1, color='orange', lw=0.8, linestyle=':', alpha=0.7, label='±1σ')
    ax3.axhline(-1, color='orange', lw=0.8, linestyle=':', alpha=0.7)
    ax3.fill_between(ts, -1, 1, alpha=0.05, color='gray')
    ax3.set_title(f'Z-Score  (Bollinger mean, window={bb_window})')
    ax3.set_xlabel('Timestamp')
    ax3.set_ylabel('Standard deviations from mean')
    ax3.legend(fontsize=8)
    ax3.grid(True, alpha=0.25)

    # ── 4. Return autocorrelogram ────────────────────────────────────────────
    ax4 = fig.add_subplot(gs[2, 0])
    max_lag = min(20, len(returns_pct) // 5)
    lags = list(range(1, max_lag + 1))
    acs = [autocorr(returns_pct, lag) for lag in lags]
    colors_ac = ['tomato' if (math.isnan(a) or a < 0) else 'steelblue' for a in acs]
    ax4.bar(lags, [0 if math.isnan(a) else a for a in acs], color=colors_ac, alpha=0.85)
    conf = 1.96 / math.sqrt(len(returns_pct)) if len(returns_pct) > 1 else 0.1
    ax4.axhline(conf, color='red', lw=1.2, linestyle='--', alpha=0.8, label=f'±95% CI ({conf:.3f})')
    ax4.axhline(-conf, color='red', lw=1.2, linestyle='--', alpha=0.8)
    ax4.axhline(0, color='black', lw=0.8)
    ax4.set_title(f'Return Autocorrelogram  (H={stats["hurst"]:.3f}, HL={hl_str})')
    ax4.set_xlabel('Lag')
    ax4.set_ylabel('Autocorrelation')
    ax4.legend(fontsize=8)
    ax4.grid(True, alpha=0.25)

    # ── 5. Return Distribution + normal fit ─────────────────────────────────
    ax5 = fig.add_subplot(gs[2, 1])
    if returns_pct:
        ax5.hist(returns_pct, bins=60, color='mediumpurple', alpha=0.7, density=True, edgecolor='none')
        mu_r = mean(returns_pct)
        sd_r = stdev(returns_pct) if len(returns_pct) > 1 else 1
        if sd_r > 0:
            xs = np.linspace(min(returns_pct), max(returns_pct), 300)
            normal_y = [1 / (sd_r * math.sqrt(2 * math.pi)) * math.exp(-0.5 * ((x - mu_r) / sd_r) ** 2)
                        for x in xs]
            ax5.plot(xs, normal_y, 'r-', lw=1.5, label='Normal fit')
        ax5.axvline(0, color='black', lw=0.8)
        ax5.set_title(f'Return Distribution  skew={stats["ret_skew"]:.2f}  kurt={stats["ret_kurt"]:.2f}')
        ax5.set_xlabel('Return (%)')
        ax5.set_ylabel('Density')
        ax5.legend(fontsize=8)
        ax5.grid(True, alpha=0.25)

    plt.tight_layout()
    if save:
        fname = f"{product.lower().replace(' ', '_')}_analysis.png"
        plt.savefig(fname, dpi=150, bbox_inches='tight')
        print(f"    Saved: {fname}")
        plt.close()
    else:
        plt.show()


def plot_correlation_heatmaps(prices: dict, products: list, ret_matrix: dict, save: bool):
    """Seaborn heatmaps: return correlation + price level correlation."""
    try:
        import seaborn as sns
    except ImportError:
        print("  [!] seaborn not installed: pip install seaborn  (falling back to matplotlib)")
        sns = None

    import matplotlib.pyplot as plt
    import numpy as np

    n = len(products)

    # Return correlation matrix
    ret_arr = np.array([[ret_matrix.get((p1, p2), float('nan')) for p2 in products] for p1 in products])

    # Price level correlation
    price_arr = np.zeros((n, n))
    for i, p1 in enumerate(products):
        for j, p2 in enumerate(products):
            ts1 = {r['ts']: r['mid'] for r in prices[p1]}
            ts2 = {r['ts']: r['mid'] for r in prices[p2]}
            common = sorted(set(ts1.keys()) & set(ts2.keys()))
            if common:
                price_arr[i, j] = pearson_r([ts1[t] for t in common], [ts2[t] for t in common])

    fig, axes = plt.subplots(1, 2, figsize=(max(9, n * 3), max(5, n * 2)))

    kwargs = dict(annot=True, fmt='.3f', cmap='RdYlGn', vmin=-1, vmax=1,
                  xticklabels=products, yticklabels=products, linewidths=0.5, square=True)

    if sns:
        sns.heatmap(ret_arr, ax=axes[0], **kwargs)
        sns.heatmap(price_arr, ax=axes[1], **kwargs)
    else:
        for ax, arr, title in [(axes[0], ret_arr, 'Return'), (axes[1], price_arr, 'Price')]:
            im = ax.imshow(arr, cmap='RdYlGn', vmin=-1, vmax=1)
            plt.colorbar(im, ax=ax)
            ax.set_xticks(range(n))
            ax.set_yticks(range(n))
            ax.set_xticklabels(products, rotation=45, ha='right')
            ax.set_yticklabels(products)
            for i in range(n):
                for j in range(n):
                    ax.text(j, i, f'{arr[i,j]:.3f}', ha='center', va='center',
                            fontsize=9, color='black' if abs(arr[i, j]) < 0.8 else 'white')

    axes[0].set_title('Return Correlation', fontsize=12, fontweight='bold')
    axes[1].set_title('Price Level Correlation', fontsize=12, fontweight='bold')
    plt.suptitle('Correlation Heatmaps', fontsize=14, fontweight='bold')
    plt.tight_layout()

    if save:
        plt.savefig('correlation_heatmaps.png', dpi=150, bbox_inches='tight')
        print("    Saved: correlation_heatmaps.png")
        plt.close()
    else:
        plt.show()


def plot_normalized_prices(prices: dict, products: list, save: bool):
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(14, 5))
    colors = plt.cm.tab10.colors
    for i, product in enumerate(products):
        rows = prices[product]
        ts = [r['ts'] for r in rows]
        mids = [r['mid'] for r in rows]
        norm = [(m - mids[0]) / mids[0] * 100 for m in mids]
        ax.plot(ts, norm, label=product, color=colors[i % 10], lw=1.3)
    ax.axhline(0, color='black', lw=0.8, linestyle='--')
    ax.set_xlabel('Timestamp')
    ax.set_ylabel('% change from t=0')
    ax.set_title('Normalized Price Comparison  (all products)')
    ax.legend()
    ax.grid(True, alpha=0.25)
    plt.tight_layout()
    if save:
        plt.savefig('price_comparison.png', dpi=150, bbox_inches='tight')
        print("    Saved: price_comparison.png")
        plt.close()
    else:
        plt.show()


def plot_pairs_spread(coint_results: list, save: bool):
    """Z-score of the cointegration spread for each detected pair."""
    import matplotlib.pyplot as plt
    cointed = [r for r in coint_results if r['cointegrated']]
    if not cointed:
        return
    fig, axes = plt.subplots(len(cointed), 1, figsize=(14, 5 * len(cointed)), squeeze=False)
    for idx, pair in enumerate(cointed):
        ax = axes[idx][0]
        res = pair['residuals']
        ts = pair['common_ts']
        m, s = mean(res), stdev(res) if len(res) > 1 else 1
        z = [(r - m) / s for r in res]
        ax.plot(ts, z, color='steelblue', lw=1)
        ax.axhline(0, color='black', lw=1)
        ax.axhline(2, color='red', lw=1.2, linestyle='--', label='±2σ entry')
        ax.axhline(-2, color='red', lw=1.2, linestyle='--')
        ax.axhline(1, color='orange', lw=0.9, linestyle=':', label='±1σ exit')
        ax.axhline(-1, color='orange', lw=0.9, linestyle=':')
        ax.fill_between(ts, -1, 1, alpha=0.05, color='gray')
        hl_str = f"{pair['halflife']:.1f}" if pair['halflife'] != float('inf') else '∞'
        ax.set_title(f"{pair['p1']} − {pair['beta']:.4f}·{pair['p2']}  |  half-life={hl_str}  σ={pair['spread_std']:.4f}")
        ax.set_xlabel('Timestamp')
        ax.set_ylabel('Z-score')
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.25)
    plt.suptitle('Cointegration Spread Z-Scores (Pairs Trading Signal)', fontsize=13, fontweight='bold')
    plt.tight_layout()
    if save:
        plt.savefig('pairs_spread.png', dpi=150, bbox_inches='tight')
        print("    Saved: pairs_spread.png")
        plt.close()
    else:
        plt.show()


# ══════════════════════════════════════════════════════════════════════════════
# PRINT HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def hl_fmt(v):
    return '∞ (non mean-reverting)' if v == float('inf') else f'{v:.1f} ticks'


def nan_fmt(v, fmt='.4f'):
    return 'n/a' if math.isnan(v) else format(v, fmt)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    args = sys.argv[1:]
    do_plot = '--plot' in args
    do_save = '--save' in args
    args = [a for a in args if not a.startswith('--')]

    if not args:
        print("Usage: python3 analyze.py <prices_csv> [trades_csv] [--plot] [--save]")
        sys.exit(1)

    prices_file = args[0]
    trades_file = args[1] if len(args) > 1 else None

    SEP = '═' * 72
    sep = '─' * 72

    print(SEP)
    print('  IMC PROSPERITY 4 — COMPREHENSIVE MARKET ANALYSIS')
    print(SEP)

    prices = load_prices(prices_file)
    trades = load_trades(trades_file) if trades_file else {}
    products = sorted(prices.keys())

    print(f"\n  Products  : {', '.join(products)}")
    print(f"  Timestamps: {max(len(v) for v in prices.values())}")
    if trades_file:
        print(f"  Trade file: {trades_file}")

    # ── Per-product ──────────────────────────────────────────────────────────
    all_stats = {}
    for product in products:
        trade_list = trades.get(product)
        stats = analyze_product(product, prices[product], trade_list)
        all_stats[product] = stats

        print(f'\n{SEP}')
        print(f'  {product}')
        print(SEP)

        print(f"\n  ── Price Structure ─────────────────────────────────────────────")
        print(f"  Observations  : {stats['n']}")
        print(f"  Mean          : {stats['mean']:.4f}")
        print(f"  Std dev       : {stats['std']:.4f}")
        print(f"  Min / Max     : {stats['min']:.2f} / {stats['max']:.2f}  (range {stats['range']:.2f})")
        print(f"  CV            : {stats['cv']:.6f}  {'← very stable' if stats['cv'] < 0.001 else ''}")
        print(f"  Skewness (px) : {stats['skew_price']:.4f}")
        print(f"  Kurtosis (px) : {stats['kurt_price']:.4f}")

        print(f"\n  ── Bid-Ask Spread ──────────────────────────────────────────────")
        print(f"  Mean spread   : {stats['spread_mean']:.4f}")
        print(f"  Median spread : {stats['spread_median']:.4f}")
        print(f"  Std spread    : {stats['spread_std']:.4f}")
        print(f"  Min / Max     : {stats['spread_min']:.2f} / {stats['spread_max']:.2f}")

        print(f"\n  ── Order Book ──────────────────────────────────────────────────")
        print(f"  OBI mean      : {stats['obi_mean']:.4f}  (+ = net bid pressure)")
        print(f"  OBI std       : {stats['obi_std']:.4f}")
        print(f"  OBI pred. r   : {nan_fmt(stats['obi_pred_r'])}  (OBI[t] → return[t+1])")
        print(f"  Weighted mid  : {stats['wmid_mean']:.4f}  (vs mid {stats['mean']:.4f}, diff {stats['wmid_vs_mid']:+.4f})")
        print(f"  Avg bid depth : {stats['avg_bid_depth']:.1f}  ask depth: {stats['avg_ask_depth']:.1f}")

        print(f"\n  ── Return Statistics ───────────────────────────────────────────")
        print(f"  Mean return   : {stats['ret_mean']:.6f}%")
        print(f"  Return vol    : {stats['ret_std']:.6f}%  per tick")
        print(f"  Skewness      : {stats['ret_skew']:.4f}")
        print(f"  Excess kurt   : {stats['ret_kurt']:.4f}  {'← fat tails' if stats['ret_kurt'] > 1 else ''}")

        print(f"\n  ── Time-Series Structure ───────────────────────────────────────")
        h = stats['hurst']
        h_label = 'MEAN-REVERTING' if h < 0.45 else ('TRENDING' if h > 0.55 else 'RANDOM WALK')
        print(f"  Hurst exponent: {h:.4f}  → {h_label}")
        print(f"  AR(1) half-life: {hl_fmt(stats['halflife'])}")
        print(f"  Optimal EMA α : {stats['opt_ema_alpha']}")
        print(f"  Autocorr AC(1): {nan_fmt(stats['ac1'])}  AC(2): {nan_fmt(stats['ac2'])}  "
              f"AC(5): {nan_fmt(stats['ac5'])}  AC(10): {nan_fmt(stats['ac10'])}")

        if trade_list:
            print(f"\n  ── Trade Microstructure ────────────────────────────────────────")
            print(f"  Trade count   : {stats['trade_count']}")
            print(f"  Total volume  : {stats['trade_volume']}")
            print(f"  VWAP          : {stats['vwap']:.4f}  (vs mid {stats['mean']:.4f}, diff {stats['vwap_vs_mid']:+.4f})")
            print(f"  Flow imbalance: {stats['flow_imbalance']:+.4f}  (+ = net buying)")
            print(f"  Kyle's λ      : {nan_fmt(stats['kyles_lambda'], '.6f')}  (price impact per unit vol)")
            print(f"  Amihud illiq. : {nan_fmt(stats['amihud'], '.6f')} × 10⁻⁶")

            named = stats.get('named_traders', {})
            if named:
                print(f"\n  ── Named Traders ───────────────────────────────────────────────")
                for trader, td in sorted(named.items()):
                    avg_b = f"{td['avg_buy_px']:.2f}" if td['avg_buy_px'] else '—'
                    avg_s = f"{td['avg_sell_px']:.2f}" if td['avg_sell_px'] else '—'
                    net_label = 'NET BUYER' if td['net_vol'] > 0 else 'NET SELLER' if td['net_vol'] < 0 else 'NEUTRAL'
                    print(f"  {trader:12s}  buys={td['buys']:4d}(vol {td['buy_vol']:6d}, avgPx {avg_b})  "
                          f"sells={td['sells']:4d}(vol {td['sell_vol']:6d}, avgPx {avg_s})  "
                          f"net={td['net_vol']:+7d}  {net_label}")

        print(f"\n  ── Strategy Recommendation ─────────────────────────────────────")
        strat, notes = strategy_recommendation(stats)
        print(f"  Strategy      : {strat}")
        for note in notes:
            print(f"    → {note}")

    # ── Multi-product ────────────────────────────────────────────────────────
    if len(products) > 1:
        print(f'\n{SEP}')
        print('  MULTI-PRODUCT ANALYSIS')
        print(SEP)

        ret_matrix, common_ts = build_return_matrix(prices, products)

        print(f"\n  Common timestamps for return alignment: {len(common_ts)}")
        print(f"\n  ── Return Correlation Matrix ───────────────────────────────────")
        header = f"{'':18s}" + "".join(f"{p:>14s}" for p in products)
        print(f"  {header}")
        for p1 in products:
            row_str = f"  {p1:18s}" + "".join(f"{ret_matrix.get((p1, p2), float('nan')):14.4f}" for p2 in products)
            print(row_str)

        coint_results = cointegration_analysis(prices, products)
        print(f"\n  ── Cointegration Analysis (Engle-Granger) ──────────────────────")
        for r in coint_results:
            co_label = 'COINTEGRATED ✓' if r['cointegrated'] else 'not cointegrated'
            hl_str = hl_fmt(r['halflife'])
            print(f"  {r['p1']} / {r['p2']}:  {co_label}  half-life={hl_str}  β={r['beta']:.4f}  σ_spread={r['spread_std']:.4f}")
            if r['cointegrated']:
                spread_mean = r['spread_mean']
                spread_std = r['spread_std']
                print(f"    → Entry: spread Z > ±2  (|spread - {spread_mean:.2f}| > {2*spread_std:.4f})")
                print(f"    → Exit : spread Z < ±0.5")

        print(f"\n  ── Highly Correlated Pairs (|r| > 0.7) ────────────────────────")
        found = False
        for i, p1 in enumerate(products):
            for p2 in products[i + 1:]:
                r = ret_matrix.get((p1, p2), float('nan'))
                if not math.isnan(r) and abs(r) > 0.7:
                    print(f"  {p1} ↔ {p2}  r = {r:.4f}  → PAIRS TRADING CANDIDATE")
                    found = True
        if not found:
            print("  None found")

    # ── Plots ────────────────────────────────────────────────────────────────
    if do_plot or do_save:
        try:
            import matplotlib
            if do_save:
                matplotlib.use('Agg')
            import matplotlib.pyplot as plt

            print(f'\n{SEP}')
            print(f"  GENERATING PLOTS{' (saving to PNG)' if do_save else ''}")
            print(SEP)

            for product in products:
                print(f"  Plotting {product}...")
                plot_product(product, prices[product], trades.get(product, []),
                             all_stats[product], save=do_save)

            if len(products) > 1:
                print("  Plotting correlation heatmaps...")
                plot_correlation_heatmaps(prices, products, ret_matrix, save=do_save)
                print("  Plotting normalized price comparison...")
                plot_normalized_prices(prices, products, save=do_save)
                if coint_results and any(r['cointegrated'] for r in coint_results):
                    print("  Plotting pairs spread Z-scores...")
                    plot_pairs_spread(coint_results, save=do_save)

            print("  Done.")

        except ImportError:
            print("\n  [!] matplotlib not installed: pip install matplotlib seaborn")

    print()


if __name__ == '__main__':
    main()
