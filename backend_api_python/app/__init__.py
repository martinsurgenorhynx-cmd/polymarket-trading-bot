"""
QuantDinger Python API - Flask application factory.
"""
from flask import Flask
from flask_cors import CORS
import logging
import traceback

from app.utils.logger import setup_logger, get_logger

logger = get_logger(__name__)

# Global singletons (avoid duplicate strategy threads).
_trading_executor = None
_pending_order_worker = None


def get_trading_executor():
    """Get the trading executor singleton."""
    global _trading_executor
    if _trading_executor is None:
        from app.services.trading_executor import TradingExecutor
        _trading_executor = TradingExecutor()
    return _trading_executor


def get_pending_order_worker():
    """Get the pending order worker singleton."""
    global _pending_order_worker
    if _pending_order_worker is None:
        from app.services.pending_order_worker import PendingOrderWorker
        _pending_order_worker = PendingOrderWorker()
    return _pending_order_worker


def start_polymarket_worker():
    """启动Polymarket后台任务"""
    try:
        from app.services.polymarket_worker import get_polymarket_worker
        get_polymarket_worker().start()
    except Exception as e:
        logger.error(f"Failed to start Polymarket worker: {e}")


def start_portfolio_monitor():
    """Start the portfolio monitor service if enabled.
    
    To enable it, set ENABLE_PORTFOLIO_MONITOR=true.
    """
    import os
    enabled = os.getenv("ENABLE_PORTFOLIO_MONITOR", "true").lower() == "true"
    if not enabled:
        logger.info("Portfolio monitor is disabled. Set ENABLE_PORTFOLIO_MONITOR=true to enable.")
        return
    
    # Avoid running twice with Flask reloader
    debug = os.getenv("PYTHON_API_DEBUG", "false").lower() == "true"
    if debug:
        if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
            return
    
    try:
        from app.services.portfolio_monitor import start_monitor_service
        start_monitor_service()
    except Exception as e:
        logger.error(f"Failed to start portfolio monitor: {e}")


def start_pending_order_worker():
    """Start the pending order worker (disabled by default in paper mode).

    To enable it, set ENABLE_PENDING_ORDER_WORKER=true.
    """
    import os
    # Local deployment: default to enabled so queued orders can be dispatched automatically.
    # To disable it, set ENABLE_PENDING_ORDER_WORKER=false explicitly.
    if os.getenv('ENABLE_PENDING_ORDER_WORKER', 'true').lower() != 'true':
        logger.info("Pending order worker is disabled (paper mode). Set ENABLE_PENDING_ORDER_WORKER=true to enable.")
        return
    try:
        get_pending_order_worker().start()
    except Exception as e:
        logger.error(f"Failed to start pending order worker: {e}")


def start_usdt_order_worker():
    """Start the USDT order background worker.

    Periodically scans pending/paid USDT orders and checks on-chain status.
    Ensures orders are confirmed even if the user closes the browser after payment.
    Only starts if USDT_PAY_ENABLED=true.
    """
    import os
    if str(os.getenv("USDT_PAY_ENABLED", "False")).lower() not in ("1", "true", "yes"):
        logger.info("USDT order worker not started (USDT_PAY_ENABLED is not true).")
        return

    # Avoid running twice with Flask reloader
    debug = os.getenv("PYTHON_API_DEBUG", "false").lower() == "true"
    if debug:
        if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
            return

    try:
        from app.services.usdt_payment_service import get_usdt_order_worker
        get_usdt_order_worker().start()
    except Exception as e:
        logger.error(f"Failed to start USDT order worker: {e}")


