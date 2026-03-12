"""
Quick Trade API — manual / discretionary order placement.

Allows users to place market or limit orders directly from AI analysis
or indicator analysis pages, without creating a strategy first.

Endpoints:
  POST /api/quick-trade/place-order      — Place a quick order
  POST /api/quick-trade/close-position    — Close an existing position
  GET  /api/quick-trade/balance          — Get available balance
  GET  /api/quick-trade/position          — Get current position for symbol
  GET  /api/quick-trade/history          — Get quick trade history
"""

from __future__ import annotations

import json
import time
import traceback
import uuid
from typing import Any, Dict

from flask import Blueprint, g, jsonify, request

from app.utils.db import get_db_connection
from app.utils.logger import get_logger
from app.utils.auth import login_required

logger = get_logger(__name__)

quick_trade_bp = Blueprint('quick_trade', __name__)


# ────────── helpers ──────────

def _convert_usdt_to_base_qty(client, symbol: str, usdt_amount: float, market_type: str, limit_price: float = 0.0) -> float:
    """
    Convert USDT amount to base asset quantity for all exchanges.
    
    This is a unified function that works for all exchanges.
    For spot: converts USDT -> base qty (e.g., 100 USDT -> 0.033 ETH)
    For swap: converts USDT -> base qty (e.g., 100 USDT -> 0.033 ETH), which will then be converted to contracts
    
    Args:
        client: Exchange client instance
        symbol: Trading pair (e.g., "ETH/USDT")
        usdt_amount: USDT amount to convert
        market_type: "spot" or "swap"
        limit_price: For limit orders, use this price if provided (optional)
    
    Returns:
        Base asset quantity
    """
    if usdt_amount <= 0:
        return usdt_amount
    
    try:
        # Try to get current price from exchange
        current_price = 0.0
        
        # For limit orders, use the provided price
        if limit_price > 0:
            current_price = limit_price
            logger.info(f"Using limit price {limit_price} for USDT conversion")
        else:
            # Try to get current market price from exchange
            # OKX
            from app.services.live_trading.okx import OkxClient
            if isinstance(client, OkxClient):
                try:
                    from app.services.live_trading.symbols import to_okx_spot_inst_id, to_okx_swap_inst_id
                    inst_id = to_okx_spot_inst_id(symbol) if market_type == "spot" else to_okx_swap_inst_id(symbol)
                    logger.debug(f"OKX: Getting ticker for inst_id={inst_id}, symbol={symbol}, market_type={market_type}")
                    ticker = client.get_ticker(inst_id=inst_id)
                    if ticker:
                        current_price = float(ticker.get("last") or ticker.get("lastPx") or 0)
                        logger.debug(f"OKX: Got price {current_price} from ticker")
                    else:
                        logger.warning(f"OKX: get_ticker returned empty result for inst_id={inst_id}")
                except AttributeError as e:
                    logger.error(f"OKX: get_ticker method not found: {e}")
                    raise
                except Exception as e:
                    logger.error(f"OKX: Failed to get ticker: {e}")
                    raise
            
            # Binance - try to get price from public API
            from app.services.live_trading.binance import BinanceFuturesClient
            from app.services.live_trading.binance_spot import BinanceSpotClient
            if isinstance(client, (BinanceFuturesClient, BinanceSpotClient)):
                try:
                    # Binance public ticker endpoint
                    base_url = getattr(client, "base_url", "")
                    if "binance" in base_url.lower():
                        import requests
                        if isinstance(client, BinanceFuturesClient):
                            ticker_url = f"{base_url}/fapi/v1/ticker/price"
                        else:
                            ticker_url = f"{base_url}/api/v3/ticker/price"
                        from app.services.live_trading.symbols import to_binance_futures_symbol
                        # Binance spot and futures use the same symbol format
                        sym = to_binance_futures_symbol(symbol)
                        resp = requests.get(ticker_url, params={"symbol": sym}, timeout=5)
                        if resp.status_code == 200:
                            data = resp.json()
                            if isinstance(data, dict):
                                current_price = float(data.get("price") or 0)
                except Exception:
                    pass
            
            # Other exchanges - can be added as needed
            # For exchanges without price API, we'll use a fallback
        
        if current_price > 0:
            base_qty = usdt_amount / current_price
            logger.info(f"Converted USDT amount {usdt_amount} to base qty {base_qty:.8f} using price {current_price} for {symbol}")
            return base_qty
        else:
            # Can't get price - this is critical for quick trade
            # Quick trade always expects USDT input, so we must convert
            logger.error(f"CRITICAL: Could not get price for {symbol} on {type(client).__name__} to convert USDT amount {usdt_amount}")
            logger.error(f"This will cause order to fail. Please check exchange API connectivity or symbol format.")
            # Still return original amount as fallback, but log error
            return usdt_amount
            
    except Exception as e:
        logger.warning(f"Failed to convert USDT amount to base qty: {e}, using original amount")
        return usdt_amount


