"""
KuCoin (direct REST) client (spot).

Signing (v2):
- KC-API-SIGN = base64(hmac_sha256(secret, timestamp + method + requestPathWithQuery + body))
- KC-API-PASSPHRASE = base64(hmac_sha256(secret, passphrase))
- KC-API-KEY-VERSION: 2
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from decimal import Decimal, ROUND_DOWN
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlencode

from app.services.live_trading.base import BaseRestClient, LiveOrderResult, LiveTradingError
from app.services.live_trading.symbols import to_kucoin_symbol


class KucoinSpotClient(BaseRestClient):
    def __init__(
        self,
        *,
        api_key: str,
        secret_key: str,
        passphrase: str,
        base_url: str = "https://api.kucoin.com",
        timeout_sec: float = 15.0,
    ):
        super().__init__(base_url=base_url, timeout_sec=timeout_sec)
        self.api_key = (api_key or "").strip()
        self.secret_key = (secret_key or "").strip()
        self.passphrase = (passphrase or "").strip()
        if not self.api_key or not self.secret_key or not self.passphrase:
            raise LiveTradingError("Missing KuCoin api_key/secret_key/passphrase")

    def _b64_hmac_sha256(self, key: str, msg: str) -> str:
        mac = hmac.new(key.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).digest()
        return base64.b64encode(mac).decode("utf-8")

    def _headers(self, ts_ms: str, sign: str) -> Dict[str, str]:
        # passphrase must be signed (v2)
        p = self._b64_hmac_sha256(self.secret_key, self.passphrase)
        return {
            "KC-API-KEY": self.api_key,
            "KC-API-SIGN": sign,
            "KC-API-TIMESTAMP": ts_ms,
            "KC-API-PASSPHRASE": p,
            "KC-API-KEY-VERSION": "2",
            "Content-Type": "application/json",
        }

    def _signed_request(self, method: str, path: str, *, params: Optional[Dict[str, Any]] = None, json_body: Optional[Dict[str, Any]] = None) -> Any:
        m = str(method or "GET").upper()
        ts_ms = str(int(time.time() * 1000))
        body_str = self._json_dumps(json_body) if json_body is not None else ""
        qs = ""
        if params:
            norm = {str(k): "" if v is None else str(v) for k, v in dict(params).items()}
            qs = urlencode(sorted(norm.items()), doseq=True)
        signed_path = f"{path}?{qs}" if qs else path
        prehash = f"{ts_ms}{m}{signed_path}{body_str}"
        sign = self._b64_hmac_sha256(self.secret_key, prehash)
        code, data, text = self._request(m, path, params=params, data=body_str if body_str else None, headers=self._headers(ts_ms, sign))
        if code >= 400:
            raise LiveTradingError(f"KuCoin HTTP {code}: {text[:500]}")
        return data

    def _public_request(self, method: str, path: str, *, params: Optional[Dict[str, Any]] = None) -> Any:
        code, data, text = self._request(method, path, params=params, headers=None, json_body=None, data=None)
        if code >= 400:
            raise LiveTradingError(f"KuCoin HTTP {code}: {text[:500]}")
        return data

    def ping(self) -> bool:
        try:
            d = self._public_request("GET", "/api/v1/timestamp")
            return isinstance(d, dict) and str(d.get("code") or "") in ("200000", "0", "")
        except Exception:
            return False

    def get_accounts(self) -> Any:
        return self._signed_request("GET", "/api/v1/accounts")

    def place_limit_order(self, *, symbol: str, side: str, size: float, price: float, client_order_id: Optional[str] = None) -> LiveOrderResult:
        sd = (side or "").strip().lower()
        if sd not in ("buy", "sell"):
            raise LiveTradingError(f"Invalid side: {side}")
        qty = float(size or 0.0)
        px = float(price or 0.0)
        if qty <= 0 or px <= 0:
            raise LiveTradingError("Invalid size/price")
        body: Dict[str, Any] = {
            "clientOid": str(client_order_id or str(int(time.time() * 1000))),
            "side": sd,
            "symbol": to_kucoin_symbol(symbol),
            "type": "limit",
            "price": str(px),
            "size": str(qty),
            "timeInForce": "GTC",
        }
        raw = self._signed_request("POST", "/api/v1/orders", json_body=body)
        oid = ""
        if isinstance(raw, dict):
            d = raw.get("data")
            if isinstance(d, dict):
                oid = str(d.get("orderId") or "")
            elif isinstance(d, str):
                oid = str(d)
        return LiveOrderResult(exchange_id="kucoin", exchange_order_id=oid, filled=0.0, avg_price=0.0, raw=raw if isinstance(raw, dict) else {"raw": raw})

    def place_market_order(
        self,
        *,
        symbol: str,
        side: str,
        size: float,
        client_order_id: Optional[str] = None,
        quote_size: bool = False,
    ) -> LiveOrderResult:
        """
        KuCoin market order:
        - sell: use size (base quantity)
        - buy: typically use funds (quote quantity). Set quote_size=True to treat `size` as funds.
        """
        sd = (side or "").strip().lower()
        if sd not in ("buy", "sell"):
            raise LiveTradingError(f"Invalid side: {side}")
        qty = float(size or 0.0)
        if qty <= 0:
            raise LiveTradingError("Invalid size")
        body: Dict[str, Any] = {
            "clientOid": str(client_order_id or str(int(time.time() * 1000))),
            "side": sd,
            "symbol": to_kucoin_symbol(symbol),
            "type": "market",
        }
        if sd == "buy" and quote_size:
            body["funds"] = str(qty)
        else:
            body["size"] = str(qty)
        raw = self._signed_request("POST", "/api/v1/orders", json_body=body)
        oid = ""
        if isinstance(raw, dict):
            d = raw.get("data")
            if isinstance(d, dict):
                oid = str(d.get("orderId") or "")
            elif isinstance(d, str):
                oid = str(d)
        return LiveOrderResult(exchange_id="kucoin", exchange_order_id=oid, filled=0.0, avg_price=0.0, raw=raw if isinstance(raw, dict) else {"raw": raw})

    def cancel_order(self, *, order_id: str = "", client_order_id: str = "") -> Any:
        if order_id:
            return self._signed_request("DELETE", f"/api/v1/orders/{str(order_id)}")
        if client_order_id:
            return self._signed_request("DELETE", f"/api/v1/order/client-order/{str(client_order_id)}")
        raise LiveTradingError("KuCoin cancel_order requires order_id or client_order_id")

    def get_order(self, *, order_id: str = "", client_order_id: str = "") -> Any:
        if order_id:
            return self._signed_request("GET", f"/api/v1/orders/{str(order_id)}")
        if client_order_id:
            return self._signed_request("GET", f"/api/v1/order/client-order/{str(client_order_id)}")
        raise LiveTradingError("KuCoin get_order requires order_id or client_order_id")

    def get_fills(self, *, order_id: str) -> Any:
        return self._signed_request("GET", "/api/v1/fills", params={"orderId": str(order_id)})

    def wait_for_fill(self, *, order_id: str, max_wait_sec: float = 10.0, poll_interval_sec: float = 0.5) -> Dict[str, Any]:
        end_ts = time.time() + float(max_wait_sec or 0.0)
        last: Dict[str, Any] = {}
        while True:
            try:
                resp = self.get_order(order_id=str(order_id))
                last = resp if isinstance(resp, dict) else {"raw": resp}
            except Exception:
                last = last or {}
            data = last.get("data") if isinstance(last, dict) else None
            od = data if isinstance(data, dict) else {}
            status = str(od.get("isActive") if od else "")
            filled = 0.0
            avg_price = 0.0
            fee = 0.0
            fee_ccy = ""
            try:
                filled = float(od.get("dealSize") or 0.0)
            except Exception:
                filled = 0.0
            try:
                funds = float(od.get("dealFunds") or 0.0)
                if filled > 0 and funds > 0:
                    avg_price = funds / filled
            except Exception:
                avg_price = 0.0
            try:
                fee = abs(float(od.get("fee") or 0.0))
            except Exception:
                fee = 0.0
            fee_ccy = str(od.get("feeCurrency") or "").strip()
            if filled > 0 and avg_price > 0:
                return {"filled": filled, "avg_price": avg_price, "fee": fee, "fee_ccy": fee_ccy, "status": status, "order": last}
            # If order is inactive, consider it terminal
            try:
                is_active = bool(od.get("isActive"))
            except Exception:
                is_active = False
            if not is_active:
                return {"filled": filled, "avg_price": avg_price, "fee": fee, "fee_ccy": fee_ccy, "status": status, "order": last}
            if time.time() >= end_ts:
                return {"filled": filled, "avg_price": avg_price, "fee": fee, "fee_ccy": fee_ccy, "status": status, "order": last}
            time.sleep(float(poll_interval_sec or 0.5))


class KucoinFuturesClient(BaseRestClient):
    """
    KuCoin Futures (USDT perpetual) direct REST client.

    Notes:
    - Base URL typically: https://api-futures.kucoin.com
    - Auth headers/signing are the same KC-API-* style as spot (v2 passphrase signing),
      but endpoints and symbol formats differ.
    - Futures order size is typically in contracts; we convert from "base qty" best-effort.
    """

    def __init__(
        self,
        *,
        api_key: str,
        secret_key: str,
        passphrase: str,
        base_url: str = "https://api-futures.kucoin.com",
        timeout_sec: float = 15.0,
    ):
        super().__init__(base_url=base_url, timeout_sec=timeout_sec)
        self.api_key = (api_key or "").strip()
        self.secret_key = (secret_key or "").strip()
        self.passphrase = (passphrase or "").strip()
        if not self.api_key or not self.secret_key or not self.passphrase:
            raise LiveTradingError("Missing KuCoin Futures api_key/secret_key/passphrase")

        # Best-effort contract cache: symbol -> (ts, contract_dict)
        self._contract_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
        self._contract_cache_ttl_sec = 300.0

    def _b64_hmac_sha256(self, key: str, msg: str) -> str:
        mac = hmac.new(key.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).digest()
        return base64.b64encode(mac).decode("utf-8")

    def _headers(self, ts_ms: str, sign: str) -> Dict[str, str]:
        p = self._b64_hmac_sha256(self.secret_key, self.passphrase)
        return {
            "KC-API-KEY": self.api_key,
            "KC-API-SIGN": sign,
            "KC-API-TIMESTAMP": ts_ms,
            "KC-API-PASSPHRASE": p,
            "KC-API-KEY-VERSION": "2",
            "Content-Type": "application/json",
        }

    def _signed_request(self, method: str, path: str, *, params: Optional[Dict[str, Any]] = None, json_body: Optional[Dict[str, Any]] = None) -> Any:
        m = str(method or "GET").upper()
        ts_ms = str(int(time.time() * 1000))
        body_str = self._json_dumps(json_body) if json_body is not None else ""
        qs = ""
        if params:
            norm = {str(k): "" if v is None else str(v) for k, v in dict(params).items()}
            qs = urlencode(sorted(norm.items()), doseq=True)
        signed_path = f"{path}?{qs}" if qs else path
        prehash = f"{ts_ms}{m}{signed_path}{body_str}"
        sign = self._b64_hmac_sha256(self.secret_key, prehash)
        code, data, text = self._request(m, path, params=params, data=body_str if body_str else None, headers=self._headers(ts_ms, sign))
        if code >= 400:
            raise LiveTradingError(f"KuCoinFutures HTTP {code}: {text[:500]}")
        return data

    def _public_request(self, method: str, path: str, *, params: Optional[Dict[str, Any]] = None) -> Any:
        code, data, text = self._request(method, path, params=params, headers=None, json_body=None, data=None)
        if code >= 400:
            raise LiveTradingError(f"KuCoinFutures HTTP {code}: {text[:500]}")
        return data

    def ping(self) -> bool:
        try:
            d = self._public_request("GET", "/api/v1/timestamp")
            return isinstance(d, dict) and str(d.get("code") or "") in ("200000", "0", "")
        except Exception:
            return False

    def get_contract(self, *, symbol: str) -> Dict[str, Any]:
        from app.services.live_trading.symbols import to_kucoin_futures_symbol

        sym = to_kucoin_futures_symbol(symbol)
        if not sym:
            return {}
        now = time.time()
        cached = self._contract_cache.get(sym)
        if cached:
            ts, obj = cached
            if obj and (now - float(ts or 0.0)) <= float(self._contract_cache_ttl_sec or 300.0):
                return obj
        # KuCoin futures active contracts list
        raw = self._public_request("GET", "/api/v1/contracts/active")
        data = (raw.get("data") if isinstance(raw, dict) else None) or []
        found: Dict[str, Any] = {}
        if isinstance(data, list):
            for it in data:
                if not isinstance(it, dict):
                    continue
                if str(it.get("symbol") or "").upper() == sym.upper():
                    found = it
                    break
        if found:
            self._contract_cache[sym] = (now, found)
        return found

    def _base_to_contracts(self, *, symbol: str, base_size: float) -> int:
        """
        Convert base-asset qty -> contracts best-effort using multiplier.
        """
        from app.services.live_trading.symbols import to_kucoin_futures_symbol

        req = Decimal(str(base_size or 0.0))
        if req <= 0:
            return 0
        sym = to_kucoin_futures_symbol(symbol)
        meta: Dict[str, Any] = {}
        try:
            meta = self.get_contract(symbol=sym) or {}
        except Exception:
            meta = {}
        # multiplier is base per contract for many KuCoin perps (best-effort)
        mult = Decimal(str(meta.get("multiplier") or meta.get("lotSize") or "0"))
        if mult <= 0:
            mult = Decimal("1")
        ct = (req / mult).to_integral_value(rounding=ROUND_DOWN)
        try:
            return int(ct)
        except Exception:
            return 0

    def get_accounts(self) -> Any:
        # Futures account overview
        return self._signed_request("GET", "/api/v1/account-overview", params={"currency": "USDT"})

    def get_positions(self) -> Any:
        return self._signed_request("GET", "/api/v1/positions")

    def set_leverage(self, *, symbol: str, leverage: float) -> bool:
        from app.services.live_trading.symbols import to_kucoin_futures_symbol

        sym = to_kucoin_futures_symbol(symbol)
        try:
            lv = int(float(leverage or 1.0))
        except Exception:
            lv = 1
        if lv < 1:
            lv = 1
        body = {"symbol": sym, "leverage": str(lv)}
        try:
            _ = self._signed_request("POST", "/api/v1/position/leverage", json_body=body)
            return True
        except Exception:
            return False

    def place_market_order(
        self,
        *,
        symbol: str,
        side: str,
        size: float,
        reduce_only: bool = False,
        client_order_id: Optional[str] = None,
    ) -> LiveOrderResult:
        from app.services.live_trading.symbols import to_kucoin_futures_symbol

        sd = (side or "").strip().lower()
        if sd not in ("buy", "sell"):
            raise LiveTradingError(f"Invalid side: {side}")
        sym = to_kucoin_futures_symbol(symbol)
        qty_ct = self._base_to_contracts(symbol=sym, base_size=float(size or 0.0))
        if qty_ct <= 0:
            raise LiveTradingError("Invalid size (converted contracts <= 0)")
        body: Dict[str, Any] = {
            "clientOid": str(client_order_id or str(int(time.time() * 1000))),
            "side": sd,
            "symbol": sym,
            "type": "market",
            "size": qty_ct,
        }
        if reduce_only:
            body["reduceOnly"] = True
        raw = self._signed_request("POST", "/api/v1/orders", json_body=body)
        oid = ""
        if isinstance(raw, dict):
            d = raw.get("data")
            if isinstance(d, dict):
                oid = str(d.get("orderId") or "")
            elif isinstance(d, str):
                oid = str(d)
        return LiveOrderResult(exchange_id="kucoin", exchange_order_id=oid, filled=0.0, avg_price=0.0, raw=raw if isinstance(raw, dict) else {"raw": raw})

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
        from app.services.live_trading.symbols import to_kucoin_futures_symbol

        sd = (side or "").strip().lower()
        if sd not in ("buy", "sell"):
            raise LiveTradingError(f"Invalid side: {side}")
        sym = to_kucoin_futures_symbol(symbol)
        px = float(price or 0.0)
        if px <= 0:
            raise LiveTradingError("Invalid price")
        qty_ct = self._base_to_contracts(symbol=sym, base_size=float(size or 0.0))
        if qty_ct <= 0:
            raise LiveTradingError("Invalid size (converted contracts <= 0)")
        body: Dict[str, Any] = {
            "clientOid": str(client_order_id or str(int(time.time() * 1000))),
            "side": sd,
            "symbol": sym,
            "type": "limit",
            "price": str(px),
            "size": qty_ct,
        }
        if reduce_only:
            body["reduceOnly"] = True
        if post_only:
            body["postOnly"] = True
        raw = self._signed_request("POST", "/api/v1/orders", json_body=body)
        oid = ""
        if isinstance(raw, dict):
            d = raw.get("data")
            if isinstance(d, dict):
                oid = str(d.get("orderId") or "")
            elif isinstance(d, str):
                oid = str(d)
        return LiveOrderResult(exchange_id="kucoin", exchange_order_id=oid, filled=0.0, avg_price=0.0, raw=raw if isinstance(raw, dict) else {"raw": raw})

    def cancel_order(self, *, order_id: str = "", client_order_id: str = "") -> Any:
        if order_id:
            return self._signed_request("DELETE", f"/api/v1/orders/{str(order_id)}")
        if client_order_id:
            return self._signed_request("DELETE", f"/api/v1/orders/client-order/{str(client_order_id)}")
        raise LiveTradingError("KuCoinFutures cancel_order requires order_id or client_order_id")

    def get_order(self, *, order_id: str = "", client_order_id: str = "") -> Any:
        if order_id:
            return self._signed_request("GET", f"/api/v1/orders/{str(order_id)}")
        if client_order_id:
            return self._signed_request("GET", f"/api/v1/orders/byClientOid", params={"clientOid": str(client_order_id)})
        raise LiveTradingError("KuCoinFutures get_order requires order_id or client_order_id")

    def wait_for_fill(self, *, order_id: str, max_wait_sec: float = 3.0, poll_interval_sec: float = 0.5) -> Dict[str, Any]:
        end_ts = time.time() + float(max_wait_sec or 0.0)
        last: Dict[str, Any] = {}
        while True:
            try:
                resp = self.get_order(order_id=str(order_id))
                last = resp if isinstance(resp, dict) else {"raw": resp}
            except Exception:
                last = last or {}
            od = (last.get("data") if isinstance(last, dict) else None) or {}
            status = str(od.get("status") or "")
            filled = 0.0
            avg_price = 0.0
            fee = 0.0
            fee_ccy = ""
            try:
                # dealSize is in contracts; convert back to base using multiplier best-effort.
                deal_ct = float(od.get("dealSize") or 0.0)
            except Exception:
                deal_ct = 0.0
            try:
                deal_value = float(od.get("dealValue") or 0.0)
            except Exception:
                deal_value = 0.0
            # Best-effort: infer avg price from dealValue / (deal contracts * multiplier)
            mult = 1.0
            try:
                sym = str(od.get("symbol") or "")
                meta = self.get_contract(symbol=sym) or {}
                mult = float(meta.get("multiplier") or meta.get("lotSize") or 1.0)
                if mult <= 0:
                    mult = 1.0
            except Exception:
                mult = 1.0
            filled = abs(float(deal_ct or 0.0)) * float(mult)
            if filled > 0 and deal_value > 0:
                avg_price = float(deal_value) / float(filled)
            # Extract fee from KuCoin Futures API (orderMargin contains fee info in some cases)
            try:
                fee = abs(float(od.get("fee") or od.get("orderFee") or 0.0))
            except Exception:
                fee = 0.0
            # KuCoin Futures fees are typically in USDT
            if fee > 0:
                fee_ccy = "USDT"
            if filled > 0 and avg_price > 0:
                return {"filled": filled, "avg_price": avg_price, "fee": fee, "fee_ccy": fee_ccy, "status": status, "order": last}
            if status.lower() in ("done", "canceled", "cancelled", "filled"):
                return {"filled": filled, "avg_price": avg_price, "fee": fee, "fee_ccy": fee_ccy, "status": status, "order": last}
            if time.time() >= end_ts:
                return {"filled": filled, "avg_price": avg_price, "fee": fee, "fee_ccy": fee_ccy, "status": status, "order": last}
            time.sleep(float(poll_interval_sec or 0.5))


