"""
config.py
---------
Central constants and defaults.

What it informs: keeps magic numbers out of logic modules so you can sweep
horizons, window sizes, and thresholds from one place.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List

# --- IMC CSV schema assumptions (explicit) ---------------------------------
# prices CSV columns (semicolon-separated):
#   day;timestamp;product;
#   bid_price_1;bid_volume_1;bid_price_2;bid_volume_2;bid_price_3;bid_volume_3;
#   ask_price_1;ask_volume_1;ask_price_2;ask_volume_2;ask_price_3;ask_volume_3;
#   mid_price;profit_and_loss
# trades CSV columns (semicolon-separated):
#   timestamp;buyer;seller;symbol;currency;price;quantity
# NOTE: timestamp is an integer tick (IMC uses 100ms steps). Missing depth
#       levels appear as empty cells.
PRICES_SEP = ";"
TRADES_SEP = ";"
PRICES_FNAME_GLOB = "prices_round_*_day_*.csv"
TRADES_FNAME_GLOB = "trades_round_*_day_*.csv"

# Column names we standardize to internally.
COL_TS = "timestamp"
COL_PRODUCT = "product"
COL_MID = "mid_price"
COL_DAY = "day"

# Default analysis parameters.
DEFAULT_HORIZONS: List[int] = [1, 5, 10, 20, 50]   # ticks ahead for FV / signal eval
DEFAULT_EMA_ALPHAS: List[float] = [0.05, 0.1, 0.2, 0.3, 0.5]
DEFAULT_ROLL_WINDOWS: List[int] = [20, 50, 100, 200]
DEFAULT_ZSCORE_WINDOWS: List[int] = [50, 100, 200]
DEFAULT_ZSCORE_THRESHOLDS: List[float] = [1.0, 1.5, 2.0, 2.5]
DEFAULT_VOL_WINDOW: int = 100
DEFAULT_OBI_DECILES: int = 10

# Strategy defaults.
DEFAULT_POSITION_LIMIT: int = 20
DEFAULT_HOLD_HORIZONS: List[int] = [5, 10, 20, 50]
DEFAULT_QUOTE_WIDTHS: List[int] = [1, 2, 3]


@dataclass
class AnalyzerConfig:
    """Runtime configuration for a pipeline run."""
    data_dir: Path = Path("data")
    output_dir: Path = Path("outputs")
    round_label: str = "round_0"
    products: List[str] = field(default_factory=list)  # empty = all
    days: List[int] = field(default_factory=list)      # empty = all
    horizons: List[int] = field(default_factory=lambda: list(DEFAULT_HORIZONS))
    ema_alphas: List[float] = field(default_factory=lambda: list(DEFAULT_EMA_ALPHAS))
    roll_windows: List[int] = field(default_factory=lambda: list(DEFAULT_ROLL_WINDOWS))
    z_windows: List[int] = field(default_factory=lambda: list(DEFAULT_ZSCORE_WINDOWS))
    z_thresholds: List[float] = field(default_factory=lambda: list(DEFAULT_ZSCORE_THRESHOLDS))
    vol_window: int = DEFAULT_VOL_WINDOW
    position_limit: int = DEFAULT_POSITION_LIMIT
    hold_horizons: List[int] = field(default_factory=lambda: list(DEFAULT_HOLD_HORIZONS))
    quote_widths: List[int] = field(default_factory=lambda: list(DEFAULT_QUOTE_WIDTHS))
    make_plots: bool = True
    run_sweeps: bool = True
    cross_product: bool = True
