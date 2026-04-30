"""
Test the pair-mean-deviation strategy on all existing pairs.
Strategy: every tick compute pair_mean = (a + b) / 2.
If a > pair_mean + ENTRY: sell a, buy b.
If b > pair_mean + ENTRY: sell b, buy a.
Exit when deviation drops within EXIT of pair_mean.
"""
import csv, subprocess, re
from pathlib import Path
from collections import defaultdict

DATA_DIR = Path('/home/j39233pt/Desktop/IMC/data/round5')
LIMIT = 10

PAIRS = {
    "XS_XL":        ("PEBBLES_XS",          "PEBBLES_XL"),
    "M_S":          ("PEBBLES_M",            "PEBBLES_S"),
    "STRAW_PIST":   ("SNACKPACK_STRAWBERRY", "SNACKPACK_PISTACHIO"),
    "AMBER_ORANGE": ("UV_VISOR_AMBER",       "UV_VISOR_ORANGE"),
    "IRON_PEBS":    ("ROBOT_IRONING",        "PEBBLES_S"),
    "CIRCLE_TRI":   ("MICROCHIP_CIRCLE",     "MICROCHIP_TRIANGLE"),
    "LAUNDRY_DISH": ("ROBOT_LAUNDRY",        "ROBOT_DISHES"),
    "SUEDE_COTTON": ("SLEEP_POD_SUEDE",      "SLEEP_POD_COTTON"),
}


def load_ts(day, products):
    path = DATA_DIR / f'prices_round_5_day_{day}.csv'
    ts_map = defaultdict(dict)
    with open(path) as f:
        for row in csv.DictReader(f, delimiter=';'):
            if row['product'] in products:
                ts = int(row['timestamp'])
                ts_map[ts][row['product']] = {
                    'mid': float(row['mid_price']),
                    'bid': float(row['bid_price_1']) if row['bid_price_1'].strip() else None,
                    'ask': float(row['ask_price_1']) if row['ask_price_1'].strip() else None,
                }
    return ts_map


def backtest(ts_map, a, b, entry, exit_t):
    pos = {a: 0, b: 0}
    cash = 0.0
    for ts in sorted(ts_map.keys()):
        p = ts_map[ts]
        if a not in p or b not in p:
            continue
        pair_mean = (p[a]['mid'] + p[b]['mid']) / 2.0
        dev = p[a]['mid'] - pair_mean  # positive = a expensive

        # Exit when deviation has collapsed back within exit_t of pair mean
        for prod in (a, b):
            position = pos[prod]
            br = LIMIT - position
            sr = LIMIT + position
            if position > 0 and abs(dev) <= exit_t and sr > 0 and p[prod]['bid']:
                cash += position * p[prod]['bid']
                pos[prod] = 0
            elif position < 0 and abs(dev) <= exit_t and br > 0 and p[prod]['ask']:
                cash += position * p[prod]['ask']
                pos[prod] = 0

        # Entry
        if dev > entry:  # a expensive: sell a, buy b
            sr = LIMIT + pos[a]
            br = LIMIT - pos[b]
            if sr > 0 and p[a]['bid']:
                cash += sr * p[a]['bid']
                pos[a] -= sr
            if br > 0 and p[b]['ask']:
                cash -= br * p[b]['ask']
                pos[b] += br
        elif dev < -entry:  # b expensive: buy a, sell b
            br = LIMIT - pos[a]
            sr = LIMIT + pos[b]
            if br > 0 and p[a]['ask']:
                cash -= br * p[a]['ask']
                pos[a] += br
            if sr > 0 and p[b]['bid']:
                cash += sr * p[b]['bid']
                pos[b] -= sr

    # Mark to market
    for ts in sorted(ts_map.keys(), reverse=True):
        prods = ts_map[ts]
        if a in prods and b in prods:
            for prod in (a, b):
                cash += pos[prod] * prods[prod]['mid']
            break
    return cash


if __name__ == '__main__':
    ENTRIES = [100, 200, 300, 400, 500, 700]
    EXITS   = [50, 100, 150]

    for name, (a, b) in PAIRS.items():
        day_data = {d: load_ts(d, {a, b}) for d in [2, 3, 4]}
        best = []
        for entry in ENTRIES:
            for exit_t in EXITS:
                pnls = [backtest(day_data[d], a, b, entry, exit_t) for d in [2, 3, 4]]
                best.append((sum(pnls), entry, exit_t, pnls))

        best.sort(reverse=True)
        t, entry, exit_t, pnls = best[0]
        print(f'{name:<16} entry={entry:>4} exit={exit_t:>4} | '
              f'D2={pnls[0]:>8.0f} D3={pnls[1]:>8.0f} D4={pnls[2]:>8.0f} | total={t:>8.0f}')
