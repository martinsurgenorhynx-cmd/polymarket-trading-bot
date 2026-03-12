"""
Exchange execution helpers (local deployment).

This module provides helpers for resolving exchange configs and safe logging.

Notes:
- In paper mode, the system only enqueues signals into `pending_orders`.
- Real trading execution is intentionally not implemented here.
"""

from __future__ import annotations

import json
from typing import Any, Dict

from app.utils.db import get_db_connection
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _safe_json_loads(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str):
        return default
    s = value.strip()
    if not s:
        return default
    try:
        return json.loads(s)
    except Exception:
        return default


def mask_secret(s: str, keep: int = 4) -> str:
    """Return a masked representation of a secret for safe logs."""
    if not s:
        return ""
    s = str(s)
    if len(s) <= keep * 2:
        return s[: max(1, keep)] + "***"
    return f"{s[:keep]}...{s[-keep:]}"


def safe_exchange_config_for_log(cfg: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(cfg, dict):
        return {}
    out = dict(cfg)
    for k in ["api_key", "secret_key", "passphrase", "apiKey", "secret", "password"]:
        if k in out and out.get(k):
            out[k] = mask_secret(str(out.get(k)))
    return out


def load_strategy_configs(strategy_id: int) -> Dict[str, Any]:
    """Load strategy config fields needed for live execution."""
    with get_db_connection() as db:
        cur = db.cursor()
        cur.execute(
            """
            SELECT id, user_id, exchange_config, trading_config, market_type, leverage, execution_mode, market_category
            FROM qd_strategies_trading
            WHERE id = %s
            """,
            (int(strategy_id),),
        )
        row = cur.fetchone() or {}
        cur.close()

    exchange_config = _safe_json_loads(row.get("exchange_config"), {})
    trading_config = _safe_json_loads(row.get("trading_config"), {})

    market_type = (row.get("market_type") or exchange_config.get("market_type") or "swap").strip()
    leverage = float(row.get("leverage") or trading_config.get("leverage") or exchange_config.get("leverage") or 1.0)
    execution_mode = (row.get("execution_mode") or "signal").strip().lower()
    market_category = (row.get("market_category") or "Crypto").strip()
    user_id = int(row.get("user_id") or 1)

    return {
        "strategy_id": int(strategy_id),
        "user_id": user_id,
        "exchange_config": exchange_config if isinstance(exchange_config, dict) else {},
        "trading_config": trading_config if isinstance(trading_config, dict) else {},
        "market_type": market_type,
        "leverage": leverage,
        "execution_mode": execution_mode,
        "market_category": market_category,
    }


def _load_credential_config(credential_id: int, user_id: int = 1) -> Dict[str, Any]:
    """Load credential JSON from qd_exchange_credentials (plaintext in local mode)."""
    with get_db_connection() as db:
        cur = db.cursor()
        cur.execute(
            """
            SELECT encrypted_config
            FROM qd_exchange_credentials
            WHERE id = %s AND user_id = %s
            """,
            (int(credential_id), int(user_id)),
        )
        row = cur.fetchone() or {}
        cur.close()
    return _safe_json_loads(row.get("encrypted_config"), {}) or {}


def resolve_exchange_config(exchange_config: Dict[str, Any], user_id: int = 1) -> Dict[str, Any]:
    """
    Resolve exchange config.

    Supports:
    - direct inline config: {exchange_id, api_key, secret_key, passphrase?}
    - credential reference: {credential_id: 123, ...overrides}
    """
    if not isinstance(exchange_config, dict):
        return {}

    merged: Dict[str, Any] = {}
    credential_id = exchange_config.get("credential_id") or exchange_config.get("credentials_id")
    try:
        if credential_id:
            base = _load_credential_config(int(credential_id), user_id=user_id)
            if isinstance(base, dict):
                merged.update(base)
    except Exception as e:
        logger.warning(f"Failed to load credential_id={credential_id}: {e}")

    # Overlay strategy-level settings (non-empty wins)
    for k, v in exchange_config.items():
        if v is None:
            continue
        if isinstance(v, str) and not v.strip():
            continue
        merged[k] = v

    return merged


