"""
DB helpers for recording live trades and maintaining local position snapshots.

Important:
- This is a local DB snapshot, not the source of truth (exchange is).
- We keep it best-effort to support UI display and strategy state.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional, Tuple

from app.utils.db import get_db_connection


def _get_user_id_from_strategy(strategy_id: int) -> int:
    """Get user_id from strategy table. Defaults to 1 if not found."""
    try:
        with get_db_connection() as db:
            cur = db.cursor()
            cur.execute("SELECT user_id FROM qd_strategies_trading WHERE id = %s", (strategy_id,))
            row = cur.fetchone()
            cur.close()
        return int((row or {}).get('user_id') or 1)
    except Exception:
        return 1


def record_trade(
    *,
    strategy_id: int,
    symbol: str,
    trade_type: str,
    price: float,
    amount: float,
    commission: float = 0.0,
    commission_ccy: str = "",
    profit: Optional[float] = None,
    user_id: int = None,
) -> None:
    value = float(amount or 0.0) * float(price or 0.0)
    if user_id is None:
        user_id = _get_user_id_from_strategy(strategy_id)
    with get_db_connection() as db:
        cur = db.cursor()
        cur.execute(
            """
            INSERT INTO qd_strategy_trades
            (user_id, strategy_id, symbol, type, price, amount, value, commission, commission_ccy, profit, created_at)
            VALUES
            (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            """,
            (
                int(user_id),
                int(strategy_id),
                str(symbol),
                str(trade_type),
                float(price or 0.0),
                float(amount or 0.0),
                float(value),
                float(commission or 0.0),
                str(commission_ccy or ""),
                profit,
            ),
        )
        db.commit()
        cur.close()


def _fetch_position(strategy_id: int, symbol: str, side: str) -> Dict[str, Any]:
    with get_db_connection() as db:
        cur = db.cursor()
        cur.execute(
            "SELECT * FROM qd_strategy_positions WHERE strategy_id = %s AND symbol = %s AND side = %s",
            (int(strategy_id), str(symbol), str(side)),
        )
        row = cur.fetchone() or {}
        cur.close()
    return row if isinstance(row, dict) else {}


def _delete_position(strategy_id: int, symbol: str, side: str) -> None:
    with get_db_connection() as db:
        cur = db.cursor()
        cur.execute(
            "DELETE FROM qd_strategy_positions WHERE strategy_id = %s AND symbol = %s AND side = %s",
            (int(strategy_id), str(symbol), str(side)),
        )
        db.commit()
        cur.close()


def upsert_position(
    *,
    strategy_id: int,
    symbol: str,
    side: str,
    size: float,
    entry_price: float,
    current_price: float,
    highest_price: float = 0.0,
    lowest_price: float = 0.0,
    user_id: int = None,
) -> None:
    if user_id is None:
        user_id = _get_user_id_from_strategy(strategy_id)
    with get_db_connection() as db:
        cur = db.cursor()
        cur.execute(
            """
            INSERT INTO qd_strategy_positions
            (user_id, strategy_id, symbol, side, size, entry_price, current_price, highest_price, lowest_price, updated_at)
            VALUES
            (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT(strategy_id, symbol, side) DO UPDATE SET
                size = excluded.size,
                entry_price = excluded.entry_price,
                current_price = excluded.current_price,
                highest_price = CASE WHEN excluded.highest_price > 0 THEN excluded.highest_price ELSE qd_strategy_positions.highest_price END,
                lowest_price = CASE WHEN excluded.lowest_price > 0 THEN excluded.lowest_price ELSE qd_strategy_positions.lowest_price END,
                updated_at = NOW()
            """,
            (int(user_id), int(strategy_id), str(symbol), str(side), float(size or 0.0), float(entry_price or 0.0), float(current_price or 0.0), float(highest_price or 0.0), float(lowest_price or 0.0)),
        )
        db.commit()
        cur.close()


def apply_fill_to_local_position(
    *,
    strategy_id: int,
    symbol: str,
    signal_type: str,
    filled: float,
    avg_price: float,
) -> Tuple[Optional[float], Optional[Dict[str, Any]]]:
    """
    Apply a fill to the local position snapshot.

    Returns (profit, updated_position_row_or_none)
    - profit is only calculated on close/reduce fills (best-effort, based on local entry_price).
    """
    sig = (signal_type or "").strip().lower()
    filled_qty = float(filled or 0.0)
    px = float(avg_price or 0.0)
    if filled_qty <= 0 or px <= 0:
        return None, None

    if "long" in sig:
        side = "long"
    elif "short" in sig:
        side = "short"
    else:
        return None, None

    is_open = sig.startswith("open_") or sig.startswith("add_")
    is_close = sig.startswith("close_") or sig.startswith("reduce_")

    current = _fetch_position(strategy_id, symbol, side)
    cur_size = float(current.get("size") or 0.0)
    cur_entry = float(current.get("entry_price") or 0.0)
    cur_high = float(current.get("highest_price") or 0.0)
    cur_low = float(current.get("lowest_price") or 0.0)

    profit: Optional[float] = None

    if is_open:
        new_size = cur_size + filled_qty
        if new_size <= 0:
            return None, None
        # Weighted average entry.
        if cur_size > 0 and cur_entry > 0:
            new_entry = (cur_size * cur_entry + filled_qty * px) / new_size
        else:
            new_entry = px
        new_high = max(cur_high or px, px)
        new_low = min(cur_low or px, px)
        upsert_position(
            strategy_id=strategy_id,
            symbol=symbol,
            side=side,
            size=new_size,
            entry_price=new_entry,
            current_price=px,
            highest_price=new_high,
            lowest_price=new_low,
        )
        return None, _fetch_position(strategy_id, symbol, side)

    if is_close:
        # Calculate PnL using local entry price.
        if cur_size > 0 and cur_entry > 0:
            close_qty = min(cur_size, filled_qty)
            if side == "long":
                profit = (px - cur_entry) * close_qty
            else:
                profit = (cur_entry - px) * close_qty

        new_size = cur_size - filled_qty
        if new_size <= 0:
            _delete_position(strategy_id, symbol, side)
            return profit, None
        # Keep entry price for remaining position.
        new_high = max(cur_high or px, px)
        new_low = min(cur_low or px, px)
        upsert_position(
            strategy_id=strategy_id,
            symbol=symbol,
            side=side,
            size=new_size,
            entry_price=cur_entry if cur_entry > 0 else px,
            current_price=px,
            highest_price=new_high,
            lowest_price=new_low,
        )
        return profit, _fetch_position(strategy_id, symbol, side)

    return None, None


