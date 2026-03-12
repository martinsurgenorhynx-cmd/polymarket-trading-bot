"""
Interactive Brokers API Routes

Standalone API endpoints for US stock trading.
"""

from flask import Blueprint, request, jsonify

from app.utils.logger import get_logger
from app.services.ibkr_trading import IBKRClient, IBKRConfig
from app.services.ibkr_trading.client import get_ibkr_client, reset_ibkr_client

logger = get_logger(__name__)

ibkr_bp = Blueprint('ibkr', __name__)

# Global client instance
_client: IBKRClient = None


def _get_client() -> IBKRClient:
    """Get current client instance."""
    global _client
    if _client is None:
        _client = get_ibkr_client()
    return _client


# ==================== Connection Management ====================

@ibkr_bp.route('/status', methods=['GET'])
def get_status():
    """
    Get connection status.
    
    GET /api/ibkr/status
    """
    try:
        client = _get_client()
        return jsonify({
            "success": True,
            "data": client.get_connection_status()
        })
    except Exception as e:
        logger.error(f"Get status failed: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@ibkr_bp.route('/connect', methods=['POST'])
def connect():
    """
    Connect to TWS / IB Gateway.
    
    POST /api/ibkr/connect
    Body: {
        "host": "127.0.0.1",      // Optional, default 127.0.0.1
        "port": 7497,             // Optional, TWS Live:7497, TWS Paper:7496, Gateway Live:4001, Gateway Paper:4002
        "clientId": 1,            // Optional, default 1
        "account": "",            // Optional, specify for multi-account
        "readonly": false         // Optional, readonly mode
    }
    """
    global _client
    
    try:
        data = request.get_json() or {}
        
        # Build config
        config = IBKRConfig(
            host=data.get('host', '127.0.0.1'),
            port=int(data.get('port', 7497)),
            client_id=int(data.get('clientId', 1)),
            account=data.get('account', ''),
            readonly=data.get('readonly', False),
        )
        
        # Disconnect existing connection
        if _client is not None and _client.connected:
            _client.disconnect()
        
        # Create new client and connect
        _client = IBKRClient(config)
        success = _client.connect()
        
        if success:
            return jsonify({
                "success": True,
                "message": "Connected successfully",
                "data": _client.get_connection_status()
            })
        else:
            return jsonify({
                "success": False,
                "error": "Connection failed. Please check if TWS/Gateway is running."
            }), 400
            
    except ImportError as e:
        return jsonify({
            "success": False,
            "error": "ib_insync not installed. Run: pip install ib_insync"
        }), 500
    except Exception as e:
        logger.error(f"Connection failed: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@ibkr_bp.route('/disconnect', methods=['POST'])
def disconnect():
    """
    Disconnect from IBKR.
    
    POST /api/ibkr/disconnect
    """
    global _client
    
    try:
        if _client is not None:
            _client.disconnect()
            _client = None
        
        reset_ibkr_client()
        
        return jsonify({
            "success": True,
            "message": "Disconnected"
        })
    except Exception as e:
        logger.error(f"Disconnect failed: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ==================== Account Queries ====================

@ibkr_bp.route('/account', methods=['GET'])
def get_account():
    """
    Get account information.
    
    GET /api/ibkr/account
    """
    try:
        client = _get_client()
        if not client.connected:
            return jsonify({
                "success": False,
                "error": "Not connected to IBKR"
            }), 400
        
        return jsonify({
            "success": True,
            "data": client.get_account_summary()
        })
    except Exception as e:
        logger.error(f"Get account info failed: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@ibkr_bp.route('/positions', methods=['GET'])
def get_positions():
    """
    Get positions.
    
    GET /api/ibkr/positions
    """
    try:
        client = _get_client()
        if not client.connected:
            return jsonify({
                "success": False,
                "error": "Not connected to IBKR"
            }), 400
        
        positions = client.get_positions()
        return jsonify({
            "success": True,
            "data": positions
        })
    except Exception as e:
        logger.error(f"Get positions failed: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@ibkr_bp.route('/orders', methods=['GET'])
def get_orders():
    """
    Get open orders.
    
    GET /api/ibkr/orders
    """
    try:
        client = _get_client()
        if not client.connected:
            return jsonify({
                "success": False,
                "error": "Not connected to IBKR"
            }), 400
        
        orders = client.get_open_orders()
        return jsonify({
            "success": True,
            "data": orders
        })
    except Exception as e:
        logger.error(f"Get orders failed: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ==================== Trading ====================

@ibkr_bp.route('/order', methods=['POST'])
def place_order():
    """
    Place an order.
    
    POST /api/ibkr/order
    Body: {
        "symbol": "AAPL",         // Required, symbol code
        "side": "buy",            // Required, buy or sell
        "quantity": 10,           // Required, number of shares
        "marketType": "USStock",  // Optional, default USStock
        "orderType": "market",    // Optional, market or limit, default market
        "price": 150.00           // Required for limit orders
    }
    """
    try:
        client = _get_client()
        if not client.connected:
            return jsonify({
                "success": False,
                "error": "Not connected to IBKR"
            }), 400
        
        data = request.get_json() or {}
        
        # Validate parameters
        symbol = data.get('symbol')
        side = data.get('side')
        quantity = data.get('quantity')
        
        if not symbol:
            return jsonify({"success": False, "error": "Missing symbol"}), 400
        if not side or side.lower() not in ('buy', 'sell'):
            return jsonify({"success": False, "error": "side must be buy or sell"}), 400
        if not quantity or float(quantity) <= 0:
            return jsonify({"success": False, "error": "quantity must be > 0"}), 400
        
        market_type = data.get('marketType', 'USStock')
        order_type = data.get('orderType', 'market').lower()
        
        # Place order
        if order_type == 'limit':
            price = data.get('price')
            if not price or float(price) <= 0:
                return jsonify({"success": False, "error": "Limit order requires price"}), 400
            
            result = client.place_limit_order(
                symbol=symbol,
                side=side,
                quantity=float(quantity),
                price=float(price),
                market_type=market_type
            )
        else:
            result = client.place_market_order(
                symbol=symbol,
                side=side,
                quantity=float(quantity),
                market_type=market_type
            )
        
        if result.success:
            return jsonify({
                "success": True,
                "message": result.message,
                "data": {
                    "orderId": result.order_id,
                    "filled": result.filled,
                    "avgPrice": result.avg_price,
                    "status": result.status,
                    "raw": result.raw
                }
            })
        else:
            return jsonify({
                "success": False,
                "error": result.message
            }), 400
            
    except Exception as e:
        logger.error(f"Place order failed: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@ibkr_bp.route('/order/<int:order_id>', methods=['DELETE'])
def cancel_order(order_id: int):
    """
    Cancel an order.
    
    DELETE /api/ibkr/order/<order_id>
    """
    try:
        client = _get_client()
        if not client.connected:
            return jsonify({
                "success": False,
                "error": "Not connected to IBKR"
            }), 400
        
        success = client.cancel_order(order_id)
        
        if success:
            return jsonify({
                "success": True,
                "message": f"Order {order_id} cancelled"
            })
        else:
            return jsonify({
                "success": False,
                "error": f"Order {order_id} not found"
            }), 404
            
    except Exception as e:
        logger.error(f"Cancel order failed: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ==================== Market Data ====================

@ibkr_bp.route('/quote', methods=['GET'])
def get_quote():
    """
    Get real-time quote.
    
    GET /api/ibkr/quote?symbol=AAPL&marketType=USStock
    """
    try:
        client = _get_client()
        if not client.connected:
            return jsonify({
                "success": False,
                "error": "Not connected to IBKR"
            }), 400
        
        symbol = request.args.get('symbol')
        market_type = request.args.get('marketType', 'USStock')
        
        if not symbol:
            return jsonify({"success": False, "error": "Missing symbol"}), 400
        
        quote = client.get_quote(symbol, market_type)
        return jsonify(quote)
        
    except Exception as e:
        logger.error(f"Get quote failed: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
