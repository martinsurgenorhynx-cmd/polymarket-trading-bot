"""
Local simulation for TradingExecutor.

Goal:
- Create one indicator strategy using `indicator_python_code/code_test.py`
- Inject deterministic K-lines and a deterministic tick-price sequence
- Run TradingExecutor for a short period
- Verify orders are enqueued into PostgreSQL table `pending_orders`

Notes:
- This is a local-only test helper. It does NOT talk to real exchanges.
- We intentionally shorten tick interval to speed up the simulation.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


def _ensure_backend_on_syspath() -> None:
    """
    Ensure `backend_api_python/` is on sys.path so `import app...` works
    no matter where the script is executed from.
    """
    backend_root = Path(__file__).resolve().parents[1]
    p = str(backend_root)
    if p not in sys.path:
        sys.path.insert(0, p)


_ensure_backend_on_syspath()

from app.services.trading_executor import TradingExecutor  # noqa: E402
from app.utils.db import get_db_connection  # noqa: E402


def _repo_root() -> Path:
    # backend_api_python/scripts/ -> backend_api_python/
    return Path(__file__).resolve().parents[1]


def _read_indicator_code() -> str:
    # Use the user's current indicator script under repo root.
    root = _repo_root().parent  # project root (quantdinger/)
    p = root / "indicator_python_code" / "code_test.py"
    return p.read_text(encoding="utf-8")


def _make_klines_1m(base: float = 3000.0, n: int = 200) -> List[Dict[str, Any]]:
    """
    Generate synthetic 1m klines to allow SuperTrend to produce buy/sell signals.
    We use a downtrend then an uptrend to force a trend flip.
    """
    now = int(time.time())
    start = now - n * 60

    klines: List[Dict[str, Any]] = []
    price = float(base)
    for i in range(n):
        ts = start + i * 60

        # Down for first part, then up for second part.
        if i < int(n * 0.45):
            price *= 0.996  # -0.4% per bar
        else:
            price *= 1.008  # +0.8% per bar

        o = price * 0.999
        c = price
        h = max(o, c) * 1.0005
        l = min(o, c) * 0.9995
        klines.append(
            {
                "time": int(ts),
                "open": float(o),
                "high": float(h),
                "low": float(l),
                "close": float(c),
                "volume": 1.0,
            }
        )
    return klines


def _count_signals_for_klines(
    ex: TradingExecutor,
    indicator_code: str,
    klines: List[Dict[str, Any]],
    trade_direction: str,
    leverage: int,
    initial_capital: float,
) -> Dict[str, int]:
    df = ex._klines_to_dataframe(klines)
    tc = {
        "trade_direction": trade_direction,
        "leverage": leverage,
        "initial_capital": initial_capital,
    }
    executed_df, _env = ex._execute_indicator_df(indicator_code, df, tc)
    if executed_df is None:
        return {"buy": 0, "sell": 0}
    buy = int(executed_df.get("buy", False).fillna(False).astype(bool).sum()) if "buy" in executed_df.columns else 0
    sell = int(executed_df.get("sell", False).fillna(False).astype(bool).sum()) if "sell" in executed_df.columns else 0
    return {"buy": buy, "sell": sell}


def _trim_klines_to_last_signal(
    ex: TradingExecutor,
    indicator_code: str,
    klines: List[Dict[str, Any]],
    keep_before: int = 220,
    keep_after: int = 0,
) -> List[Dict[str, Any]]:
    """
    Trim klines so the last buy/sell signal falls within the last 1~2 bars,
    which is what TradingExecutor evaluates.
    """
    df = ex._klines_to_dataframe(klines)
    tc = {"trade_direction": "both", "leverage": 5, "initial_capital": 1000.0}
    executed_df, _env = ex._execute_indicator_df(indicator_code, df, tc)
    if executed_df is None or "buy" not in executed_df.columns or "sell" not in executed_df.columns:
        return klines

    buy = executed_df["buy"].fillna(False).astype(bool).values.tolist()
    sell = executed_df["sell"].fillna(False).astype(bool).values.tolist()
    last_idx = -1
    for i in range(len(buy) - 1, -1, -1):
        if buy[i] or sell[i]:
            last_idx = i
            break
    if last_idx < 0:
        return klines

    start = max(0, last_idx - int(keep_before))
    end = min(len(klines), last_idx + 1 + int(keep_after))
    out = klines[start:end]
    if len(out) < 30:
        return klines

    # Rebase timestamps so the last bar is close to "now".
    # Otherwise TradingExecutor will consider signals expired (it compares signal_timestamp vs time.time()).
    try:
        now = int(time.time())
        last_ts = int(out[-1].get("time") or 0)
        if last_ts > 0:
            shift = (now - 60) - last_ts  # keep last candle near current time
            for row in out:
                row["time"] = int(row.get("time") or 0) + int(shift)
    except Exception:
        pass

    return out


def _find_klines_with_signal(ex: TradingExecutor, indicator_code: str) -> List[Dict[str, Any]]:
    """
    Try a few synthetic patterns until SuperTrend produces at least one buy/sell.
    This makes the simulation deterministic.
    """
    patterns = [
        # (down_mult, up_mult, split_ratio)
        (0.998, 1.004, 0.45),
        (0.996, 1.008, 0.45),
        (0.994, 1.012, 0.50),
        (0.992, 1.015, 0.55),
        (0.990, 1.020, 0.60),
    ]
    for down_mult, up_mult, split in patterns:
        kl = _make_klines_1m(base=3000.0, n=260)
        # Rewrite using the requested multipliers (keep timestamps).
        price = 3000.0
        for i, row in enumerate(kl):
            if i < int(len(kl) * split):
                price *= float(down_mult)
            else:
                price *= float(up_mult)
            o = price * 0.999
            c = price
            h = max(o, c) * 1.0005
            l = min(o, c) * 0.9995
            row["open"] = float(o)
            row["high"] = float(h)
            row["low"] = float(l)
            row["close"] = float(c)

        cnt = _count_signals_for_klines(ex, indicator_code, kl, "both", 5, 1000.0)
        if cnt["buy"] > 0 or cnt["sell"] > 0:
            kl2 = _trim_klines_to_last_signal(ex, indicator_code, kl, keep_before=220, keep_after=0)
            cnt2 = _count_signals_for_klines(ex, indicator_code, kl2, "both", 5, 1000.0)
            print(f"[OK] Found signals with pattern down={down_mult}, up={up_mult}, split={split}: {cnt} -> trimmed={cnt2}, bars={len(kl2)}")
            return kl2
        print(f"[MISS] Pattern down={down_mult}, up={up_mult}, split={split}: {cnt}")

    print("[WARN] No buy/sell signals found in tested patterns; falling back to default klines.")
    return _make_klines_1m(base=3000.0, n=260)


def _insert_strategy(
    *,
    symbol: str,
    indicator_code: str,
    initial_capital: float,
    leverage: int,
    trade_direction: str,
    timeframe: str,
    stop_loss_pct: float,
    take_profit_pct: float,
    trailing_enabled: bool,
    trailing_activation_pct: float,
    trailing_stop_pct: float,
) -> int:
    """
    Insert one strategy row into qd_strategies_trading and return its id.
    """
    now = int(time.time())
    trading_config = {
        "symbol": symbol,
        "initial_capital": float(initial_capital),
        "leverage": int(leverage),
        "trade_direction": str(trade_direction),
        "timeframe": str(timeframe),
        "market_type": "swap",
        # Make entries deterministic in this simulation.
        "entry_trigger_mode": "immediate",
        "exit_trigger_mode": "immediate",
        # Aggressive = allow current candle signals. This makes simulation deterministic.
        "signal_mode": "aggressive",
        "exit_signal_mode": "aggressive",
        # Risk params (config-driven exits)
        "stop_loss_pct": float(stop_loss_pct),
        "take_profit_pct": float(take_profit_pct),
        "trailing_enabled": bool(trailing_enabled),
        "trailing_activation_pct": float(trailing_activation_pct),
        "trailing_stop_pct": float(trailing_stop_pct),
        # Position sizing
        "entry_pct": 1.0,
    }
    indicator_config = {
        "indicator_id": 1,
        "indicator_name": "code_test.py",
        "indicator_code": indicator_code,
    }

    with get_db_connection() as db:
        cur = db.cursor()
        cur.execute(
            """
            INSERT INTO qd_strategies_trading
            (strategy_name, strategy_type, market_category, execution_mode, notification_config,
             status, symbol, timeframe, initial_capital, leverage, market_type,
             exchange_config, indicator_config, trading_config, ai_model_config, decide_interval,
             created_at, updated_at)
            VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "SIM_ETH_1m",
                "IndicatorStrategy",
                "Crypto",
                "signal",
                json.dumps({"channels": ["webhook"]}, ensure_ascii=False),
                "running",
                symbol,
                timeframe,
                float(initial_capital),
                int(leverage),
                "swap",
                json.dumps({}, ensure_ascii=False),
                json.dumps(indicator_config, ensure_ascii=False),
                json.dumps(trading_config, ensure_ascii=False),
                json.dumps({}, ensure_ascii=False),
                300,
                now,
                now,
            ),
        )
        sid = int(cur.lastrowid)
        db.commit()
        cur.close()
    return sid


