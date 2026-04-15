"""
parsers/imc_submission_log.py
-----------------------------
Parse the official IMC Prosperity website submission log format into a
canonical ``Run``.

Format: a single top-level JSON object with keys:
    submissionId   – str
    activitiesLog  – semicolon-delimited CSV string (same columns as the
                     prices/trades CSVs, plus profit_and_loss)
    logs           – list of {sandboxLog, lambdaLog, timestamp} objects
                     where lambdaLog is the JSON array emitted by the
                     project's Logger class:
                         [
                           [ts, traderData, listings, order_depths,
                            own_trades, market_trades, position, observations],
                           [[symbol, price, qty], ...],   # orders submitted
                           conversions,
                           trader_data,
                           log_string
                         ]
    tradeHistory   – list of trade dicts  {timestamp, buyer, seller,
                                           symbol, price, quantity, ...}
"""
from __future__ import annotations

import json
import logging
from io import StringIO
from pathlib import Path

import pandas as pd

from ..schema import Fill, MarketSnap, Order, PnlSnap, PositionSnap, Run

log = logging.getLogger(__name__)

SUBMISSION = "SUBMISSION"


class ImcSubmissionLogParser:
    name = "imc_submission_log"

    def can_parse(self, path: Path) -> bool:
        if path.suffix != ".log":
            return False
        try:
            with open(path, "r", errors="ignore") as f:
                head = f.read(128)
            return head.lstrip().startswith("{") and "submissionId" in head
        except OSError:
            return False

    def parse(self, path: Path) -> Run:
        text = path.read_text(errors="ignore")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            log.error("%s: JSON parse failed: %s", path.name, e)
            return Run(run_id=path.stem, source_path=str(path))

        run = Run(run_id=path.stem, source_path=str(path))

        _parse_logs(data.get("logs") or [], run)
        _parse_activities(data.get("activitiesLog") or "", run)
        _parse_trade_history(data.get("tradeHistory") or [], run)

        run.products = sorted(
            {o.product for o in run.orders}
            | {f.product for f in run.fills}
            | {p.product for p in run.positions}
        )
        return run


# ---------------------------------------------------------------------------
# Lambda logs → orders + positions
# ---------------------------------------------------------------------------

def _parse_logs(logs: list, run: Run) -> None:
    for entry in logs:
        lam = entry.get("lambdaLog") or ""
        if not lam:
            continue
        try:
            frame = json.loads(lam)
        except json.JSONDecodeError:
            continue

        if not isinstance(frame, list) or len(frame) < 2:
            continue

        state_arr = frame[0]   # [ts, traderData, listings, depths, ...]
        orders_arr = frame[1]  # [[symbol, price, qty], ...]

        if not isinstance(state_arr, list) or len(state_arr) < 7:
            continue

        ts = int(state_arr[0])

        # Positions (index 6 is the position dict)
        pos_map = state_arr[6]
        if isinstance(pos_map, dict):
            for prod, qty in pos_map.items():
                run.positions.append(
                    PositionSnap(ts=ts, product=str(prod), position=int(qty))
                )

        # Orders submitted this tick
        if not isinstance(orders_arr, list):
            continue
        for o in orders_arr:
            if not isinstance(o, list) or len(o) < 3:
                continue
            symbol, price, qty = o[0], o[1], o[2]
            if qty == 0:
                continue
            run.orders.append(Order(
                ts=ts,
                product=str(symbol),
                side=+1 if qty > 0 else -1,
                price=float(price),
                size=abs(int(qty)),
                kind="quote",
            ))


# ---------------------------------------------------------------------------
# activitiesLog CSV → market snaps + PnL snaps
# ---------------------------------------------------------------------------

def _parse_activities(blob: str, run: Run) -> None:
    blob = blob.strip()
    if not blob:
        return
    try:
        df = pd.read_csv(StringIO(blob), sep=";")
    except Exception as e:
        log.warning("Failed to parse activitiesLog: %s", e)
        return

    for _, r in df.iterrows():
        prod = r.get("product")
        if pd.isna(prod):
            continue
        ts = int(r["timestamp"])
        bb = r.get("bid_price_1")
        ba = r.get("ask_price_1")
        mid = r.get("mid_price")
        run.market.append(MarketSnap(
            ts=ts,
            product=str(prod),
            best_bid=float(bb) if pd.notna(bb) else None,
            best_ask=float(ba) if pd.notna(ba) else None,
            mid=float(mid) if pd.notna(mid) else None,
        ))
        pnl_val = r.get("profit_and_loss")
        if pd.notna(pnl_val):
            run.pnl.append(PnlSnap(
                ts=ts,
                product=str(prod),
                realized=float("nan"),
                unrealized=float("nan"),
                total=float(pnl_val),
            ))


# ---------------------------------------------------------------------------
# tradeHistory → fills
# ---------------------------------------------------------------------------

def _parse_trade_history(trades: list, run: Run) -> None:
    for t in trades:
        buyer = t.get("buyer") or ""
        seller = t.get("seller") or ""
        if buyer != SUBMISSION and seller != SUBMISSION:
            continue
        side = +1 if buyer == SUBMISSION else -1
        counterparty = seller if side > 0 else buyer
        run.fills.append(Fill(
            ts=int(t["timestamp"]),
            product=str(t["symbol"]),
            side=side,
            price=float(t["price"]),
            size=int(t["quantity"]),
            counterparty=counterparty or None,
        ))
