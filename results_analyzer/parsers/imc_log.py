"""
parsers/imc_log.py
------------------
Parse the IMC Prosperity submission log format into a canonical ``Run``.

Observed format (explicit assumptions, may evolve by round):
  1. "Sandbox logs:" section. Newline-separated JSON objects, each:
       {"sandboxLog": str, "lambdaLog": <json string>, "timestamp": int}
     ``lambdaLog`` is a JSON string emitted by our trader. We assume the
     convention used by this project:
         {
           "GENERAL": {"TS": int, "POS": {product: int, ...}},
           "<PRODUCT>": {
              "BUY":  {"p": price, "v": size},   # our bid quote
              "SELL": {"p": price, "v": size},   # our ask quote
              "EMA":  float, "Z": float,
              "OBI":  float, "SHIFT": float,
              "QUOTES": [bid, ask],
              ...
           }, ...
         }
     If a future trader emits an explicit "TAG" key per product we also
     capture it as the order tag.

  2. "Activities log:" — CSV identical to prices_round_*_day_*.csv plus
     ``profit_and_loss`` column (authoritative PnL per product per tick).

  3. "Trade History:" — JSON list of trade dicts. IMC emits trailing commas
     before closing braces which standard json rejects; we sanitize first.
     Rows where ``buyer`` == ``SUBMISSION`` or ``seller`` == ``SUBMISSION``
     are our fills.

If any section is absent we degrade gracefully — downstream modules check
``Run.has(...)``.
"""
from __future__ import annotations

import json
import logging
import re
from io import StringIO
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from ..schema import (Fill, MarketSnap, Order, PnlSnap, PositionSnap, Run,
                      SignalEvent)

log = logging.getLogger(__name__)


SUBMISSION = "SUBMISSION"


class ImcLogParser:
    name = "imc_log"

    def can_parse(self, path: Path) -> bool:
        if path.suffix != ".log":
            return False
        # Cheap signature check.
        with open(path, "r", errors="ignore") as f:
            head = f.read(256)
        return "Sandbox logs:" in head or "lambdaLog" in head

    def parse(self, path: Path) -> Run:
        text = Path(path).read_text(errors="ignore")
        sandbox_raw, activities_raw, trades_raw = _split_sections(text)

        run = Run(run_id=path.stem, source_path=str(path))

        # Section 1: sandbox logs -> orders, positions, signals
        if sandbox_raw:
            _parse_sandbox(sandbox_raw, run)
        else:
            log.warning("%s: no Sandbox logs section", path.name)

        # Section 2: activities -> market snaps + authoritative PnL snaps
        if activities_raw:
            _parse_activities(activities_raw, run)
        else:
            log.warning("%s: no Activities log section", path.name)

        # Section 3: trade history -> fills
        if trades_raw:
            _parse_trades(trades_raw, run)
        else:
            log.warning("%s: no Trade History section", path.name)

        run.products = sorted({o.product for o in run.orders} |
                              {f.product for f in run.fills} |
                              {p.product for p in run.positions})
        run.meta["sections"] = {
            "sandbox": bool(sandbox_raw),
            "activities": bool(activities_raw),
            "trades": bool(trades_raw),
        }
        return run


# --- Section splitting -----------------------------------------------------

def _split_sections(text: str) -> Tuple[str, str, str]:
    """Return (sandbox_block, activities_block, trades_block)."""
    # Headers appear on their own lines.
    idx_act = text.find("\nActivities log:")
    idx_th = text.find("\nTrade History:")
    # "Sandbox logs:" header at the top.
    sandbox_start = text.find("Sandbox logs:")
    sandbox_block = ""
    if sandbox_start != -1:
        sandbox_end = idx_act if idx_act != -1 else (idx_th if idx_th != -1 else len(text))
        sandbox_block = text[sandbox_start + len("Sandbox logs:"):sandbox_end]
    activities_block = ""
    if idx_act != -1:
        act_end = idx_th if idx_th != -1 else len(text)
        activities_block = text[idx_act + len("\nActivities log:"):act_end]
    trades_block = ""
    if idx_th != -1:
        trades_block = text[idx_th + len("\nTrade History:"):]
    return sandbox_block, activities_block, trades_block


# --- Sandbox block ---------------------------------------------------------

