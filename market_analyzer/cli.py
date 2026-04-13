"""
cli.py
------
Command-line entrypoint. Usage:

    python -m market_analyzer --data-dir data --output-dir outputs --round round_0
    python -m market_analyzer --product EMERALDS --day -1
    python -m market_analyzer --no-sweeps --no-plots            # reports/tables only
    python -m market_analyzer --no-cross-product

Trading decision informed: one repeatable command to regenerate every
artefact from fresh data — no notebook archaeology during the round.
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from .config import AnalyzerConfig
from .pipeline import run_pipeline


def _parse_args(argv=None) -> AnalyzerConfig:
    p = argparse.ArgumentParser(prog="market_analyzer",
                                description="IMC Prosperity 4 research analyzer")
    p.add_argument("--data-dir", type=Path, default=Path("data"))
    p.add_argument("--output-dir", type=Path, default=Path("outputs"))
    p.add_argument("--round", dest="round_label", default="round_0")
    p.add_argument("--product", action="append", default=[],
                   help="Restrict to product (repeatable). Default: all.")
    p.add_argument("--day", action="append", type=int, default=[],
                   help="Restrict to day (repeatable). Default: all.")
    p.add_argument("--no-plots", action="store_true")
    p.add_argument("--no-sweeps", action="store_true")
    p.add_argument("--no-cross-product", action="store_true")
    p.add_argument("--position-limit", type=int, default=20)
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    return AnalyzerConfig(
        data_dir=args.data_dir,
        output_dir=args.output_dir,
        round_label=args.round_label,
        products=args.product,
        days=args.day,
        make_plots=not args.no_plots,
        run_sweeps=not args.no_sweeps,
        cross_product=not args.no_cross_product,
        position_limit=args.position_limit,
    )


def main(argv=None) -> int:
    cfg = _parse_args(argv)
    run_pipeline(cfg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
