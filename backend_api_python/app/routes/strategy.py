"""
Trading Strategy API Routes
"""
from flask import Blueprint, request, jsonify, g
import traceback
import time

from app.services.strategy import StrategyService
from app.services.strategy_compiler import StrategyCompiler
from app.services.backtest import BacktestService
from app import get_trading_executor
from app.utils.logger import get_logger
from app.utils.db import get_db_connection
from app.utils.auth import login_required
from app.data_sources import DataSourceFactory

logger = get_logger(__name__)

strategy_bp = Blueprint('strategy', __name__)

# Local mode: avoid heavy initialization during module import.
# Instantiate services lazily on first use to keep startup clean.
_strategy_service = None

def get_strategy_service() -> StrategyService:
    global _strategy_service
    if _strategy_service is None:
        _strategy_service = StrategyService()
    return _strategy_service


@strategy_bp.route('/strategies', methods=['GET'])
@login_required
def list_strategies():
    """
    List strategies for the current user.
    """
    try:
        user_id = g.user_id
        items = get_strategy_service().list_strategies(user_id=user_id)
        return jsonify({'code': 1, 'msg': 'success', 'data': {'strategies': items}})
    except Exception as e:
        logger.error(f"list_strategies failed: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'code': 0, 'msg': str(e), 'data': {'strategies': []}}), 500


@strategy_bp.route('/strategies/detail', methods=['GET'])
@login_required
def get_strategy_detail():
    try:
        user_id = g.user_id
        strategy_id = request.args.get('id', type=int)
        if not strategy_id:
            return jsonify({'code': 0, 'msg': 'Missing strategy id parameter', 'data': None}), 400
        st = get_strategy_service().get_strategy(strategy_id, user_id=user_id)
        if not st:
            return jsonify({'code': 0, 'msg': 'Strategy not found', 'data': None}), 404
        return jsonify({'code': 1, 'msg': 'success', 'data': st})
    except Exception as e:
        logger.error(f"get_strategy_detail failed: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'code': 0, 'msg': str(e), 'data': None}), 500


@strategy_bp.route('/strategies/create', methods=['POST'])
@login_required
def create_strategy():
    try:
        user_id = g.user_id
        payload = request.get_json() or {}
        # Use current user's ID
        payload['user_id'] = user_id
        payload['strategy_type'] = payload.get('strategy_type') or 'IndicatorStrategy'
        new_id = get_strategy_service().create_strategy(payload)
        return jsonify({'code': 1, 'msg': 'success', 'data': {'id': new_id}})
    except Exception as e:
        logger.error(f"create_strategy failed: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'code': 0, 'msg': str(e), 'data': None}), 500


@strategy_bp.route('/strategies/batch-create', methods=['POST'])
@login_required
def batch_create_strategies():
    """
    Batch create strategies (multiple symbols)
    
    Request body:
        strategy_name: Base strategy name
        symbols: Array of symbols, e.g. ["Crypto:BTC/USDT", "Crypto:ETH/USDT"]
        ... other strategy config
    """
    try:
        user_id = g.user_id
        payload = request.get_json() or {}
        payload['user_id'] = user_id
        payload['strategy_type'] = payload.get('strategy_type') or 'IndicatorStrategy'
        
        result = get_strategy_service().batch_create_strategies(payload)
        
        if result['success']:
            return jsonify({
                'code': 1,
                'msg': f"Successfully created {result['total_created']} strategies",
                'data': result
            })
        else:
            return jsonify({
                'code': 0,
                'msg': 'Batch creation failed',
                'data': result
            })
    except Exception as e:
        logger.error(f"batch_create_strategies failed: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'code': 0, 'msg': str(e), 'data': None}), 500


@strategy_bp.route('/strategies/batch-start', methods=['POST'])
@login_required
def batch_start_strategies():
    """
    Batch start strategies
    
    Request body:
        strategy_ids: Array of strategy IDs
        or
        strategy_group_id: Strategy group ID
    """
    try:
        user_id = g.user_id
        payload = request.get_json() or {}
        strategy_ids = payload.get('strategy_ids') or []
        strategy_group_id = payload.get('strategy_group_id')
        
        # If strategy_group_id provided, get all strategies in the group
        if strategy_group_id and not strategy_ids:
            strategy_ids = get_strategy_service().get_strategies_by_group(strategy_group_id, user_id=user_id)
        
        if not strategy_ids:
            return jsonify({'code': 0, 'msg': 'Please provide strategy IDs', 'data': None}), 400
        
        # Update database status first
        result = get_strategy_service().batch_start_strategies(strategy_ids, user_id=user_id)
        
        # Then start executor
        executor = get_trading_executor()
        for sid in result.get('success_ids', []):
            try:
                executor.start_strategy(sid)
            except Exception as e:
                logger.error(f"Failed to start executor for strategy {sid}: {e}")
        
        return jsonify({
            'code': 1 if result['success'] else 0,
            'msg': f"Successfully started {len(result.get('success_ids', []))} strategies",
            'data': result
        })
    except Exception as e:
        logger.error(f"batch_start_strategies failed: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'code': 0, 'msg': str(e), 'data': None}), 500


@strategy_bp.route('/strategies/batch-stop', methods=['POST'])
@login_required
def batch_stop_strategies():
    """
    Batch stop strategies
    
    Request body:
        strategy_ids: Array of strategy IDs
        or
        strategy_group_id: Strategy group ID
    """
    try:
        user_id = g.user_id
        payload = request.get_json() or {}
        strategy_ids = payload.get('strategy_ids') or []
        strategy_group_id = payload.get('strategy_group_id')
        
        if strategy_group_id and not strategy_ids:
            strategy_ids = get_strategy_service().get_strategies_by_group(strategy_group_id, user_id=user_id)
        
        if not strategy_ids:
            return jsonify({'code': 0, 'msg': 'Please provide strategy IDs', 'data': None}), 400
        
        # Stop executor first
        executor = get_trading_executor()
        for sid in strategy_ids:
            try:
                executor.stop_strategy(sid)
            except Exception as e:
                logger.error(f"Failed to stop executor for strategy {sid}: {e}")
        
        # Then update database status
        result = get_strategy_service().batch_stop_strategies(strategy_ids, user_id=user_id)
        
        return jsonify({
            'code': 1 if result['success'] else 0,
            'msg': f"Successfully stopped {len(result.get('success_ids', []))} strategies",
            'data': result
        })
    except Exception as e:
        logger.error(f"batch_stop_strategies failed: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'code': 0, 'msg': str(e), 'data': None}), 500


@strategy_bp.route('/strategies/batch-delete', methods=['DELETE'])
@login_required
def batch_delete_strategies():
    """
    Batch delete strategies
    
    Request body:
        strategy_ids: Array of strategy IDs
        or
        strategy_group_id: Strategy group ID
    """
    try:
        user_id = g.user_id
        payload = request.get_json() or {}
        strategy_ids = payload.get('strategy_ids') or []
        strategy_group_id = payload.get('strategy_group_id')
        
        if strategy_group_id and not strategy_ids:
            strategy_ids = get_strategy_service().get_strategies_by_group(strategy_group_id, user_id=user_id)
        
        if not strategy_ids:
            return jsonify({'code': 0, 'msg': 'Please provide strategy IDs', 'data': None}), 400
        
        # Stop executor first
        executor = get_trading_executor()
        for sid in strategy_ids:
            try:
                executor.stop_strategy(sid)
            except Exception as e:
                pass  # Ignore stop errors
        
        # Then delete
        result = get_strategy_service().batch_delete_strategies(strategy_ids, user_id=user_id)
        
        return jsonify({
            'code': 1 if result['success'] else 0,
            'msg': f"Successfully deleted {len(result.get('success_ids', []))} strategies",
            'data': result
        })
    except Exception as e:
        logger.error(f"batch_delete_strategies failed: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'code': 0, 'msg': str(e), 'data': None}), 500


@strategy_bp.route('/strategies/update', methods=['PUT'])
@login_required
def update_strategy():
    try:
        user_id = g.user_id
        strategy_id = request.args.get('id', type=int)
        if not strategy_id:
            return jsonify({'code': 0, 'msg': 'Missing strategy id parameter', 'data': None}), 400
        payload = request.get_json() or {}
        ok = get_strategy_service().update_strategy(strategy_id, payload, user_id=user_id)
        if not ok:
            return jsonify({'code': 0, 'msg': 'Strategy not found', 'data': None}), 404
        return jsonify({'code': 1, 'msg': 'success', 'data': None})
    except Exception as e:
        logger.error(f"update_strategy failed: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'code': 0, 'msg': str(e), 'data': None}), 500


@strategy_bp.route('/strategies/delete', methods=['DELETE'])
@login_required
def delete_strategy():
    try:
        user_id = g.user_id
        strategy_id = request.args.get('id', type=int)
        if not strategy_id:
            return jsonify({'code': 0, 'msg': 'Missing strategy id parameter', 'data': None}), 400
        ok = get_strategy_service().delete_strategy(strategy_id, user_id=user_id)
        return jsonify({'code': 1 if ok else 0, 'msg': 'success' if ok else 'failed', 'data': None})
    except Exception as e:
        logger.error(f"delete_strategy failed: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'code': 0, 'msg': str(e), 'data': None}), 500


@strategy_bp.route('/strategies/trades', methods=['GET'])
@login_required
def get_trades():
    """Get trade records for the current user's strategy."""
    try:
        user_id = g.user_id
        strategy_id = request.args.get('id', type=int)
        if not strategy_id:
            return jsonify({'code': 0, 'msg': 'Missing strategy id parameter', 'data': {'trades': [], 'items': []}}), 400
        
        # Verify strategy belongs to user
        st = get_strategy_service().get_strategy(strategy_id, user_id=user_id)
        if not st:
            return jsonify({'code': 0, 'msg': 'Strategy not found', 'data': {'trades': [], 'items': []}}), 404
        
        with get_db_connection() as db:
            cur = db.cursor()
            cur.execute(
                """
                SELECT id, strategy_id, symbol, type, price, amount, value, commission, commission_ccy, profit, created_at
                FROM qd_strategy_trades
                WHERE strategy_id = ?
                ORDER BY id DESC
                """,
                (strategy_id,)
            )
            rows = cur.fetchall() or []
            cur.close()
        
        # Convert created_at to UTC timestamp (seconds) for frontend
        # This ensures consistent timezone handling
        processed_rows = []
        for row in rows:
            trade = dict(row)
            created_at = trade.get('created_at')
            if created_at:
                if hasattr(created_at, 'timestamp'):
                    # datetime object - convert to UTC timestamp
                    trade['created_at'] = int(created_at.timestamp())
                elif isinstance(created_at, str):
                    # ISO string - parse and convert
                    try:
                        from datetime import datetime
                        dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                        trade['created_at'] = int(dt.timestamp())
                    except Exception:
                        pass
            processed_rows.append(trade)
        
        # Frontend expects data.trades; keep data.items for compatibility with list-style components.
        return jsonify({'code': 1, 'msg': 'success', 'data': {'trades': processed_rows, 'items': processed_rows}})
    except Exception as e:
        logger.error(f"get_trades failed: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'code': 0, 'msg': str(e), 'data': {'trades': [], 'items': []}}), 500


@strategy_bp.route('/strategies/positions', methods=['GET'])
@login_required
def get_positions():
    """Get position records for the current user's strategy."""
    try:
        user_id = g.user_id
        strategy_id = request.args.get('id', type=int)
        if not strategy_id:
            return jsonify({'code': 0, 'msg': 'Missing strategy id parameter', 'data': {'positions': [], 'items': []}}), 400
        
        # Verify strategy belongs to user
        st = get_strategy_service().get_strategy(strategy_id, user_id=user_id)
        if not st:
            return jsonify({'code': 0, 'msg': 'Strategy not found', 'data': {'positions': [], 'items': []}}), 404
        
        with get_db_connection() as db:
            cur = db.cursor()
            cur.execute(
                """
                SELECT id, strategy_id, symbol, side, size, entry_price, current_price, highest_price,
                       unrealized_pnl, pnl_percent, equity, updated_at
                FROM qd_strategy_positions
                WHERE strategy_id = ?
                ORDER BY id DESC
                """,
                (strategy_id,)
            )
            rows = cur.fetchall() or []
            cur.close()

        # Sync current price and PnL on read (frontend polls every few seconds).
        def _calc_unrealized_pnl(side: str, entry_price: float, current_price: float, size: float) -> float:
            ep = float(entry_price or 0.0)
            cp = float(current_price or 0.0)
            sz = float(size or 0.0)
            if ep <= 0 or cp <= 0 or sz <= 0:
                return 0.0
            s = (side or "").strip().lower()
            if s == "short":
                return (ep - cp) * sz
            return (cp - ep) * sz

        def _calc_pnl_percent(entry_price: float, size: float, pnl: float) -> float:
            ep = float(entry_price or 0.0)
            sz = float(size or 0.0)
            denom = ep * sz
            if denom <= 0:
                return 0.0
            return float(pnl) / denom * 100.0

        now = int(time.time())
        # Fetch prices once per symbol to reduce API calls.
        sym_to_price: dict[str, float] = {}
        ds = DataSourceFactory.get_source("Crypto")
        for r in rows:
            sym = (r.get("symbol") or "").strip()
            if not sym:
                continue
            if sym in sym_to_price:
                continue
            try:
                t = ds.get_ticker(sym) or {}
                px = float(t.get("last") or t.get("close") or 0.0)
                if px > 0:
                    sym_to_price[sym] = px
            except Exception:
                continue

        # Apply to rows and persist best-effort
        out = []
        with get_db_connection() as db:
            cur = db.cursor()
            for r in rows:
                sym = (r.get("symbol") or "").strip()
                side = (r.get("side") or "").strip().lower()
                entry = float(r.get("entry_price") or 0.0)
                size = float(r.get("size") or 0.0)
                cp = float(sym_to_price.get(sym) or r.get("current_price") or 0.0)
                pnl = _calc_unrealized_pnl(side, entry, cp, size)
                pct = _calc_pnl_percent(entry, size, pnl)

                rr = dict(r)
                # 确保 entry_price 有值（如果数据库中是 NULL，使用计算出的 entry 值）
                if not rr.get("entry_price") or float(rr.get("entry_price") or 0.0) <= 0:
                    rr["entry_price"] = float(entry or 0.0)
                else:
                    rr["entry_price"] = float(rr.get("entry_price") or 0.0)
                rr["current_price"] = float(cp or 0.0)
                rr["unrealized_pnl"] = float(pnl)
                rr["pnl_percent"] = float(pct)
                rr["updated_at"] = now
                out.append(rr)

                try:
                    cur.execute(
                        """
                        UPDATE qd_strategy_positions
                        SET current_price = ?, unrealized_pnl = ?, pnl_percent = ?, updated_at = NOW()
                        WHERE id = ?
                        """,
                        (float(cp or 0.0), float(pnl), float(pct), int(rr.get("id"))),
                    )
                except Exception:
                    pass
            db.commit()
            cur.close()

        return jsonify({'code': 1, 'msg': 'success', 'data': {'positions': out, 'items': out}})
    except Exception as e:
        logger.error(f"get_positions failed: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'code': 0, 'msg': str(e), 'data': {'positions': [], 'items': []}}), 500


@strategy_bp.route('/strategies/equityCurve', methods=['GET'])
@login_required
def get_equity_curve():
    """Get equity curve for the current user's strategy."""
    try:
        user_id = g.user_id
        strategy_id = request.args.get('id', type=int)
        if not strategy_id:
            return jsonify({'code': 0, 'msg': 'Missing strategy id parameter', 'data': []}), 400

        st = get_strategy_service().get_strategy(strategy_id, user_id=user_id) or {}
        if not st:
            return jsonify({'code': 0, 'msg': 'Strategy not found', 'data': []}), 404
        initial = float(st.get('initial_capital') or (st.get('trading_config') or {}).get('initial_capital') or 0)
        if initial <= 0:
            initial = 1000.0

        with get_db_connection() as db:
            cur = db.cursor()
            cur.execute(
                """
                SELECT created_at, profit
                FROM qd_strategy_trades
                WHERE strategy_id = ?
                ORDER BY created_at ASC
                """,
                (strategy_id,)
            )
            rows = cur.fetchall() or []
            cur.close()

        equity = initial
        curve = []
        for r in rows:
            try:
                equity += float(r.get('profit') or 0)
            except Exception:
                pass
            created_at = r.get('created_at')
            if created_at and hasattr(created_at, 'timestamp'):
                ts = int(created_at.timestamp())
            elif created_at:
                ts = int(created_at)
            else:
                ts = int(time.time())
            curve.append({'time': ts, 'equity': equity})

        return jsonify({'code': 1, 'msg': 'success', 'data': curve})
    except Exception as e:
        logger.error(f"get_equity_curve failed: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'code': 0, 'msg': str(e), 'data': []}), 500





@strategy_bp.route('/strategies/stop', methods=['POST'])
@login_required
def stop_strategy():
    """
    Stop a strategy for the current user.
    
    Params:
        id: Strategy ID
    """
    try:
        user_id = g.user_id
        strategy_id = request.args.get('id', type=int)
        
        if not strategy_id:
            return jsonify({
                'code': 0,
                'msg': 'Missing strategy id parameter',
                'data': None
            }), 400
        
        # Verify strategy belongs to user
        st = get_strategy_service().get_strategy(strategy_id, user_id=user_id)
        if not st:
            return jsonify({'code': 0, 'msg': 'Strategy not found', 'data': None}), 404
        
        # Get strategy type
        strategy_type = get_strategy_service().get_strategy_type(strategy_id)
        
        # Local backend: AI strategy executor was removed. Only indicator strategies are supported.
        if strategy_type == 'PromptBasedStrategy':
            return jsonify({'code': 0, 'msg': 'AI strategy has been removed; local edition does not support starting/stopping AI strategies', 'data': None}), 400

        # Indicator strategy
        get_trading_executor().stop_strategy(strategy_id)
        
        # Update strategy status
        get_strategy_service().update_strategy_status(strategy_id, 'stopped', user_id=user_id)
        
        return jsonify({
            'code': 1,
            'msg': 'Stopped successfully',
            'data': None
        })
        
    except Exception as e:
        logger.error(f"Failed to stop strategy: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'code': 0,
            'msg': f'Failed to stop strategy: {str(e)}',
            'data': None
        }), 500


@strategy_bp.route('/strategies/start', methods=['POST'])
@login_required
def start_strategy():
    """
    Start a strategy for the current user.
    
    Params:
        id: Strategy ID
    """
    try:
        user_id = g.user_id
        strategy_id = request.args.get('id', type=int)
        
        if not strategy_id:
            return jsonify({
                'code': 0,
                'msg': 'Missing strategy id parameter',
                'data': None
            }), 400
        
        # Verify strategy belongs to user
        st = get_strategy_service().get_strategy(strategy_id, user_id=user_id)
        if not st:
            return jsonify({'code': 0, 'msg': 'Strategy not found', 'data': None}), 404
        
        # Get strategy type
        strategy_type = get_strategy_service().get_strategy_type(strategy_id)
        
        # Update strategy status
        get_strategy_service().update_strategy_status(strategy_id, 'running', user_id=user_id)
        
        # Local backend: AI strategy executor was removed. Only indicator strategies are supported.
        if strategy_type == 'PromptBasedStrategy':
            return jsonify({'code': 0, 'msg': 'AI strategy has been removed; local edition does not support starting AI strategies', 'data': None}), 400

        # Indicator strategy
        success = get_trading_executor().start_strategy(strategy_id)
        
        if not success:
            # If start failed, restore status
            get_strategy_service().update_strategy_status(strategy_id, 'stopped', user_id=user_id)
            return jsonify({
                'code': 0,
                'msg': 'Failed to start strategy executor',
                'data': None
            }), 500
        
        return jsonify({
            'code': 1,
            'msg': 'Started successfully',
            'data': None
        })
        
    except Exception as e:
        logger.error(f"Failed to start strategy: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'code': 0,
            'msg': f'Failed to start strategy: {str(e)}',
            'data': None
        }), 500


@strategy_bp.route('/strategies/test-connection', methods=['POST'])
@login_required
def test_connection():
    """
    Test exchange connection.
    
    Request body:
        exchange_config: Exchange configuration (may contain credential_id or inline keys)
    """
    try:
        data = request.get_json() or {}
        
        # 记录请求数据（用于调试，但不记录敏感信息）
        logger.debug(f"Connection test request keys: {list(data.keys())}")
        
        # 获取交易所配置
        exchange_config = data.get('exchange_config', data)
        
        # Local deployment: no encryption/decryption; accept dict or JSON string.
        if isinstance(exchange_config, str):
            try:
                import json
                exchange_config = json.loads(exchange_config)
            except Exception:
                pass
        
        # 验证 exchange_config 是否为字典
        if not isinstance(exchange_config, dict):
            logger.error(f"Invalid exchange_config type: {type(exchange_config)}, data: {str(exchange_config)[:200]}")
            # Frontend expects HTTP 200 with {code:0} for business failures.
            return jsonify({'code': 0, 'msg': 'Invalid exchange config format; please check your payload', 'data': None})

        # Resolve credential_id → full config (merges credential keys with any overrides).
        # This allows the frontend to send just {credential_id: 5} without raw api_key/secret_key.
        from app.services.exchange_execution import resolve_exchange_config
        user_id = g.user_id if hasattr(g, 'user_id') else 1
        resolved = resolve_exchange_config(exchange_config, user_id=user_id)

        # 验证必要字段 (check resolved config after credential merge)
        if not resolved.get('exchange_id'):
            return jsonify({'code': 0, 'msg': 'Please select an exchange', 'data': None})
        
        api_key = resolved.get('api_key', '')
        secret_key = resolved.get('secret_key', '')
        
        # 详细日志排查
        logger.info(f"Testing connection: exchange_id={resolved.get('exchange_id')}")
        if api_key:
            logger.info(f"API Key: {api_key[:5]}... (len={len(api_key)})")
        if secret_key:
            logger.info(f"Secret Key: {secret_key[:5]}... (len={len(secret_key)})")
        
        # 检查是否有特殊字符
        if api_key and api_key.strip() != api_key:
            logger.warning("API key contains leading/trailing whitespace")
        if secret_key and secret_key.strip() != secret_key:
            logger.warning("Secret key contains leading/trailing whitespace")
            
        if not api_key or not secret_key:
            return jsonify({'code': 0, 'msg': 'Please provide API key and secret key', 'data': None})
        
        # Pass the resolved config (with actual keys) to the service
        result = get_strategy_service().test_exchange_connection(resolved)
        
        if result['success']:
            return jsonify({'code': 1, 'msg': result.get('message') or 'Connection successful', 'data': result.get('data')})
        # Always return HTTP 200 for business-level failures.
        return jsonify({'code': 0, 'msg': result.get('message') or 'Connection failed', 'data': result.get('data')})
        
    except Exception as e:
        logger.error(f"Connection test failed: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'code': 0,
            'msg': f'Connection test failed: {str(e)}',
            'data': None
        }), 500


@strategy_bp.route('/strategies/get-symbols', methods=['POST'])
@login_required
def get_symbols():
    """
    Get exchange trading pairs list.
    
    Request body:
        exchange_config: Exchange configuration
    """
    try:
        data = request.get_json() or {}
        exchange_config = data.get('exchange_config', data)
        
        result = get_strategy_service().get_exchange_symbols(exchange_config)
        
        if result['success']:
            return jsonify({
                'code': 1,
                'msg': result['message'],
                'data': {
                    'symbols': result['symbols']
                }
            })
        else:
            return jsonify({
                'code': 0,
                'msg': result['message'],
                'data': {
                    'symbols': []
                }
            })
        
    except Exception as e:
        logger.error(f"Failed to fetch symbols: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'code': 0,
            'msg': f'Failed to fetch symbols: {str(e)}',
            'data': {
                'symbols': []
            }
        }), 500


@strategy_bp.route('/strategies/preview-compile', methods=['POST'])
@login_required
def preview_compile():
    """
    Preview compiled strategy result.
    """
    try:
        data = request.get_json() or {}
        # strategy_config is passed as 'config'
        config = data.get('config')
        
        if not config:
             return jsonify({'code': 0, 'msg': 'Missing config'}), 400

        # Compile
        compiler = StrategyCompiler()
        try:
            code = compiler.compile(config)
        except Exception as e:
            return jsonify({'code': 0, 'msg': f'Compilation failed: {str(e)}'}), 400
        
        # Execute
        symbol = config.get('symbol', 'BTC/USDT')
        timeframe = config.get('timeframe', '4h')
        
        backtest_service = BacktestService()
        result = backtest_service.run_code_strategy(
            code=code,
            symbol=symbol,
            timeframe=timeframe,
            limit=500 
        )
        
        if result.get('error'):
             return jsonify({'code': 0, 'msg': f"Execution failed: {result['error']}"}), 400

        return jsonify({
            'code': 1,
            'msg': 'Success',
            'data': result
        })
        
    except Exception as e:
        logger.error(f"Preview failed: {e}")
        return jsonify({'code': 0, 'msg': str(e)}), 500


@strategy_bp.route('/strategies/notifications', methods=['GET'])
@login_required
def get_strategy_notifications():
    """
    Strategy signal notifications for the current user.

    Query:
      - id: strategy id (optional)
      - limit: default 50, max 200
      - since_id: return rows with id > since_id (optional)
    """
    try:
        user_id = g.user_id
        strategy_id = request.args.get('id', type=int)
        limit = request.args.get('limit', type=int) or 50
        limit = max(1, min(200, int(limit)))
        since_id = request.args.get('since_id', type=int) or 0

        # Get user's strategy IDs for filtering notifications
        user_strategy_ids = []
        with get_db_connection() as db:
            cur = db.cursor()
            cur.execute("SELECT id FROM qd_strategies_trading WHERE user_id = ?", (user_id,))
            rows = cur.fetchall() or []
            user_strategy_ids = [r.get('id') for r in rows if r.get('id')]
            cur.close()
        
        where = []
        args = []
        
        # Filter by user's strategies
        if strategy_id:
            if strategy_id in user_strategy_ids:
                where.append("strategy_id = ?")
                args.append(int(strategy_id))
            else:
                return jsonify({'code': 1, 'msg': 'success', 'data': {'items': []}})
        else:
            if user_strategy_ids:
                placeholders = ",".join(["?"] * len(user_strategy_ids))
                where.append(f"(strategy_id IN ({placeholders}) OR (strategy_id IS NULL AND user_id = ?))")
                args.extend(user_strategy_ids)
                args.append(user_id)
            else:
                # Only portfolio monitor notifications (strategy_id is NULL)
                where.append("strategy_id IS NULL AND user_id = ?")
                args.append(user_id)
        
        if since_id:
            where.append("id > ?")
            args.append(int(since_id))
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        with get_db_connection() as db:
            cur = db.cursor()
            cur.execute(
                f"""
                SELECT *
                FROM qd_strategy_notifications
                {where_sql}
                ORDER BY id DESC
                LIMIT ?
                """,
                tuple(args + [int(limit)]),
            )
            rows = cur.fetchall() or []
            cur.close()

        # Convert created_at to UTC timestamp (seconds) for frontend
        processed_rows = []
        for row in rows:
            item = dict(row)
            created_at = item.get('created_at')
            if created_at:
                if hasattr(created_at, 'timestamp'):
                    item['created_at'] = int(created_at.timestamp())
                elif isinstance(created_at, str):
                    try:
                        from datetime import datetime
                        dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                        item['created_at'] = int(dt.timestamp())
                    except Exception:
                        pass
            processed_rows.append(item)

        return jsonify({'code': 1, 'msg': 'success', 'data': {'items': processed_rows}})
    except Exception as e:
        logger.error(f"get_strategy_notifications failed: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'code': 0, 'msg': str(e), 'data': {'items': []}}), 500


@strategy_bp.route('/strategies/notifications/read', methods=['POST'])
@login_required
def mark_notification_read():
    """Mark a single notification as read for the current user."""
    try:
        user_id = g.user_id
        data = request.get_json(force=True, silent=True) or {}
        notification_id = data.get('id')
        if not notification_id:
            return jsonify({'code': 0, 'msg': 'Missing id'}), 400

        # Update notifications for user's strategies OR portfolio monitor notifications
        with get_db_connection() as db:
            cur = db.cursor()
            cur.execute(
                """
                UPDATE qd_strategy_notifications SET is_read = 1 
                WHERE id = ? AND (
                    strategy_id IN (SELECT id FROM qd_strategies_trading WHERE user_id = ?)
                    OR (strategy_id IS NULL AND user_id = ?)
                )
                """,
                (int(notification_id), user_id, user_id)
            )
            db.commit()
            cur.close()

        return jsonify({'code': 1, 'msg': 'success'})
    except Exception as e:
        logger.error(f"mark_notification_read failed: {str(e)}")
        return jsonify({'code': 0, 'msg': str(e)}), 500


@strategy_bp.route('/strategies/notifications/read-all', methods=['POST'])
@login_required
def mark_all_notifications_read():
    """Mark all notifications as read for the current user."""
    try:
        user_id = g.user_id
        with get_db_connection() as db:
            cur = db.cursor()
            cur.execute(
                """
                UPDATE qd_strategy_notifications SET is_read = 1 
                WHERE strategy_id IN (SELECT id FROM qd_strategies_trading WHERE user_id = ?)
                   OR (strategy_id IS NULL AND user_id = ?)
                """,
                (user_id, user_id)
            )
            db.commit()
            cur.close()

        return jsonify({'code': 1, 'msg': 'success'})
    except Exception as e:
        logger.error(f"mark_all_notifications_read failed: {str(e)}")
        return jsonify({'code': 0, 'msg': str(e)}), 500


@strategy_bp.route('/strategies/notifications/clear', methods=['DELETE'])
@login_required
def clear_notifications():
    """Clear all notifications for the current user."""
    try:
        user_id = g.user_id
        with get_db_connection() as db:
            cur = db.cursor()
            cur.execute(
                """
                DELETE FROM qd_strategy_notifications 
                WHERE strategy_id IN (SELECT id FROM qd_strategies_trading WHERE user_id = ?)
                   OR (strategy_id IS NULL AND user_id = ?)
                """,
                (user_id, user_id)
            )
            db.commit()
            cur.close()

        return jsonify({'code': 1, 'msg': 'success'})
    except Exception as e:
        logger.error(f"clear_notifications failed: {str(e)}")
        return jsonify({'code': 0, 'msg': str(e)}), 500