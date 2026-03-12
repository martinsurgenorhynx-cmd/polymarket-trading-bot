# QuantDinger 本地调试指南

无需启动服务器，直接调试和测试代码。

## 快速开始

### 1. 运行简单测试

```bash
cd backend_api_python
python simple_test.py
```

这会测试所有核心服务是否正常工作。

### 2. 交互式调试

```bash
python -i simple_test.py
```

进入交互模式后，可以直接使用已导入的模块：

```python
# 查询数据库
from app.utils.db import get_db_connection
with get_db_connection() as db:
    cur = db.cursor()
    cur.execute("SELECT * FROM qd_users")
    print(cur.fetchall())
    cur.close()

# 使用用户服务
from app.services.user_service import get_user_service
service = get_user_service()
user = service.get_user_by_username('quantdinger')
print(user)

# 编译策略
from app.services.strategy_compiler import StrategyCompiler
compiler = StrategyCompiler()
config = {'name': '测试', 'position_config': {'mode': 'fixed', 'size': 1}, 'rules': []}
code = compiler.compile(config)
print(code[:500])
```

## 可用的调试脚本

### simple_test.py
最简单的测试脚本，测试所有核心服务。

```bash
python simple_test.py
```

### debug_examples.py
交互式调试工具，提供多个测试选项。

```bash
python debug_examples.py
```

选项：
- 1. 数据库连接测试
- 2. 用户服务测试
- 3. 策略编译器测试
- 4. 安全执行环境测试
- 5. 指标计算测试
- 6. 策略执行逻辑测试
- 7. K线数据服务测试
- 8. 回测服务测试
- 0. 运行所有测试

### examples/test_database.py
数据库查询示例。

```bash
python examples/test_database.py
```

显示：
- 所有表的行数
- 用户列表
- 策略列表（如果有）
- 回测结果（如果有）

## 核心服务使用示例

### 1. 数据库操作

```python
from app.utils.db import get_db_connection

with get_db_connection() as db:
    cur = db.cursor()
    
    # 查询
    cur.execute("SELECT * FROM qd_users WHERE username = ?", ('quantdinger',))
    user = cur.fetchone()
    print(user)
    
    # 插入（如果需要）
    # cur.execute("INSERT INTO table_name (...) VALUES (...)", (...))
    # db.commit()
    
    cur.close()
```

### 2. 用户服务

```python
from app.services.user_service import get_user_service

service = get_user_service()

# 获取用户
user = service.get_user_by_username('quantdinger')
user = service.get_user_by_id(1)
user = service.get_user_by_email('user@example.com')

# 认证
user = service.authenticate('quantdinger', '123456')

# 创建用户
user_id = service.create_user(
    username='newuser',
    password='password123',
    email='new@example.com',
    role='user'
)
```

### 3. 策略编译

```python
from app.services.strategy_compiler import StrategyCompiler

compiler = StrategyCompiler()

config = {
    'name': '我的策略',
    'position_config': {
        'mode': 'fixed',  # 或 'percent'
        'size': 1
    },
    'rules': [
        {
            'type': 'entry',
            'conditions': [
                {'indicator': 'close', 'operator': '>', 'value': 'ma20'}
            ]
        }
    ]
}

strategy_code = compiler.compile(config)
print(strategy_code)
```

### 4. 回测服务

```python
from app.services.backtest import BacktestService

service = BacktestService()

# 注意：需要有效的市场数据源
result = service.run_backtest(
    strategy_code="...",  # 策略代码
    market='Crypto',
    symbol='BTC/USDT',
    start_date='2024-01-01',
    end_date='2024-01-31',
    initial_capital=10000,
    timeframe='1h'
)

print(result)
```

### 5. 快速分析服务

```python
from app.services.fast_analysis import get_fast_analysis_service

service = get_fast_analysis_service()

# 注意：需要配置LLM和市场数据源
result = service.analyze(
    market='Crypto',
    symbol='BTC/USDT',
    language='zh-CN',
    timeframe='1D'
)

print(result)
```