class _SimPriceFeed:
    def __init__(self, prices: List[float]):
        self._prices = list(prices)
        self._idx = 0

    def next(self) -> float:
        if not self._prices:
            return 0.0
        if self._idx >= len(self._prices):
            return float(self._prices[-1])
        p = float(self._prices[self._idx])
        self._idx += 1
        return p


def main() -> None:
    # Speed up: 1s tick in simulation (logic is identical to 10s tick).
    os.environ.setdefault("STRATEGY_TICK_INTERVAL_SEC", "1")
    # Disable in-memory price cache so each tick uses next simulated price.
    os.environ.setdefault("PRICE_CACHE_TTL_SEC", "0")

    indicator_code = _read_indicator_code()

    ex = TradingExecutor()
    klines = _find_klines_with_signal(ex, indicator_code)

    # Your requested config (note: risk percentages are margin-based, executor divides by leverage).
    strategy_id = _insert_strategy(
        symbol="ETH/USDT",
        indicator_code=indicator_code,
        initial_capital=1000.0,
        leverage=5,
        trade_direction="both",
        timeframe="1m",
        stop_loss_pct=0.02,  # 2%
        take_profit_pct=0.0,
        trailing_enabled=True,
        trailing_activation_pct=0.04,  # 4%
        trailing_stop_pct=0.01,  # 1%
    )

    # Build a price path that triggers trailing:
    # - start near last close
    # - move up enough to activate trailing (activation is divided by leverage in executor)
    # - then pull back enough to hit trailing stop
    last_close = float(klines[-1]["close"])
    up = last_close * 1.02  # +2% (enough to activate when leverage=5)
    high = last_close * 1.03
    pullback = high * (1 - 0.004)  # -0.4% from high (enough to hit trailing when leverage=5)

    prices = [
        last_close,
        last_close * 1.005,
        last_close * 1.01,
        up,
        high,
        high * 0.999,
        pullback,
        pullback * 0.999,
    ]
    feed = _SimPriceFeed(prices)

    # Monkeypatch market data methods (no network).
    ex._fetch_latest_kline = lambda _symbol, _tf, limit=500: klines  # type: ignore[assignment]
    ex._fetch_current_price = lambda _exchange, _symbol, market_type=None: feed.next()  # type: ignore[assignment]

    ok = ex.start_strategy(strategy_id)
    if not ok:
        raise SystemExit("Failed to start strategy thread")

    # Let it run a few ticks.
    time.sleep(10)

    # Stop strategy by updating DB status.
    with get_db_connection() as db:
        cur = db.cursor()
        cur.execute("UPDATE qd_strategies_trading SET status = 'stopped' WHERE id = ?", (strategy_id,))
        db.commit()
        cur.close()

    # Wait for thread to exit.
    time.sleep(2)

    # Print pending orders.
    with get_db_connection() as db:
        cur = db.cursor()
        cur.execute(
            """
            SELECT id, strategy_id, symbol, signal_type, amount, price, status, created_at
            FROM pending_orders
            WHERE strategy_id = ?
            ORDER BY id ASC
            """,
            (strategy_id,),
        )
        rows = cur.fetchall() or []
        cur.close()

    print(f"strategy_id={strategy_id}, pending_orders={len(rows)}")
    for r in rows:
        print(r)


if __name__ == "__main__":
    main()