def restore_running_strategies():
    """
    Restore running strategies on startup.
    Local deployment: only restores IndicatorStrategy.
    """
    import os
    # You can disable auto-restore to avoid starting many threads on low-resource hosts.
    if os.getenv('DISABLE_RESTORE_RUNNING_STRATEGIES', 'false').lower() == 'true':
        logger.info("Startup strategy restore is disabled via DISABLE_RESTORE_RUNNING_STRATEGIES")
        return
    try:
        from app.services.strategy import StrategyService
        
        strategy_service = StrategyService()
        trading_executor = get_trading_executor()
        
        running_strategies = strategy_service.get_running_strategies_with_type()
        
        if not running_strategies:
            logger.info("No running strategies to restore.")
            return
        
        logger.info(f"Restoring {len(running_strategies)} running strategies...")
        
        restored_count = 0
        for strategy_info in running_strategies:
            strategy_id = strategy_info['id']
            strategy_type = strategy_info.get('strategy_type', '')
            
            try:
                if strategy_type and strategy_type != 'IndicatorStrategy':
                    logger.info(f"Skip restore unsupported strategy type: id={strategy_id}, type={strategy_type}")
                    continue

                success = trading_executor.start_strategy(strategy_id)
                strategy_type_name = 'IndicatorStrategy'
                
                if success:
                    restored_count += 1
                    logger.info(f"[OK] {strategy_type_name} {strategy_id} restored")
                else:
                    logger.warning(f"[FAIL] {strategy_type_name} {strategy_id} restore failed (state may be stale)")
                    # 如果恢复失败，更新数据库状态为stopped，避免策略处于"僵尸"状态
                    try:
                        strategy_service.update_strategy_status(strategy_id, 'stopped')
                        logger.info(f"[FIX] Updated strategy {strategy_id} status to 'stopped' after restore failure")
                    except Exception as e:
                        logger.error(f"Failed to update strategy {strategy_id} status after restore failure: {e}")
            except Exception as e:
                logger.error(f"Error restoring strategy {strategy_id}: {str(e)}")
                logger.error(traceback.format_exc())
        
        logger.info(f"Strategy restore completed: {restored_count}/{len(running_strategies)} restored")
        
    except Exception as e:
        logger.error(f"Failed to restore running strategies: {str(e)}")
        logger.error(traceback.format_exc())
        # Do not raise; avoid breaking app startup.


def create_app(config_name='default'):
    """
    Flask application factory.
    
    Args:
        config_name: config name
        
    Returns:
        Flask app
    """
    app = Flask(__name__)
    
    app.config['JSON_AS_ASCII'] = False
    
    CORS(app)
    
    setup_logger()
    
    # Initialize database and ensure admin user exists
    try:
        from app.utils.db import init_database, get_db_type
        logger.info(f"Database type: {get_db_type()}")
        init_database()
        
        # Ensure admin user exists (multi-user mode)
        from app.services.user_service import get_user_service
        get_user_service().ensure_admin_exists()
    except Exception as e:
        logger.warning(f"Database initialization note: {e}")

    # =====================================================
    # Demo Mode Middleware (Read-Only Mode)
    # =====================================================
    import os
    from flask import request, jsonify

    # Check environment variable IS_DEMO_MODE
    is_demo_mode = os.getenv('IS_DEMO_MODE', 'false').lower() == 'true'

    if is_demo_mode:
        logger.info("!!! SYSTEM STARTING IN DEMO MODE (READ-ONLY) !!!")

        @app.before_request
        def global_demo_mode_check():
            """
            Global interceptor for demo mode.
            Blocks all state-changing methods AND access to sensitive GET endpoints.
            """
            path = request.path

            # 1. Block access to sensitive settings/config APIs (even if GET)
            # These endpoints reveal internal config or allow settings changes
            sensitive_endpoints = [
                '/api/settings',           # All settings routes
                '/api/credentials',        # Credentials management
                '/api/market/watchlist/add', # Modifying watchlist (POST, already blocked but good to be explicit)
                '/api/market/watchlist/remove'
            ]
            
            # Check if path starts with any sensitive prefix
            if any(path.startswith(endpoint) for endpoint in sensitive_endpoints):
                 return jsonify({
                    'code': 403,
                    'msg': 'Demo mode: Access to settings and credentials is forbidden.',
                    'data': None
                }), 403

            # 2. Allow safe methods (GET, HEAD, OPTIONS)
            if request.method in ['GET', 'HEAD', 'OPTIONS']:
                return None
            
            # 2. Allow Authentication (Login/Logout)
            # The auth routes are mounted at /api/user (see app/routes/__init__.py)
            if request.path.endswith('/login') or request.path.endswith('/logout'):
                return None

            # 3. Allow specific read-only POST endpoints (Whitelist)
            # Some search/query endpoints use POST for complex payloads but don't modify state.
            whitelist_post_endpoints = [
                '/api/indicator/getIndicators', # Search indicators
                '/api/market/klines',           # Fetch K-lines (sometimes POST)
                '/api/ai/chat',                 # AI Chat (generates response, doesn't mutate system state)
                '/api/fast-analysis/analyze',   # Fast AI Analysis request
            ]
            
            # Check if current path ends with any whitelist item
            if any(request.path.endswith(endpoint) for endpoint in whitelist_post_endpoints):
                return None

            # 4. Block everything else
            return jsonify({
                'code': 403,
                'msg': 'Demo mode: Read-only access. Forbidden to modify data.',
                'data': None
            }), 403
    
    from app.routes import register_routes
    register_routes(app)
    
    # Startup hooks.
    with app.app_context():
        start_pending_order_worker()
        start_portfolio_monitor()
        start_usdt_order_worker()
        start_polymarket_worker()
        restore_running_strategies()
    
    return app

