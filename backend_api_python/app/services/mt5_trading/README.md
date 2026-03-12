# MetaTrader 5 Trading Module

Supports forex and CFD trading via MetaTrader 5 terminal.

## Requirements

- **Windows platform** (MT5 Python library is Windows-only)
- MetaTrader 5 terminal installed
- MT5 account with a broker

## Installation

```bash
pip install MetaTrader5
```

Or the dependency is already in `requirements.txt`.

## MT5 Terminal Configuration

1. Download and install MetaTrader 5 from your broker or [official website](https://www.metatrader5.com/)
2. Login to your trading account
3. Go to **Tools** → **Options** → **Expert Advisors**
4. Enable:
   - ✅ Allow algorithmic trading
   - ✅ Allow DLL imports (optional, may be needed for some features)
5. Click OK

## Strategy Configuration

When creating a forex strategy, configure the MT5 connection in the "Live Trading" section:

| Field | Description | Example |
|-------|-------------|---------|
| **Broker** | Select "MetaTrader 5" | - |
| **Server** | Broker server name | `ICMarkets-Demo` |
| **Account** | MT5 login number | `12345678` |
| **Password** | MT5 password | `****` |

## Symbol Format

| Market | Format | Examples |
|--------|--------|----------|
| Forex | Currency pair | `EURUSD`, `GBPUSD`, `USDJPY` |
| Metals | XAU/XAG pairs | `XAUUSD`, `XAGUSD` |
| Indices | CFD symbols | `US30`, `US500`, `DE40` |
| Crypto | Symbol pairs | `BTCUSD`, `ETHUSD` |

> **Note**: Symbol names may vary by broker. Some brokers use suffixes like `EURUSDm`, `EURUSD.raw`, etc.

## Lot Size Reference

| Type | Units | Example |
|------|-------|---------|
| Standard Lot | 100,000 | 1.0 lot = 100,000 EUR |
| Mini Lot | 10,000 | 0.1 lot = 10,000 EUR |
| Micro Lot | 1,000 | 0.01 lot = 1,000 EUR |

## API Endpoints

### Connection Management

```
GET  /api/mt5/status          # Get connection status
POST /api/mt5/connect         # Connect to MT5 terminal
POST /api/mt5/disconnect      # Disconnect
```

### Account Queries

```
GET  /api/mt5/account         # Account information
GET  /api/mt5/positions       # Open positions
GET  /api/mt5/orders          # Pending orders
GET  /api/mt5/symbols         # Available symbols
```

### Trading

```
POST   /api/mt5/order         # Place order
POST   /api/mt5/close         # Close position
DELETE /api/mt5/order/<id>    # Cancel pending order
```

### Market Data

```
GET  /api/mt5/quote?symbol=EURUSD
```

## Usage Examples

### Connect

```bash
curl -X POST http://localhost:5000/api/mt5/connect \
  -H "Content-Type: application/json" \
  -d '{"login": 12345678, "password": "your_password", "server": "ICMarkets-Demo"}'
```

### Place Market Order

```bash
# Buy 0.1 lot EURUSD
curl -X POST http://localhost:5000/api/mt5/order \
  -H "Content-Type: application/json" \
  -d '{"symbol": "EURUSD", "side": "buy", "volume": 0.1}'

# Sell 0.5 lot XAUUSD
curl -X POST http://localhost:5000/api/mt5/order \
  -H "Content-Type: application/json" \
  -d '{"symbol": "XAUUSD", "side": "sell", "volume": 0.5}'
```

### Place Limit Order

```bash
curl -X POST http://localhost:5000/api/mt5/order \
  -H "Content-Type: application/json" \
  -d '{"symbol": "EURUSD", "side": "buy", "volume": 0.1, "orderType": "limit", "price": 1.0800}'
```

### Close Position

```bash
curl -X POST http://localhost:5000/api/mt5/close \
  -H "Content-Type: application/json" \
  -d '{"ticket": 123456789}'
```

## Important Notes

1. **MT5 terminal must be running**: The terminal must be open and logged in
2. **Windows only**: The MetaTrader5 Python library only works on Windows
3. **Broker symbol names**: Symbol names vary by broker, check your broker's symbol list
4. **Demo account first**: Test with a demo account before using real funds
5. **Market hours**: Forex trades 24/5, check specific market hours for other instruments

## Troubleshooting

| Error | Cause | Solution |
|-------|-------|----------|
| ImportError | MetaTrader5 not installed | `pip install MetaTrader5` |
| ImportError | Not on Windows | Use a Windows machine or VM |
| Connection failed | Terminal not running | Start MT5 and login |
| Connection failed | Wrong credentials | Verify login/password/server |
| Symbol not found | Invalid symbol | Check broker's symbol list |
| Trade not allowed | Trading disabled | Enable algo trading in MT5 options |

## Security Recommendations

- Use a dedicated trading account
- Test with demo account first
- Set appropriate lot sizes and risk limits
- Monitor positions regularly
- Keep MT5 terminal updated

## Removing This Module

To remove this module, delete:

```
backend_api_python/app/services/mt5_trading/    # Entire directory
backend_api_python/app/routes/mt5.py            # Route file
```

Then remove the related import and registration code in `app/routes/__init__.py`.

## See Also

- [Python Strategy Development Guide](../../docs/STRATEGY_DEV_GUIDE.md)
- [MetaTrader 5 Python Documentation](https://www.mql5.com/en/docs/python_metatrader5)
