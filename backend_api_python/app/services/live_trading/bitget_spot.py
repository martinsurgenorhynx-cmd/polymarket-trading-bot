"""
Bitget Spot (direct REST) client.

Endpoints are aligned with hummingbot constants:
- POST /api/v2/spot/trade/place-order
- POST /api/v2/spot/trade/cancel-order
- GET  /api/v2/spot/trade/orderInfo
- GET  /api/v2/spot/trade/fills
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
from app.services.live_trading.symbols import to_bitget_um_symbol


class BitgetSpotClient(BaseRestClient):
    def __init__(
        self,
        *,
        api_key: str,
        secret_key: str,
        passphrase: str,
        base_url: str = "https://api.bitget.com",
        timeout_sec: float = 15.0,
        channel_api_code: str = "bntva",
    ):
        super().__init__(base_url=base_url, timeout_sec=timeout_sec)
        self.api_key = (api_key or "").strip()
        self.secret_key = (secret_key or "").strip()
        self.passphrase = (passphrase or "").strip()
        self.channel_api_code = (channel_api_code or "").strip()
        if not self.api_key or not self.secret_key or not self.passphrase:
            raise LiveTradingError("Missing Bitget api_key/secret_key/passphrase")

        # Best-effort cache for public symbol metadata used to normalize order sizes.
        # Key: symbol -> (fetched_at_ts, meta_dict)
        self._sym_meta_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
        self._sym_meta_cache_ttl_sec = 300.0

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
        Bitget requires quantities to match quantityStep/quantityScale precision.
        
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

    def _sign(self, ts_ms: str, method: str, path: str, body: str) -> str:
        prehash = f"{ts_ms}{method.upper()}{path}{body}"
        mac = hmac.new(self.secret_key.encode("utf-8"), prehash.encode("utf-8"), hashlib.sha256).digest()
        return base64.b64encode(mac).decode("utf-8")

    def _headers(self, ts_ms: str, sign: str) -> Dict[str, str]:
        h = {
            "ACCESS-KEY": self.api_key,
            "ACCESS-SIGN": sign,
            "ACCESS-TIMESTAMP": ts_ms,
            "ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json",
        }
        if self.channel_api_code:
            h["X-CHANNEL-API-CODE"] = self.channel_api_code
        return h

    def _signed_request(
        self,
        method: str,
        path: str,
        *,
        json_body: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Bitget signature must match the exact body string sent over the wire.
        """
        ts_ms = str(int(time.time() * 1000))
        body_str = self._json_dumps(json_body) if json_body is not None else ""

        qs = ""
        if params:
            norm = {str(k): "" if v is None else str(v) for k, v in dict(params).items()}
            qs = urlencode(sorted(norm.items()), doseq=True)
        signed_path = f"{path}?{qs}" if qs else path

        sign = self._sign(ts_ms, method, signed_path, body_str)
        code, data, text = self._request(
            method,
            path,
            params=params,
            data=body_str if body_str else None,
            headers=self._headers(ts_ms, sign),
        )
        if code >= 400:
            raise LiveTradingError(f"BitgetSpot HTTP {code}: {text[:500]}")
        if isinstance(data, dict):
            c = str(data.get("code") or "")
            if c and c not in ("00000", "0"):
                raise LiveTradingError(f"BitgetSpot error: {data}")
        return data if isinstance(data, dict) else {"raw": data}

    def _public_request(self, method: str, path: str, *, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        code, data, text = self._request(method, path, params=params, headers=None, json_body=None, data=None)
        if code >= 400:
            raise LiveTradingError(f"BitgetSpot HTTP {code}: {text[:500]}")
        if isinstance(data, dict):
            c = str(data.get("code") or "")
            if c and c not in ("00000", "0"):
                raise LiveTradingError(f"BitgetSpot error: {data}")
        return data if isinstance(data, dict) else {"raw": data}

    def get_symbol_meta(self, *, symbol: str) -> Dict[str, Any]:
        """
        Fetch spot symbol metadata (best-effort).

        Endpoint (Bitget v2 spot): GET /api/v2/spot/public/symbols
        """
        sym = to_bitget_um_symbol(symbol)
        if not sym:
            return {}
        now = time.time()
        cached = self._sym_meta_cache.get(sym)
        if cached:
            ts, obj = cached
            if obj and (now - float(ts or 0.0)) <= float(self._sym_meta_cache_ttl_sec or 300.0):
                return obj

        raw = self._public_request("GET", "/api/v2/spot/public/symbols")
        data = raw.get("data") if isinstance(raw, dict) else None
        items = data if isinstance(data, list) else []
        found: Dict[str, Any] = {}
        for it in items:
            if not isinstance(it, dict):
                continue
            s = str(it.get("symbol") or it.get("symbolName") or "")
            if s and s.upper() == sym.upper():
                found = it
                break
        if found:
            self._sym_meta_cache[sym] = (now, found)
        return found

    def _normalize_base_size(self, *, symbol: str, base_size: float) -> Tuple[Decimal, Optional[int]]:
        """
        Normalize spot base size to lot/step constraints (best-effort).
        
        Returns:
            Tuple of (normalized_size, precision) where precision is the number of decimal places required.
        """
        req = self._to_dec(base_size)
        if req <= 0:
            return (Decimal("0"), None)

        meta: Dict[str, Any] = {}
        try:
            meta = self.get_symbol_meta(symbol=symbol) or {}
        except Exception:
            meta = {}

        # Try common fields. If unavailable, keep as-is.
        step = self._to_dec(meta.get("quantityScale") or meta.get("quantityStep") or meta.get("sizeStep") or meta.get("minTradeIncrement") or "0")
        size_precision = None
        if step <= 0:
            # Some endpoints expose decimals instead of step.
            qd = meta.get("quantityPrecision") or meta.get("quantityPlace") or meta.get("sizePlace")
            try:
                places = int(qd) if qd is not None else 0
            except Exception:
                places = 0
            if places >= 0 and places <= 18:
                step = Decimal("1") / (Decimal("10") ** Decimal(str(places)))
                size_precision = places

        if step > 0:
            req = self._floor_to_step(req, step)
            # Infer precision from step if not already set
            if size_precision is None:
                try:
                    step_normalized = step.normalize()
                    step_str = str(step_normalized)
                    if '.' in step_str:
                        decimal_part = step_str.split('.')[1]
                        size_precision = len(decimal_part)
                        if size_precision < 0:
                            size_precision = 0
                        if size_precision > 18:
                            size_precision = 18
                    else:
                        size_precision = 0
                except Exception:
                    pass

        mn = self._to_dec(meta.get("minTradeAmount") or meta.get("minTradeNum") or meta.get("minQty") or meta.get("minSize") or "0")
        if mn > 0 and req < mn:
            return (Decimal("0"), size_precision)
        return (req, size_precision)

    def place_limit_order(self, *, symbol: str, side: str, size: float, price: float, client_order_id: Optional[str] = None) -> LiveOrderResult:
        sym = to_bitget_um_symbol(symbol)
        sd = (side or "").lower()
        if sd not in ("buy", "sell"):
            raise LiveTradingError(f"Invalid side: {side}")
        req = float(size or 0.0)
        px = float(price or 0.0)
        if req <= 0 or px <= 0:
            raise LiveTradingError("Invalid size/price")
        sz_dec, sz_precision = self._normalize_base_size(symbol=symbol, base_size=req)
        if float(sz_dec or 0) <= 0:
            raise LiveTradingError(f"Invalid size (below step/min): requested={req}")

        body: Dict[str, Any] = {
            "side": sd,
            "symbol": sym,
            "size": self._dec_str(sz_dec, strict_precision=sz_precision),
            "orderType": "limit",
            "force": "gtc",
            "price": str(px),
        }
        if client_order_id:
            body["clientOid"] = str(client_order_id)
        raw = self._signed_request("POST", "/api/v2/spot/trade/place-order", json_body=body)
        data = raw.get("data") if isinstance(raw, dict) else None
        order_id = str(data.get("orderId") or "") if isinstance(data, dict) else ""
        return LiveOrderResult(exchange_id="bitget", exchange_order_id=order_id, filled=0.0, avg_price=0.0, raw=raw)

    def place_market_order(self, *, symbol: str, side: str, size: float, client_order_id: Optional[str] = None) -> LiveOrderResult:
        """
        NOTE: Bitget spot market BUY may expect quote amount. We accept `size` as base size,
        but the caller can also pass a quote-sized value if desired.
        """
        sym = to_bitget_um_symbol(symbol)
        sd = (side or "").lower()
        if sd not in ("buy", "sell"):
            raise LiveTradingError(f"Invalid side: {side}")
        req = float(size or 0.0)
        if req <= 0:
            raise LiveTradingError("Invalid size")

        # For Bitget spot market BUY, many APIs interpret size as quote amount.
        # Our worker may pass quote-sized value for BUY; do not quantize it as base size.
        if sd == "sell":
            sz_dec, sz_precision = self._normalize_base_size(symbol=symbol, base_size=req)
            if float(sz_dec or 0) <= 0:
                raise LiveTradingError(f"Invalid size (below step/min): requested={req}")
            sz_str = self._dec_str(sz_dec, strict_precision=sz_precision)
        else:
            sz_str = str(req)

        body: Dict[str, Any] = {
            "side": sd,
            "symbol": sym,
            "size": sz_str,
            "orderType": "market",
            "force": "gtc",
        }
        if client_order_id:
            body["clientOid"] = str(client_order_id)
        raw = self._signed_request("POST", "/api/v2/spot/trade/place-order", json_body=body)
        data = raw.get("data") if isinstance(raw, dict) else None
        order_id = str(data.get("orderId") or "") if isinstance(data, dict) else ""
        return LiveOrderResult(exchange_id="bitget", exchange_order_id=order_id, filled=0.0, avg_price=0.0, raw=raw)

    def cancel_order(self, *, symbol: str, client_order_id: str) -> Dict[str, Any]:
        sym = to_bitget_um_symbol(symbol)
        if not client_order_id:
            raise LiveTradingError("BitgetSpot cancel_order requires client_order_id")
        body = {"symbol": sym, "clientOid": str(client_order_id)}
        return self._signed_request("POST", "/api/v2/spot/trade/cancel-order", json_body=body)

    def get_order(self, *, symbol: str, order_id: str = "", client_order_id: str = "") -> Dict[str, Any]:
        sym = to_bitget_um_symbol(symbol)
        params: Dict[str, Any] = {"symbol": sym}
        if order_id:
            params["orderId"] = str(order_id)
        elif client_order_id:
            params["clientOid"] = str(client_order_id)
        else:
            raise LiveTradingError("BitgetSpot get_order requires order_id or client_order_id")
        return self._signed_request("GET", "/api/v2/spot/trade/orderInfo", params=params)

    def get_fills(self, *, symbol: str, order_id: str) -> Dict[str, Any]:
        sym = to_bitget_um_symbol(symbol)
        params: Dict[str, Any] = {"symbol": sym, "orderId": str(order_id)}
        return self._signed_request("GET", "/api/v2/spot/trade/fills", params=params)

    def wait_for_fill(
        self,
        *,
        symbol: str,
        order_id: str,
        client_order_id: str = "",
        max_wait_sec: float = 10.0,
        poll_interval_sec: float = 0.5,
    ) -> Dict[str, Any]:
        end_ts = time.time() + float(max_wait_sec or 0.0)
        last_order: Dict[str, Any] = {}
        last_fills: Dict[str, Any] = {}
        state = ""

        while True:
            # Prefer fills to compute weighted average if available.
            try:
                last_fills = self.get_fills(symbol=symbol, order_id=str(order_id))
                data = last_fills.get("data") if isinstance(last_fills, dict) else None
                fills = data if isinstance(data, list) else []
                total_base = 0.0
                total_quote = 0.0
                total_fee = 0.0
                fee_ccy = ""
                if isinstance(fills, list):
                    for f in fills:
                        try:
                            sz = float(f.get("size") or 0.0)
                            px = float(f.get("priceAvg") or f.get("price") or 0.0)
                            if sz > 0 and px > 0:
                                total_base += sz
                                total_quote += sz * px
                            # Best-effort fee extraction (fields vary by endpoint/version).
                            fee_v = f.get("fee")
                            if fee_v is None:
                                fee_v = f.get("fillFee")
                            if fee_v is None:
                                fee_v = f.get("tradeFee")
                            try:
                                fee = float(fee_v or 0.0)
                            except Exception:
                                fee = 0.0
                            ccy = str(f.get("feeCoin") or f.get("feeCcy") or f.get("fillFeeCoin") or f.get("fillFeeCcy") or "").strip()
                            if fee != 0.0:
                                total_fee += abs(float(fee))
                                if (not fee_ccy) and ccy:
                                    fee_ccy = ccy
                        except Exception:
                            continue
                if total_base > 0 and total_quote > 0:
                    return {
                        "filled": total_base,
                        "avg_price": total_quote / total_base,
                        "fee": float(total_fee),
                        "fee_ccy": str(fee_ccy or ""),
                        "state": state,
                        "order": last_order,
                        "fills": last_fills
                    }
            except Exception:
                pass

            try:
                last_order = self.get_order(symbol=symbol, order_id=str(order_id or ""), client_order_id=str(client_order_id or ""))
                od = last_order.get("data") if isinstance(last_order, dict) else None
                if isinstance(od, dict):
                    state = str(od.get("status") or od.get("state") or "")
            except Exception:
                pass

            if time.time() >= end_ts:
                return {"filled": 0.0, "avg_price": 0.0, "state": state, "order": last_order, "fills": last_fills}
            time.sleep(float(poll_interval_sec or 0.5))

    def get_assets(self) -> Dict[str, Any]:
        """
        Spot assets/balances.

        Endpoint: GET /api/v2/spot/account/assets
        """
        return self._signed_request("GET", "/api/v2/spot/account/assets")


