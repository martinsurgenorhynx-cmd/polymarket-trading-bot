# 交易所支持矩阵

## 概览

QuantDinger 支持 **15+ 交易所/经纪商**，覆盖 **4 大资产类别**：

| 资产类别 | 交易所数量 | 主要交易所 |
|---------|-----------|-----------|
| 加密货币 | 10 | Binance, OKX, Bybit, Bitget |
| 美股 | 1 | Interactive Brokers (IBKR) |
| 外汇 | 1 | MetaTrader 5 (MT5) |
| 预测市场 | 0 | Polymarket (待开发) |

---

## 1. 加密货币交易所 (Crypto Exchanges)

### 1.1 Binance (币安)
**文件**: `binance.py`, `binance_spot.py`

| 品类 | 支持 | 说明 |
|-----|------|------|
| 现货 (Spot) | ✅ | BTC/USDT, ETH/USDT 等 |
| USDT 合约 (USDT-M Futures) | ✅ | 永续合约，支持杠杆 |
| 币本位合约 (COIN-M Futures) | ❌ | 未实现 |
| 期权 (Options) | ❌ | 未实现 |

**特性**:
- 支持模拟交易 (Demo Trading)
- 支持对冲模式 (Hedge Mode) 和单向模式 (One-way Mode)
- 自动处理精度和最小下单量
- 支持市价单、限价单

**配置示例**:
```json
{
  "exchange_id": "binance",
  "market_type": "swap",  // "spot" 或 "swap"
  "api_key": "your_api_key",
  "secret_key": "your_secret_key",
  "enable_demo_trading": false
}
```

---

### 1.2 OKX (欧易)
**文件**: `okx.py`

| 品类 | 支持 | 说明 |
|-----|------|------|
| 现货 (Spot) | ✅ | 通过 instType=SPOT |
| USDT 永续合约 (SWAP) | ✅ | 主要支持 |
| 交割合约 (Futures) | ✅ | 通过 instType=FUTURES |
| 期权 (Options) | ❌ | 未实现 |

**特性**:
- 支持逐仓 (isolated) 和全仓 (cross) 保证金模式
- 支持对冲模式 (long_short_mode) 和净持仓模式 (net_mode)
- 自动设置杠杆
- 支持市价单、限价单、止盈止损单

**配置示例**:
```json
{
  "exchange_id": "okx",
  "api_key": "your_api_key",
  "secret_key": "your_secret_key",
  "passphrase": "your_passphrase"
}
```

---

### 1.3 Bybit
**文件**: `bybit.py`

| 品类 | 支持 | 说明 |
|-----|------|------|
| 现货 (Spot) | ✅ | category=spot |
| USDT 永续合约 (Linear) | ✅ | category=linear |
| USDC 永续合约 | ✅ | category=linear |
| 反向合约 (Inverse) | ❌ | 未实现 |
| 期权 (Options) | ❌ | 未实现 |

**特性**:
- 使用 Bybit V5 API
- 支持统一账户 (Unified Trading Account)
- 自动处理精度和最小下单量
- 支持市价单、限价单

**配置示例**:
```json
{
  "exchange_id": "bybit",
  "market_type": "swap",  // "spot" 或 "swap"
  "api_key": "your_api_key",
  "secret_key": "your_secret_key",
  "category": "linear"
}
```

---

### 1.4 Bitget
**文件**: `bitget.py`, `bitget_spot.py`

| 品类 | 支持 | 说明 |
|-----|------|------|
| 现货 (Spot) | ✅ | BitgetSpotClient |
| USDT 永续合约 (Mix) | ✅ | BitgetMixClient |
| USDC 永续合约 | ✅ | 通过 Mix API |
| 币本位合约 | ❌ | 未实现 |

**特性**:
- 支持 Bitget 渠道 API 码 (channel_api_code)
- 支持对冲模式和单向模式
- 自动处理精度
- 支持市价单、限价单

**配置示例**:
```json
{
  "exchange_id": "bitget",
  "market_type": "swap",  // "spot" 或 "swap"
  "api_key": "your_api_key",
  "secret_key": "your_secret_key",
  "passphrase": "your_passphrase",
  "channel_api_code": "bntva"  // 仅现货需要
}
```

---

### 1.5 Coinbase Exchange
**文件**: `coinbase_exchange.py`

| 品类 | 支持 | 说明 |
|-----|------|------|
| 现货 (Spot) | ✅ | 仅支持现货 |
| 合约 | ❌ | 不支持 |

**特性**:
- 使用 Coinbase Advanced Trade API
- 支持限价单、市价单
- 自动处理精度

**配置示例**:
```json
{
  "exchange_id": "coinbase_exchange",
  "market_type": "spot",
  "api_key": "your_api_key",
  "secret_key": "your_secret_key",
  "passphrase": "your_passphrase"
}
```

---

### 1.6 Kraken (海妖)
**文件**: `kraken.py`, `kraken_futures.py`