def _safe_json(v, default=None):
    if v is None:
        return default
    if isinstance(v, (dict, list)):
        return v
    try:
        return json.loads(v) if isinstance(v, str) else default
    except Exception:
        return default


def _load_credential(credential_id: int, user_id: int) -> Dict[str, Any]:
    """Load exchange credential JSON for the given user."""
    with get_db_connection() as db:
        cur = db.cursor()
        cur.execute(
            "SELECT encrypted_config FROM qd_exchange_credentials WHERE id = %s AND user_id = %s",
            (int(credential_id), int(user_id)),
        )
        row = cur.fetchone() or {}
        cur.close()
    return _safe_json(row.get("encrypted_config"), {})


def _build_exchange_config(credential_id: int, user_id: int, overrides: Dict[str, Any] = None) -> Dict[str, Any]:
    """Build exchange config from saved credential + overrides."""
    base = _load_credential(credential_id, user_id)
    if not base:
        raise ValueError("Credential not found or access denied")
    if overrides:
        for k, v in overrides.items():
            if v is not None and (not isinstance(v, str) or v.strip()):
                base[k] = v
    return base


def _create_client(exchange_config: Dict[str, Any], market_type: str = "swap"):
    """Create exchange client from config."""
    from app.services.live_trading.factory import create_client
    return create_client(exchange_config, market_type=market_type)


def _record_quick_trade(
    user_id: int,
    credential_id: int,
    exchange_id: str,
    symbol: str,
    side: str,
    order_type: str,
    amount: float,
    price: float,
    leverage: int,
    market_type: str,
    tp_price: float,
    sl_price: float,
    status: str,
    exchange_order_id: str,
    filled: float,
    avg_price: float,
    error_msg: str,
    source: str,
    raw_result: Dict[str, Any],
):
    """Insert a quick trade record into the database."""
    try:
        with get_db_connection() as db:
            cur = db.cursor()
            cur.execute(
                """
                INSERT INTO qd_quick_trades
                    (user_id, credential_id, exchange_id, symbol, side, order_type,
                     amount, price, leverage, market_type, tp_price, sl_price,
                     status, exchange_order_id, filled_amount, avg_fill_price,
                     error_msg, source, raw_result, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                RETURNING id
                """,
                (
                    user_id, credential_id, exchange_id, symbol, side, order_type,
                    amount, price, leverage, market_type, tp_price, sl_price,
                    status, exchange_order_id, filled, avg_price,
                    error_msg, source, json.dumps(raw_result or {}),
                ),
            )
            row = cur.fetchone()
            db.commit()
            cur.close()
            return (row or {}).get("id")
    except Exception as e:
        logger.error(f"Failed to record quick trade: {e}")
        return None


# ────────── endpoints ──────────

