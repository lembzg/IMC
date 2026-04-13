"""
pipeline.py
-----------
Top-level orchestration: result log(s) -> diagnostics artefacts.

Inputs:  ``ResultsConfig``.
Outputs: ``results_outputs/<run_id>/<product>/...`` + a summary folder per run.

Trading decision informed: single command after every submission produces the
full post-mortem — report.md section J is the shortlist of concrete changes.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List

import pandas as pd

from . import (execution_analysis, order_lifecycle, pnl_analysis, plotting,
               position_analysis, regime_analysis, report_generator,
               signal_analysis, trade_diagnostics)
from .config import ResultsConfig
from .run_loader import load_runs
from .schema import Run

log = logging.getLogger(__name__)


def run_pipeline(cfg: ResultsConfig) -> Dict:
    runs: List[Run] = load_runs(Path(cfg.log_path), run_ids=cfg.run_ids or None)
    all_summaries: Dict = {}
    for run in runs:
        log.info("Analyzing run %s (%d orders, %d fills, %d market snaps)",
                 run.run_id, len(run.orders), len(run.fills), len(run.market))
        summary = _analyze_run(run, cfg)
        all_summaries[run.run_id] = summary
    # top-level index
    idx = Path(cfg.output_dir) / "index.json"
    idx.parent.mkdir(parents=True, exist_ok=True)
    idx.write_text(json.dumps(all_summaries, indent=2, default=float))
    log.info("Wrote index %s", idx)
    return all_summaries


def _analyze_run(run: Run, cfg: ResultsConfig) -> Dict:
    run_dir = Path(cfg.output_dir) / run.run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    orders = run.orders_df()
    fills = run.fills_df()
    market = run.market_df()
    signals = run.signals_df()
    positions_snap = run.positions_df()
    pnl_snaps = run.pnl_df()

    products = cfg.products or run.products
    sections_present = run.meta.get("sections", {"sandbox": True, "activities": True, "trades": True})

    # --- core reconstructions ---
    lifecycle = order_lifecycle.build_lifecycle(orders, fills, market)
    fill_rate = order_lifecycle.fill_rate_summary(lifecycle)
    positions_recon = position_analysis.reconstruct_positions(fills, products)
    if positions_snap.empty:
        positions_df = positions_recon
    else:
        positions_df = positions_snap  # prefer authoritative snapshots
    inv_stats = position_analysis.inventory_stats(positions_df)
    pnl_series = pnl_analysis.reconstruct_pnl(fills, market)
    authoritative = pnl_analysis.authoritative_pnl(pnl_snaps)
    pnl_stats = pnl_analysis.pnl_summary(pnl_series, fills)
    tag_attribution = pnl_analysis.attribution_by_tag(fills)

    annotated_fills = execution_analysis.annotate_fills(fills, market, cfg.horizons)
    exec_summary = execution_analysis.execution_summary(annotated_fills, cfg.horizons)

    sig_tables = signal_analysis.signal_effectiveness(
        fills, signals, market, cfg.horizons, n_buckets=cfg.signal_buckets)

    rt_df = trade_diagnostics.round_trips(fills, market)
    rt_stats = trade_diagnostics.round_trip_summary(rt_df)

    regime_df = regime_analysis.performance_by_regime(annotated_fills, market, horizon=10) \
        if sections_present.get("activities", True) else pd.DataFrame()

    # --- write tables ---
    summary_dir = run_dir / "summary"
    summary_dir.mkdir(parents=True, exist_ok=True)
    _dump_csv(orders, summary_dir / "orders.csv")
    _dump_csv(fills, summary_dir / "fills.csv")
    _dump_csv(lifecycle, summary_dir / "order_lifecycle.csv")
    _dump_csv(fill_rate, summary_dir / "fill_rate_summary.csv")
    _dump_csv(positions_df, summary_dir / "positions.csv")
    _dump_csv(pnl_series, summary_dir / "pnl_series.csv")
    _dump_csv(authoritative.reset_index() if not authoritative.empty else authoritative,
              summary_dir / "activities_pnl.csv")
    _dump_csv(annotated_fills, summary_dir / "fills_annotated.csv")
    _dump_csv(rt_df, summary_dir / "round_trips.csv")
    _dump_csv(tag_attribution, summary_dir / "tag_attribution.csv")
    _dump_csv(regime_df, summary_dir / "regime_performance.csv")
    for name, df in sig_tables.items():
        _dump_csv(df, summary_dir / f"signal_{name}.csv")

    # --- per-product plots + reports ---
    product_summaries: Dict[str, Dict] = {}
    for prod in products:
        prod_dir = run_dir / prod
        plots_dir = prod_dir / "plots"
        tables_dir = prod_dir / "tables"
        plots_dir.mkdir(parents=True, exist_ok=True)
        tables_dir.mkdir(parents=True, exist_ok=True)

        # per-product tables
        for name, df in {
            "orders": orders, "fills": fills, "lifecycle": lifecycle,
            "positions": positions_df, "pnl_series": pnl_series,
            "annotated_fills": annotated_fills, "round_trips": rt_df,
            "fill_rate": fill_rate, "regime": regime_df, "tag_attribution": tag_attribution,
        }.items():
            if df is None or df.empty or "product" not in df.columns:
                continue
            _dump_csv(df[df["product"] == prod], tables_dir / f"{name}.csv")

        if cfg.make_plots:
            plotting.plot_price_with_fills(market, fills, plots_dir / "01_price_fills.png", prod)
            plotting.plot_pnl(pnl_series, plots_dir / "02_pnl.png", prod, authoritative)
            plotting.plot_position(positions_df, plots_dir / "03_position.png", prod)
            plotting.plot_trade_pnl_hist(rt_df, plots_dir / "04_rt_pnl_hist.png", prod)
            plotting.plot_holding_time(rt_df, plots_dir / "05_holding_time.png", prod)
            plotting.plot_mfe_mae(rt_df, plots_dir / "06_mfe_mae.png", prod)
            plotting.plot_signal_buckets(sig_tables, plots_dir / "07_signal_buckets.png", prod)
            plotting.plot_fill_rate_by_tag(fill_rate, plots_dir / "08_fill_rate.png", prod)

        recs = report_generator.build_recommendations(
            prod, pnl_stats, inv_stats, exec_summary, rt_stats, fill_rate, sections_present)
        report_generator.write_product_report(
            prod_dir, run_id=run.run_id, product=prod,
            sections_present=sections_present,
            pnl_stats=pnl_stats, inv_stats=inv_stats,
            fill_rate=fill_rate, exec_summary=exec_summary,
            signal_tables=sig_tables, round_trip_stats=rt_stats,
            regime_table=regime_df, tag_attribution=tag_attribution,
            recommendations=recs,
        )
        product_summaries[prod] = {
            "pnl": pnl_stats.get(prod, {}),
            "inventory": inv_stats.get(prod, {}),
            "execution": exec_summary.get(prod, {}),
            "round_trip": rt_stats.get(prod, {}),
            "recommendations": recs,
        }

    run_summary = {
        "run_id": run.run_id,
        "source": run.source_path,
        "sections_present": sections_present,
        "products": products,
        "per_product": product_summaries,
    }
    report_generator.write_run_summary(summary_dir, run_summary)
    return run_summary


def _dump_csv(df: pd.DataFrame, path: Path) -> None:
    if df is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
