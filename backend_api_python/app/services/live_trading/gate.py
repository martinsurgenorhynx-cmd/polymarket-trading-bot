"""
Gate.io (direct REST) clients:
- Spot: /api/v4/spot/*
- Futures USDT: /api/v4/futures/usdt/*

Signing (apiv4):
SIGN = hex(hmac_sha512(secret, method + "\\n" + url + "\\n" + query + "\\n" + body + "\\n" + timestamp))
Headers:
- KEY: api key
- Timestamp: unix seconds
- SIGN: signature hex
"""

from __future__ import annotations

import hashlib
import hmac
import time
from decimal import Decimal, ROUND_DOWN
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlencode

from app.services.live_trading.base import BaseRestClient, LiveOrderResult, LiveTradingError
from app.services.live_trading.symbols import to_gate_currency_pair


class _GateBase(BaseRestClient):
    def __init__(self, *, api_key: str, secret_key: str, base_url: str = "https://api.gateio.ws", timeout_sec: float = 15.0):
        super().__init__(base_url=base_url, timeout_sec=timeout_sec)
        self.api_key = (api_key or "").strip()
        self.secret_key = (secret_key or "").strip()
        if not self.api_key or not self.secret_key:
            raise LiveTradingError("Missing Gate api_key/secret_key")

    def _sign(self, *, method: str, url: str, query_string: str, body_str: str, ts: str) -> str:
        msg = f"{method.upper()}\n{url}\n{query_string}\n{body_str}\n{ts}"
        return hmac.new(self.secret_key.encode("utf-8"), msg.encode("utf-8"), hashlib.sha512).hexdigest()

    def _headers(self, ts: str, sign: str) -> Dict[str, str]:
        return {"KEY": self.api_key, "Timestamp": ts, "SIGN": sign, "Content-Type": "application/json"}

    def _signed_request(self, method: str, path: str, *, params: Optional[Dict[str, Any]] = None, json_body: Optional[Dict[str, Any]] = None) -> Any:
        m = str(method or "GET").upper()
        ts = str(int(time.time()))
        body_str = self._json_dumps(json_body) if json_body is not None else ""
        qs = ""
        if params:
            norm = {str(k): "" if v is None else str(v) for k, v in dict(params).items()}
            qs = urlencode(sorted(norm.items()), doseq=True)
        sign = self._sign(method=m, url=path, query_string=qs, body_str=body_str, ts=ts)
        code, data, text = self._request(m, path, params=params, data=body_str if body_str else None, headers=self._headers(ts, sign))
        if code >= 400:
            raise LiveTradingError(f"Gate HTTP {code}: {text[:500]}")
        return data

    def _public_request(self, method: str, path: str, *, params: Optional[Dict[str, Any]] = None) -> Any:
        code, data, text = self._request(method, path, params=params, headers=None, json_body=None, data=None)
        if code >= 400:
            raise LiveTradingError(f"Gate HTTP {code}: {text[:500]}")
        return data


