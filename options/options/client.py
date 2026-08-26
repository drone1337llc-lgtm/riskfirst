"""Alpaca client adapter.

Two backends:

  * MockClient  : in-memory feed + order log (default, used by offline tests).
  * McpClient   : REAL Alpaca MCP server (uvx alpaca-mcp-server) over stdio
                  JSON-RPC, gated behind ALPACA_IS_LIVE=1. Paper mode is
                  hard-forced via ALPACA_PAPER=true.

All order submissions route through submit_order() so the risk arbiter can
always inspect what would have been sent.
"""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

from . import config, options as opt


# --------------------------------------------------------------------------- #
# Base interface
# --------------------------------------------------------------------------- #
class BaseClient:
    """Interface contract implemented by mock and MCP backends."""

    def get_account(self) -> dict:
        raise NotImplementedError

    def get_positions(self) -> list[dict]:
        raise NotImplementedError

    def get_contracts(self, underlying: str) -> list[opt.Option]:
        """Return raw Option contracts for an underlying."""
        raise NotImplementedError

    def submit_order(self, proposal) -> dict:
        raise NotImplementedError

    def flatten(self) -> None:
        """Close all open options positions (risk circuit-breaker)."""
        raise NotImplementedError


# --------------------------------------------------------------------------- #
# Offline mock — deterministic synthetic market for tests / dry runs.
# --------------------------------------------------------------------------- #
def _mk_option(
    underlying: str,
    strike: float,
    expiry: date,
    is_call: bool,
    spot: float,
    iv: float,
    oi: int,
    today: date,
    iv_rank: float = 0.70,
) -> opt.Option:
    today = today or date.today()
    dte = max(1, (expiry - today).days)
    T = dte / 365.0
    g = opt.greeks(spot, strike, T, 0.05, iv, is_call)
    mid = max(opt.black_scholes(spot, strike, T, 0.05, iv, is_call), 0.05)
    spread = max(mid * 0.02, 0.05)
    return opt.Option(
        symbol=(
            f"{underlying}{expiry:%y%m%d}{'C' if is_call else 'P'}"
            f"{int(strike * 1000):08d}"
        ),
        underlying=underlying,
        strike=strike,
        expiry=expiry,
        is_call=is_call,
        bid=round(mid - spread / 2, 2),
        ask=round(mid + spread / 2, 2),
        mid=round(mid, 2),
        open_interest=oi,
        spot=spot,
        dte=dte,
        iv=iv,
        g=g,
        iv_rank=iv_rank,
        score=mid,
    )


SPOT_PRICES = {"SPY": 560.0, "QQQ": 480.0}


class MockClient(BaseClient):
    """Deterministic offline backend. No network, no keys.

    SPY starts with 200 held shares so the covered-call strategy is exercisable
    without needing a prior stock purchase.
    """

    def __init__(self, equity: float = 100_000.0, today: Optional[date] = None):
        self._equity = equity
        self._today = today or date.today()
        self._cash = 0.6 * equity
        self._orders: list[dict] = []
        self._positions: list[dict] = []
        self._shares = {"SPY": 200, "QQQ": 0}   # SPY holdings enable covered calls
        self._chain_cache: dict[str, list[opt.Option]] = {}

    # -- account ----------------------------------------------------------- #
    def get_account(self) -> dict:
        return {
            "equity": self._equity,
            "cash": self._cash,
            "buying_power": self._equity,
            "options_level": 3,
            "daytrade_count": 0,
        }

    def get_positions(self) -> list[dict]:
        return [
            {"symbol": s, "qty": q, "asset_class": "us_equity"}
            for s, q in self._shares.items() if q
        ] + self._positions

    def set_shares(self, symbol: str, qty: int) -> None:
        self._shares[symbol] = qty

    def set_cash(self, cash: float) -> None:
        self._cash = cash

    def set_equity(self, equity: float) -> None:
        self._equity = equity

    # -- data --------------------------------------------------------------- #
    def get_contracts(self, symbol: str) -> list[opt.Option]:
        if symbol not in self._chain_cache:
            self._chain_cache[symbol] = self._build_chain(symbol)
        return self._chain_cache[symbol]

    def _build_chain(self, symbol: str) -> list[opt.Option]:
        spot = SPOT_PRICES.get(symbol, 100.0)
        out: list[opt.Option] = []
        step = round(spot * 0.01, 2)
        # Two expiry cohorts near target DTE.
        for dte in (21, 45):
            expiry = self._today + timedelta(days=dte)
            for i in range(-12, 13):
                strike = round(spot + i * step, 0)
                oi = 400 + abs(i) * 50
                for is_call in (True, False):
                    out.append(
                        _mk_option(symbol, strike, expiry, is_call, spot, 0.28,
                                   oi, self._today)
                    )
        return out

    # -- orders ------------------------------------------------------------- #
    def submit_order(self, proposal) -> dict:
        rec = {
            "time": datetime.now().isoformat(),
            "strategy": proposal.strategy,
            "symbol": proposal.symbol,
            "side": proposal.side,
            "qty": proposal.qty,
            "price": proposal.price,
            "delta": proposal.delta,
            "dte": proposal.dte,
            "iv_rank": proposal.iv_rank,
            "notional": proposal.notional,
        }
        self._orders.append(rec)
        # Track the open option position so net_delta() reflects the book.
        # qty sign: sell_to_open reduces delta (short call delta < 0),
        # buy_to_open adds it. Sign follows the proposal delta as quoted.
        self._positions.append({
            "symbol": proposal.symbol,
            "qty": proposal.qty,
            "asset_class": "us_option",
            "delta": proposal.delta * proposal.qty,
        })
        return {"status": "accepted", "order": rec}

    @property
    def orders(self) -> list[dict]:
        return self._orders

    def flatten(self) -> None:
        self._orders.append({
            "time": datetime.now().isoformat(),
            "action": "FLATTEN",
            "reason": "risk circuit-breaker",
        })
        self._positions = []