| 品类 | 支持 | 说明 |
|-----|------|------|
| 现货 (Spot) | ✅ | KrakenClient |
| 期货 (Futures) | ✅ | KrakenFuturesClient |
| 永续合约 | ✅ | 通过 Futures API |

**特性**:
- 现货和期货使用不同的 API 端点
- 支持限价单、市价单
- 自动处理精度

**配置示例**:
```json
{
  "exchange_id": "kraken",
  "market_type": "spot",  // "spot" 或 "swap"
  "api_key": "your_api_key",
  "secret_key": "your_secret_key"
}
```

---

### 1.7 KuCoin (库币)
**文件**: `kucoin.py`

| 品类 | 支持 | 说明 |
|-----|------|------|
| 现货 (Spot) | ✅ | KucoinSpotClient |
| 永续合约 (Futures) | ✅ | KucoinFuturesClient |

**特性**:
- 现货和期货使用不同的 API 端点
- 支持限价单、市价单
- 需要 passphrase

**配置示例**:
```json
{
  "exchange_id": "kucoin",
  "market_type": "swap",  // "spot" 或 "swap"
  "api_key": "your_api_key",
  "secret_key": "your_secret_key",
  "passphrase": "your_passphrase"
}
```

---

### 1.8 Gate.io
**文件**: `gate.py`

| 品类 | 支持 | 说明 |
|-----|------|------|
| 现货 (Spot) | ✅ | GateSpotClient |
| USDT 永续合约 | ✅ | GateUsdtFuturesClient |
| 币本位合约 | ❌ | 未实现 |

**特性**:
- 支持限价单、市价单
- 自动处理精度

**配置示例**:
```json
{
  "exchange_id": "gate",
  "market_type": "swap",  // "spot" 或 "swap"
  "api_key": "your_api_key",
  "secret_key": "your_secret_key"
}
```

---

### 1.9 Bitfinex
**文件**: `bitfinex.py`

| 品类 | 支持 | 说明 |
|-----|------|------|
| 现货 (Spot) | ✅ | BitfinexClient |
| 衍生品 (Derivatives) | ✅ | BitfinexDerivativesClient |
| 永续合约 | ✅ | 通过 Derivatives API |

**特性**:
- 支持限价单、市价单
- 支持保证金交易

**配置示例**:
```json
{
  "exchange_id": "bitfinex",
  "market_type": "spot",  // "spot" 或 "swap"
  "api_key": "your_api_key",
  "secret_key": "your_secret_key"
}
```

---

### 1.10 Deepcoin
**文件**: `deepcoin.py`

| 品类 | 支持 | 说明 |
|-----|------|------|
| 现货 (Spot) | ✅ | market_type=spot |
| 永续合约 (Swap) | ✅ | market_type=swap |

**特性**:
- 支持限价单、市价单
- 需要 passphrase

**配置示例**:
```json
{
  "exchange_id": "deepcoin",
  "market_type": "swap",
  "api_key": "your_api_key",
  "secret_key": "your_secret_key",
  "passphrase": "your_passphrase"
}
```

---

## 2. 传统券商 (Traditional Brokers)

### 2.1 Interactive Brokers (IBKR)
**文件**: `app/services/ibkr_trading/client.py`

| 品类 | 支持 | 说明 |
|-----|------|------|
| 美股 (US Stocks) | ✅ | NYSE, NASDAQ 等 |
| 期权 (Options) | ❌ | 未实现 |
| 期货 (Futures) | ❌ | 未实现 |
| 外汇 (Forex) | ❌ | 未实现 |
| 债券 (Bonds) | ❌ | 未实现 |

**特性**:
- 使用 `ib_insync` 库
- 需要运行 TWS (Trader Workstation) 或 IB Gateway
- 支持实时行情
- 支持市价单、限价单
- 自动处理股票代码转换

**配置示例**:
```json
{
  "exchange_id": "ibkr",
  "ibkr_host": "127.0.0.1",
  "ibkr_port": 7497,  // TWS: 7497, Gateway: 4001
  "ibkr_client_id": 1,
  "ibkr_account": ""  // 留空自动选择
}
```

**依赖安装**:
```bash
pip install ib_insync
```

---

## 3. 外汇经纪商 (Forex Brokers)

### 3.1 MetaTrader 5 (MT5)
**文件**: `app/services/mt5_trading/client.py`

| 品类 | 支持 | 说明 |
|-----|------|------|
| 外汇 (Forex) | ✅ | EUR/USD, GBP/USD 等 |
| 黄金 (Gold) | ✅ | XAU/USD |
| 原油 (Oil) | ✅ | 通过 MT5 |
| 指数 (Indices) | ✅ | 通过 MT5 |
| 加密货币 | ✅ | 部分经纪商支持 |

**特性**:
- 使用 `MetaTrader5` Python 库
- 仅支持 Windows 系统
- 需要安装 MT5 终端
- 支持市价单、限价单、止损单
- 支持多种订单类型

