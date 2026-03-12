"""
Coinbase Exchange (legacy, direct REST) client.

Auth headers:
- CB-ACCESS-KEY
- CB-ACCESS-SIGN = base64(hmac_sha256(base64_decode(secret), timestamp + method + request_path + body))
- CB-ACCESS-TIMESTAMP (seconds)
- CB-ACCESS-PASSPHRASE
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from typing import Any, Dict, Optional

from app.services.live_trading.base import BaseRestClient, LiveOrderResult, LiveTradingError
from app.services.live_trading.symbols import to_coinbase_product_id


class CoinbaseExchangeClient(BaseRestClient):
    def __init__(
        self,
        *,
        api_key: str,
        secret_key: str,
        passphrase: str,
        base_url: str = "https://api.exchange.coinbase.com",
        timeout_sec: float = 15.0,
    ):
        super().__init__(base_url=base_url, timeout_sec=timeout_sec)
        self.api_key = (api_key or "").strip()
        self.secret_key = (secret_key or "").strip()
        self.passphrase = (passphrase or "").strip()
        if not self.api_key or not self.secret_key or not self.passphrase:
            raise LiveTradingError("Missing CoinbaseExchange api_key/secret_key/passphrase")

        try:
            self._secret_bytes = base64.b64decode(self.secret_key)
        except Exception as e:
            raise LiveTradingError(f"Invalid CoinbaseExchange secret_key (base64 decode failed): {e}")

    def _sign(self, message: str) -> str:
        mac = hmac.new(self._secret_bytes, message.encode("utf-8"), hashlib.sha256).digest()
        return base64.b64encode(mac).decode("utf-8")

    def _headers(self, ts: str, sign: str) -> Dict[str, str]:
        return {
            "CB-ACCESS-KEY": self.api_key,
            "CB-ACCESS-SIGN": sign,
            "CB-ACCESS-TIMESTAMP": ts,
            "CB-ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json",
        }

    def _signed_request(self, method: str, path: str, *, params: Optional[Dict[str, Any]] = None, json_body: Optional[Dict[str, Any]] = None) -> Any:
        m = str(method or "GET").upper()
        ts = str(int(time.time()))
        body_str = self._json_dumps(json_body) if json_body is not None else ""
        # Coinbase expects request_path to include query string for signature when GET params exist.
        # We keep signature aligned with actual request params by relying on requests to encode params,
        # but include them in the prehash in a stable order.
        signed_path = path
        if params:
            # stable ordering
            items = []
            for k in sorted(params.keys()):
                v = params.get(k)
                if v is None:
                    continue
                items.append(f"{k}={v}")
            if items:
                signed_path = f"{path}?{'&'.join(items)}"
        prehash = f"{ts}{m}{signed_path}{body_str}"
        sign = self._sign(prehash)
        code, data, text = self._request(m, path, params=params, data=body_str if body_str else None, headers=self._headers(ts, sign))
        if code >= 400:
            raise LiveTradingError(f"CoinbaseExchange HTTP {code}: {text[:500]}")
        return data

    def _public_request(self, method: str, path: str, *, params: Optional[Dict[str, Any]] = None) -> Any:
        code, data, text = self._request(method, path, params=params, headers=None, json_body=None, data=None)
        if code >= 400:
            raise LiveTradingError(f"CoinbaseExchange HTTP {code}: {text[:500]}")
        return data

    def ping(self) -> bool:
        try:
            _ = self._public_request("GET", "/time")
            return True
        except Exception:
            return False

    def get_accounts(self) -> Any:
        return self._signed_request("GET", "/accounts")

    def place_market_order(self, *, symbol: str, side: str, size: float, client_order_id: Optional[str] = None) -> LiveOrderResult:
        sd = (side or "").strip().lower()
        if sd not in ("buy", "sell"):
            raise LiveTradingError(f"Invalid side: {side}")
        qty = float(size or 0.0)
        if qty <= 0:
            raise LiveTradingError("Invalid size")
        body: Dict[str, Any] = {
            "product_id": to_coinbase_product_id(symbol),
            "side": sd,
            "type": "market",
            "size": str(qty),
        }
        if client_order_id:
            body["client_oid"] = str(client_order_id)
        raw = self._signed_request("POST", "/orders", json_body=body)
        oid = str(raw.get("id") or raw.get("order_id") or raw.get("client_oid") or "")
        return LiveOrderResult(exchange_id="coinbaseexchange", exchange_order_id=oid, filled=0.0, avg_price=0.0, raw=raw if isinstance(raw, dict) else {"raw": raw})

    def place_limit_order(self, *, symbol: str, side: str, size: float, price: float, client_order_id: Optional[str] = None) -> LiveOrderResult:
        sd = (side or "").strip().lower()
        if sd not in ("buy", "sell"):
            raise LiveTradingError(f"Invalid side: {side}")
        qty = float(size or 0.0)
        px = float(price or 0.0)
        if qty <= 0 or px <= 0:
            raise LiveTradingError("Invalid size/price")
        body: Dict[str, Any] = {
            "product_id": to_coinbase_product_id(symbol),
            "side": sd,
            "type": "limit",
            "price": str(px),
            "size": str(qty),
            "time_in_force": "GTC",
        }
        if client_order_id:
            body["client_oid"] = str(client_order_id)
        raw = self._signed_request("POST", "/orders", json_body=body)
        oid = str(raw.get("id") or raw.get("order_id") or raw.get("client_oid") or "")
        return LiveOrderResult(exchange_id="coinbaseexchange", exchange_order_id=oid, filled=0.0, avg_price=0.0, raw=raw if isinstance(raw, dict) else {"raw": raw})

    def cancel_order(self, *, order_id: str = "", client_order_id: str = "") -> Any:
        if order_id:
            return self._signed_request("DELETE", f"/orders/{str(order_id)}")
        if client_order_id:
            return self._signed_request("DELETE", f"/orders/client:{str(client_order_id)}")
        raise LiveTradingError("CoinbaseExchange cancel_order requires order_id or client_order_id")

    def get_order(self, *, order_id: str = "", client_order_id: str = "") -> Any:
        if order_id:
            return self._signed_request("GET", f"/orders/{str(order_id)}")
        if client_order_id:
            return self._signed_request("GET", f"/orders/client:{str(client_order_id)}")
        raise LiveTradingError("CoinbaseExchange get_order requires order_id or client_order_id")

    def wait_for_fill(
        self,
        *,
        order_id: str = "",
        client_order_id: str = "",
        max_wait_sec: float = 10.0,
        poll_interval_sec: float = 0.5,
    ) -> Dict[str, Any]:
        end_ts = time.time() + float(max_wait_sec or 0.0)
        last: Dict[str, Any] = {}
        while True:
            try:
                resp = self.get_order(order_id=str(order_id or ""), client_order_id=str(client_order_id or ""))
                last = resp if isinstance(resp, dict) else {"raw": resp}
            except Exception:
                last = last or {}
            status = str(last.get("status") or "")
            filled = 0.0
            avg_price = 0.0
            fee = 0.0
            fee_ccy = ""
            try:
                filled = float(last.get("filled_size") or 0.0)
            except Exception:
                filled = 0.0
            try:
                executed_value = float(last.get("executed_value") or 0.0)
                if filled > 0 and executed_value > 0:
                    avg_price = executed_value / filled
            except Exception:
                avg_price = 0.0
            # Extract fee from fill_fees (Coinbase API field)
            try:
                fee = abs(float(last.get("fill_fees") or 0.0))
            except Exception:
                fee = 0.0
            # Coinbase fees are typically in the quote currency (e.g., USD)
            if fee > 0:
                fee_ccy = "USD"
            if filled > 0 and avg_price > 0:
                return {"filled": filled, "avg_price": avg_price, "fee": fee, "fee_ccy": fee_ccy, "status": status, "order": last}
            if status.lower() in ("done", "rejected", "canceled", "cancelled"):
                return {"filled": filled, "avg_price": avg_price, "fee": fee, "fee_ccy": fee_ccy, "status": status, "order": last}
            if time.time() >= end_ts:
                return {"filled": filled, "avg_price": avg_price, "fee": fee, "fee_ccy": fee_ccy, "status": status, "order": last}
            time.sleep(float(poll_interval_sec or 0.5))


