"""
Kraken (direct REST) client (spot).

Auth:
- API-Key: api key string
- API-Sign: base64(hmac_sha512(base64_decode(secret), uri_path + sha256(nonce + postdata)))

Notes:
- Kraken spot uses asset pairs like XBTUSDT; we do best-effort normalization.
- This client is spot-only in this project (no futures).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from typing import Any, Dict, Optional
from urllib.parse import urlencode

from app.services.live_trading.base import BaseRestClient, LiveOrderResult, LiveTradingError
from app.services.live_trading.symbols import to_kraken_pair


class KrakenClient(BaseRestClient):
    def __init__(self, *, api_key: str, secret_key: str, base_url: str = "https://api.kraken.com", timeout_sec: float = 15.0):
        super().__init__(base_url=base_url, timeout_sec=timeout_sec)
        self.api_key = (api_key or "").strip()
        self.secret_key = (secret_key or "").strip()
        if not self.api_key or not self.secret_key:
            raise LiveTradingError("Missing Kraken api_key/secret_key")
        try:
            self._secret_bytes = base64.b64decode(self.secret_key)
        except Exception as e:
            raise LiveTradingError(f"Invalid Kraken secret_key (base64 decode failed): {e}")

    def ping(self) -> bool:
        try:
            code, data, _ = self._request("GET", "/0/public/Time")
            return code == 200 and isinstance(data, dict) and (data.get("error") in ([], None, ""))
        except Exception:
            return False

    def get_balance(self) -> Dict[str, Any]:
        """
        Private balance endpoint (best-effort credential validation).
        """
        return self._signed_request("POST", "/0/private/Balance", data={})

    def _sign(self, *, urlpath: str, nonce: str, postdata: str) -> str:
        sha = hashlib.sha256((nonce + postdata).encode("utf-8")).digest()
        mac = hmac.new(self._secret_bytes, urlpath.encode("utf-8") + sha, hashlib.sha512).digest()
        return base64.b64encode(mac).decode("utf-8")

    def _signed_request(self, method: str, path: str, *, data: Dict[str, Any]) -> Dict[str, Any]:
        m = str(method or "POST").upper()
        if m != "POST":
            raise LiveTradingError("Kraken private endpoints in this client use POST")
        nonce = str(int(time.time() * 1000))
        body = dict(data or {})
        body["nonce"] = nonce
        postdata = urlencode(body, doseq=True)
        sign = self._sign(urlpath=path, nonce=nonce, postdata=postdata)
        headers = {"API-Key": self.api_key, "API-Sign": sign, "Content-Type": "application/x-www-form-urlencoded"}
        code, resp, text = self._request("POST", path, params=None, json_body=None, data=postdata, headers=headers)
        if code >= 400:
            raise LiveTradingError(f"Kraken HTTP {code}: {text[:500]}")
        if isinstance(resp, dict):
            errs = resp.get("error")
            if isinstance(errs, list) and errs:
                raise LiveTradingError(f"Kraken error: {errs}")
        return resp if isinstance(resp, dict) else {"raw": resp}

    def add_order(
        self,
        *,
        pair: str,
        side: str,
        ordertype: str,
        volume: float,
        price: float = 0.0,
        client_order_id: str = "",
    ) -> Dict[str, Any]:
        sd = (side or "").strip().lower()
        if sd not in ("buy", "sell"):
            raise LiveTradingError(f"Invalid side: {side}")
        ot = (ordertype or "").strip().lower()
        if ot not in ("market", "limit"):
            raise LiveTradingError(f"Invalid ordertype: {ordertype}")
        vol = float(volume or 0.0)
        if vol <= 0:
            raise LiveTradingError("Invalid volume")
        body: Dict[str, Any] = {"pair": str(pair), "type": sd, "ordertype": ot, "volume": str(vol)}
        if ot == "limit":
            px = float(price or 0.0)
            if px <= 0:
                raise LiveTradingError("Invalid limit price")
            body["price"] = str(px)
        # Best-effort userref (integer). Only digits allowed. Keep short.
        if client_order_id:
            try:
                body["userref"] = int("".join([c for c in str(client_order_id) if c.isdigit()])[:9] or "0")
            except Exception:
                pass
        return self._signed_request("POST", "/0/private/AddOrder", data=body)

    def place_market_order(self, *, symbol: str, side: str, size: float, client_order_id: Optional[str] = None) -> LiveOrderResult:
        pair = to_kraken_pair(symbol)
        raw = self.add_order(pair=pair, side=side, ordertype="market", volume=float(size or 0.0), client_order_id=str(client_order_id or ""))
        txid = ""
        try:
            tx = ((raw.get("result") or {}).get("txid")) if isinstance(raw, dict) else None
            if isinstance(tx, list) and tx:
                txid = str(tx[0])
        except Exception:
            txid = ""
        return LiveOrderResult(exchange_id="kraken", exchange_order_id=txid, filled=0.0, avg_price=0.0, raw=raw)

    def place_limit_order(self, *, symbol: str, side: str, size: float, price: float, client_order_id: Optional[str] = None) -> LiveOrderResult:
        pair = to_kraken_pair(symbol)
        raw = self.add_order(pair=pair, side=side, ordertype="limit", volume=float(size or 0.0), price=float(price or 0.0), client_order_id=str(client_order_id or ""))
        txid = ""
        try:
            tx = ((raw.get("result") or {}).get("txid")) if isinstance(raw, dict) else None
            if isinstance(tx, list) and tx:
                txid = str(tx[0])
        except Exception:
            txid = ""
        return LiveOrderResult(exchange_id="kraken", exchange_order_id=txid, filled=0.0, avg_price=0.0, raw=raw)

    def cancel_order(self, *, order_id: str) -> Dict[str, Any]:
        if not order_id:
            raise LiveTradingError("Kraken cancel_order requires order_id")
        return self._signed_request("POST", "/0/private/CancelOrder", data={"txid": str(order_id)})

    def get_order(self, *, order_id: str) -> Dict[str, Any]:
        if not order_id:
            raise LiveTradingError("Kraken get_order requires order_id")
        resp = self._signed_request("POST", "/0/private/QueryOrders", data={"txid": str(order_id)})
        res = (resp.get("result") or {}) if isinstance(resp, dict) else {}
        od = (res.get(str(order_id)) if isinstance(res, dict) else None) or {}
        return od if isinstance(od, dict) else {}

    def wait_for_fill(self, *, order_id: str, max_wait_sec: float = 10.0, poll_interval_sec: float = 0.5) -> Dict[str, Any]:
        end_ts = time.time() + float(max_wait_sec or 0.0)
        last: Dict[str, Any] = {}
        while True:
            try:
                last = self.get_order(order_id=str(order_id))
            except Exception:
                last = last or {}
            status = str(last.get("status") or "")
            filled = 0.0
            avg_price = 0.0
            fee = 0.0
            fee_ccy = ""
            try:
                filled = float(last.get("vol_exec") or 0.0)
            except Exception:
                filled = 0.0
            # Kraken provides "cost" in quote currency. avg = cost / filled.
            try:
                cost = float(last.get("cost") or 0.0)
                if filled > 0 and cost > 0:
                    avg_price = cost / filled
            except Exception:
                avg_price = 0.0
            # Extract fee from Kraken API
            try:
                fee = abs(float(last.get("fee") or 0.0))
            except Exception:
                fee = 0.0
            # Kraken fees are typically in the quote currency (e.g., USD)
            if fee > 0:
                fee_ccy = "USD"
            if filled > 0 and avg_price > 0:
                return {"filled": filled, "avg_price": avg_price, "fee": fee, "fee_ccy": fee_ccy, "status": status, "order": last}
            if status.lower() in ("closed", "canceled", "cancelled", "expired"):
                return {"filled": filled, "avg_price": avg_price, "fee": fee, "fee_ccy": fee_ccy, "status": status, "order": last}
            if time.time() >= end_ts:
                return {"filled": filled, "avg_price": avg_price, "fee": fee, "fee_ccy": fee_ccy, "status": status, "order": last}
            time.sleep(float(poll_interval_sec or 0.5))