# --------------------------------------------------------------------------- #
# Real Alpaca MCP backend (stdio JSON-RPC, LIVE-gated, paper-forced).
# --------------------------------------------------------------------------- #
class MCPError(RuntimeError):
    """Raised when the Alpaca MCP server returns an error or the pipe dies."""


def _pick(obj: dict, *keys):
    """Defensive first-hit lookup across key conventions (camel/snake/space)."""
    if not isinstance(obj, dict):
        return None
    for k in keys:
        if k in obj and obj[k] is not None:
            return obj[k]
    lowered = {str(k).lower().replace("-", "_"): v for k, v in obj.items()}
    for k in keys:
        if k.lower() in lowered and lowered[k.lower()] is not None:
            return lowered[k.lower()]
    return None


def _unwrap(result):
    """Normalize an MCP tools/call result to a plain value.

    The MCP server may wrap payloads in content blocks:
        {"content": [{"type": "text", "text": "<json-or-text>"}]}
    or return the payload directly. This peels the wrapping so downstream
    parsers see one stable shape.
    """
    if isinstance(result, dict):
        content = result.get("content")
        if isinstance(content, list):
            parts = []
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text" and isinstance(block.get("text"), str):
                    parts.append(block["text"])
                elif isinstance(block.get("text"), (dict, list)):
                    parts.append(block["text"])
            if parts:
                if len(parts) == 1:
                    return parts[0]
                return parts
        if "text" in result and isinstance(result["text"], (str, dict, list)):
            return result["text"]
    return result