class GateSpotClient(_GateBase):
    def ping(self) -> bool:
        try:
            _ = self._public_request("GET", "/api/v4/spot/time")
            return True
        except Exception:
            return False

    def get_accounts(self) -> Any:
        return self._signed_request("GET", "/api/v4/spot/accounts")

    def place_limit_order(self, *, symbol: str, side: str, size: float, price: float, client_order_id: Optional[str] = None) -> LiveOrderResult:
        sd = (side or "").strip().lower()
        if sd not in ("buy", "sell"):
            raise LiveTradingError(f"Invalid side: {side}")
        qty = float(size or 0.0)
        px = float(price or 0.0)
        if qty <= 0 or px <= 0:
            raise LiveTradingError("Invalid size/price")
        body: Dict[str, Any] = {
            "currency_pair": to_gate_currency_pair(symbol),
            "side": sd,
            "type": "limit",
            "amount": str(qty),
            "price": str(px),
            "time_in_force": "gtc",
        }
        if client_order_id:
            body["text"] = str(client_order_id)
        raw = self._signed_request("POST", "/api/v4/spot/orders", json_body=body)
        oid = str(raw.get("id") or "") if isinstance(raw, dict) else ""
        return LiveOrderResult(exchange_id="gate", exchange_order_id=oid, filled=0.0, avg_price=0.0, raw=raw if isinstance(raw, dict) else {"raw": raw})

    def place_market_order(self, *, symbol: str, side: str, size: float, client_order_id: Optional[str] = None) -> LiveOrderResult:
        sd = (side or "").strip().lower()
        if sd not in ("buy", "sell"):
            raise LiveTradingError(f"Invalid side: {side}")
        qty = float(size or 0.0)
        if qty <= 0:
            raise LiveTradingError("Invalid size")
        body: Dict[str, Any] = {
            "currency_pair": to_gate_currency_pair(symbol),
            "side": sd,
            "type": "market",
            "amount": str(qty),
        }
        if client_order_id:
            body["text"] = str(client_order_id)
        raw = self._signed_request("POST", "/api/v4/spot/orders", json_body=body)
        oid = str(raw.get("id") or "") if isinstance(raw, dict) else ""
        return LiveOrderResult(exchange_id="gate", exchange_order_id=oid, filled=0.0, avg_price=0.0, raw=raw if isinstance(raw, dict) else {"raw": raw})

    def cancel_order(self, *, order_id: str) -> Any:
        if not order_id:
            raise LiveTradingError("Gate spot cancel_order requires order_id")
        return self._signed_request("DELETE", f"/api/v4/spot/orders/{str(order_id)}")

    def get_order(self, *, order_id: str) -> Any:
        if not order_id:
            raise LiveTradingError("Gate spot get_order requires order_id")
        return self._signed_request("GET", f"/api/v4/spot/orders/{str(order_id)}")

    def wait_for_fill(self, *, order_id: str, max_wait_sec: float = 10.0, poll_interval_sec: float = 0.5) -> Dict[str, Any]:
        end_ts = time.time() + float(max_wait_sec or 0.0)
        last: Dict[str, Any] = {}
        while True:
            try:
                resp = self.get_order(order_id=str(order_id))
                last = resp if isinstance(resp, dict) else {"raw": resp}
            except Exception:
                last = last or {}
            status = str(last.get("status") or "")
            filled = 0.0
            avg_price = 0.0
            fee = 0.0
            fee_ccy = ""
            try:
                filled = float(last.get("filled_amount") or 0.0)
            except Exception:
                filled = 0.0
            try:
                filled_total = float(last.get("filled_total") or 0.0)
                if filled > 0 and filled_total > 0:
                    avg_price = filled_total / filled
            except Exception:
                avg_price = 0.0
            # Extract fee from Gate API
            try:
                fee = abs(float(last.get("fee") or 0.0))
            except Exception:
                fee = 0.0
            fee_ccy = str(last.get("fee_currency") or "").strip()
            if filled > 0 and avg_price > 0:
                return {"filled": filled, "avg_price": avg_price, "fee": fee, "fee_ccy": fee_ccy, "status": status, "order": last}
            if status.lower() in ("closed", "cancelled", "canceled"):
                return {"filled": filled, "avg_price": avg_price, "fee": fee, "fee_ccy": fee_ccy, "status": status, "order": last}
            if time.time() >= end_ts:
                return {"filled": filled, "avg_price": avg_price, "fee": fee, "fee_ccy": fee_ccy, "status": status, "order": last}
            time.sleep(float(poll_interval_sec or 0.5))


