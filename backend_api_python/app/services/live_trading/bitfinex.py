"""
Bitfinex (direct REST) client (v2, exchange spot).

Auth headers:
- bfx-apikey
- bfx-nonce
- bfx-signature = hex(hmac_sha384(secret, "/api/v2" + path + nonce + body))

Notes:
- This client targets "exchange" (spot) order types: EXCHANGE MARKET / EXCHANGE LIMIT.
- Derivatives/perps are not fully implemented here; only best-effort spot execution.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any, Dict, Optional

from app.services.live_trading.base import BaseRestClient, LiveOrderResult, LiveTradingError
from app.services.live_trading.symbols import to_bitfinex_spot_symbol
from app.services.live_trading.symbols import to_bitfinex_perp_symbol


class BitfinexClient(BaseRestClient):
    def __init__(self, *, api_key: str, secret_key: str, base_url: str = "https://api.bitfinex.com", timeout_sec: float = 15.0):
        super().__init__(base_url=base_url, timeout_sec=timeout_sec)
        self.api_key = (api_key or "").strip()
        self.secret_key = (secret_key or "").strip()
        if not self.api_key or not self.secret_key:
            raise LiveTradingError("Missing Bitfinex api_key/secret_key")

    def _nonce(self) -> str:
        # Use ms; Bitfinex accepts monotonic increasing nonces.
        return str(int(time.time() * 1000))

    def _sign(self, path: str, nonce: str, body_str: str) -> str:
        payload = f"/api/v2{path}{nonce}{body_str}"
        return hmac.new(self.secret_key.encode("utf-8"), payload.encode("utf-8"), hashlib.sha384).hexdigest()

    def _headers(self, nonce: str, sign: str) -> Dict[str, str]:
        return {"bfx-apikey": self.api_key, "bfx-nonce": nonce, "bfx-signature": sign, "content-type": "application/json"}

    def _signed_request(self, method: str, path: str, *, json_body: Optional[Dict[str, Any]] = None) -> Any:
        m = str(method or "POST").upper()
        nonce = self._nonce()
        body_str = self._json_dumps(json_body) if json_body is not None else ""
        sign = self._sign(path, nonce, body_str)
        code, data, text = self._request(m, path, params=None, data=body_str if body_str else None, headers=self._headers(nonce, sign))
        if code >= 400:
            raise LiveTradingError(f"Bitfinex HTTP {code}: {text[:500]}")
        return data

    def _public_request(self, method: str, path: str, *, params: Optional[Dict[str, Any]] = None) -> Any:
        code, data, text = self._request(method, path, params=params, headers=None, json_body=None, data=None)
        if code >= 400:
            raise LiveTradingError(f"Bitfinex HTTP {code}: {text[:500]}")
        return data

    def ping(self) -> bool:
        try:
            d = self._public_request("GET", "/v2/platform/status")
            return isinstance(d, list) and d and int(d[0]) == 1
        except Exception:
            return False

    def get_wallets(self) -> Any:
        """
        Private endpoint to validate credentials (best-effort).
        """
        return self._signed_request("POST", "/v2/auth/r/wallets", json_body={})


class BitfinexDerivativesClient(BitfinexClient):
    """
    Bitfinex derivatives/perpetual client (best-effort).

    Differences vs spot:
    - Symbol uses tBASEF0:QUOTEF0 (e.g. tBTCF0:USTF0)
    - Order type typically uses MARKET/LIMIT (not EXCHANGE MARKET/LIMIT)
    """

    def place_market_order(self, *, symbol: str, side: str, size: float, client_order_id: Optional[str] = None) -> LiveOrderResult:
        sd = (side or "").strip().lower()
        if sd not in ("buy", "sell"):
            raise LiveTradingError(f"Invalid side: {side}")
        qty = float(size or 0.0)
        if qty <= 0:
            raise LiveTradingError("Invalid size")
        sym = to_bitfinex_perp_symbol(symbol)
        amt = qty if sd == "buy" else -qty
        body: Dict[str, Any] = {"type": "MARKET", "symbol": sym, "amount": str(amt)}
        if client_order_id:
            try:
                cid = int("".join([c for c in str(client_order_id) if c.isdigit()])[:18] or "0")
                if cid > 0:
                    body["cid"] = cid
            except Exception:
                pass
        raw = self._signed_request("POST", "/v2/auth/w/order/submit", json_body=body)
        oid = ""
        try:
            if isinstance(raw, list) and len(raw) >= 4 and isinstance(raw[3], list) and raw[3]:
                order = raw[3][0]
                if isinstance(order, list) and order:
                    oid = str(order[0])
        except Exception:
            oid = ""
        return LiveOrderResult(exchange_id="bitfinex", exchange_order_id=oid, filled=0.0, avg_price=0.0, raw={"raw": raw})

    def place_limit_order(self, *, symbol: str, side: str, size: float, price: float, client_order_id: Optional[str] = None) -> LiveOrderResult:
        sd = (side or "").strip().lower()
        if sd not in ("buy", "sell"):
            raise LiveTradingError(f"Invalid side: {side}")
        qty = float(size or 0.0)
        px = float(price or 0.0)
        if qty <= 0 or px <= 0:
            raise LiveTradingError("Invalid size/price")
        sym = to_bitfinex_perp_symbol(symbol)
        amt = qty if sd == "buy" else -qty
        body: Dict[str, Any] = {"type": "LIMIT", "symbol": sym, "amount": str(amt), "price": str(px)}
        if client_order_id:
            try:
                cid = int("".join([c for c in str(client_order_id) if c.isdigit()])[:18] or "0")
                if cid > 0:
                    body["cid"] = cid
            except Exception:
                pass
        raw = self._signed_request("POST", "/v2/auth/w/order/submit", json_body=body)
        oid = ""
        try:
            if isinstance(raw, list) and len(raw) >= 4 and isinstance(raw[3], list) and raw[3]:
                order = raw[3][0]
                if isinstance(order, list) and order:
                    oid = str(order[0])
        except Exception:
            oid = ""
        return LiveOrderResult(exchange_id="bitfinex", exchange_order_id=oid, filled=0.0, avg_price=0.0, raw={"raw": raw})

    def get_positions(self) -> Any:
        return self._signed_request("POST", "/v2/auth/r/positions", json_body={})

    def place_market_order(self, *, symbol: str, side: str, size: float, client_order_id: Optional[str] = None) -> LiveOrderResult:
        sd = (side or "").strip().lower()
        if sd not in ("buy", "sell"):
            raise LiveTradingError(f"Invalid side: {side}")
        qty = float(size or 0.0)
        if qty <= 0:
            raise LiveTradingError("Invalid size")
        sym = to_bitfinex_spot_symbol(symbol)
        amt = qty if sd == "buy" else -qty
        body: Dict[str, Any] = {"type": "EXCHANGE MARKET", "symbol": sym, "amount": str(amt)}
        if client_order_id:
            # Bitfinex uses numeric cid; best-effort digits only
            try:
                cid = int("".join([c for c in str(client_order_id) if c.isdigit()])[:18] or "0")
                if cid > 0:
                    body["cid"] = cid
            except Exception:
                pass
        raw = self._signed_request("POST", "/v2/auth/w/order/submit", json_body=body)
        oid = ""
        try:
            # Response is usually [.., [order_fields]]
            if isinstance(raw, list) and len(raw) >= 4 and isinstance(raw[3], list) and raw[3]:
                order = raw[3][0]
                if isinstance(order, list) and order:
                    oid = str(order[0])
        except Exception:
            oid = ""
        return LiveOrderResult(exchange_id="bitfinex", exchange_order_id=oid, filled=0.0, avg_price=0.0, raw={"raw": raw})

    def place_limit_order(self, *, symbol: str, side: str, size: float, price: float, client_order_id: Optional[str] = None) -> LiveOrderResult:
        sd = (side or "").strip().lower()
        if sd not in ("buy", "sell"):
            raise LiveTradingError(f"Invalid side: {side}")
        qty = float(size or 0.0)
        px = float(price or 0.0)
        if qty <= 0 or px <= 0:
            raise LiveTradingError("Invalid size/price")
        sym = to_bitfinex_spot_symbol(symbol)
        amt = qty if sd == "buy" else -qty
        body: Dict[str, Any] = {"type": "EXCHANGE LIMIT", "symbol": sym, "amount": str(amt), "price": str(px)}
        if client_order_id:
            try:
                cid = int("".join([c for c in str(client_order_id) if c.isdigit()])[:18] or "0")
                if cid > 0:
                    body["cid"] = cid
            except Exception:
                pass
        raw = self._signed_request("POST", "/v2/auth/w/order/submit", json_body=body)
        oid = ""
        try:
            if isinstance(raw, list) and len(raw) >= 4 and isinstance(raw[3], list) and raw[3]:
                order = raw[3][0]
                if isinstance(order, list) and order:
                    oid = str(order[0])
        except Exception:
            oid = ""
        return LiveOrderResult(exchange_id="bitfinex", exchange_order_id=oid, filled=0.0, avg_price=0.0, raw={"raw": raw})

    def cancel_order(self, *, order_id: str = "", client_order_id: str = "") -> Any:
        if order_id:
            try:
                oid = int(float(order_id))
            except Exception:
                oid = 0
            if oid <= 0:
                raise LiveTradingError("Bitfinex cancel_order invalid order_id")
            return self._signed_request("POST", "/v2/auth/w/order/cancel", json_body={"id": oid})
        # Best-effort cancel by cid is possible via /auth/w/order/cancel/multi, but not implemented.
        if client_order_id:
            raise LiveTradingError("Bitfinex cancel by client_order_id is not implemented (requires cid date)")
        raise LiveTradingError("Bitfinex cancel_order requires order_id")

    def get_order(self, *, order_id: str) -> Any:
        try:
            oid = int(float(order_id))
        except Exception:
            oid = 0
        if oid <= 0:
            raise LiveTradingError("Bitfinex get_order invalid order_id")
        # Bitfinex v2 order status endpoint
        return self._signed_request("POST", f"/v2/auth/r/order/{oid}")

    def wait_for_fill(self, *, order_id: str, max_wait_sec: float = 10.0, poll_interval_sec: float = 0.5) -> Dict[str, Any]:
        end_ts = time.time() + float(max_wait_sec or 0.0)
        last: Any = None
        while True:
            try:
                last = self.get_order(order_id=str(order_id))
            except Exception:
                last = last or []
            filled = 0.0
            avg_price = 0.0
            fee = 0.0
            fee_ccy = ""
            status = ""
            # best-effort parsing from array fields
            # Bitfinex order response format: [ID, GID, CID, SYMBOL, MTS_CREATE, MTS_UPDATE, AMOUNT, AMOUNT_ORIG, TYPE, TYPE_PREV, MTS_TIF, _, FLAGS, STATUS, _, PRICE_AVG, ...]
            try:
                if isinstance(last, list) and len(last) >= 15:
                    status = str(last[13] or "")
                    amount_remaining = float(last[6] or 0.0)
                    amount_orig = float(last[7] or 0.0)
                    filled = abs(amount_orig - amount_remaining)
                    avg_price = float(last[14] or 0.0)
            except Exception:
                pass
            # Note: Bitfinex order response doesn't include fee; fee is typically in trades.
            # We return 0.0 here; actual fee can be fetched via trades endpoint if needed.
            if filled > 0 and avg_price > 0:
                return {"filled": filled, "avg_price": avg_price, "fee": fee, "fee_ccy": fee_ccy, "status": status, "order": last}
            if isinstance(status, str) and ("EXECUTED" in status.upper() or "CANCELED" in status.upper()):
                return {"filled": filled, "avg_price": avg_price, "fee": fee, "fee_ccy": fee_ccy, "status": status, "order": last}
            if time.time() >= end_ts:
                return {"filled": filled, "avg_price": avg_price, "fee": fee, "fee_ccy": fee_ccy, "status": status, "order": last}
            time.sleep(float(poll_interval_sec or 0.5))


