#!/usr/bin/env python3
"""Questrade auto-trader with approval gate.

Modes:
- plan: generate trade plan with reasons, no orders.
- execute: place orders only when both TRADE_ENABLED=true and confirmation is YES.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class Config:
    refresh_token: str
    account_id: str
    is_demo: bool
    trade_enabled: bool
    max_trades_per_day: int
    max_notional_per_trade: float
    daily_loss_limit: float
    symbol_universe: List[str]


class QuestradeClient:
    def __init__(self, refresh_token: str, is_demo: bool) -> None:
        self.refresh_token = refresh_token
        self.is_demo = is_demo
        self.access_token = ""
        self.api_server = ""

    def _http_json(self, method: str, url: str, headers: Optional[Dict[str, str]] = None, payload: Optional[dict] = None) -> dict:
        req_headers = {"User-Agent": "codex-autotrader/1.0"}
        if headers:
            req_headers.update(headers)
        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            req_headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))

    def authenticate(self) -> None:
        base = "https://practicelogin.questrade.com/oauth2/token" if self.is_demo else "https://login.questrade.com/oauth2/token"
        url = f"{base}?grant_type=refresh_token&refresh_token={urllib.parse.quote_plus(self.refresh_token)}"
        data = self._http_json("GET", url)
        self.access_token = data["access_token"]
        self.api_server = data["api_server"]

    def auth_headers(self) -> Dict[str, str]:
        if not self.access_token:
            raise RuntimeError("Not authenticated")
        return {"Authorization": f"Bearer {self.access_token}"}

    def get_balances(self, account_id: str) -> dict:
        return self._http_json("GET", f"{self.api_server}v1/accounts/{account_id}/balances", headers=self.auth_headers())

    def lookup_symbols(self, symbols: List[str]) -> dict:
        names = ",".join(symbols)
        return self._http_json("GET", f"{self.api_server}v1/symbols?names={urllib.parse.quote_plus(names)}", headers=self.auth_headers())

    def get_quotes(self, symbol_ids: List[int]) -> dict:
        sid = ",".join(str(i) for i in symbol_ids)
        return self._http_json("GET", f"{self.api_server}v1/markets/quotes/{sid}", headers=self.auth_headers())

    def place_market_order(self, account_id: str, symbol_id: int, qty: int, side: str) -> dict:
        payload = {
            "orderType": "Market",
            "action": side,
            "symbolId": symbol_id,
            "quantity": qty,
            "isAllOrNone": False,
            "isAnonymous": False,
            "timeInForce": "Day",
            "primaryRoute": "AUTO",
            "secondaryRoute": "AUTO",
        }
        return self._http_json(
            "POST",
            f"{self.api_server}v1/accounts/{account_id}/orders",
            headers=self.auth_headers(),
            payload=payload,
        )


def fetch_stooq_close(symbol: str) -> Optional[List[float]]:
    stooq_symbol = symbol.lower() + ".us"
    url = f"https://stooq.com/q/d/l/?s={urllib.parse.quote_plus(stooq_symbol)}&i=d"
    try:
        csv_data = subprocess.check_output(["curl", "-fsSL", url], text=True)
    except Exception:
        return None
    lines = [ln.strip() for ln in csv_data.splitlines() if ln.strip()]
    if len(lines) < 22:
        return None

    closes = []
    for ln in lines[1:]:
        cols = ln.split(",")
        if len(cols) < 5:
            continue
        try:
            closes.append(float(cols[4]))
        except Exception:
            continue
    return closes[-21:] if len(closes) >= 21 else None


def momentum_score(closes: List[float]) -> float:
    return (closes[-1] / closes[0]) - 1.0


def extract_cash_usd(balance_payload: dict) -> float:
    combined = balance_payload.get("combinedBalances", [])
    for row in combined:
        if row.get("currency") == "USD":
            return float(row.get("cash", 0.0))
    return 0.0


def build_config() -> Config:
    refresh = os.getenv("QUESTRADE_REFRESH_TOKEN", "").strip()
    account_id = os.getenv("QUESTRADE_ACCOUNT_ID", "").strip()
    if not refresh or not account_id:
        raise RuntimeError("QUESTRADE_REFRESH_TOKEN and QUESTRADE_ACCOUNT_ID are required")

    universe = os.getenv(
        "TRADE_UNIVERSE",
        "AAPL,MSFT,NVDA,AMD,META,PLTR,SOFI,SPY,QQQ,BITO,MSTR,COIN",
    ).split(",")

    return Config(
        refresh_token=refresh,
        account_id=account_id,
        is_demo=os.getenv("QUESTRADE_IS_DEMO", "false").lower() == "true",
        trade_enabled=os.getenv("TRADE_ENABLED", "false").lower() == "true",
        max_trades_per_day=int(os.getenv("MAX_TRADES_PER_DAY", "3")),
        max_notional_per_trade=float(os.getenv("MAX_NOTIONAL_PER_TRADE", "20")),
        daily_loss_limit=float(os.getenv("DAILY_LOSS_LIMIT", "5")),
        symbol_universe=[s.strip().upper() for s in universe if s.strip()],
    )


def select_candidates(cfg: Config) -> List[dict]:
    scored = []
    for sym in cfg.symbol_universe:
        closes = fetch_stooq_close(sym)
        if not closes:
            continue
        score = momentum_score(closes)
        last_close = closes[-1]
        scored.append({"symbol": sym, "score": score, "last_close": last_close})

    winners = [x for x in scored if x["score"] > 0]
    winners.sort(key=lambda x: x["score"], reverse=True)
    return winners


def build_plan(cfg: Config, client: QuestradeClient) -> dict:
    balances = client.get_balances(cfg.account_id)
    cash = extract_cash_usd(balances)
    winners = select_candidates(cfg)

    if not winners:
        return {
            "date": dt.datetime.now().strftime("%Y-%m-%d"),
            "mode": "plan",
            "cash_usd": round(cash, 2),
            "orders": [],
            "sell_plan": "No sells today (long-only entry model).",
            "summary": "No positive 20-day momentum symbols found.",
        }

    symbols = [w["symbol"] for w in winners[: min(len(winners), 12)]]
    symbol_lookup = client.lookup_symbols(symbols).get("symbols", [])
    by_symbol = {x.get("symbol"): x for x in symbol_lookup}

    order_candidates = []
    for w in winners:
        sym = w["symbol"]
        row = by_symbol.get(sym)
        if not row:
            continue
        sid = int(row["symbolId"])
        quotes = client.get_quotes([sid]).get("quotes", [])
        if not quotes:
            continue
        ask = float(quotes[0].get("askPrice") or quotes[0].get("lastTradePrice") or 0)
        if ask <= 0:
            continue

        qty = math.floor(cfg.max_notional_per_trade / ask)
        if qty < 1:
            continue

        notional = qty * ask
        reason = (
            f"20-day momentum is positive ({w['score']*100:.2f}%), "
            f"price is affordable for risk cap (${cfg.max_notional_per_trade:.2f}/trade)."
        )
        order_candidates.append(
            {
                "symbol": sym,
                "symbol_id": sid,
                "side": "Buy",
                "qty": qty,
                "ask": round(ask, 4),
                "est_notional": round(notional, 2),
                "reason": reason,
                "momentum_20d_pct": round(w["score"] * 100, 2),
            }
        )

        if len(order_candidates) >= cfg.max_trades_per_day:
            break

    if cash > 0:
        running = 0.0
        filtered = []
        for o in order_candidates:
            if running + o["est_notional"] <= cash + 1e-9:
                filtered.append(o)
                running += o["est_notional"]
        order_candidates = filtered

    summary = (
        f"Prepared {len(order_candidates)} buy order(s), max {cfg.max_trades_per_day}/day, "
        f"max ${cfg.max_notional_per_trade:.2f} each."
    )

    return {
        "date": dt.datetime.now().strftime("%Y-%m-%d"),
        "mode": "plan",
        "cash_usd": round(cash, 2),
        "orders": order_candidates,
        "sell_plan": "No sells today (long-only entry model).",
        "summary": summary,
    }


def execute_plan(cfg: Config, client: QuestradeClient, plan: dict, confirm_text: str) -> dict:
    if confirm_text.strip().upper() != "YES":
        return {"status": "blocked", "reason": "Confirmation text must be YES", "executed": []}

    if not cfg.trade_enabled:
        return {"status": "blocked", "reason": "TRADE_ENABLED is false", "executed": []}

    executed = []
    for o in plan.get("orders", [])[: cfg.max_trades_per_day]:
        resp = client.place_market_order(cfg.account_id, int(o["symbol_id"]), int(o["qty"]), "Buy")
        executed.append({"symbol": o["symbol"], "qty": o["qty"], "response": resp})

    return {"status": "ok", "executed": executed}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["plan", "execute"], default="plan")
    parser.add_argument("--confirm", default=os.getenv("CONFIRM_TRADE", ""))
    args = parser.parse_args()

    cfg = build_config()
    client = QuestradeClient(cfg.refresh_token, cfg.is_demo)
    client.authenticate()

    plan = build_plan(cfg, client)

    if args.mode == "plan":
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0

    result = execute_plan(cfg, client, plan, args.confirm)
    out = {"plan": plan, "execution": result}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
