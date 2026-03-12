"""
Base REST client helpers for direct exchange connections.

Notes:
- Keep this minimal and dependency-light (requests only).
- All secrets must be excluded from logs.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import requests


@dataclass
class LiveOrderResult:
    exchange_id: str
    exchange_order_id: str
    filled: float
    avg_price: float
    raw: Dict[str, Any]


class LiveTradingError(Exception):
    pass


class BaseRestClient:
    def __init__(self, base_url: str, timeout_sec: float = 15.0):
        self.base_url = (base_url or "").rstrip("/")
        self.timeout_sec = float(timeout_sec)

    def _url(self, path: str) -> str:
        p = str(path or "")
        if not p.startswith("/"):
            p = "/" + p
        return f"{self.base_url}{p}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        data: Optional[Any] = None,
    ) -> Tuple[int, Dict[str, Any], str]:
        url = self._url(path)
        resp = requests.request(
            method=str(method or "GET").upper(),
            url=url,
            params=params or None,
            json=json_body if json_body is not None else None,
            data=data,
            headers=headers or None,
            timeout=self.timeout_sec,
        )
        text = resp.text or ""
        parsed: Dict[str, Any] = {}
        try:
            parsed = resp.json() if text else {}
        except Exception:
            parsed = {"raw_text": text[:2000]}
        return int(resp.status_code), parsed, text

    @staticmethod
    def _now_ms() -> int:
        return int(time.time() * 1000)

    @staticmethod
    def _json_dumps(obj: Any) -> str:
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


