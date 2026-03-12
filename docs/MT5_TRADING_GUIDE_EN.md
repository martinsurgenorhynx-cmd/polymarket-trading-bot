# MetaTrader 5 (MT5) Trading Guide

QuantDinger supports forex live trading via MetaTrader 5 terminal.

## Overview

This feature enables automated forex trading execution through your MetaTrader 5 account. Once configured, your trading strategies can automatically place orders via the MT5 API.

## Prerequisites

- MetaTrader 5 account with a forex broker
- MT5 terminal installed (Windows only)
- Market data subscription (for real-time quotes)

## Installation

The `MetaTrader5` library is already included in `requirements.txt`. If you need to install manually:

```bash
pip install MetaTrader5
```

> **Note**: The MetaTrader5 Python library only works on Windows. For Linux/Mac deployments, consider using a Windows VM or a remote Windows server.

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
| **Forex Broker** | Select "MetaTrader 5" | - |
| **Server** | Broker server name | `ICMarkets-Demo` |
| **Account Number** | MT5 login number | `12345678` |
| **Password** | MT5 password | `****` |
| **MT5 Terminal Path** | Terminal path (optional) | `C:\Program Files\MetaTrader 5\terminal64.exe` |

> **Note**: If MT5 terminal is installed in the default location, you can leave the "MT5 Terminal Path" field empty. Only fill in the full path if MT5 is installed in a custom location.

## Symbol Format

| Market | Format | Examples |
|--------|--------|----------|
| Forex | Currency pair | `EURUSD`, `GBPUSD`, `USDJPY` |
| Metals | XAU/XAG pairs | `XAUUSD`, `XAGUSD` |
| Indices | CFD symbols | `US30`, `US500`, `DE40` |

> **Note**: Symbol names may vary by broker. Some brokers use suffixes like `EURUSDm`, `EURUSD.raw`, etc. Check your broker's symbol list.

## Lot Size Reference

| Type | Units | Example |
|------|-------|---------|
| Standard Lot | 100,000 | 1.0 lot = 100,000 EUR |
| Mini Lot | 10,000 | 0.1 lot = 10,000 EUR |
| Micro Lot | 1,000 | 0.01 lot = 1,000 EUR |

## Trading Flow

```
Strategy Signal → Pending Order Queue → MT5 Execution → Position Update
```

1. Your strategy generates a buy/sell signal
2. The signal is queued as a pending order
3. The background worker connects to MT5 and executes the order
4. Position and trade records are updated

## Supported Signal Types

| Signal | Action | Description |
|--------|--------|-------------|
| `open_long` | BUY | Open a long position |
| `add_long` | BUY | Add to existing long position |
| `close_long` | SELL | Close long position |
| `reduce_long` | SELL | Reduce long position |
| `open_short` | SELL | Open a short position |
| `add_short` | SELL | Add to existing short position |
| `close_short` | BUY | Close short position |
| `reduce_short` | BUY | Reduce short position |

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

### Test Connection (via curl)

```bash
# Using default terminal path
curl -X POST http://localhost:5000/api/mt5/connect \
  -H "Content-Type: application/json" \
  -d '{"login": 12345678, "password": "your_password", "server": "ICMarkets-Demo"}'

# With custom terminal path
curl -X POST http://localhost:5000/api/mt5/connect \
  -H "Content-Type: application/json" \
  -d '{"login": 12345678, "password": "your_password", "server": "ICMarkets-Demo", "terminal_path": "C:\\Program Files\\MetaTrader 5\\terminal64.exe"}'
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

1. **MT5 terminal must be running**: The terminal must be open and logged in before trading
2. **Windows only**: The MetaTrader5 Python library only works on Windows
3. **Broker symbol names**: Symbol names vary by broker, check your broker's symbol list
4. **Demo account first**: Test with a demo account before using real funds
5. **Market hours**: Forex trades 24/5, check specific market hours for other instruments
6. **Leverage**: Forex trading uses leverage. Be aware of margin requirements

## Troubleshooting

| Error | Cause | Solution |
|-------|-------|----------|
| ImportError | MetaTrader5 not installed | `pip install MetaTrader5` |
| ImportError | Not on Windows | Use a Windows machine or VM |
| Connection failed | Terminal not running | Start MT5 and login |
| Connection failed | Wrong credentials | Verify login/password/server |
| Symbol not found | Invalid symbol | Check broker's symbol list |
| Trade not allowed | Trading disabled | Enable algo trading in MT5 options |
| Order rejected | Insufficient margin | Check account balance and margin |

## Docker Deployment

When running QuantDinger in Docker, MT5 trading requires:

1. **Windows host**: Docker Desktop on Windows, or Windows Server
2. **MT5 on host**: Run MT5 terminal on the Windows host
3. **Network access**: Container must be able to access the host's MT5 terminal

For Linux/Mac deployments, consider:
- Running QuantDinger backend on a Windows VM
- Using a remote Windows server for MT5 connection

## Security Recommendations

- Use a dedicated trading account
- Test with demo account first
- Set appropriate lot sizes and risk limits
- Monitor positions regularly
- Keep MT5 terminal updated
- Use strong passwords

## See Also

- [Python Strategy Development Guide](STRATEGY_DEV_GUIDE.md)
- [MetaTrader 5 Python Documentation](https://www.mql5.com/en/docs/python_metatrader5)