@quick_trade_bp.route('/place-order', methods=['POST'])
@login_required
def place_order():
    """
    Place a quick market or limit order.

    Body JSON:
      credential_id  (int)    — saved exchange credential ID
      symbol         (str)    — e.g. "BTC/USDT"
      side           (str)    — "buy" or "sell"
      order_type     (str)    — "market" or "limit"  (default: market)
      amount         (float)  — USDT amount (always in USDT, will be converted to base qty)
      price          (float)  — limit price (required for limit orders)
      leverage       (int)    — leverage multiplier (default: 1)
                                - leverage = 1: spot market
                                - leverage > 1: swap (perpetual futures) market
      market_type    (str)    — "swap" / "spot" (optional, auto-determined by leverage if not provided)
      tp_price       (float)  — take-profit price (optional, for record only)
      sl_price       (float)  — stop-loss price (optional, for record only)
      source         (str)    — "ai_radar" / "ai_analysis" / "indicator" / "manual"
    """
    try:
        user_id = g.user_id
        body = request.get_json(force=True, silent=True) or {}

        credential_id = int(body.get("credential_id") or 0)
        symbol = str(body.get("symbol") or "").strip()
        side = str(body.get("side") or "").strip().lower()
        order_type = str(body.get("order_type") or "market").strip().lower()
        usdt_amount = float(body.get("amount") or 0)  # Always USDT amount
        price = float(body.get("price") or 0)
        leverage = int(body.get("leverage") or 1)
        market_type = str(body.get("market_type") or "").strip().lower()
        tp_price = float(body.get("tp_price") or 0)
        sl_price = float(body.get("sl_price") or 0)
        source = str(body.get("source") or "manual").strip()

        # ---- validation ----
        if not credential_id:
            return jsonify({"code": 0, "msg": "Missing credential_id"}), 400
        if not symbol:
            return jsonify({"code": 0, "msg": "Missing symbol"}), 400
        if side not in ("buy", "sell"):
            return jsonify({"code": 0, "msg": "side must be 'buy' or 'sell'"}), 400
        if usdt_amount <= 0:
            return jsonify({"code": 0, "msg": "amount must be > 0"}), 400
        if order_type == "limit" and price <= 0:
            return jsonify({"code": 0, "msg": "price required for limit orders"}), 400

        # ---- Auto-determine market_type from leverage ----
        # leverage = 1 -> spot, leverage > 1 -> swap
        if not market_type:
            market_type = "spot" if leverage == 1 else "swap"
        if market_type in ("futures", "future", "perp", "perpetual"):
            market_type = "swap"
        # Override: if leverage > 1, force swap; if leverage = 1, force spot
        if leverage > 1:
            market_type = "swap"
        elif leverage == 1:
            market_type = "spot"

        # ---- build exchange client ----
        exchange_config = _build_exchange_config(credential_id, user_id, {
            "market_type": market_type,
        })
        exchange_id = (exchange_config.get("exchange_id") or "").strip().lower()
        if not exchange_id:
            return jsonify({"code": 0, "msg": "Invalid credential: missing exchange_id"}), 400

        client = _create_client(exchange_config, market_type=market_type)

        # ---- Convert USDT amount to base asset quantity ----
        # Quick trade always accepts USDT amount, convert to base qty for all exchanges
        # For limit orders, use the provided price; for market orders, fetch current price
        limit_price_for_conversion = price if order_type == "limit" and price > 0 else 0.0
        base_qty = _convert_usdt_to_base_qty(client, symbol, usdt_amount, market_type, limit_price_for_conversion)
        
        # Validate conversion: if base_qty equals usdt_amount, conversion likely failed
        # For swap markets, base_qty should be much smaller than usdt_amount (e.g., 100 USDT -> 0.033 ETH)
        if market_type != "spot" and base_qty == usdt_amount and usdt_amount >= 1:
            logger.error(f"USDT conversion may have failed: base_qty ({base_qty}) equals usdt_amount ({usdt_amount})")
            logger.error(f"This suggests the price fetch failed. Order may fail due to insufficient margin.")

        # ---- set leverage (futures only) ----
        if market_type != "spot" and leverage > 1:
            try:
                if hasattr(client, "set_leverage"):
                    from app.services.live_trading.okx import OkxClient
                    from app.services.live_trading.gate import GateUsdtFuturesClient
                    
                    # OKX requires inst_id instead of symbol
                    if isinstance(client, OkxClient):
                        from app.services.live_trading.symbols import to_okx_swap_inst_id
                        inst_id = to_okx_swap_inst_id(symbol)
                        client.set_leverage(inst_id=inst_id, lever=leverage)
                    # Gate requires contract (currency_pair) instead of symbol
                    elif isinstance(client, GateUsdtFuturesClient):
                        from app.services.live_trading.symbols import to_gate_currency_pair
                        contract = to_gate_currency_pair(symbol)
                        client.set_leverage(contract=contract, leverage=leverage)
                    # Most other exchanges use symbol
                    else:
                        # Try common parameter names
                        try:
                            client.set_leverage(symbol=symbol, leverage=leverage)
                        except TypeError:
                            try:
                                client.set_leverage(symbol=symbol, lever=leverage)
                            except TypeError:
                                pass
            except Exception as le:
                logger.warning(f"set_leverage failed (non-fatal): {le}")

        # ---- place order ----
        # Generate client_order_id: OKX clOrdId requirements: 1-32 chars, alphanumeric, underscore, hyphen only
        timestamp_suffix = str(int(time.time()))[-6:]  # Last 6 digits of timestamp
        uuid_suffix = uuid.uuid4().hex[:8]  # 8 hex chars
        client_order_id = f"qt{timestamp_suffix}{uuid_suffix}"  # Total: 2 + 6 + 8 = 16 chars

        result = None
        if order_type == "market":
            # Use execution.py's place_order_from_signal for market orders to ensure consistency
            # Convert side to signal_type: buy -> open_long, sell -> open_short (for swap) or close_long (for spot)
            from app.services.live_trading.execution import place_order_from_signal
            
            if market_type == "spot":
                # Spot: buy = open_long, sell = close_long (assuming we're closing a position)
                signal_type = "open_long" if side == "buy" else "close_long"
            else:
                # Swap: buy = open_long, sell = open_short
                signal_type = "open_long" if side == "buy" else "open_short"
            
            result = place_order_from_signal(
                client=client,
                signal_type=signal_type,
                symbol=symbol,
                amount=base_qty,  # Use converted base qty
                market_type=market_type,
                exchange_config=exchange_config,
                client_order_id=client_order_id,
            )
        else:
            # Limit orders: use direct client call (execution.py doesn't handle limit orders)
            result = client.place_limit_order(
                symbol=symbol,
                side=side.upper() if "binance" in exchange_id else side,
                **_limit_order_kwargs(client, symbol, base_qty, price, side, market_type, client_order_id),
            )

        # ---- extract result ----
        exchange_order_id = str(getattr(result, "exchange_order_id", "") or "")
        filled = float(getattr(result, "filled", 0) or 0)
        avg_fill = float(getattr(result, "avg_price", 0) or 0)
        raw = getattr(result, "raw", {}) or {}

        # ---- record trade ----
        # Record original USDT amount, not converted base qty
        trade_id = _record_quick_trade(
            user_id=user_id,
            credential_id=credential_id,
            exchange_id=exchange_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            amount=usdt_amount,  # Record original USDT amount
            price=price if order_type == "limit" else avg_fill,
            leverage=leverage,
            market_type=market_type,
            tp_price=tp_price,
            sl_price=sl_price,
            status="filled" if filled > 0 else "submitted",
            exchange_order_id=exchange_order_id,
            filled=filled,
            avg_price=avg_fill,
            error_msg="",
            source=source,
            raw_result=raw,
        )

        return jsonify({
            "code": 1,
            "msg": "Order placed successfully",
            "data": {
                "trade_id": trade_id,
                "exchange_order_id": exchange_order_id,
                "filled": filled,
                "avg_price": avg_fill,
                "status": "filled" if filled > 0 else "submitted",
            },
        })

    except Exception as e:
        logger.error(f"quick trade failed: {e}")
        logger.error(traceback.format_exc())

        # Try to record the failure
        try:
            _record_quick_trade(
                user_id=g.user_id,
                credential_id=int(body.get("credential_id") or 0),
                exchange_id="",
                symbol=str(body.get("symbol") or ""),
                side=str(body.get("side") or ""),
                order_type=str(body.get("order_type") or "market"),
                amount=float(body.get("amount") or 0),  # Original USDT amount
                price=0,
                leverage=int(body.get("leverage") or 1),
                market_type=str(body.get("market_type") or "swap"),
                tp_price=0,
                sl_price=0,
                status="failed",
                exchange_order_id="",
                filled=0,
                avg_price=0,
                error_msg=str(e)[:500],
                source=str(body.get("source") or "manual"),
                raw_result={},
            )
        except Exception:
            pass

        return jsonify({"code": 0, "msg": str(e)}), 500


