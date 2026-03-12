# MetaTrader 5 (MT5) 外汇实盘交易指南

QuantDinger 支持通过 MetaTrader 5 终端进行外汇实盘交易。

## 概述

此功能可通过您的 MetaTrader 5 账户实现外汇的自动化交易执行。配置完成后，您的交易策略可以通过 MT5 API 自动下单。

## 前置条件

- MetaTrader 5 外汇账户
- 已安装 MT5 终端（仅支持 Windows）
- 已订阅市场数据（用于实时报价）

## 安装

`MetaTrader5` 库已包含在 `requirements.txt` 中。如需手动安装：

```bash
pip install MetaTrader5
```

> **注意**：MetaTrader5 Python 库仅支持 Windows 平台。Linux/Mac 部署请考虑使用 Windows VM 或远程 Windows 服务器。

## MT5 终端配置

1. 从您的券商或[官网](https://www.metatrader5.com/)下载并安装 MetaTrader 5
2. 登录您的交易账户
3. 进入 **工具** → **选项** → **智能交易系统**
4. 启用：
   - ✅ 允许自动交易
   - ✅ 允许 DLL 导入（可选，某些功能可能需要）
5. 点击 确定

## 策略配置

创建外汇策略时，在"实盘交易"部分配置 MT5 连接：

| 字段 | 说明 | 示例 |
|------|------|------|
| **外汇券商** | 选择"MetaTrader 5" | - |
| **服务器** | 券商服务器名称 | `ICMarkets-Demo` |
| **账户号** | MT5 登录账号 | `12345678` |
| **密码** | MT5 密码 | `****` |
| **MT5 终端路径** | 终端路径（可选） | `C:\Program Files\MetaTrader 5\terminal64.exe` |

> **注意**：如果 MT5 终端安装在默认位置，可以留空"MT5 终端路径"字段。只有在自定义安装位置时才需要填写完整路径。

## 代码格式

| 市场 | 格式 | 示例 |
|------|------|------|
| 外汇 | 货币对 | `EURUSD`, `GBPUSD`, `USDJPY` |
| 贵金属 | XAU/XAG 对 | `XAUUSD`, `XAGUSD` |
| 指数 | CFD 代码 | `US30`, `US500`, `DE40` |

> **注意**：代码名称可能因券商而异。部分券商使用后缀，如 `EURUSDm`、`EURUSD.raw` 等。请查看您券商的代码列表。

## 手数参考

| 类型 | 单位 | 示例 |
|------|------|------|
| 标准手 | 100,000 | 1.0 手 = 100,000 EUR |
| 迷你手 | 10,000 | 0.1 手 = 10,000 EUR |
| 微手 | 1,000 | 0.01 手 = 1,000 EUR |

## 交易流程

```
策略信号 → 待执行订单队列 → MT5 执行 → 持仓更新
```

1. 您的策略生成买入/卖出信号
2. 信号作为待执行订单入队
3. 后台工作线程连接 MT5 并执行订单
4. 更新持仓和交易记录

## 支持的信号类型

| 信号 | 动作 | 说明 |
|------|------|------|
| `open_long` | 买入 | 开多仓 |
| `add_long` | 买入 | 加多仓 |
| `close_long` | 卖出 | 平多仓 |
| `reduce_long` | 卖出 | 减多仓 |
| `open_short` | 卖出 | 开空仓 |
| `add_short` | 卖出 | 加空仓 |
| `close_short` | 买入 | 平空仓 |
| `reduce_short` | 买入 | 减空仓 |

## API 接口

### 连接管理

```
GET  /api/mt5/status          # 获取连接状态
POST /api/mt5/connect         # 连接到 MT5 终端
POST /api/mt5/disconnect      # 断开连接
```

### 账户查询

```
GET  /api/mt5/account         # 账户信息
GET  /api/mt5/positions       # 当前持仓
GET  /api/mt5/orders          # 未成交订单
GET  /api/mt5/symbols         # 可用代码列表
```

### 交易

```
POST   /api/mt5/order         # 下单
POST   /api/mt5/close         # 平仓
DELETE /api/mt5/order/<id>    # 撤单
```

### 行情数据

```
GET  /api/mt5/quote?symbol=EURUSD
```

## 使用示例

### 测试连接（通过 curl）

```bash
# 使用默认终端路径
curl -X POST http://localhost:5000/api/mt5/connect \
  -H "Content-Type: application/json" \
  -d '{"login": 12345678, "password": "your_password", "server": "ICMarkets-Demo"}'

# 指定自定义终端路径
curl -X POST http://localhost:5000/api/mt5/connect \
  -H "Content-Type: application/json" \
  -d '{"login": 12345678, "password": "your_password", "server": "ICMarkets-Demo", "terminal_path": "C:\\Program Files\\MetaTrader 5\\terminal64.exe"}'
```

### 下市价单

```bash
# 买入 0.1 手 EURUSD
curl -X POST http://localhost:5000/api/mt5/order \
  -H "Content-Type: application/json" \
  -d '{"symbol": "EURUSD", "side": "buy", "volume": 0.1}'

# 卖出 0.5 手 XAUUSD
curl -X POST http://localhost:5000/api/mt5/order \
  -H "Content-Type: application/json" \
  -d '{"symbol": "XAUUSD", "side": "sell", "volume": 0.5}'
```

### 下限价单

```bash
curl -X POST http://localhost:5000/api/mt5/order \
  -H "Content-Type: application/json" \
  -d '{"symbol": "EURUSD", "side": "buy", "volume": 0.1, "orderType": "limit", "price": 1.0800}'
```

### 平仓

```bash
curl -X POST http://localhost:5000/api/mt5/close \
  -H "Content-Type: application/json" \
  -d '{"ticket": 123456789}'
```

## 重要说明

1. **MT5 终端必须运行**：交易前确保 MT5 终端已打开并登录
2. **仅支持 Windows**：MetaTrader5 Python 库仅支持 Windows
3. **券商代码名称**：代码名称因券商而异，请查看您券商的代码列表
4. **先使用模拟账户**：使用真实资金前，请先用模拟账户测试
5. **交易时间**：外汇 24/5 交易，其他品种请查看具体交易时间
6. **杠杆**：外汇交易使用杠杆，请注意保证金要求

## 常见问题排查

| 错误 | 原因 | 解决方案 |
|------|------|----------|
| ImportError | MetaTrader5 未安装 | `pip install MetaTrader5` |
| ImportError | 非 Windows 系统 | 使用 Windows 机器或 VM |
| 连接失败 | 终端未运行 | 启动 MT5 并登录 |
| 连接失败 | 凭证错误 | 验证登录账号/密码/服务器 |
| 代码未找到 | 无效代码 | 查看券商的代码列表 |
| 交易被禁用 | 交易未启用 | 在 MT5 选项中启用自动交易 |
| 订单被拒绝 | 保证金不足 | 检查账户余额和保证金 |

## Docker 部署

在 Docker 中运行 QuantDinger 时，MT5 交易需要：

1. **Windows 主机**：Windows 上的 Docker Desktop 或 Windows Server
2. **主机上的 MT5**：在 Windows 主机上运行 MT5 终端
3. **网络访问**：容器必须能访问主机的 MT5 终端

对于 Linux/Mac 部署，请考虑：
- 在 Windows VM 上运行 QuantDinger 后端
- 使用远程 Windows 服务器进行 MT5 连接

## 安全建议

- 使用专用交易账户
- 先使用模拟账户测试
- 设置适当的手数和风险限制
- 定期监控您的持仓
- 保持 MT5 终端更新
- 使用强密码

## 参见

- [Python 策略开发指南](STRATEGY_DEV_GUIDE_CN.md)
- [MetaTrader 5 Python 文档](https://www.mql5.com/en/docs/python_metatrader5)