**配置示例**:
```json
{
  "exchange_id": "mt5",
  "mt5_login": 12345678,
  "mt5_password": "your_password",
  "mt5_server": "ICMarkets-Demo",
  "mt5_terminal_path": ""  // 可选，自动检测
}
```

**依赖安装**:
```bash
pip install MetaTrader5  # 仅 Windows
```

---

## 4. 预测市场 (Prediction Markets)

### 4.1 Polymarket
**状态**: ❌ 未实现（仅有数据获取和 AI 分析）

| 品类 | 支持 | 说明 |
|-----|------|------|
| 预测市场 | ❌ | 待开发 |
| YES/NO 代币交易 | ❌ | 待开发 |

**当前功能**:
- ✅ 市场数据获取
- ✅ AI 分析和预测
- ✅ 机会评分
- ❌ 自动下单（待开发）

**计划实现**:
- 使用 `py-clob-client` SDK
- 支持 YES/NO 代币交易
- 支持限价单、市价单
- 自动结算

---

## 交易品类总结

### 按资产类别

| 资产类别 | 交易所 | 品类 |
|---------|-------|------|
| **加密货币** | Binance, OKX, Bybit, Bitget, Coinbase, Kraken, KuCoin, Gate, Bitfinex, Deepcoin | 现货、永续合约、交割合约 |
| **美股** | Interactive Brokers | 股票 |
| **外汇** | MetaTrader 5 | 外汇对、黄金、原油、指数 |
| **预测市场** | Polymarket (待开发) | YES/NO 代币 |

### 按交易类型

| 交易类型 | 支持的交易所 |
|---------|-------------|
| **现货 (Spot)** | Binance, OKX, Bybit, Bitget, Coinbase, Kraken, KuCoin, Gate, Bitfinex, Deepcoin |
| **永续合约 (Perpetual Swap)** | Binance, OKX, Bybit, Bitget, Kraken, KuCoin, Gate, Bitfinex, Deepcoin |
| **交割合约 (Futures)** | OKX, Kraken, KuCoin |
| **股票 (Stocks)** | Interactive Brokers |
| **外汇 (Forex)** | MetaTrader 5 |
| **预测市场 (Prediction)** | Polymarket (待开发) |

---

## 交易功能对比

| 功能 | 加密货币 | 美股 (IBKR) | 外汇 (MT5) | 预测市场 |
|-----|---------|------------|-----------|---------|
| 市价单 | ✅ | ✅ | ✅ | ❌ |
| 限价单 | ✅ | ✅ | ✅ | ❌ |
| 止损单 | ✅ | ✅ | ✅ | ❌ |
| 止盈单 | ✅ | ✅ | ✅ | ❌ |
| 杠杆交易 | ✅ | ❌ | ✅ | ❌ |
| 做空 | ✅ | ✅ | ✅ | ❌ |
| 对冲模式 | ✅ | ❌ | ✅ | ❌ |
| 模拟交易 | ✅ (部分) | ✅ | ✅ | ❌ |

---

## 使用示例

### 1. 创建加密货币客户端
```python
from app.services.live_trading.factory import create_client

# Binance 永续合约
config = {
    "exchange_id": "binance",
    "market_type": "swap",
    "api_key": "your_api_key",
    "secret_key": "your_secret_key"
}
client = create_client(config, market_type="swap")

# 下市价单
result = client.place_market_order(
    symbol="BTCUSDT",
    side="buy",
    size=0.001
)
```

### 2. 创建美股客户端
```python
# Interactive Brokers
config = {
    "exchange_id": "ibkr",
    "ibkr_host": "127.0.0.1",
    "ibkr_port": 7497,
    "ibkr_client_id": 1
}
client = create_client(config)

# 下限价单
result = client.place_limit_order(
    symbol="AAPL",
    side="buy",
    size=10,
    price=150.00
)
```

### 3. 创建外汇客户端
```python
# MetaTrader 5
config = {
    "exchange_id": "mt5",
    "mt5_login": 12345678,
    "mt5_password": "password",
    "mt5_server": "ICMarkets-Demo"
}
client = create_client(config)

# 下市价单
result = client.place_market_order(
    symbol="EURUSD",
    side="buy",
    size=0.1  # 0.1 lot
)
```

---

## 开发路线图

### 已完成 ✅
- 10 个加密货币交易所
- Interactive Brokers (美股)
- MetaTrader 5 (外汇)
- 统一的交易接口
- 自动精度处理
- 订单管理和持仓跟踪

### 进行中 🚧
- Polymarket 交易对接

### 计划中 📋
- 更多传统券商支持
- 期权交易
- 算法交易策略
- 风险管理工具
- 回测引擎优化

---

## 相关文件

- `app/services/live_trading/factory.py` - 交易所工厂类
- `app/services/live_trading/base.py` - 基础客户端接口
- `app/services/live_trading/execution.py` - 交易执行逻辑
- `app/services/live_trading/records.py` - 交易记录管理
- `app/services/pending_order_worker.py` - 待处理订单后台任务
- `POLYMARKET_TRADING_ANALYSIS.md` - Polymarket 交易分析