def _market_order_kwargs(client, symbol, amount, side, market_type, client_order_id):
    """Build kwargs compatible with any exchange client's place_market_order."""
    from app.services.live_trading.binance import BinanceFuturesClient
    from app.services.live_trading.binance_spot import BinanceSpotClient
    from app.services.live_trading.okx import OkxClient
    from app.services.live_trading.bitget import BitgetMixClient
    from app.services.live_trading.bybit import BybitClient

    if isinstance(client, (BinanceFuturesClient, BinanceSpotClient)):
        return {"quantity": amount, "client_order_id": client_order_id}
    if isinstance(client, OkxClient):
        kwargs = {"market_type": market_type, "size": amount, "client_order_id": client_order_id}
        # For swap market, OKX requires pos_side. Infer from side:
        # buy -> long, sell -> short
        # The _resolve_pos_side method will handle net_mode vs long_short_mode
        if market_type and market_type.strip().lower() != "spot":
            pos_side = "long" if side.lower() == "buy" else "short"
            kwargs["pos_side"] = pos_side
        return kwargs
    if isinstance(client, BitgetMixClient):
        return {"size": amount, "client_order_id": client_order_id}
    if isinstance(client, BybitClient):
        return {"qty": amount, "client_order_id": client_order_id}
    # Generic fallback
    return {"size": amount, "client_order_id": client_order_id}


