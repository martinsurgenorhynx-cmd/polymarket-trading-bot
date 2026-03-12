"""
Kraken Futures (direct REST) client.

Kraken Futures (formerly CryptoFacilities) uses a different API than Kraken spot.
Base URL example: https://futures.kraken.com
API prefix: /derivatives/api/v3

Auth (best-effort):
- APIKey: <api key>
- Nonce: <milliseconds>
- Authent: base64(hmac_sha256(secret, nonce + postdata + endpoint_path))

IMPORTANT:
- Instruments are exchange-specific (e.g. PF_XBTUSD, PI_XBTUSD). This project will pass through
  those symbols if you choose them in UI, or best-effort map BTC/USDT -> PF_XBTUSD.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from typing import Any, Dict, Optional
from urllib.parse import urlencode

from app.services.live_trading.base import BaseRestClient, LiveOrderResult, LiveTradingError
from app.services.live_trading.symbols import to_kraken_futures_symbol


class KrakenFuturesClient(BaseRestClient):
    def __init__(self, *, api_key: str, secret_key: str, base_url: str = "https://futures.kraken.com", timeout_sec: float = 15.0):
        super().__init__(base_url=base_url, timeout_sec=timeout_sec)
        self.api_key = (api_key or "").strip()
        self.secret_key = (secret_key or "").strip()
        if not self.api_key or not self.secret_key:
            raise LiveTradingError("Missing KrakenFutures api_key/secret_key")

    def _b64_hmac_sha256(self, msg: str) -> str:
        mac = hmac.new(self.secret_key.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).digest()
        return base64.b64encode(mac).decode("utf-8")

    def _headers(self, nonce: str, authent: str) -> Dict[str, str]:
        return {"APIKey": self.api_key, "Nonce": nonce, "Authent": authent, "Content-Type": "application/x-www-form-urlencoded"}

    def _signed_request(self, method: str, path: str, *, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        m = str(method or "POST").upper()
        # Kraken Futures private endpoints often use POST.
        nonce = str(int(time.time() * 1000))
        body = dict(data or {})
        postdata = urlencode(body, doseq=True) if body else ""
        # Sign with endpoint path (not including domain)
        prehash = f"{nonce}{postdata}{path}"
        authent = self._b64_hmac_sha256(prehash)
        code, resp, text = self._request(m, path, params=None, json_body=None, data=postdata if postdata else None, headers=self._headers(nonce, authent))
        if code >= 400:
            raise LiveTradingError(f"KrakenFutures HTTP {code}: {text[:500]}")
        if isinstance(resp, dict):
            # Futures API often uses "result":"success"/"error" or "errors"
            if str(resp.get("result") or "").lower() == "error" or resp.get("errors"):
                raise LiveTradingError(f"KrakenFutures error: {resp}")
        return resp if isinstance(resp, dict) else {"raw": resp}

    def _public_request(self, method: str, path: str, *, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        code, resp, text = self._request(method, path, params=params, headers=None, json_body=None, data=None)
        if code >= 400:
            raise LiveTradingError(f"KrakenFutures HTTP {code}: {text[:500]}")
        return resp if isinstance(resp, dict) else {"raw": resp}

    def ping(self) -> bool:
        try:
            _ = self._public_request("GET", "/derivatives/api/v3/tickers")
            return True
        except Exception:
            return False

    def get_accounts(self) -> Dict[str, Any]:
        # Best-effort private endpoint (varies by account type)
        return self._signed_request("GET", "/derivatives/api/v3/accounts")

    def get_open_positions(self) -> Dict[str, Any]:
        return self._signed_request("GET", "/derivatives/api/v3/openpositions")

    def place_market_order(
        self,
        *,
        symbol: str,
        side: str,
        size: float,
        reduce_only: bool = False,
        client_order_id: Optional[str] = None,
    ) -> LiveOrderResult:
        sd = (side or "").strip().lower()
        if sd not in ("buy", "sell"):
            raise LiveTradingError(f"Invalid side: {side}")
        qty = float(size or 0.0)
        if qty <= 0:
            raise LiveTradingError("Invalid size")
        instr = to_kraken_futures_symbol(symbol)
        body: Dict[str, Any] = {
            "orderType": "mkt",
            "symbol": str(instr),
            "side": sd,
            # Kraken Futures uses "size" in contracts; we treat incoming size as "contracts" for now.
            "size": str(qty),
        }
        if reduce_only:
            body["reduceOnly"] = "true"
        if client_order_id:
            body["cliOrdId"] = str(client_order_id)[:32]
        raw = self._signed_request("POST", "/derivatives/api/v3/sendorder", data=body)
        oid = str((raw.get("sendStatus") or {}).get("order_id") or (raw.get("order_id") or "")) if isinstance(raw, dict) else ""
        return LiveOrderResult(exchange_id="kraken", exchange_order_id=oid, filled=0.0, avg_price=0.0, raw=raw)

    def place_limit_order(
        self,
        *,
        symbol: str,
        side: str,
        size: float,
        price: float,
        reduce_only: bool = False,
        post_only: bool = False,
        client_order_id: Optional[str] = None,
    ) -> LiveOrderResult:
        sd = (side or "").strip().lower()
        if sd not in ("buy", "sell"):
            raise LiveTradingError(f"Invalid side: {side}")
        qty = float(size or 0.0)
        px = float(price or 0.0)
        if qty <= 0 or px <= 0:
            raise LiveTradingError("Invalid size/price")
        instr = to_kraken_futures_symbol(symbol)
        body: Dict[str, Any] = {
            "orderType": "lmt",
            "symbol": str(instr),
            "side": sd,
            "size": str(qty),
            "limitPrice": str(px),
        }
        if reduce_only:
            body["reduceOnly"] = "true"
        if post_only:
            body["postOnly"] = "true"
        if client_order_id:
            body["cliOrdId"] = str(client_order_id)[:32]
        raw = self._signed_request("POST", "/derivatives/api/v3/sendorder", data=body)
        oid = str((raw.get("sendStatus") or {}).get("order_id") or (raw.get("order_id") or "")) if isinstance(raw, dict) else ""
        return LiveOrderResult(exchange_id="kraken", exchange_order_id=oid, filled=0.0, avg_price=0.0, raw=raw)

    def cancel_order(self, *, order_id: str = "", client_order_id: str = "") -> Dict[str, Any]:
        body: Dict[str, Any] = {}
        if order_id:
            body["order_id"] = str(order_id)
        elif client_order_id:
            body["cliOrdId"] = str(client_order_id)
        else:
            raise LiveTradingError("KrakenFutures cancel_order requires order_id or client_order_id")
        return self._signed_request("POST", "/derivatives/api/v3/cancelorder", data=body)

    def get_order(self, *, order_id: str = "", client_order_id: str = "") -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        if order_id:
            params["order_id"] = str(order_id)
        elif client_order_id:
            params["cliOrdId"] = str(client_order_id)
        else:
            raise LiveTradingError("KrakenFutures get_order requires order_id or client_order_id")
        return self._signed_request("GET", "/derivatives/api/v3/order", data=params)

    def wait_for_fill(
        self,
        *,
        order_id: str = "",
        client_order_id: str = "",
        max_wait_sec: float = 3.0,
        poll_interval_sec: float = 0.5,
    ) -> Dict[str, Any]:
        end_ts = time.time() + float(max_wait_sec or 0.0)
        last: Dict[str, Any] = {}
        while True:
            try:
                last = self.get_order(order_id=str(order_id or ""), client_order_id=str(client_order_id or ""))
            except Exception:
                last = last or {}
            status = str(last.get("status") or last.get("orderStatus") or "")
            filled = 0.0
            avg_price = 0.0
            fee = 0.0
            fee_ccy = ""
            try:
                filled = float(last.get("filledSize") or last.get("filled_size") or 0.0)
            except Exception:
                filled = 0.0
            try:
                avg_price = float(last.get("avgFillPrice") or last.get("avg_fill_price") or 0.0)
            except Exception:
                avg_price = 0.0
            # Extract fee from Kraken Futures API (if available)
            try:
                fee = abs(float(last.get("fee") or 0.0))
            except Exception:
                fee = 0.0
            # Kraken Futures fees are typically in USD
            if fee > 0:
                fee_ccy = "USD"
            if filled > 0 and avg_price > 0:
                return {"filled": filled, "avg_price": avg_price, "fee": fee, "fee_ccy": fee_ccy, "status": status, "order": last}
            if status.lower() in ("filled", "cancelled", "canceled", "rejected"):
                return {"filled": filled, "avg_price": avg_price, "fee": fee, "fee_ccy": fee_ccy, "status": status, "order": last}
            if time.time() >= end_ts:
                return {"filled": filled, "avg_price": avg_price, "fee": fee, "fee_ccy": fee_ccy, "status": status, "order": last}
            time.sleep(float(poll_interval_sec or 0.5))


