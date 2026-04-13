"""
config.py
---------
Defaults for the results analyzer.

Trading decision informed: single place to change fill-inference thresholds,
horizon windows, and plot settings for competition-time iteration.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List


@dataclass
class ResultsConfig:
    log_path: Path = Path("backtests")       # file OR folder of .log files
    output_dir: Path = Path("results_outputs")
    run_ids: List[str] = field(default_factory=list)   # empty = all logs in folder
    products: List[str] = field(default_factory=list)  # empty = all
    make_plots: bool = True
    # Horizons (in ticks) over which to measure adverse selection & signal efficacy.
    horizons: List[int] = field(default_factory=lambda: [1, 5, 10, 20, 50])
    # Signal buckets for effectiveness tables.
    signal_buckets: int = 5
    # Passive vs aggressive classifier: if our quote price was at/inside the
    # best quotes we call it "quote"; if it was >= best_ask (buy) or
    # <= best_bid (sell) at that tick, we treat it as a "take". Parser sets
    # this when it has market context.
    # Round-trip reconstruction uses FIFO matching by default.
    rt_match: str = "fifo"
    counterparty_submission: str = "SUBMISSION"