def _limit_order_kwargs(client, symbol, amount, price, side, market_type, client_order_id):
    """Build kwargs compatible with any exchange client's place_limit_order."""
    from app.services.live_trading.binance import BinanceFuturesClient
    from app.services.live_trading.binance_spot import BinanceSpotClient
    from app.services.live_trading.okx import OkxClient

    if isinstance(client, (BinanceFuturesClient, BinanceSpotClient)):
        return {"quantity": amount, "price": price, "client_order_id": client_order_id}
    if isinstance(client, OkxClient):
        kwargs = {"market_type": market_type, "size": amount, "price": price, "client_order_id": client_order_id}
        # For swap market, OKX requires pos_side. Infer from side:
        # buy -> long, sell -> short
        # The _resolve_pos_side method will handle net_mode vs long_short_mode
        if market_type and market_type.strip().lower() != "spot":
            pos_side = "long" if side.lower() == "buy" else "short"
            kwargs["pos_side"] = pos_side
        return kwargs
    # Generic fallback
    return {"size": amount, "price": price, "client_order_id": client_order_id}


@quick_trade_bp.route('/balance', methods=['GET'])
@login_required
def get_balance():
    """
    Get available balance from exchange.

    Query: credential_id (int), market_type (str, default "swap")
    """
    try:
        user_id = g.user_id
        credential_id = request.args.get("credential_id", type=int)
        market_type = request.args.get("market_type", "swap").strip().lower()

        if not credential_id:
            return jsonify({"code": 0, "msg": "Missing credential_id"}), 400

        exchange_config = _build_exchange_config(credential_id, user_id, {"market_type": market_type})
        exchange_id = (exchange_config.get("exchange_id") or "").strip().lower()
        client = _create_client(exchange_config, market_type=market_type)

        balance_data = {"available": 0, "total": 0, "currency": "USDT"}

        try:
            if hasattr(client, "get_balance"):
                raw = client.get_balance()
                balance_data = _parse_balance(raw, exchange_id, market_type)
            elif hasattr(client, "get_account"):
                raw = client.get_account()
                balance_data = _parse_balance(raw, exchange_id, market_type)
            elif hasattr(client, "get_accounts"):
                raw = client.get_accounts()
                balance_data = _parse_balance(raw, exchange_id, market_type)
        except Exception as be:
            logger.warning(f"Balance fetch failed: {be}")
            balance_data["error"] = str(be)

        return jsonify({"code": 1, "msg": "success", "data": balance_data})
    except Exception as e:
        logger.error(f"get_balance failed: {e}")
        return jsonify({"code": 0, "msg": str(e)}), 500


def _parse_balance(raw: Any, exchange_id: str, market_type: str) -> Dict[str, Any]:
    """Best-effort parse balance from various exchange responses."""
    result = {"available": 0, "total": 0, "currency": "USDT"}
    if not raw:
        return result
    try:
        if isinstance(raw, dict):
            # Binance futures
            if "availableBalance" in raw:
                result["available"] = float(raw.get("availableBalance") or 0)
                result["total"] = float(raw.get("totalWalletBalance") or raw.get("totalMarginBalance") or 0)
                return result
            # Binance spot
            if "balances" in raw:
                for b in raw.get("balances", []):
                    if str(b.get("asset") or "").upper() == "USDT":
                        result["available"] = float(b.get("free") or 0)
                        result["total"] = float(b.get("free") or 0) + float(b.get("locked") or 0)
                        return result
                return result
            # OKX
            data = raw.get("data")
            if isinstance(data, list) and data:
                first = data[0] if isinstance(data[0], dict) else {}
                # Account balance
                details = first.get("details", [])
                if isinstance(details, list):
                    for d in details:
                        if str(d.get("ccy") or "").upper() == "USDT":
                            result["available"] = float(d.get("availBal") or d.get("availEq") or 0)
                            result["total"] = float(d.get("eq") or d.get("cashBal") or 0)
                            return result
                # Fallback
                result["available"] = float(first.get("availBal") or first.get("totalEq") or 0)
                result["total"] = float(first.get("totalEq") or 0)
                return result
            # Bybit
            if "result" in raw:
                res = raw["result"]
                if isinstance(res, dict):
                    coin_list = res.get("list", [])
                    if isinstance(coin_list, list):
                        for acc in coin_list:
                            coins = acc.get("coin", []) if isinstance(acc, dict) else []
                            for c in coins:
                                if str(c.get("coin") or "").upper() == "USDT":
                                    result["available"] = float(c.get("availableToWithdraw") or c.get("walletBalance") or 0)
                                    result["total"] = float(c.get("walletBalance") or 0)
                                    return result
        # Fallback: try to find any USDT-like values
        if isinstance(raw, dict):
            for k, v in raw.items():
                if "avail" in str(k).lower() and isinstance(v, (int, float)):
                    result["available"] = float(v)
                if "total" in str(k).lower() and isinstance(v, (int, float)):
                    result["total"] = float(v)
    except Exception as e:
        logger.warning(f"_parse_balance error: {e}")
    return result


