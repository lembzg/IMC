"""
cli.py
------
CLI for the results analyzer.

Examples:
    python -m results_analyzer --log-path backtests/2026-04-13_02-32-38.log
    python -m results_analyzer --log-path backtests --run-id 2026-04-13_02-32-38
    python -m results_analyzer --product TOMATOES --no-plots
    python -m results_analyzer --output-dir results_outputs --log-path backtests
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from .config import ResultsConfig
from .pipeline import run_pipeline


def _parse_args(argv=None) -> ResultsConfig:
    p = argparse.ArgumentParser(prog="results_analyzer",
                                description="IMC Prosperity 4 post-run diagnostics")
    p.add_argument("--log-path", type=Path, default=Path("backtests"),
                   help="log file OR folder of .log files (default: backtests)")
    p.add_argument("--output-dir", type=Path, default=Path("results_outputs"))
    p.add_argument("--run-id", action="append", default=[],
                   help="Restrict to these run ids (stem of .log). Repeatable.")
    p.add_argument("--product", action="append", default=[])
    p.add_argument("--no-plots", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    return ResultsConfig(
        log_path=args.log_path,
        output_dir=args.output_dir,
        run_ids=args.run_id,
        products=args.product,
        make_plots=not args.no_plots,
    )


def main(argv=None) -> int:
    cfg = _parse_args(argv)
    run_pipeline(cfg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
