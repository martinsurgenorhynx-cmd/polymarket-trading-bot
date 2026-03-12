# QuantDinger 完整业务流程指南

## 概述

本文档说明如何使用 QuantDinger 的完整业务流程，包括数据获取、策略生成、回测和AI分析。

## 已修复的问题

### 1. ✅ K线数据字段名
- **问题**: 代码中使用 `timestamp` 字段，实际是 `time` 字段
- **修复**: 所有K线数据访问改为使用 `time` 字段
- **影响**: `complete_workflow_test.py` 中的数据展示部分

### 2. ✅ K线服务方法名
- **问题**: 使用 `get_klines()` 方法，实际是 `get_kline()`
- **修复**: 更正方法名
- **参数**: `timeframe` 而不是 `interval`

### 3. ✅ 安全执行函数名
- **问题**: 使用 `safe_exec()`，实际是 `safe_exec_code()`
- **修复**: 更正函数名
- **影响**: `simple_test.py`

### 4. ✅ 回测服务方法名
- **问题**: 使用 `run_backtest()`，实际是 `run()`
- **修复**: 更正方法名和参数格式

### 5. ✅ 环境变量加载
- **问题**: `.env` 文件加载不稳定
- **修复**: 使用绝对路径加载 `.env` 文件

## 业务流程说明

### 流程1: 数据获取

```python
from app.data_sources.factory import DataSourceFactory

factory = DataSourceFactory()
crypto_source = factory.get_source('Crypto')

# 获取K线数据
klines = crypto_source.get_kline(
    symbol='BTC/USDT',
    timeframe='1h',  # 注意：是 timeframe 不是 interval
    limit=100
)

# K线数据格式
# {
#     'time': 1234567890,  # Unix时间戳（秒）
#     'open': 50000.0,
#     'high': 51000.0,
#     'low': 49000.0,
#     'close': 50500.0,
#     'volume': 1000.0
# }
```

### 流程2: K线数据可视化

```python
import pandas as pd

# 转换为DataFrame
df = pd.DataFrame(klines)
df['datetime'] = pd.to_datetime(df['time'], unit='s')

# 计算技术指标
df['ma5'] = df['close'].rolling(window=5).mean()
df['ma20'] = df['close'].rolling(window=20).mean()

# RSI
delta = df['close'].diff()
gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
rs = gain / loss
df['rsi'] = 100 - (100 / (1 + rs))

# MACD
exp1 = df['close'].ewm(span=12, adjust=False).mean()
exp2 = df['close'].ewm(span=26, adjust=False).mean()
df['macd'] = exp1 - exp2
df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
```

### 流程3: 策略生成

```python
from app.services.strategy_compiler import StrategyCompiler

compiler = StrategyCompiler()

# 策略配置
strategy_config = {
    'name': 'MA交叉策略',
    'position_config': {
        'mode': 'percent',
        'size': 50  # 50%仓位
    },
    'risk_management': {
        'stop_loss_pct': 2.0,
        'take_profit_pct': 5.0
    },
    'rules': [
        {
            'type': 'entry',
            'direction': 'long',
            'conditions': [
                {
                    'indicator': 'ma',
                    'params': {'period': 5},
                    'operator': '>',
                    'compare_to': 'ma',
                    'compare_params': {'period': 20}
                }
            ]
        }
    ]
}

# 编译策略
strategy_code = compiler.compile(strategy_config)
```

### 流程4: 回测执行

**注意**: 回测服务需要的是指标代码（生成买卖信号），而不是完整的策略代码。

```python
from app.services.backtest import BacktestService
from datetime import datetime

# 指标代码示例（生成买卖信号）
indicator_code = """
# 计算均线
df['ma5'] = df['close'].rolling(window=5).mean()
df['ma20'] = df['close'].rolling(window=20).mean()

# 生成信号
df['buy'] = (df['ma5'] > df['ma20']) & (df['ma5'].shift(1) <= df['ma20'].shift(1))
df['sell'] = (df['ma5'] < df['ma20']) & (df['ma5'].shift(1) >= df['ma20'].shift(1))
"""

backtest_service = BacktestService()

result = backtest_service.run(
    indicator_code=indicator_code,  # 注意：是指标代码，不是完整策略代码
    market='Crypto',
    symbol='BTC/USDT',
    timeframe='1h',
    start_date=datetime(2024, 1, 1),
    end_date=datetime(2024, 1, 31),
    initial_capital=10000,
    commission=0.001,
    leverage=1
)

# 结果包含
# - total_return: 总收益率
# - sharpe_ratio: 夏普比率
# - max_drawdown: 最大回撤
# - trades: 交易记录
# - equity_curve: 资金曲线
```