def _to_date(val) -> Optional[date]:
    if val is None:
        return None
    if isinstance(val, date):
        return val
    s = str(val)[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def parse_option(item: dict, underlying: str) -> Optional[opt.Option]:
    """Map one MCP get_option_chain contract dict to our Option model.

    Defensively tolerates both API response shapes (snake_case and camelCase)
    so a schema drift surfaces as a skipped contract, not a crash.
    """
    symbol = _pick(item, "symbol", "contract_symbol", "contract_id")
    strike = _pick(item, "strike_price", "strike")
    expiry = _to_date(_pick(item, "expiration_date", "expiry", "expiration"))
    ctype = _pick(item, "type", "option_type", "contract_type")
    if not symbol or strike is None or not expiry or not ctype:
        return None
    is_call = str(ctype).lower() in ("call", "c")
    greeks = _pick(item, "greeks", "Greeks") or {}
    bid = _pick(item, "bid", "bid_price") or _pick(_pick(item, "quote", "Quote") or {}, "bid_price", "bid")
    ask = _pick(item, "ask", "ask_price") or _pick(_pick(item, "quote", "Quote") or {}, "ask_price", "ask")
    oi = _pick(item, "open_interest", "oi") or 0
    spot = _pick(item, "underlying_price", "underlying_spot", "spot", "price")
    if spot is None and greeks:
        spot = _pick(greeks, "underlying_price", "spot")
    spot = float(spot) if spot is not None else 0.0
    iv = _pick(greeks, "iv", "implied_volatility", "implied_vol")
    iv = float(iv) if iv is not None else 0.0
    delta = _pick(greeks, "delta")
    gamma = _pick(greeks, "gamma")
    theta = _pick(greeks, "theta")
    vega = _pick(greeks, "vega")
    rho = _pick(greeks, "rho")
    today = date.today()
    dte = max(0, (expiry - today).days)
    g = None
    if delta is not None:
        g = opt.Greeks(
            delta=float(delta),
            gamma=float(gamma) if gamma is not None else 0.0,
            theta=float(theta) if theta is not None else 0.0,
            vega=float(vega) if vega is not None else 0.0,
            rho=float(rho) if rho is not None else 0.0,
            iv=iv,
        )
    # IV rank percentile needs a vol history; default 0.5 (mid) until a
    # historical-vol tracker is wired. Structure matrix still works.
    return opt.Option(
        symbol=str(symbol),
        underlying=underlying,
        strike=float(strike),
        expiry=expiry,
        is_call=is_call,
        bid=float(bid) if bid is not None else 0.0,
        ask=float(ask) if ask is not None else 0.0,
        mid=0.5 * (float(bid or 0.0) + float(ask or 0.0)),
        open_interest=int(oi or 0),
        spot=spot,
        dte=dte,
        iv=iv,
        g=g,
        iv_rank=0.5,
        score=0.0,
    )


def build_chain_args(underlying: str, today: Optional[date] = None,
                     limits: Optional[config.RiskLimits] = None) -> dict:
    """Query args for get_option_chain.

    The MCP get_option_chain tool takes only underlying + limit (+feed); DTE
    and call/put narrowing happen client-side after parsing (the response
    already carries per-contract IV + Greeks).
    """
    today = today or date.today()
    limits = limits or config.RiskLimits()
    return {"underlying_symbol": underlying, "limit": 250}


def build_order_args(proposal) -> dict:
    """Map an OrderProposal onto the MCP place_option_order single-leg shape."""
    side = "buy" if str(proposal.side).startswith("buy") else "sell"
    return {
        "symbol": proposal.symbol,
        "qty": str(int(proposal.qty)),
        "side": side,
        "position_intent": proposal.side,   # buy_to_open / sell_to_open / ...
        "type": "market",
        "time_in_force": "day",
    }


class McpClient(BaseClient):
    """Talks to the REAL Alpaca MCP server over stdio JSON-RPC.

    Requirement-faithful (mandatory MCP/CLI track): every data + order call is
    an MCP tool invocation, not a raw SDK call. Paper mode is hard-forced with
    ALPACA_PAPER=true in the server env, so even live keys cannot reach a real
    account from this class. Gated by config.live_mode() (ALPACA_IS_LIVE=1).
    """

    def __init__(self, api_key: str | None = None, secret_key: str | None = None,
                 server_cmd=("uvx", "alpaca-mcp-server")):
        self._api_key = api_key or config.keys()[0]
        self._secret_key = secret_key or config.keys()[1]
        if not self._api_key or not self._secret_key:
            raise RuntimeError(
                "ALPACA_API_KEY + ALPACA_SECRET_KEY (paper) required for MCP live."
            )
        env = dict(os.environ)
        env["ALPACA_API_KEY"] = self._api_key
        env["ALPACA_SECRET_KEY"] = self._secret_key
        env["ALPACA_PAPER"] = "true"                 # hard rail: paper only
        env.setdefault("ALPACA_OPTIONS_LEVEL", "3")
        self._proc = subprocess.Popen(
            list(server_cmd),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env, text=True, bufsize=1,
        )
        self._req_id = 0
        self._initialize()

    # -- JSON-RPC plumbing ------------------------------------------------ #
    def _initialize(self) -> None:
        info = self._request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "riskfirst", "version": "0.1.0"},
        })
        self._server = (info or {}).get("serverInfo", {})
        self._notify("notifications/initialized")

    def _request(self, method: str, params: dict):
        self._req_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._req_id,
            "method": method,
            "params": params,
        }
        try:
            self._proc.stdin.write(json.dumps(payload) + "\n")
            self._proc.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise MCPError(f"MCP write failed ({method}): {exc}") from exc
        line = self._proc.stdout.readline()
        if not line:
            raise MCPError(f"MCP server closed stdout on {method}")
        try:
            resp = json.loads(line)
        except json.JSONDecodeError as exc:
            raise MCPError(f"MCP non-JSON response to {method}: {line[:200]}") from exc
        if "error" in resp and resp["error"]:
            raise MCPError(f"MCP {method} error: {resp['error']}")
        return resp.get("result")

    def _notify(self, method: str, params: dict | None = None) -> None:
        payload = {"jsonrpc": "2.0", "method": method}
        if params:
            payload["params"] = params
        try:
            self._proc.stdin.write(json.dumps(payload) + "\n")
            self._proc.stdin.flush()
        except (BrokenPipeError, OSError):
            pass  # server already closed; next real call will surface it

    def close(self) -> None:
        try:
            self._notify("notifications/exit")
            self._proc.wait(timeout=5)
        except Exception:
            try:
                self._proc.terminate()
            except Exception:
                pass

    # -- interface --------------------------------------------------------- #
    def get_account(self) -> dict:
        info = self._request("tools/call", {
            "name": "get_account_info",
            "arguments": {},
        })
        text = _unwrap(info)
        # A text block may carry a JSON object instead of formatted prose.
        if isinstance(text, str) and text.lstrip().startswith("{"):
            try:
                text = json.loads(text)
            except json.JSONDecodeError:
                pass
        # The MCP server returns formatted text; normalize the numeric fields
        # we rely on. If parsing fails, surface zeroes so the arbiter halts
        # rather than trading blind.
        acct = {}
        if isinstance(text, str):
            import re
            for key in ("equity", "cash", "buying_power"):
                # Accept "Buying Power" (spaced) as well as snake_case keys.
                pat = key.replace("_", " ")
                m = re.search(rf"(?im)^{pat}[^0-9-]*(-?[0-9.,]+)", text)
                if m:
                    acct[key] = float(m.group(1).replace(",", ""))
        elif isinstance(text, dict):
            acct = {
                "equity": _pick(text, "equity", "Equity") or 0.0,
                "cash": _pick(text, "cash", "Cash") or 0.0,
                "buying_power": _pick(text, "buying_power", "Buying Power") or 0.0,
            }
        return {
            "equity": float(acct.get("equity") or 0.0),
            "cash": float(acct.get("cash") or 0.0),
            "buying_power": float(acct.get("buying_power") or 0.0),
            "options_level": int(config.options_level()),
            "daytrade_count": 0,
        }

    def get_positions(self) -> list[dict]:
        result = self._request("tools/call", {
            "name": "get_all_positions",
            "arguments": {},
        })
        raw = _unwrap(result)
        if isinstance(raw, str) and raw.lstrip().startswith(("[", "{")):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                pass
        if isinstance(raw, dict):
            raw = _pick(raw, "positions", "data", "content") or []
            if isinstance(raw, list):
                pass
        out = []
        if isinstance(raw, list):
            for p in raw:
                if isinstance(p, dict):
                    greeks = _pick(p, "greeks", "Greeks") or {}
                    delta = None
                    if isinstance(greeks, dict):
                        delta = _pick(greeks, "delta", "Delta")
                    out.append({
                        "symbol": _pick(p, "symbol", "Symbol") or "",
                        "qty": float(_pick(p, "qty", "qty") or _pick(p, "quantity", "Quantity") or 0),
                        "asset_class": _pick(p, "asset_class", "asset_class") or "us_equity",
                        "delta": float(delta) if delta is not None else None,
                    })
        return out

    def get_contracts(self, underlying: str) -> list[opt.Option]:
        """Fetch the option chain via get_option_chain, filter client-side."""
        limits = config.RiskLimits()
        today = date.today()
        out: list[opt.Option] = []
        result = self._request("tools/call", {
            "name": "get_option_chain",
            "arguments": build_chain_args(underlying),
        })
        chain = result
        if isinstance(chain, dict):
            chain = _pick(chain, "chain", "contracts", "data", "options") or []
        if isinstance(chain, list):
            for item in chain:
                if not isinstance(item, dict):
                    continue
                o = parse_option(item, underlying)
                if o is None:
                    continue
                if not (limits.min_dte <= o.dte <= limits.max_dte):
                    continue
                out.append(o)
        return out

    def submit_order(self, proposal) -> dict:
        args = build_order_args(proposal)
        result = self._request("tools/call", {
            "name": "place_option_order",
            "arguments": args,
        })
        return {"status": "submitted", "mcp_result": result}

    def flatten(self) -> None:
        try:
            self._request("tools/call", {
                "name": "close_all_positions",
                "arguments": {},
            })
        except MCPError:
            pass  # best-effort circuit breaker; next cycle will re-check


def build_client(live: bool | None = None) -> BaseClient:
    """Return MockClient unless live trading is explicitly requested.

    live defaults to config.live_mode() (paper-forced MCP for the hackathon).
    """
    live = config.live_mode() if live is None else live
    if live:
        return McpClient()
    return MockClient()