@quick_trade_bp.route('/position', methods=['GET'])
@login_required
def get_position():
    """
    Get current position for a symbol from exchange.

    Query: credential_id (int), symbol (str), market_type (str)
    """
    try:
        user_id = g.user_id
        credential_id = request.args.get("credential_id", type=int)
        symbol = request.args.get("symbol", "").strip()
        market_type = request.args.get("market_type", "swap").strip().lower()

        if not credential_id or not symbol:
            return jsonify({"code": 0, "msg": "Missing credential_id or symbol"}), 400

        exchange_config = _build_exchange_config(credential_id, user_id, {"market_type": market_type})
        client = _create_client(exchange_config, market_type=market_type)

        positions = []
        try:
            # OKX requires inst_id instead of symbol
            from app.services.live_trading.okx import OkxClient
            if isinstance(client, OkxClient):
                from app.services.live_trading.symbols import to_okx_swap_inst_id, to_okx_spot_inst_id
                if market_type == "spot":
                    inst_id = to_okx_spot_inst_id(symbol)
                    inst_type = "SPOT"
                else:
                    inst_id = to_okx_swap_inst_id(symbol)
                    inst_type = "SWAP"
                raw = client.get_positions(inst_id=inst_id, inst_type=inst_type)
                positions = _parse_positions(raw)
                logger.info(f"OKX positions query: inst_id={inst_id}, inst_type={inst_type}, found {len(positions)} positions")
            elif hasattr(client, "get_positions"):
                raw = client.get_positions(symbol=symbol)
                positions = _parse_positions(raw)
            elif hasattr(client, "get_position"):
                raw = client.get_position(symbol=symbol)
                positions = _parse_positions(raw)
        except Exception as pe:
            logger.warning(f"Position fetch failed: {pe}")
            logger.warning(traceback.format_exc())

        logger.info(f"Returning {len(positions)} positions for symbol={symbol}, market_type={market_type}")
        return jsonify({"code": 1, "msg": "success", "data": {"positions": positions}})
    except Exception as e:
        logger.error(f"get_position failed: {e}")
        return jsonify({"code": 0, "msg": str(e)}), 500


def _parse_positions(raw: Any) -> list:
    """Best-effort parse positions from exchange response."""
    result = []
    if not raw:
        return result
    try:
        items = []
        if isinstance(raw, list):
            items = raw
        elif isinstance(raw, dict):
            data = raw.get("data") or raw.get("result") or raw.get("positions") or []
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                items = data.get("list", []) if "list" in data else [data]

        for item in items:
            if not isinstance(item, dict):
                continue
            # For OKX, position size can be in different fields
            # SWAP: posAmt, pos
            # SPOT: bal (balance), availBal (available balance)
            size = float(item.get("posAmt") or item.get("pos") or item.get("size") or item.get("contracts") or 
                         item.get("bal") or item.get("availBal") or 0)
            if abs(size) < 1e-10:
                continue
            
            # For spot, side is always "long" (you own the asset)
            # For swap, determine side from sign of size
            side = "long"
            if size < 0:
                side = "short"
            elif item.get("posSide"):
                # OKX may have posSide field: "long" or "short"
                pos_side = str(item.get("posSide", "")).strip().lower()
                if pos_side in ("long", "short"):
                    side = pos_side
            
            result.append({
                "symbol": item.get("symbol") or item.get("instId") or "",
                "side": side,
                "size": abs(size),
                "entry_price": float(item.get("entryPrice") or item.get("avgCost") or item.get("avgPx") or item.get("avgPx") or 0),
                "unrealized_pnl": float(item.get("unRealizedProfit") or item.get("upl") or item.get("unrealisedPnl") or item.get("pnl") or 0),
                "leverage": float(item.get("leverage") or item.get("lever") or 1),
                "mark_price": float(item.get("markPrice") or item.get("markPx") or item.get("last") or 0),
            })
    except Exception as e:
        logger.warning(f"_parse_positions error: {e}")
    return result