### 流程5: AI市场分析

```python
from app.services.fast_analysis import get_fast_analysis_service

analysis_service = get_fast_analysis_service()

result = analysis_service.analyze(
    market='Crypto',
    symbol='BTC/USDT',
    language='zh-CN',
    timeframe='1D'
)

# 结果包含
# - decision: BUY/SELL/HOLD
# - confidence: 置信度 (0-100)
# - summary: 分析摘要
# - trading_plan: 交易计划（入场、止损、止盈价格）
# - reasons: 关键原因
# - risks: 风险提示
# - scores: 技术面/基本面/情绪面评分
```

## 已知限制

### 1. 策略编译器 vs 回测服务

- **策略编译器**: 生成完整的可执行策略代码（包含参数、逻辑、输出等）
- **回测服务**: 需要指标代码（只生成 `df['buy']` 和 `df['sell']` 信号）

这两者的代码格式不同，不能直接互换使用。

### 2. FastAnalysisService Bug

在 `backend_api_python/app/services/fast_analysis.py:71` 有一个bug：

```python
raw_indicators = self.tools.calculate_technical_indicators(kline_data)
```

`self.tools` 从未初始化，这一行应该删除。但由于后续代码已经手动计算了所有指标，所以不影响实际使用。

### 3. LLM API配置

AI分析功能需要配置LLM API密钥：

```bash
# .env 文件
LLM_PROVIDER=openai
OPENAI_API_KEY=your_api_key_here
OPENAI_BASE_URL=https://api.openai.com/v1
```

当前配置使用阿里云DashScope，但API密钥未配置，导致分析失败。

### 4. 数据源配置

某些数据源可能需要API密钥才能获取实时数据。当前使用的是免费数据源，可能有延迟。

## 测试脚本

### simple_test.py
测试所有核心服务是否正常工作。

```bash
python simple_test.py
```

### complete_workflow_test.py
完整的端到端业务流程测试。

```bash
python complete_workflow_test.py
```

## 交互式调试

```bash
# 进入交互模式
python -i simple_test.py

# 然后可以直接使用
>>> from app.utils.db import get_db_connection
>>> with get_db_connection() as db:
...     cur = db.cursor()
...     cur.execute("SELECT * FROM qd_users")
...     print(cur.fetchall())
...     cur.close()
```

## 正确的函数/方法名总结

| 错误的名称 | 正确的名称 | 位置 |
|-----------|-----------|------|
| `get_klines()` | `get_kline()` | CryptoDataSource |
| `safe_exec()` | `safe_exec_code()` | app.utils.safe_exec |
| `get_kline_service()` | `KlineService` | app.services.kline |
| `run_backtest()` | `run()` | BacktestService |
| `interval` 参数 | `timeframe` 参数 | get_kline() |
| `timestamp` 字段 | `time` 字段 | K线数据 |

## 下一步

1. **修复 FastAnalysisService bug**
   - 删除 `self.tools.calculate_technical_indicators` 这一行

2. **配置LLM API**
   - 设置正确的 `OPENAI_API_KEY`

3. **理解策略代码格式**
   - 策略编译器生成的代码用于前端展示和手动执行
   - 回测服务需要的是简单的指标代码

4. **配置数据源**
   - 如需实时数据，配置相应的API密钥

## 参考文档

- `DEBUG_GUIDE.md` - 调试指南
- `TEST_RESULTS.md` - 测试结果
- `DEVELOPMENT_SUMMARY.md` - 开发环境总结
- `LOCAL_SETUP_GUIDE.md` - 本地设置指南
