"""
Parameter Sweep Backtester — IMC Prosperity 4
==============================================
Wraps prosperity4btest (https://github.com/nabayansaha/imc-prosperity-4-backtester)
with a parameter grid search. For each combination it injects new constants into
a temp copy of trader.py, runs the CLI, parses total P&L, and ranks results.

Install the backtester once:
    pip install -U prosperity4btest

Usage:
    python backtester.py                         # 50 random combos, round 0
    python backtester.py --round 0               # explicit round (all days)
    python backtester.py --round 0--2 0--1 0-0  # specific days, P&L summed
    python backtester.py --full-grid             # exhaustive (can be slow)
    python backtester.py --samples 100 --top 10
    python backtester.py --match-trades worse    # match-trades mode

Edit SWEEP_PARAMS below to control what gets swept.
Set FIXED_PARAMS to hold specific parameters constant.
"""

import subprocess
import itertools
import random
import re
import os
import sys
import csv
import json
import tempfile
import argparse
from io import StringIO
from pathlib import Path
from datetime import datetime

TRADER_FILE   = Path(__file__).parent / 'trader_diagnostic.py'
DATA_DIR      = Path(__file__).parent / 'data_bt'
BACKTESTS_DIR = Path(__file__).parent / 'backtests'
BACKTESTS_DIR.mkdir(exist_ok=True)


# ══════════════════════════════════════════════════════════════════════════════
# PARAMETER SEARCH SPACE
# ══════════════════════════════════════════════════════════════════════════════
# Keys must exactly match the constant names at module level in trader.py.
# Each value is a list of candidates to try.

SWEEP_PARAMS = {
    # ── trader_diagnostic dual-EMA trend-filtered reversion sweep ─────────────
    'HYDRO_LOOKBACK':        [100, 150, 200, 300, 400],
    'HYDRO_DROP_THRESH':     [20, 25, 30, 35, 40, 50],
    'HYDRO_RISE_THRESH':     [20, 25, 30, 35, 40, 50],
    'HYDRO_EXIT_PROFIT':     [10, 15, 20, 25],
    'HYDRO_EMA_FAST_ALPHA':  [0.01, 0.02, 0.05],
    'HYDRO_EMA_SLOW_ALPHA':  [0.002, 0.005, 0.01],
    'HYDRO_SWEEP_QTY':       [30, 50, 80],
}
# Parameters fixed at a specific value (excluded from sweep):
FIXED_PARAMS: dict = {}

# Validity filter: only run combos satisfying these constraints.
# Each entry is a tuple of (param_a, param_b) meaning param_a must be > param_b.
COMBO_CONSTRAINTS: list = []


# ══════════════════════════════════════════════════════════════════════════════
# PARAMETER INJECTION
# ══════════════════════════════════════════════════════════════════════════════

def inject_params(source: str, params: dict) -> str:
    """
    Patch scalar constant assignments in trader.py source.
    Handles:  PARAM = 1.5   →   PARAM = <new_value>
    Works for int, float, and list values.
    Does NOT touch lines inside class bodies or functions.
    """
    for name, value in params.items():
        if isinstance(value, float):
            val_str = repr(value)          # e.g. 0.4
        elif isinstance(value, int):
            val_str = str(value)           # e.g. 4
        elif isinstance(value, list):
            val_str = repr(value)          # e.g. [6, 3, 1]
        else:
            val_str = repr(value)

        # Match: ^[whitespace]NAME   =   <anything up to end of line>
        # Handles both module-level and indented class-level constants.
        source = re.sub(
            rf'^(\s*{re.escape(name)}\s*=\s*).*$',
            rf'\g<1>{val_str}',
            source,
            flags=re.MULTILINE,
        )
    return source


# ══════════════════════════════════════════════════════════════════════════════
# P&L PARSING
# ══════════════════════════════════════════════════════════════════════════════