@quick_trade_bp.route('/close-position', methods=['POST'])
@login_required
def close_position():
    """
    Close an existing position.
    
    Body JSON:
      credential_id  (int)    — saved exchange credential ID
      symbol         (str)    — e.g. "BTC/USDT"
      market_type    (str)    — "swap" / "spot" (default: swap)
      size            (float)  — position size to close (optional, defaults to full position)
      source          (str)    — "ai_radar" / "ai_analysis" / "indicator" / "manual"
    """
    try:
        user_id = g.user_id
        body = request.get_json(force=True, silent=True) or {}
        
        credential_id = int(body.get("credential_id") or 0)
        symbol = str(body.get("symbol") or "").strip()
        market_type = str(body.get("market_type") or "swap").strip().lower()
        close_size = float(body.get("size") or 0)  # 0 means close full position
        source = str(body.get("source") or "manual").strip()
        
        # ---- validation ----
        if not credential_id:
            return jsonify({"code": 0, "msg": "Missing credential_id"}), 400
        if not symbol:
            return jsonify({"code": 0, "msg": "Missing symbol"}), 400
        
        if market_type in ("futures", "future", "perp", "perpetual"):
            market_type = "swap"
        
        # ---- build exchange client ----
        exchange_config = _build_exchange_config(credential_id, user_id, {
            "market_type": market_type,
        })
        exchange_id = (exchange_config.get("exchange_id") or "").strip().lower()
        if not exchange_id:
            return jsonify({"code": 0, "msg": "Invalid credential: missing exchange_id"}), 400
        
        client = _create_client(exchange_config, market_type=market_type)
        
        # ---- get current position ----
        positions = []
        try:
            from app.services.live_trading.okx import OkxClient
            if isinstance(client, OkxClient):
                from app.services.live_trading.symbols import to_okx_swap_inst_id, to_okx_spot_inst_id
                if market_type == "spot":
                    inst_id = to_okx_spot_inst_id(symbol)
                else:
                    inst_id = to_okx_swap_inst_id(symbol)
                raw = client.get_positions(inst_id=inst_id)
                positions = _parse_positions(raw)
            elif hasattr(client, "get_positions"):
                raw = client.get_positions(symbol=symbol)
                positions = _parse_positions(raw)
            elif hasattr(client, "get_position"):
                raw = client.get_position(symbol=symbol)
                positions = _parse_positions(raw)
        except Exception as pe:
            logger.warning(f"Position fetch failed: {pe}")
        
        if not positions:
            return jsonify({"code": 0, "msg": f"No position found for {symbol}"}), 404
        
        # Find matching position for this symbol
        position = None
        for pos in positions:
            pos_symbol = pos.get("symbol", "").strip()
            # Match by symbol (may need normalization)
            if symbol.upper().replace("/", "") in pos_symbol.upper().replace("/", "").replace("-", ""):
                position = pos
                break
        
        if not position:
            return jsonify({"code": 0, "msg": f"No position found for {symbol}"}), 404
        
        position_side = str(position.get("side") or "").strip().lower()
        position_size = float(position.get("size") or 0)
        
        if position_size <= 0:
            return jsonify({"code": 0, "msg": "Position size is zero or invalid"}), 400
        
        # Determine close size
        actual_close_size = close_size if close_size > 0 else position_size
        if actual_close_size > position_size:
            actual_close_size = position_size
        
        # ---- determine signal type based on position side ----
        if market_type == "spot":
            # Spot only supports long positions
            if position_side != "long":
                return jsonify({"code": 0, "msg": "Spot market only supports closing long positions"}), 400
            signal_type = "close_long"
        else:
            # Swap: close_long or close_short
            if position_side == "long":
                signal_type = "close_long"
            elif position_side == "short":
                signal_type = "close_short"
            else:
                return jsonify({"code": 0, "msg": f"Unknown position side: {position_side}"}), 400
        
        # ---- place close order ----
        from app.services.live_trading.execution import place_order_from_signal
        
        # Generate client_order_id
        timestamp_suffix = str(int(time.time()))[-6:]
        uuid_suffix = uuid.uuid4().hex[:8]
        client_order_id = f"qtc{timestamp_suffix}{uuid_suffix}"  # 'c' for close
        
        result = place_order_from_signal(
            client=client,
            signal_type=signal_type,
            symbol=symbol,
            amount=actual_close_size,  # Use position size directly (already in base qty)
            market_type=market_type,
            exchange_config=exchange_config,
            client_order_id=client_order_id,
        )
        
        # ---- extract result ----
        exchange_order_id = str(getattr(result, "exchange_order_id", "") or "")
        filled = float(getattr(result, "filled", 0) or 0)
        avg_fill = float(getattr(result, "avg_price", 0) or 0)
        raw = getattr(result, "raw", {}) or {}
        
        # ---- calculate USDT amount for recording ----
        # Convert base asset quantity to USDT amount for consistent recording
        # amount (USDT) = base_qty * price
        usdt_amount = actual_close_size * avg_fill if avg_fill > 0 else 0
        # If price is not available, try to use entry price or mark price as fallback
        if usdt_amount <= 0:
            entry_price = float(position.get("entry_price") or 0)
            mark_price = float(position.get("mark_price") or 0)
            fallback_price = mark_price if mark_price > 0 else entry_price
            if fallback_price > 0:
                usdt_amount = actual_close_size * fallback_price
        
        # ---- record trade ----
        trade_id = _record_quick_trade(
            user_id=user_id,
            credential_id=credential_id,
            exchange_id=exchange_id,
            symbol=symbol,
            side="sell" if position_side == "long" else "buy",  # Opposite of position side
            order_type="market",
            amount=usdt_amount,  # Record USDT amount, not base asset quantity
            price=avg_fill,
            leverage=float(position.get("leverage") or 1),
            market_type=market_type,
            tp_price=0,
            sl_price=0,
            status="filled" if filled > 0 else "submitted",
            exchange_order_id=exchange_order_id,
            filled=filled,
            avg_price=avg_fill,
            error_msg="",
            source=source,
            raw_result=raw,
        )
        
        return jsonify({
            "code": 1,
            "msg": "Position closed successfully",
            "data": {
                "trade_id": trade_id,
                "exchange_order_id": exchange_order_id,
                "filled": filled,
                "avg_price": avg_fill,
                "closed_size": actual_close_size,
                "position_side": position_side,
                "status": "filled" if filled > 0 else "submitted",
            },
        })
        
    except Exception as e:
        logger.error(f"close_position failed: {e}")
        logger.error(traceback.format_exc())
        return jsonify({"code": 0, "msg": str(e)}), 500


