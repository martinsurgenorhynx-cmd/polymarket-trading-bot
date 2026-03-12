"""
Bybit (direct REST) client for spot / linear perpetual orders (v5).

Signing (v5):
- X-BAPI-SIGN = hex(hmac_sha256(secret, timestamp + api_key + recv_window + payload))
- payload:
  - GET: query string (sorted, urlencoded)
  - POST: raw body string
"""

from __future__ import annotations

import hashlib
import hmac
import time
from decimal import Decimal, ROUND_DOWN
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlencode

from app.services.live_trading.base import BaseRestClient, LiveOrderResult, LiveTradingError
from app.services.live_trading.symbols import to_bybit_symbol


class BybitClient(BaseRestClient):
    def __init__(
        self,
        *,
        api_key: str,
        secret_key: str,
        base_url: str = "https://api.bybit.com",
        timeout_sec: float = 15.0,
        category: str = "linear",  # "linear" (USDT perpetual) or "spot"
        recv_window_ms: int = 5000,
    ):
        super().__init__(base_url=base_url, timeout_sec=timeout_sec)
        self.api_key = (api_key or "").strip()
        self.secret_key = (secret_key or "").strip()
        self.category = (category or "linear").strip().lower()
        if self.category not in ("linear", "spot"):
            self.category = "linear"
        try:
            self.recv_window_ms = int(recv_window_ms or 5000)
        except Exception:
            self.recv_window_ms = 5000
        if self.recv_window_ms <= 0:
            self.recv_window_ms = 5000

        if not self.api_key or not self.secret_key:
            raise LiveTradingError("Missing Bybit api_key/secret_key")

        # Best-effort cache for linear instrument metadata (qty step, min qty, etc.)
        # Key: f"{category}:{symbol}" -> (fetched_at_ts, info_dict)
        self._inst_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
        self._inst_cache_ttl_sec = 300.0

    @staticmethod
    def _to_dec(x: Any) -> Decimal:
        try:
            return Decimal(str(x))
        except Exception:
            return Decimal("0")

    @staticmethod
    def _dec_str(d: Decimal, max_decimals: int = 18, strict_precision: Optional[int] = None) -> str:
        """
        Convert Decimal to string with controlled precision.
        Bybit requires quantities to match qtyStep precision.
        
        Args:
            d: Decimal value to format
            max_decimals: Maximum decimal places (fallback if strict_precision not provided)
            strict_precision: If provided, strictly limit to this many decimal places
        """
        try:
            if d == 0:
                return "0"
            normalized = d.normalize()
            
            if strict_precision is not None:
                try:
                    prec = int(strict_precision)
                    if 0 <= prec <= 18:
                        q = Decimal("1").scaleb(-prec)
                        quantized = normalized.quantize(q, rounding=ROUND_DOWN)
                        s = format(quantized, f".{prec}f")
                        if '.' in s:
                            s = s.rstrip('0').rstrip('.')
                        return s if s else "0"
                except Exception:
                    pass
            
            s = format(normalized, f".{max_decimals}f")
            if '.' in s:
                s = s.rstrip('0').rstrip('.')
            return s if s else "0"
        except Exception:
            try:
                f = float(d)
                if f == 0:
                    return "0"
                if strict_precision is not None:
                    try:
                        prec = int(strict_precision)
                        if 0 <= prec <= 18:
                            s = format(f, f".{prec}f")
                            if '.' in s:
                                s = s.rstrip('0').rstrip('.')
                            return s if s else "0"
                    except Exception:
                        pass
                s = format(f, f".{max_decimals}f")
                if '.' in s:
                    s = s.rstrip('0').rstrip('.')
                return s if s else "0"
            except Exception:
                s = str(d)
                if 'e' in s.lower() or 'E' in s:
                    try:
                        f = float(s)
                        if strict_precision is not None:
                            try:
                                prec = int(strict_precision)
                                if 0 <= prec <= 18:
                                    s = format(f, f".{prec}f")
                                    if '.' in s:
                                        s = s.rstrip('0').rstrip('.')
                                    return s if s else "0"
                            except Exception:
                                pass
                        s = format(f, f".{max_decimals}f")
                        if '.' in s:
                            s = s.rstrip('0').rstrip('.')
                    except Exception:
                        pass
                return s if s else "0"

    @staticmethod
    def _floor_to_step(value: Decimal, step: Decimal) -> Decimal:
        if step is None:
            return value
        if value <= 0:
            return Decimal("0")
        try:
            st = Decimal(step)
        except Exception:
            st = Decimal("0")
        if st <= 0:
            return value
        try:
            n = (value / st).to_integral_value(rounding=ROUND_DOWN)
            return n * st
        except Exception:
            return Decimal("0")

    def _sign(self, prehash: str) -> str:
        return hmac.new(self.secret_key.encode("utf-8"), prehash.encode("utf-8"), hashlib.sha256).hexdigest()

    def _headers(self, ts_ms: str, sign: str) -> Dict[str, str]:
        return {
            "X-BAPI-API-KEY": self.api_key,
            "X-BAPI-SIGN": sign,
            "X-BAPI-TIMESTAMP": ts_ms,
            "X-BAPI-RECV-WINDOW": str(self.recv_window_ms),
            "X-BAPI-SIGN-TYPE": "2",
            "Content-Type": "application/json",
        }

    def _signed_request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        m = str(method or "GET").upper()
        ts_ms = str(int(time.time() * 1000))

        body_str = self._json_dumps(json_body) if json_body is not None else ""
        qs = ""
        if params:
            norm = {str(k): "" if v is None else str(v) for k, v in dict(params).items()}
            qs = urlencode(sorted(norm.items()), doseq=True)

        payload = qs if m == "GET" else body_str
        prehash = f"{ts_ms}{self.api_key}{self.recv_window_ms}{payload}"
        sign = self._sign(prehash)

        code, data, text = self._request(
            m,
            path,
            params=params if (m == "GET" and params) else (params or None),
            data=body_str if body_str else None,
            headers=self._headers(ts_ms, sign),
        )
        if code >= 400:
            raise LiveTradingError(f"Bybit HTTP {code}: {text[:500]}")
        if isinstance(data, dict):
            rc = data.get("retCode")
            if rc not in (0, "0", None, ""):
                raise LiveTradingError(f"Bybit error: {data}")
        return data if isinstance(data, dict) else {"raw": data}

    def _public_request(self, method: str, path: str, *, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        code, data, text = self._request(method, path, params=params, headers=None, json_body=None, data=None)
        if code >= 400:
            raise LiveTradingError(f"Bybit HTTP {code}: {text[:500]}")
        if isinstance(data, dict):
            rc = data.get("retCode")
            if rc not in (0, "0", None, ""):
                raise LiveTradingError(f"Bybit error: {data}")
        return data if isinstance(data, dict) else {"raw": data}

    def ping(self) -> bool:
        try:
            data = self._public_request("GET", "/v5/market/time")
            return isinstance(data, dict) and (data.get("retCode") in (0, "0", None, ""))
        except Exception:
            return False

    def get_wallet_balance(self, *, account_type: str = "UNIFIED") -> Dict[str, Any]:
        return self._signed_request("GET", "/v5/account/wallet-balance", params={"accountType": str(account_type or "UNIFIED")})

    def get_instrument_info(self, *, category: str, symbol: str) -> Dict[str, Any]:
        cat = str(category or self.category or "linear").strip().lower()
        sym = to_bybit_symbol(symbol)
        if not sym:
            return {}
        key = f"{cat}:{sym}"
        now = time.time()
        cached = self._inst_cache.get(key)
        if cached:
            ts, obj = cached
            if obj and (now - float(ts or 0.0)) <= float(self._inst_cache_ttl_sec or 300.0):
                return obj
        raw = self._public_request("GET", "/v5/market/instruments-info", params={"category": cat, "symbol": sym})
        lst = (((raw.get("result") or {}).get("list")) if isinstance(raw, dict) else None) or []
        first: Dict[str, Any] = lst[0] if isinstance(lst, list) and lst else {}
        if isinstance(first, dict) and first:
            self._inst_cache[key] = (now, first)
        return first if isinstance(first, dict) else {}

    def _normalize_qty(self, *, symbol: str, qty: float) -> Tuple[Decimal, Optional[int]]:
        q = self._to_dec(qty)
        if q <= 0:
            return (Decimal("0"), None)
        sym = to_bybit_symbol(symbol)
        try:
            info = self.get_instrument_info(category=self.category, symbol=sym) or {}
        except Exception:
            info = {}
        lot = (info.get("lotSizeFilter") if isinstance(info, dict) else None) or {}
        step = self._to_dec((lot or {}).get("qtyStep") or "0")
        mn = self._to_dec((lot or {}).get("minOrderQty") or "0")
        if step > 0:
            q = self._floor_to_step(q, step)
        
        # Infer precision from qtyStep
        qty_precision = None
        if step > 0:
            try:
                step_normalized = step.normalize()
                step_str = str(step_normalized)
                if '.' in step_str:
                    decimal_part = step_str.split('.')[1]
                    qty_precision = len(decimal_part)
                    if qty_precision < 0:
                        qty_precision = 0
                    if qty_precision > 18:
                        qty_precision = 18
                else:
                    qty_precision = 0
            except Exception:
                pass
        
        if mn > 0 and q < mn:
            return (Decimal("0"), qty_precision)
        return (q, qty_precision)

    def place_market_order(
        self,
        *,
        symbol: str,
        side: str,
        qty: float,
        reduce_only: bool = False,
        client_order_id: Optional[str] = None,
    ) -> LiveOrderResult:
        sym = to_bybit_symbol(symbol)
        sd = (side or "").strip().lower()
        if sd not in ("buy", "sell"):
            raise LiveTradingError(f"Invalid side: {side}")
        q_req = float(qty or 0.0)
        q_dec, qty_precision = self._normalize_qty(symbol=symbol, qty=q_req)
        if float(q_dec or 0) <= 0:
            raise LiveTradingError(f"Invalid qty (below step/min): requested={q_req}")
        body: Dict[str, Any] = {
            "category": self.category,
            "symbol": sym,
            "side": "Buy" if sd == "buy" else "Sell",
            "orderType": "Market",
            "qty": self._dec_str(q_dec, strict_precision=qty_precision),
            "timeInForce": "GTC",
        }
        if reduce_only and self.category == "linear":
            body["reduceOnly"] = True
        if client_order_id:
            body["orderLinkId"] = str(client_order_id)
        raw = self._signed_request("POST", "/v5/order/create", json_body=body)
        res = (raw.get("result") or {}) if isinstance(raw, dict) else {}
        oid = str(res.get("orderId") or res.get("orderLinkId") or "")
        return LiveOrderResult(exchange_id="bybit", exchange_order_id=oid, filled=0.0, avg_price=0.0, raw=raw)

    def place_limit_order(
        self,
        *,
        symbol: str,
        side: str,
        qty: float,
        price: float,
        reduce_only: bool = False,
        client_order_id: Optional[str] = None,
    ) -> LiveOrderResult:
        sym = to_bybit_symbol(symbol)
        sd = (side or "").strip().lower()
        if sd not in ("buy", "sell"):
            raise LiveTradingError(f"Invalid side: {side}")
        q_req = float(qty or 0.0)
        px = float(price or 0.0)
        if q_req <= 0 or px <= 0:
            raise LiveTradingError("Invalid qty/price")
        q_dec, qty_precision = self._normalize_qty(symbol=symbol, qty=q_req)
        if float(q_dec or 0) <= 0:
            raise LiveTradingError(f"Invalid qty (below step/min): requested={q_req}")
        body: Dict[str, Any] = {
            "category": self.category,
            "symbol": sym,
            "side": "Buy" if sd == "buy" else "Sell",
            "orderType": "Limit",
            "qty": self._dec_str(q_dec, strict_precision=qty_precision),
            "price": str(px),
            "timeInForce": "GTC",
        }
        if reduce_only and self.category == "linear":
            body["reduceOnly"] = True
        if client_order_id:
            body["orderLinkId"] = str(client_order_id)
        raw = self._signed_request("POST", "/v5/order/create", json_body=body)
        res = (raw.get("result") or {}) if isinstance(raw, dict) else {}
        oid = str(res.get("orderId") or res.get("orderLinkId") or "")
        return LiveOrderResult(exchange_id="bybit", exchange_order_id=oid, filled=0.0, avg_price=0.0, raw=raw)

    def cancel_order(self, *, symbol: str, order_id: str = "", client_order_id: str = "") -> Dict[str, Any]:
        sym = to_bybit_symbol(symbol)
        body: Dict[str, Any] = {"category": self.category, "symbol": sym}
        if order_id:
            body["orderId"] = str(order_id)
        elif client_order_id:
            body["orderLinkId"] = str(client_order_id)
        else:
            raise LiveTradingError("Bybit cancel_order requires order_id or client_order_id")
        return self._signed_request("POST", "/v5/order/cancel", json_body=body)

    def get_order(self, *, symbol: str, order_id: str = "", client_order_id: str = "") -> Dict[str, Any]:
        sym = to_bybit_symbol(symbol)
        params: Dict[str, Any] = {"category": self.category, "symbol": sym}
        if order_id:
            params["orderId"] = str(order_id)
        elif client_order_id:
            params["orderLinkId"] = str(client_order_id)
        else:
            raise LiveTradingError("Bybit get_order requires order_id or client_order_id")
        raw = self._signed_request("GET", "/v5/order/realtime", params=params)
        lst = (((raw.get("result") or {}).get("list")) if isinstance(raw, dict) else None) or []
        first: Dict[str, Any] = lst[0] if isinstance(lst, list) and lst else {}
        return first if isinstance(first, dict) else {}

    def wait_for_fill(
        self,
        *,
        symbol: str,
        order_id: str = "",
        client_order_id: str = "",
        max_wait_sec: float = 3.0,
        poll_interval_sec: float = 0.5,
    ) -> Dict[str, Any]:
        end_ts = time.time() + float(max_wait_sec or 0.0)
        last: Dict[str, Any] = {}
        while True:
            try:
                last = self.get_order(symbol=symbol, order_id=str(order_id or ""), client_order_id=str(client_order_id or ""))
            except Exception:
                last = last or {}
            status = str(last.get("orderStatus") or last.get("order_status") or "")
            try:
                filled = float(last.get("cumExecQty") or 0.0)
            except Exception:
                filled = 0.0
            avg_price = 0.0
            try:
                avg_price = float(last.get("avgPrice") or 0.0)
            except Exception:
                avg_price = 0.0
            # Extract fee from cumExecFee (Bybit API field for cumulative execution fee)
            fee = 0.0
            fee_ccy = ""
            try:
                fee = abs(float(last.get("cumExecFee") or 0.0))
            except Exception:
                fee = 0.0
            # Bybit linear contracts are settled in USDT
            if fee > 0:
                fee_ccy = "USDT"
            if filled > 0 and avg_price > 0:
                return {"filled": filled, "avg_price": avg_price, "fee": fee, "fee_ccy": fee_ccy, "status": status, "order": last}
            if status.lower() in ("filled", "cancelled", "canceled", "rejected"):
                return {"filled": filled, "avg_price": avg_price, "fee": fee, "fee_ccy": fee_ccy, "status": status, "order": last}
            if time.time() >= end_ts:
                return {"filled": filled, "avg_price": avg_price, "fee": fee, "fee_ccy": fee_ccy, "status": status, "order": last}
            time.sleep(float(poll_interval_sec or 0.5))

    def get_positions(self) -> Dict[str, Any]:
        if self.category != "linear":
            raise LiveTradingError("Bybit positions are only supported for linear category in this client")
        return self._signed_request("GET", "/v5/position/list", params={"category": "linear"})

    def set_leverage(self, *, symbol: str, leverage: float) -> bool:
        if self.category != "linear":
            return False
        sym = to_bybit_symbol(symbol)
        try:
            lv = int(float(leverage or 1.0))
        except Exception:
            lv = 1
        if lv < 1:
            lv = 1
        # Bybit leverage caps vary per symbol; keep best-effort.
        body = {"category": "linear", "symbol": sym, "buyLeverage": str(lv), "sellLeverage": str(lv)}
        try:
            resp = self._signed_request("POST", "/v5/position/set-leverage", json_body=body)
            ok = isinstance(resp, dict) and (resp.get("retCode") in (0, "0", None, ""))
            return bool(ok)
        except Exception:
            return False