def parse_pnl(output: str) -> float | None:
    """
    Extract total P&L from prosperity4btest stdout.

    Primary format (printed to stdout):
        Total profit: 25,146

    When multiple days are run the last "Total profit:" line is the grand total.
    Falls back to summing per-product lines if the grand total is absent.
    """
    # ── Strategy 1: last "Total profit: X" line (grand total across all days) ─
    matches = re.findall(r'Total profit:\s*(-?[\d,]+)', output)
    if matches:
        # Last match = grand total when multiple days are printed
        return float(matches[-1].replace(',', ''))

    # ── Strategy 2: sum product lines  "PRODUCT: X,XXX" ─────────────────────
    # e.g. "EMERALDS: 7,182" / "TOMATOES: 5,678"
    # Only take the last block (last day) to avoid double-counting
    product_matches = re.findall(r'^[A-Z_]+:\s*(-?[\d,]+)$', output, re.MULTILINE)
    if product_matches:
        # The last N product lines before the final summary
        try:
            return sum(float(v.replace(',', '')) for v in product_matches[-len(product_matches)//2 or len(product_matches):])
        except Exception:
            return sum(float(v.replace(',', '')) for v in product_matches)

    # ── Strategy 3: Activities log CSV (log-file format) ─────────────────────
    m = re.search(
        r'Activities log:\s*\n(.*?)(?:\n\s*\nTrade History:|\n\s*\nSandbox|\Z)',
        output, re.DOTALL
    )
    if m:
        try:
            reader = csv.DictReader(StringIO(m.group(1).strip()), delimiter=';')
            last_pnl: dict[str, float] = {}
            for row in reader:
                product = row.get('product', '').strip()
                raw     = row.get('profit_and_loss', '').strip()
                if product and raw:
                    last_pnl[product] = float(raw)
            if last_pnl:
                return sum(last_pnl.values())
        except Exception:
            pass

    return None


# ══════════════════════════════════════════════════════════════════════════════
# SINGLE BACKTEST RUN
# ══════════════════════════════════════════════════════════════════════════════

def run_one(params: dict, round_days: list[str], extra_args: list[str]) -> float | None:
    """
    Inject params into a temp file, run prosperity4btest, return total P&L.
    Returns None on timeout or parse failure.
    """
    source  = TRADER_FILE.read_text()
    patched = inject_params(source, params)

    tmp = tempfile.NamedTemporaryFile(
        mode='w', suffix='.py', delete=False, prefix='trader_sweep_',
        dir=tempfile.gettempdir()
    )
    tmp.write(patched)
    tmp.close()

    try:
        cmd = (
            ['prosperity4btest', tmp.name]
            + round_days
            + ['--no-out', '--data', str(DATA_DIR)]
            + extra_args
        )
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        return parse_pnl(proc.stdout + proc.stderr)

    except subprocess.TimeoutExpired:
        return None

    except FileNotFoundError:
        print('\n[ERROR] prosperity4btest not found.')
        print('  Install with:  pip install -U prosperity4btest')
        sys.exit(1)

    finally:
        os.unlink(tmp.name)


# ══════════════════════════════════════════════════════════════════════════════
# GRID BUILDING
# ══════════════════════════════════════════════════════════════════════════════

def build_grid() -> list[dict]:
    """Cartesian product of SWEEP_PARAMS minus fixed params, filtered by COMBO_CONSTRAINTS."""
    sweep = {k: v for k, v in SWEEP_PARAMS.items() if k not in FIXED_PARAMS}
    keys  = list(sweep.keys())
    grid  = []
    for vals in itertools.product(*[sweep[k] for k in keys]):
        combo = dict(FIXED_PARAMS)
        combo.update(zip(keys, vals))
        if all(combo[a] > combo[b] for a, b in COMBO_CONSTRAINTS
               if a in combo and b in combo):
            grid.append(combo)
    return grid


# ══════════════════════════════════════════════════════════════════════════════
# DISPLAY HELPERS
# ══════════════════════════════════════════════════════════════════════════════

SEP = '═' * 72
sep = '─' * 72


def fmt_params(combo: dict, keys: list) -> str:
    return '  '.join(f'{k}={combo[k]}' for k in keys)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(
        description='Parameter sweep using prosperity4btest',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  python backtester.py                           # 50 random combos, round 0
  python backtester.py --round 0--2 0--1 0-0    # three specific days
  python backtester.py --full-grid               # exhaustive (slow)
  python backtester.py --samples 30 --top 10
  python backtester.py --match-trades worse
        """
    )
    ap.add_argument('--round', nargs='+', default=['3-0', '3-1', '3-2'], metavar='SPEC',
                    help='Round/day specifiers passed to prosperity4btest (default: 1-0 1--1 1--2)')
    ap.add_argument('--full-grid', action='store_true',
                    help='Run every combination (can be very slow)')
    ap.add_argument('--samples', type=int, default=50,
                    help='Random combos to try when not using --full-grid (default: 50)')
    ap.add_argument('--top', type=int, default=20,
                    help='Top N results to display (default: 20)')
    ap.add_argument('--seed', type=int, default=42,
                    help='RNG seed for reproducibility (default: 42)')
    ap.add_argument('--match-trades', choices=['all', 'worse', 'none'], default=None,
                    help='Trade matching mode (default: backtester default)')
    args = ap.parse_args()

    grid        = build_grid()
    total_grid  = len(grid)
    sweep_keys  = [k for k in SWEEP_PARAMS if k not in FIXED_PARAMS]

    if args.full_grid:
        combos = grid
        mode   = f'FULL GRID ({total_grid} combos)'
    else:
        n      = min(args.samples, total_grid)
        random.seed(args.seed)
        combos = random.sample(grid, n)
        mode   = f'RANDOM SAMPLE  {n} of {total_grid} possible combos'

    extra_args = []
    if args.match_trades:
        extra_args += ['--match-trades', args.match_trades]

    # ── Header ──────────────────────────────────────────────────────────────
    print(SEP)
    print(f'  IMC PROSPERITY 4 — PARAMETER SWEEP')
    print(SEP)
    print(f'  Mode       : {mode}')
    print(f'  Round/days : {" ".join(args.round)}')
    print(f'  Trader     : {TRADER_FILE}')
    print(f'\n  Sweeping {len(sweep_keys)} parameters:')
    for k in sweep_keys:
        print(f'    {k:30s} {SWEEP_PARAMS[k]}')
    if FIXED_PARAMS:
        print(f'\n  Fixed:')
        for k, v in FIXED_PARAMS.items():
            print(f'    {k:30s} = {v}')
    print(f'\n  Running {len(combos)} backtests...\n')
    print(sep)

    results: list[tuple[float, dict]] = []
    best_pnl = float('-inf')
    failed   = 0

    for i, combo in enumerate(combos, 1):
        print(f'  [{i:>{len(str(len(combos)))}}/{len(combos)}]  '
              f'{fmt_params(combo, sweep_keys)}', end='  →  ', flush=True)

        pnl = run_one(combo, args.round, extra_args)

        if pnl is None:
            print('FAILED (check backtester install or log format)')
            failed += 1
        else:
            is_best = pnl > best_pnl
            if is_best:
                best_pnl = pnl
            print(f'P&L = {pnl:>12.2f}' + ('  ← NEW BEST' if is_best else ''))
            results.append((pnl, combo))

    if not results:
        print(f'\n[ERROR] All {len(combos)} runs failed.')
        print('  • Is prosperity4btest installed?  pip install -U prosperity4btest')
        print('  • Does round data exist?  Check https://github.com/nabayansaha/imc-prosperity-4-backtester')
        sys.exit(1)

    results.sort(key=lambda x: x[0], reverse=True)
    show = min(args.top, len(results))

    # ── Results table ────────────────────────────────────────────────────────
    print(f'\n{SEP}')
    print(f'  TOP {show} RESULTS  ({failed} failed / {len(results)} succeeded)')
    print(SEP)

    col_w = max(len(k) for k in sweep_keys) + 2
    for rank, (pnl, combo) in enumerate(results[:show], 1):
        marker = '  ★ BEST' if rank == 1 else ''
        print(f'\n  #{rank}  P&L = {pnl:,.2f}{marker}')
        for k in sweep_keys:
            print(f'    {k:{col_w}s} = {combo[k]}')

    # ── Best params block ────────────────────────────────────────────────────
    best_pnl, best_combo = results[0]
    print(f'\n{SEP}')
    print(f'  BEST PARAMETERS — paste into trader.py')
    print(sep)
    for k in sweep_keys:
        v = best_combo[k]
        print(f'  {k:30s} = {v!r}')
    print(sep)
    print(f'  Best total P&L: {best_pnl:,.2f}')
    print(f'  Baseline (current trader.py):')

    # Show what the current trader.py has for comparison
    source = TRADER_FILE.read_text()
    for k in sweep_keys:
        m = re.search(rf'^{re.escape(k)}\s*=\s*(.+)$', source, re.MULTILINE)
        current = m.group(1).strip() if m else '(not found)'
        print(f'    {k:30s} = {current}')

    # ── Save results ─────────────────────────────────────────────────────────
    ts       = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    out_file = BACKTESTS_DIR / f'sweep_{ts}.json'
    with open(out_file, 'w') as f:
        json.dump({
            'timestamp':  ts,
            'round_days': args.round,
            'mode':       mode,
            'fixed':      FIXED_PARAMS,
            'sweep':      {k: SWEEP_PARAMS[k] for k in sweep_keys},
            'results': [
                {'rank': rank, 'pnl': pnl, 'params': combo}
                for rank, (pnl, combo) in enumerate(results, 1)
            ],
        }, f, indent=2)

    print(f'\n  Full results saved → {out_file}')
    print(SEP)


if __name__ == '__main__':
    main()