@quick_trade_bp.route('/history', methods=['GET'])
@login_required
def get_history():
    """
    Get quick trade history for the current user.

    Query: limit (int, default 50), offset (int, default 0)
    """
    try:
        user_id = g.user_id
        limit = min(int(request.args.get("limit") or 50), 200)
        offset = int(request.args.get("offset") or 0)

        with get_db_connection() as db:
            cur = db.cursor()
            cur.execute(
                """
                SELECT id, exchange_id, symbol, side, order_type, amount, price,
                       leverage, market_type, tp_price, sl_price, status,
                       exchange_order_id, filled_amount, avg_fill_price,
                       error_msg, source, created_at
                FROM qd_quick_trades
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
                """,
                (user_id, limit, offset),
            )
            rows = cur.fetchall() or []
            cur.close()

        trades = []
        for r in rows:
            trades.append({
                "id": r.get("id"),
                "exchange_id": r.get("exchange_id") or "",
                "symbol": r.get("symbol") or "",
                "side": r.get("side") or "",
                "order_type": r.get("order_type") or "market",
                "amount": float(r.get("amount") or 0),
                "price": float(r.get("price") or 0),
                "leverage": int(r.get("leverage") or 1),
                "market_type": r.get("market_type") or "swap",
                "tp_price": float(r.get("tp_price") or 0),
                "sl_price": float(r.get("sl_price") or 0),
                "status": r.get("status") or "",
                "exchange_order_id": r.get("exchange_order_id") or "",
                "filled_amount": float(r.get("filled_amount") or 0),
                "avg_fill_price": float(r.get("avg_fill_price") or 0),
                "error_msg": r.get("error_msg") or "",
                "source": r.get("source") or "",
                "created_at": str(r.get("created_at") or ""),
            })

        return jsonify({"code": 1, "msg": "success", "data": {"trades": trades}})
    except Exception as e:
        logger.error(f"get_history failed: {e}")
        return jsonify({"code": 0, "msg": str(e)}), 500