def _iter_json_objects(blob: str):
    """Yield successive JSON objects from a concatenated stream."""
    decoder = json.JSONDecoder()
    i, n = 0, len(blob)
    while i < n:
        # skip whitespace
        while i < n and blob[i] in " \r\n\t":
            i += 1
        if i >= n:
            break
        try:
            obj, end = decoder.raw_decode(blob, i)
        except json.JSONDecodeError:
            # Skip to next '{'
            nxt = blob.find("{", i + 1)
            if nxt == -1:
                return
            i = nxt
            continue
        yield obj
        i = end


def _parse_sandbox(blob: str, run: Run) -> None:
    for obj in _iter_json_objects(blob):
        ts = int(obj.get("timestamp", 0))
        lam = obj.get("lambdaLog") or ""
        if not lam:
            continue
        try:
            state = json.loads(lam)
        except json.JSONDecodeError:
            continue

        general = state.get("GENERAL") or {}
        pos_map: Dict[str, int] = general.get("POS") or {}
        for prod, p in pos_map.items():
            run.positions.append(PositionSnap(ts=ts, product=prod, position=int(p)))

        for prod, pd_ in state.items():
            if prod == "GENERAL" or not isinstance(pd_, dict):
                continue
            # Bid quote
            bid = pd_.get("BUY") or {}
            if isinstance(bid, dict) and "p" in bid and "v" in bid:
                run.orders.append(Order(
                    ts=ts, product=prod, side=+1,
                    price=float(bid["p"]), size=int(bid["v"]),
                    kind="quote", tag=pd_.get("TAG_BUY") or pd_.get("TAG"),
                ))
            # Ask quote
            ask = pd_.get("SELL") or {}
            if isinstance(ask, dict) and "p" in ask and "v" in ask:
                run.orders.append(Order(
                    ts=ts, product=prod, side=-1,
                    price=float(ask["p"]), size=int(ask["v"]),
                    kind="quote", tag=pd_.get("TAG_SELL") or pd_.get("TAG"),
                ))
            # Signal fields.
            for name in ("EMA", "Z", "OBI", "SHIFT"):
                if name in pd_ and isinstance(pd_[name], (int, float)):
                    run.signals.append(SignalEvent(
                        ts=ts, product=prod, name=name, value=float(pd_[name])))


# --- Activities block ------------------------------------------------------

def _parse_activities(blob: str, run: Run) -> None:
    blob = blob.strip()
    if not blob:
        return
    try:
        df = pd.read_csv(StringIO(blob), sep=";")
    except Exception as e:
        log.warning("Failed to parse Activities log: %s", e)
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
            ts=ts, product=str(prod),
            best_bid=float(bb) if pd.notna(bb) else None,
            best_ask=float(ba) if pd.notna(ba) else None,
            mid=float(mid) if pd.notna(mid) else None,
        ))
        pnl_val = r.get("profit_and_loss")
        if pd.notna(pnl_val):
            # Activities-log PnL is total; split breakdown unknown => NaN.
            run.pnl.append(PnlSnap(
                ts=ts, product=str(prod),
                realized=float("nan"), unrealized=float("nan"),
                total=float(pnl_val),
            ))


# --- Trade history block ---------------------------------------------------

_TRAILING_COMMA = re.compile(r",(\s*[}\]])")


def _parse_trades(blob: str, run: Run) -> None:
    blob = blob.strip()
    if not blob:
        return
    sanitized = _TRAILING_COMMA.sub(r"\1", blob)
    try:
        trades = json.loads(sanitized)
    except json.JSONDecodeError as e:
        log.warning("Failed to parse Trade History: %s", e)
        return
    for t in trades:
        buyer = t.get("buyer") or ""
        seller = t.get("seller") or ""
        if buyer != SUBMISSION and seller != SUBMISSION:
            continue  # not our fill
        side = +1 if buyer == SUBMISSION else -1
        counterparty = seller if side > 0 else buyer
        run.fills.append(Fill(
            ts=int(t["timestamp"]),
            product=str(t["symbol"]),
            side=side,
            price=float(t["price"]),
            size=int(t["quantity"]),
            counterparty=counterparty or None,
            tag=None,   # can be enriched later if trader emits tags
        ))
