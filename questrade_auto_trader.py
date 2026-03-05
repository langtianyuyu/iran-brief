#!/usr/bin/env python3
"""Lightweight Questrade auto-trader with hard risk limits.

Configured for small-account experiments:
- starting capital reference: 100 USD
- max trades per run/day: 3
- max notional per trade: 20 USD

This script is designed to run once per trading day (e.g., via GitHub Actions cron).
"""

from __future__ import annotations

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
    max_trades_per_day: int = 3
    max_notional_per_trade: float = 20.0
    daily_loss_limit: float = 5.0
    trade_enabled: bool = False
    symbol_universe: List[str] = None


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

    def get_accounts(self) -> dict:
        return self._http_json("GET", f"{self.api_server}v1/accounts", headers=self.auth_headers())

    def get_positions(self, account_id: str) -> dict:
        return self._http_json("GET", f"{self.api_server}v1/accounts/{account_id}/positions", headers=self.auth_headers())

    def get_balances(self, account_id: str) -> dict:
        return self._http_json("GET", f"{self.api_server}v1/accounts/{account_id}/balances", headers=self.auth_headers())

    def lookup_symbols(self, symbols: List[str]) -> dict:
        names = ",".join(symbols)
        return self._http_json("GET", f"{self.api_server}v1/symbols?names={urllib.parse.quote_plus(names)}", headers=self.auth_headers())

    def get_quotes(self, symbol_ids: List[int]) -> dict:
        sid = ",".join(str(i) for i in symbol_ids)
        return self._http_json("GET", f"{self.api_server}v1/markets/quotes/{sid}", headers=self.auth_headers())

    def place_market_order(self, account_id: str, symbol_id: int, qty: int, side: str) -> dict:
        # Questrade accepts this endpoint with market order shape per API docs.
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
    # Stooq format prefers lowercase and .us suffix for US symbols.
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
    # 20-day momentum.
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
        # Tech + broad + bitcoin-related ETF/stock proxies.
        "AAPL,MSFT,NVDA,AMD,META,PLTR,SOFI,SPY,QQQ,BITO,MSTR,COIN",
    ).split(",")

    return Config(
        refresh_token=refresh,
        account_id=account_id,
        is_demo=os.getenv("QUESTRADE_IS_DEMO", "false").lower() == "true",
        max_trades_per_day=int(os.getenv("MAX_TRADES_PER_DAY", "3")),
        max_notional_per_trade=float(os.getenv("MAX_NOTIONAL_PER_TRADE", "20")),
        daily_loss_limit=float(os.getenv("DAILY_LOSS_LIMIT", "5")),
        trade_enabled=os.getenv("TRADE_ENABLED", "false").lower() == "true",
        symbol_universe=[s.strip().upper() for s in universe if s.strip()],
    )


def select_candidates(universe: List[str]) -> List[str]:
    scored = []
    for sym in universe:
        closes = fetch_stooq_close(sym)
        if not closes:
            continue
        score = momentum_score(closes)
        last_price = closes[-1]
        scored.append((sym, score, last_price))

    # Keep positive momentum only, sorted strongest first.
    winners = [row for row in scored if row[1] > 0]
    winners.sort(key=lambda x: x[1], reverse=True)

    # Because max order is 20 USD and no fractional shares, only pick symbols we can buy.
    affordable = [sym for sym, _score, px in winners if px <= 20.0]
    return affordable[:3]


def run() -> int:
    cfg = build_config()
    today = dt.datetime.now().strftime("%Y-%m-%d")

    client = QuestradeClient(cfg.refresh_token, cfg.is_demo)
    client.authenticate()

    balances = client.get_balances(cfg.account_id)
    cash = extract_cash_usd(balances)

    if cash <= 0:
        print("No USD cash available; no trades placed.")
        return 0

    candidates = select_candidates(cfg.symbol_universe)
    if not candidates:
        print("No affordable positive-momentum symbols found; no trades placed.")
        return 0

    symbol_map = client.lookup_symbols(candidates)
    symbols = symbol_map.get("symbols", [])
    by_symbol = {s.get("symbol"): s for s in symbols}

    trades_done = 0
    spent = 0.0
    report_rows = []

    for sym in candidates:
        if trades_done >= cfg.max_trades_per_day:
            break

        entry = by_symbol.get(sym)
        if not entry:
            continue

        symbol_id = int(entry["symbolId"])

        quotes = client.get_quotes([symbol_id]).get("quotes", [])
        if not quotes:
            continue
        ask = float(quotes[0].get("askPrice") or quotes[0].get("lastTradePrice") or 0)
        if ask <= 0:
            continue

        budget = min(cfg.max_notional_per_trade, cash - spent)
        qty = math.floor(budget / ask)
        if qty < 1:
            continue

        notional = qty * ask
        if notional > cfg.max_notional_per_trade + 1e-9:
            continue

        if not cfg.trade_enabled:
            order_resp = {"status": "skipped", "reason": "TRADE_ENABLED is false"}
        else:
            order_resp = client.place_market_order(cfg.account_id, symbol_id, qty, "Buy")
        spent += notional
        trades_done += 1
        report_rows.append(
            {
                "date": today,
                "symbol": sym,
                "qty": qty,
                "est_price": round(ask, 4),
                "est_notional": round(notional, 2),
                "order_response": order_resp,
            }
        )

    out = {
        "date": today,
        "cash_before": round(cash, 2),
        "spent_estimate": round(spent, 2),
        "trades_done": trades_done,
        "max_trades_per_day": cfg.max_trades_per_day,
        "max_notional_per_trade": cfg.max_notional_per_trade,
        "universe": cfg.symbol_universe,
        "filled": report_rows,
    }

    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(run())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