class GateUsdtFuturesClient(_GateBase):
    def __init__(self, *, api_key: str, secret_key: str, base_url: str = "https://api.gateio.ws", timeout_sec: float = 15.0):
        super().__init__(api_key=api_key, secret_key=secret_key, base_url=base_url, timeout_sec=timeout_sec)
        # Best-effort cache for contract metadata to convert base qty -> contracts.
        self._contract_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
        self._contract_cache_ttl_sec = 300.0

    @staticmethod
    def _to_dec(x: Any) -> Decimal:
        try:
            return Decimal(str(x))
        except Exception:
            return Decimal("0")

    @staticmethod
    def _floor(value: Decimal) -> Decimal:
        try:
            return value.to_integral_value(rounding=ROUND_DOWN)
        except Exception:
            return Decimal("0")

    def ping(self) -> bool:
        try:
            _ = self._public_request("GET", "/api/v4/futures/usdt/time")
            return True
        except Exception:
            return False

    def get_contract(self, *, contract: str) -> Dict[str, Any]:
        c = str(contract or "").strip()
        if not c:
            return {}
        now = time.time()
        cached = self._contract_cache.get(c)
        if cached:
            ts, obj = cached
            if obj and (now - float(ts or 0.0)) <= float(self._contract_cache_ttl_sec or 300.0):
                return obj
        raw = self._public_request("GET", f"/api/v4/futures/usdt/contracts/{c}")
        obj = raw if isinstance(raw, dict) else {}
        if obj:
            self._contract_cache[c] = (now, obj)
        return obj

    def _base_to_contracts(self, *, contract: str, base_size: float) -> int:
        req = self._to_dec(base_size)
        if req <= 0:
            return 0
        meta: Dict[str, Any] = {}
        try:
            meta = self.get_contract(contract=contract) or {}
        except Exception:
            meta = {}
        qm = self._to_dec(meta.get("quanto_multiplier") or meta.get("quantoMultiplier") or meta.get("contract_size") or meta.get("contractSize") or "0")
        if qm <= 0:
            # Fallback: 1 contract ~= 1 base unit (best-effort)
            qm = Decimal("1")
        contracts = req / qm
        return int(self._floor(contracts))

    def get_accounts(self) -> Any:
        return self._signed_request("GET", "/api/v4/futures/usdt/accounts")

    def get_positions(self) -> Any:
        return self._signed_request("GET", "/api/v4/futures/usdt/positions")

    def set_leverage(self, *, contract: str, leverage: float) -> bool:
        c = str(contract or "").strip()
        if not c:
            return False
        try:
            lv = int(float(leverage or 1.0))
        except Exception:
            lv = 1
        if lv < 1:
            lv = 1
        try:
            _ = self._signed_request("POST", f"/api/v4/futures/usdt/positions/{c}/leverage", json_body={"leverage": str(lv)})
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
        sd = (side or "").strip().lower()
        if sd not in ("buy", "sell"):
            raise LiveTradingError(f"Invalid side: {side}")
        contract = to_gate_currency_pair(symbol)
        csz = self._base_to_contracts(contract=contract, base_size=float(size or 0.0))
        if csz <= 0:
            raise LiveTradingError("Invalid size (converted contracts <= 0)")
        signed_size = int(csz) if sd == "buy" else -int(csz)
        body: Dict[str, Any] = {"contract": contract, "size": signed_size, "price": "0", "tif": "ioc"}
        if reduce_only:
            body["reduce_only"] = True
        if client_order_id:
            body["text"] = str(client_order_id)
        raw = self._signed_request("POST", "/api/v4/futures/usdt/orders", json_body=body)
        oid = str(raw.get("id") or "") if isinstance(raw, dict) else ""
        return LiveOrderResult(exchange_id="gate", exchange_order_id=oid, filled=0.0, avg_price=0.0, raw=raw if isinstance(raw, dict) else {"raw": raw})

    def place_limit_order(
        self,
        *,
        symbol: str,
        side: str,
        size: float,
        price: float,
        reduce_only: bool = False,
        client_order_id: Optional[str] = None,
    ) -> LiveOrderResult:
        sd = (side or "").strip().lower()
        if sd not in ("buy", "sell"):
            raise LiveTradingError(f"Invalid side: {side}")
        contract = to_gate_currency_pair(symbol)
        csz = self._base_to_contracts(contract=contract, base_size=float(size or 0.0))
        if csz <= 0:
            raise LiveTradingError("Invalid size (converted contracts <= 0)")
        px = float(price or 0.0)
        if px <= 0:
            raise LiveTradingError("Invalid price")
        signed_size = int(csz) if sd == "buy" else -int(csz)
        body: Dict[str, Any] = {"contract": contract, "size": signed_size, "price": str(px), "tif": "gtc"}
        if reduce_only:
            body["reduce_only"] = True
        if client_order_id:
            body["text"] = str(client_order_id)
        raw = self._signed_request("POST", "/api/v4/futures/usdt/orders", json_body=body)
        oid = str(raw.get("id") or "") if isinstance(raw, dict) else ""
        return LiveOrderResult(exchange_id="gate", exchange_order_id=oid, filled=0.0, avg_price=0.0, raw=raw if isinstance(raw, dict) else {"raw": raw})

    def cancel_order(self, *, order_id: str) -> Any:
        if not order_id:
            raise LiveTradingError("Gate futures cancel_order requires order_id")
        return self._signed_request("DELETE", f"/api/v4/futures/usdt/orders/{str(order_id)}")

    def get_order(self, *, order_id: str) -> Any:
        if not order_id:
            raise LiveTradingError("Gate futures get_order requires order_id")
        return self._signed_request("GET", f"/api/v4/futures/usdt/orders/{str(order_id)}")

    def wait_for_fill(self, *, order_id: str, contract: str, max_wait_sec: float = 3.0, poll_interval_sec: float = 0.5) -> Dict[str, Any]:
        end_ts = time.time() + float(max_wait_sec or 0.0)
        last: Dict[str, Any] = {}
        qm = Decimal("1")
        try:
            meta = self.get_contract(contract=str(contract)) or {}
            qm = self._to_dec(meta.get("quanto_multiplier") or meta.get("contract_size") or "1")
            if qm <= 0:
                qm = Decimal("1")
        except Exception:
            qm = Decimal("1")
        while True:
            try:
                resp = self.get_order(order_id=str(order_id))
                last = resp if isinstance(resp, dict) else {"raw": resp}
            except Exception:
                last = last or {}
            status = str(last.get("status") or "")
            filled = 0.0
            avg_price = 0.0
            fee = 0.0
            fee_ccy = ""
            try:
                # Gate futures often returns "filled_size" in contracts.
                filled_ct = abs(float(last.get("filled_size") or last.get("filledSize") or 0.0))
                filled = float(Decimal(str(filled_ct)) * qm)
            except Exception:
                filled = 0.0
            try:
                avg_price = float(last.get("fill_price") or last.get("fillPrice") or last.get("price") or 0.0)
            except Exception:
                avg_price = 0.0
            # Extract fee from Gate Futures API
            try:
                fee = abs(float(last.get("fee") or 0.0))
            except Exception:
                fee = 0.0
            # Gate USDT futures fees are in USDT
            if fee > 0:
                fee_ccy = "USDT"
            if filled > 0 and avg_price > 0:
                return {"filled": filled, "avg_price": avg_price, "fee": fee, "fee_ccy": fee_ccy, "status": status, "order": last}
            if str(status).lower() in ("finished", "cancelled", "canceled"):
                return {"filled": filled, "avg_price": avg_price, "fee": fee, "fee_ccy": fee_ccy, "status": status, "order": last}
            if time.time() >= end_ts:
                return {"filled": filled, "avg_price": avg_price, "fee": fee, "fee_ccy": fee_ccy, "status": status, "order": last}
            time.sleep(float(poll_interval_sec or 0.5))


