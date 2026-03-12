"""
Binance Spot (direct REST) client.
"""

from __future__ import annotations

import hmac
import hashlib
import time
from decimal import Decimal, ROUND_DOWN
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlencode

from app.services.live_trading.base import BaseRestClient, LiveOrderResult, LiveTradingError
from app.services.live_trading.symbols import to_binance_futures_symbol


class BinanceSpotClient(BaseRestClient):
    def __init__(self, *, api_key: str, secret_key: str, base_url: str = None, enable_demo_trading: bool = False, timeout_sec: float = 15.0):
        if not base_url:
            base_url = "https://demo-api.binance.com" if enable_demo_trading else "https://api.binance.com"

        super().__init__(base_url=base_url, timeout_sec=timeout_sec)
        self.api_key = (api_key or "").strip()
        self.secret_key = (secret_key or "").strip()
        if not self.api_key or not self.secret_key:
            raise LiveTradingError("Missing Binance api_key/secret_key")

        # Best-effort cache for public symbol filters used to normalize quantities.
        self._sym_filter_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
        self._sym_filter_cache_ttl_sec = 300.0

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
        Binance requires quantities/prices to match LOT_SIZE/PRICE_FILTER precision.
        This method ensures the output string doesn't exceed the required precision.
        
        Args:
            d: Decimal value to format
            max_decimals: Maximum decimal places (fallback if strict_precision not provided)
            strict_precision: If provided, strictly limit to this many decimal places (no trailing zero removal)
        """
        try:
            if d == 0:
                return "0"
            # Normalize to remove unnecessary trailing zeros from internal representation
            normalized = d.normalize()
            
            # If strict_precision is provided, use it and strictly limit decimal places
            # This ensures we match the stepSize requirement exactly
            if strict_precision is not None:
                try:
                    prec = int(strict_precision)
                    if prec < 0:
                        prec = 0
                    if prec > 18:
                        prec = 18
                    # Use quantize to ensure exact precision (round down to match stepSize)
                    q = Decimal("1").scaleb(-prec)
                    quantized = normalized.quantize(q, rounding=ROUND_DOWN)
                    # Format with exact precision - this will produce at most 'prec' decimal places
                    # Use fixed-point format to ensure we don't exceed precision
                    s = format(quantized, f".{prec}f")
                    # Remove trailing zeros and decimal point if not needed
                    # This is safe because we've already quantized to the correct precision
                    if '.' in s:
                        s = s.rstrip('0').rstrip('.')
                    return s if s else "0"
                except Exception:
                    pass
            
            # Fallback to original logic if strict_precision not provided or failed
            # Convert to string using fixed-point notation
            s = format(normalized, f".{max_decimals}f")
            # Remove trailing zeros and decimal point if not needed
            if '.' in s:
                s = s.rstrip('0').rstrip('.')
            return s if s else "0"
        except Exception:
            # Fallback: try to convert safely
            try:
                f = float(d)
                if f == 0:
                    return "0"
                if strict_precision is not None:
                    try:
                        prec = int(strict_precision)
                        if prec < 0:
                            prec = 0
                        if prec > 18:
                            prec = 18
                        s = format(f, f".{prec}f")
                        if '.' in s:
                            s = s.rstrip('0').rstrip('.')
                        return s if s else "0"
                    except Exception:
                        pass
                # Format with max_decimals and remove trailing zeros
                s = format(f, f".{max_decimals}f")
                if '.' in s:
                    s = s.rstrip('0').rstrip('.')
                return s if s else "0"
            except Exception:
                # Last resort: convert to string
                s = str(d)
                # Try to remove scientific notation if present
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

    def _sign(self, query_string: str) -> str:
        return hmac.new(self.secret_key.encode("utf-8"), query_string.encode("utf-8"), hashlib.sha256).hexdigest()

    def _signed_headers(self) -> Dict[str, str]:
        return {"X-MBX-APIKEY": self.api_key}

    def _signed_request(self, method: str, path: str, *, params: Dict[str, Any]) -> Dict[str, Any]:
        p = dict(params or {})
        p["timestamp"] = int(time.time() * 1000)
        qs = urlencode(p, doseq=True)
        p["signature"] = self._sign(qs)
        code, data, text = self._request(method, path, params=p, headers=self._signed_headers())
        if code >= 400:
            raise LiveTradingError(f"BinanceSpot HTTP {code}: {text[:500]}")
        if isinstance(data, dict) and data.get("code") and int(data.get("code")) < 0:
            raise LiveTradingError(f"BinanceSpot error: {data}")
        return data if isinstance(data, dict) else {"raw": data}

    def ping(self) -> bool:
        """
        Public connectivity check.

        Endpoint: GET /api/v3/time
        """
        code, data, _ = self._request("GET", "/api/v3/time")
        return code == 200 and isinstance(data, dict)

    def _public_request(self, method: str, path: str, *, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        code, data, text = self._request(method, path, params=params, headers=None, json_body=None, data=None)
        if code >= 400:
            raise LiveTradingError(f"BinanceSpot HTTP {code}: {text[:500]}")
        if isinstance(data, dict) and data.get("code") and int(data.get("code")) < 0:
            raise LiveTradingError(f"BinanceSpot error: {data}")
        return data if isinstance(data, dict) else {"raw": data}

    def get_symbol_filters(self, *, symbol: str) -> Dict[str, Any]:
        """
        Get spot symbol filters from exchangeInfo (best-effort).

        Endpoint: GET /api/v3/exchangeInfo?symbol=...
        """
        sym = to_binance_futures_symbol(symbol)
        if not sym:
            return {}
        now = time.time()
        cached = self._sym_filter_cache.get(sym)
        if cached:
            ts, obj = cached
            if obj and (now - float(ts or 0.0)) <= float(self._sym_filter_cache_ttl_sec or 300.0):
                return obj

        raw = self._public_request("GET", "/api/v3/exchangeInfo", params={"symbol": sym})
        symbols = raw.get("symbols") if isinstance(raw, dict) else None
        # Defensive: some gateways/proxies may strip query params; Binance may then return full list.
        first: Dict[str, Any] = {}
        if isinstance(symbols, list) and symbols:
            picked = None
            try:
                picked = next((s for s in symbols if isinstance(s, dict) and str(s.get("symbol") or "") == sym), None)
            except Exception:
                picked = None
            first = picked if isinstance(picked, dict) else (symbols[0] if isinstance(symbols[0], dict) else {})
        filters = first.get("filters") if isinstance(first, dict) else None
        fdict: Dict[str, Any] = {}
        if isinstance(filters, list):
            for f in filters:
                if isinstance(f, dict) and f.get("filterType"):
                    fdict[str(f.get("filterType"))] = f
        # Also keep precision metadata when available (used to avoid -1111).
        try:
            qty_prec = first.get("baseAssetPrecision") if isinstance(first, dict) else None
            # For spot, price precision is typically quotePrecision/quoteAssetPrecision.
            price_prec = None
            if isinstance(first, dict):
                price_prec = first.get("quotePrecision")
                if price_prec is None:
                    price_prec = first.get("quoteAssetPrecision")
            meta = {
                "symbol": str(first.get("symbol") or "") if isinstance(first, dict) else "",
                "quantityPrecision": int(qty_prec) if qty_prec is not None else None,
                "pricePrecision": int(price_prec) if price_prec is not None else None,
            }
            fdict["_meta"] = meta
        except Exception:
            pass
        if fdict:
            self._sym_filter_cache[sym] = (now, fdict)
        return fdict

    @staticmethod
    def _floor_to_precision(value: Decimal, precision: Optional[int]) -> Decimal:
        try:
            if precision is None:
                return value
            p = int(precision)
        except Exception:
            return value
        if p < 0 or p > 18:
            return value
        try:
            q = Decimal("1").scaleb(-p)
            return value.quantize(q, rounding=ROUND_DOWN)
        except Exception:
            return value

    def _normalize_price(self, *, symbol: str, price: float) -> Decimal:
        """
        Normalize spot limit price using PRICE_FILTER tickSize (best-effort).
        """
        px = self._to_dec(price)
        if px <= 0:
            return Decimal("0")
        fdict: Dict[str, Any] = {}
        try:
            fdict = self.get_symbol_filters(symbol=symbol) or {}
        except Exception:
            fdict = {}

        filt = fdict.get("PRICE_FILTER") or {}
        tick = self._to_dec((filt or {}).get("tickSize") or "0")
        min_px = self._to_dec((filt or {}).get("minPrice") or "0")

        if tick > 0:
            px = self._floor_to_step(px, tick)
        # Enforce price precision cap (some symbols reject more decimals even if tick looks permissive).
        try:
            meta = fdict.get("_meta") or {}
            px = self._floor_to_precision(px, (meta.get("pricePrecision") if isinstance(meta, dict) else None))
        except Exception:
            pass
        if min_px > 0 and px < min_px:
            return Decimal("0")
        return px

    def _normalize_quantity(self, *, symbol: str, quantity: float, for_market: bool) -> Tuple[Decimal, Optional[int]]:
        """
        Normalize spot order quantity using LOT_SIZE / MARKET_LOT_SIZE filters (best-effort).
        
        Returns:
            Tuple of (normalized_quantity, precision) where precision is the number of decimal places required.
        """
        q = self._to_dec(quantity)
        if q <= 0:
            return (Decimal("0"), None)
        fdict: Dict[str, Any] = {}
        try:
            fdict = self.get_symbol_filters(symbol=symbol) or {}
        except Exception:
            fdict = {}

        key = "MARKET_LOT_SIZE" if for_market else "LOT_SIZE"
        filt = fdict.get(key) or fdict.get("LOT_SIZE") or {}

        step = self._to_dec((filt or {}).get("stepSize") or "0")
        min_qty = self._to_dec((filt or {}).get("minQty") or "0")

        if step > 0:
            q = self._floor_to_step(q, step)
        
        # Enforce quantity precision cap (Binance may reject quantities with too many decimals: -1111).
        # First try to get precision from metadata
        qty_precision = None
        try:
            meta = fdict.get("_meta") or {}
            if isinstance(meta, dict):
                qty_precision = meta.get("quantityPrecision")
        except Exception:
            pass
        
        # If precision not available, infer from stepSize
        if qty_precision is None and step > 0:
            try:
                # stepSize like "0.001" means 3 decimal places
                # Use normalize() to remove trailing zeros, then count decimal places
                step_normalized = step.normalize()
                step_str = str(step_normalized)
                if '.' in step_str:
                    # Count decimal places after removing trailing zeros
                    decimal_part = step_str.split('.')[1]
                    qty_precision = len(decimal_part)
                    # Ensure precision is at least 0 and at most 18
                    if qty_precision < 0:
                        qty_precision = 0
                    if qty_precision > 18:
                        qty_precision = 18
                else:
                    # If stepSize is 1 or larger, precision is 0
                    qty_precision = 0
            except Exception:
                pass
        
        # Apply precision limit
        if qty_precision is not None:
            q = self._floor_to_precision(q, qty_precision)
        
        if min_qty > 0 and q < min_qty:
            return (Decimal("0"), qty_precision)
        return (q, qty_precision)

    def place_limit_order(
        self,
        *,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        client_order_id: Optional[str] = None,
    ) -> LiveOrderResult:
        sym = to_binance_futures_symbol(symbol)
        sd = (side or "").upper()
        if sd not in ("BUY", "SELL"):
            raise LiveTradingError(f"Invalid side: {side}")
        q_req = float(quantity or 0.0)
        px = float(price or 0.0)
        if q_req <= 0 or px <= 0:
            raise LiveTradingError("Invalid quantity/price")
        q_dec, qty_precision = self._normalize_quantity(symbol=symbol, quantity=q_req, for_market=False)
        if float(q_dec or 0) <= 0:
            raise LiveTradingError(f"Invalid quantity (below step/minQty): requested={q_req}")
        px_dec = self._normalize_price(symbol=symbol, price=px)
        if float(px_dec or 0) <= 0:
            raise LiveTradingError(f"Invalid price (bad tick/minPrice): requested={px}")

        params: Dict[str, Any] = {
            "symbol": sym,
            "side": sd,
            "type": "LIMIT",
            "timeInForce": "GTC",
            "quantity": self._dec_str(q_dec, strict_precision=qty_precision),
            "price": self._dec_str(px_dec),
        }
        if client_order_id:
            params["newClientOrderId"] = str(client_order_id)
        try:
            raw = self._signed_request("POST", "/api/v3/order", params=params)
        except LiveTradingError as e:
            raise LiveTradingError(
                f"{e} | debug: symbol={sym} side={sd} "
                f"qty_req={q_req} qty_norm={self._dec_str(q_dec, strict_precision=qty_precision)} "
                f"price_req={px} price_norm={self._dec_str(px_dec)}"
            )
        return LiveOrderResult(
            exchange_id="binance",
            exchange_order_id=str(raw.get("orderId") or raw.get("clientOrderId") or ""),
            filled=float(raw.get("executedQty") or 0.0),
            avg_price=float(raw.get("cummulativeQuoteQty") or 0.0) / float(raw.get("executedQty") or 1.0) if float(raw.get("executedQty") or 0.0) > 0 else 0.0,
            raw=raw,
        )

    def place_market_order(
        self,
        *,
        symbol: str,
        side: str,
        quantity: float,
        client_order_id: Optional[str] = None,
    ) -> LiveOrderResult:
        sym = to_binance_futures_symbol(symbol)
        sd = (side or "").upper()
        if sd not in ("BUY", "SELL"):
            raise LiveTradingError(f"Invalid side: {side}")
        q_req = float(quantity or 0.0)
        q_dec, qty_precision = self._normalize_quantity(symbol=symbol, quantity=q_req, for_market=True)
        if float(q_dec or 0) <= 0:
            raise LiveTradingError(f"Invalid quantity (below step/minQty): requested={q_req}")

        params: Dict[str, Any] = {
            "symbol": sym,
            "side": sd,
            "type": "MARKET",
            "quantity": self._dec_str(q_dec, strict_precision=qty_precision),
        }
        if client_order_id:
            params["newClientOrderId"] = str(client_order_id)
        try:
            raw = self._signed_request("POST", "/api/v3/order", params=params)
        except LiveTradingError as e:
            raise LiveTradingError(
                f"{e} | debug: symbol={sym} side={sd} "
                f"qty_req={q_req} qty_norm={self._dec_str(q_dec, strict_precision=qty_precision)}"
            )
        return LiveOrderResult(
            exchange_id="binance",
            exchange_order_id=str(raw.get("orderId") or raw.get("clientOrderId") or ""),
            filled=float(raw.get("executedQty") or 0.0),
            avg_price=float(raw.get("cummulativeQuoteQty") or 0.0) / float(raw.get("executedQty") or 1.0) if float(raw.get("executedQty") or 0.0) > 0 else 0.0,
            raw=raw,
        )

    def get_account(self) -> Dict[str, Any]:
        """
        Get spot account balances.

        Endpoint: GET /api/v3/account
        """
        return self._signed_request("GET", "/api/v3/account", params={})

    def get_my_trades(self, *, symbol: str, order_id: str = "", limit: int = 100) -> Any:
        """
        Fetch spot trade fills.

        Endpoint: GET /api/v3/myTrades
        """
        sym = to_binance_futures_symbol(symbol)
        if not sym:
            return []
        params: Dict[str, Any] = {"symbol": sym}
        if order_id:
            params["orderId"] = str(order_id)
        try:
            lim = int(limit or 100)
        except Exception:
            lim = 100
        lim = max(1, min(1000, lim))
        params["limit"] = lim
        data = self._signed_request("GET", "/api/v3/myTrades", params=params)
        return data

    def get_fee_for_order(self, *, symbol: str, order_id: str) -> Tuple[float, str]:
        """
        Best-effort: sum commissions from fills for a specific spot order.

        Returns: (total_fee, fee_ccy)
        """
        try:
            trades = self.get_my_trades(symbol=symbol, order_id=str(order_id or ""), limit=200)
        except Exception:
            trades = []
        if not isinstance(trades, list):
            return 0.0, ""
        total_fee = 0.0
        fee_ccy = ""
        for t in trades:
            if not isinstance(t, dict):
                continue
            try:
                fee = float(t.get("commission") or 0.0)
            except Exception:
                fee = 0.0
            ccy = str(t.get("commissionAsset") or "").strip()
            if fee != 0.0:
                total_fee += abs(float(fee))
                if (not fee_ccy) and ccy:
                    fee_ccy = ccy
        return float(total_fee), str(fee_ccy or "")

    def cancel_order(self, *, symbol: str, order_id: str = "", client_order_id: str = "") -> Dict[str, Any]:
        sym = to_binance_futures_symbol(symbol)
        params: Dict[str, Any] = {"symbol": sym}
        if order_id:
            params["orderId"] = str(order_id)
        elif client_order_id:
            params["origClientOrderId"] = str(client_order_id)
        else:
            raise LiveTradingError("BinanceSpot cancel_order requires order_id or client_order_id")
        return self._signed_request("DELETE", "/api/v3/order", params=params)

    def get_order(self, *, symbol: str, order_id: str = "", client_order_id: str = "") -> Dict[str, Any]:
        sym = to_binance_futures_symbol(symbol)
        params: Dict[str, Any] = {"symbol": sym}
        if order_id:
            params["orderId"] = str(order_id)
        elif client_order_id:
            params["origClientOrderId"] = str(client_order_id)
        else:
            raise LiveTradingError("BinanceSpot get_order requires order_id or client_order_id")
        return self._signed_request("GET", "/api/v3/order", params=params)

    def wait_for_fill(
        self,
        *,
        symbol: str,
        order_id: str = "",
        client_order_id: str = "",
        max_wait_sec: float = 10.0,
        poll_interval_sec: float = 0.5,
    ) -> Dict[str, Any]:
        end_ts = time.time() + float(max_wait_sec or 0.0)
        last: Dict[str, Any] = {}
        while True:
            try:
                last = self.get_order(symbol=symbol, order_id=str(order_id or ""), client_order_id=str(client_order_id or ""))
            except Exception:
                last = last or {}

            status = str(last.get("status") or "")
            try:
                filled = float(last.get("executedQty") or 0.0)
            except Exception:
                filled = 0.0
            avg_price = 0.0
            try:
                cum_quote = float(last.get("cummulativeQuoteQty") or 0.0)
                if filled > 0 and cum_quote > 0:
                    avg_price = cum_quote / filled
            except Exception:
                pass

            if filled > 0 and avg_price > 0:
                return {"filled": filled, "avg_price": avg_price, "status": status, "order": last}
            if status in ("FILLED", "CANCELED", "EXPIRED", "REJECTED"):
                return {"filled": filled, "avg_price": avg_price, "status": status, "order": last}
            if time.time() >= end_ts:
                return {"filled": filled, "avg_price": avg_price, "status": status, "order": last}
            time.sleep(float(poll_interval_sec or 0.5))