### 6. 数据源

```python
from app.data_sources.factory import DataSourceFactory

factory = DataSourceFactory()

# 获取加密货币数据源
crypto_source = factory.get_source('Crypto')

# 获取K线数据
klines = crypto_source.get_klines(
    symbol='BTC/USDT',
    interval='1h',
    limit=100
)

print(klines)
```

## 常见调试场景

### 场景1: 测试策略逻辑

创建一个测试文件 `test_my_strategy.py`:

```python
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

# 你的策略代码
strategy_code = """
def initialize(context):
    context.symbol = 'BTCUSDT'

def handle_bar(context, bar_dict):
    print(f"价格: {bar_dict['close']}")
"""

# 编译并测试
from app.services.strategy_compiler import StrategyCompiler
# ... 测试逻辑
```

### 场景2: 查询和分析数据

```python
from app.utils.db import get_db_connection

with get_db_connection() as db:
    cur = db.cursor()
    
    # 查询最近的交易记录
    cur.execute("""
        SELECT * FROM qd_strategy_trades
        ORDER BY created_at DESC
        LIMIT 10
    """)
    
    trades = cur.fetchall()
    for trade in trades:
        print(trade)
    
    cur.close()
```

### 场景3: 测试指标计算

```python
import pandas as pd
import numpy as np

# 生成模拟数据
dates = pd.date_range('2024-01-01', periods=100, freq='1h')
prices = 100 + np.cumsum(np.random.randn(100))

df = pd.DataFrame({
    'timestamp': dates,
    'close': prices
})

# 计算MA
df['ma20'] = df['close'].rolling(window=20).mean()

# 计算RSI
delta = df['close'].diff()
gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
rs = gain / loss
df['rsi'] = 100 - (100 / (1 + rs))

print(df.tail())
```

## 调试技巧

### 1. 使用 IPython

```bash
pip install ipython
ipython
```

然后：

```python
%load_ext autoreload
%autoreload 2

import sys
sys.path.insert(0, '/path/to/backend_api_python')

from app.services.user_service import get_user_service
service = get_user_service()
```

### 2. 使用 pdb 调试器

在代码中添加断点：

```python
import pdb; pdb.set_trace()
```

### 3. 日志输出

```python
from app.utils.logger import get_logger

logger = get_logger(__name__)
logger.debug("调试信息")
logger.info("普通信息")
logger.warning("警告信息")
logger.error("错误信息")
```

### 4. 打印SQL查询

```python
from app.utils.db import get_db_connection

with get_db_connection() as db:
    cur = db.cursor()
    
    query = "SELECT * FROM qd_users WHERE id = ?"
    params = (1,)
    
    print(f"SQL: {query}")
    print(f"参数: {params}")
    
    cur.execute(query, params)
    result = cur.fetchone()
    print(f"结果: {result}")
    
    cur.close()
```

## 注意事项

1. **环境变量**: 确保 `.env` 文件配置正确
2. **数据库连接**: 确保 PostgreSQL 正在运行
3. **虚拟环境**: 使用 `source venv/bin/activate` 激活虚拟环境
4. **依赖包**: 确保所有依赖已安装 `pip install -r requirements.txt`
5. **数据源**: 某些功能需要配置外部数据源（API密钥等）

## 常见问题

### Q: 导入模块失败
A: 确保在脚本开头添加：
```python
import sys
sys.path.insert(0, '/path/to/backend_api_python')
```

### Q: 数据库连接失败
A: 检查 `.env` 中的 `DATABASE_URL` 配置

### Q: 缺少某些表
A: 某些表可能在新版本中被重命名或删除，检查实际的表结构

### Q: 数据源不可用
A: 配置相应的API密钥或使用模拟数据

## 更多资源

- [本地设置指南](LOCAL_SETUP_GUIDE.md)
- [快速开始](QUICK_START.md)
- [服务说明](app/services/README.md)
- [Worker指南](WORKERS_GUIDE.md)
