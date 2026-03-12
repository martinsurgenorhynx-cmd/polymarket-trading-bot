# 数据库表数据来源说明

## 概述

Dashboard 监控页面显示的数据来自 4 个核心表，这些表的数据由**策略执行引擎**在运行时写入。

---

## 📊 核心数据表

### 1. qd_strategies_trading - 策略配置表

**作用**: 存储用户创建的交易策略配置

**数据来源**: 用户通过前端创建/编辑策略

**写入时机**:
- 用户创建新策略
- 用户修改策略配置
- 用户启动/停止策略

**写入位置**:
- `app/routes/strategy.py` - 策略 CRUD API
  - `POST /api/strategy/create` - 创建策略
  - `PUT /api/strategy/update` - 更新策略
  - `POST /api/strategy/start` - 启动策略
  - `POST /api/strategy/stop` - 停止策略

**关键字段**:
```sql
CREATE TABLE qd_strategies_trading (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    strategy_name VARCHAR(255),
    strategy_type VARCHAR(50),        -- 'IndicatorStrategy'
    status VARCHAR(20),               -- 'running', 'stopped', 'paused'
    initial_capital DECIMAL(20,8),    -- 初始资金
    leverage INTEGER,                 -- 杠杆倍数
    market_type VARCHAR(20),          -- 'swap', 'spot'
    symbol VARCHAR(50),               -- 交易对
    timeframe VARCHAR(10),            -- 时间周期
    indicator_code TEXT,              -- 指标代码
    trading_config JSON,              -- 交易配置
    exchange_config JSON,             -- 交易所配置
    execution_mode VARCHAR(20),       -- 'signal', 'live'
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

**数据流**:
```
用户在前端创建策略
    ↓
POST /api/strategy/create
    ↓
strategy.py 路由
    ↓
INSERT INTO qd_strategies_trading
    ↓
返回策略 ID
```

---

### 2. qd_strategy_positions - 持仓表

**作用**: 存储策略的当前持仓信息

**数据来源**: 策略执行引擎在开仓/平仓时写入

**写入时机**:
1. **开仓时**: 创建新持仓记录
2. **加仓时**: 更新持仓数量和均价
3. **平仓时**: 删除持仓记录
4. **价格更新时**: 更新当前价格和未实现盈亏

**写入位置**:

#### A. 策略执行引擎 (TradingExecutor)
`app/services/trading_executor.py`

```python
class TradingExecutor:
    def _execute_strategy_loop(self, strategy_id):
        """策略主循环"""
        while True:
            # 1. 获取最新K线
            klines = self._fetch_klines(...)
            
            # 2. 执行指标代码，生成信号
            signals = self._execute_indicator(indicator_code, klines)
            
            # 3. 处理信号
            if signals['buy']:
                self._handle_buy_signal(...)
                # ↓ 写入 pending_orders
                
            if signals['sell']:
                self._handle_sell_signal(...)
                # ↓ 写入 pending_orders
            
            time.sleep(tick_interval)
```

#### B. 挂单处理器 (PendingOrderWorker)
`app/services/pending_order_worker.py`

```python
class PendingOrderWorker:
    def _dispatch_one(self, order):
        """处理单个订单"""
        # 1. 执行订单（调用交易所 API 或发送通知）
        result = self._execute_order(order)
        
        # 2. 更新持仓
        if order['signal_type'] == 'open_long':
            # INSERT INTO qd_strategy_positions
            self._create_position(...)
        
        elif order['signal_type'] == 'close_long':
            # DELETE FROM qd_strategy_positions
            self._close_position(...)
```

#### C. 实盘交易记录器
`app/services/live_trading/records.py`

```python
def apply_fill_to_local_position(fill_info):
    """根据成交信息更新本地持仓"""
    # INSERT INTO qd_strategy_positions
    # 或 UPDATE qd_strategy_positions
```

**关键字段**:
```sql
CREATE TABLE qd_strategy_positions (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    strategy_id INTEGER,
    symbol VARCHAR(50),
    side VARCHAR(10),              -- 'long', 'short'
    size DECIMAL(20,8),            -- 持仓数量
    entry_price DECIMAL(20,8),     -- 开仓均价
    current_price DECIMAL(20,8),   -- 当前价格
    highest_price DECIMAL(20,8),   -- 持仓期间最高价
    lowest_price DECIMAL(20,8),    -- 持仓期间最低价
    unrealized_pnl DECIMAL(20,8),  -- 未实现盈亏
    pnl_percent DECIMAL(10,4),     -- 盈亏百分比
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

**数据流**:
```
策略生成买入信号
    ↓
TradingExecutor._handle_buy_signal()
    ↓
INSERT INTO pending_orders (status='pending')
    ↓
PendingOrderWorker 轮询
    ↓
执行订单（调用交易所 API 或发送通知）
    ↓
INSERT INTO qd_strategy_positions
    ↓
Dashboard 查询显示
```

---

### 3. qd_strategy_trades - 交易记录表

**作用**: 存储策略的历史交易记录（已平仓）

**数据来源**: 策略平仓时写入

**写入时机**:
- 策略平仓（close_long / close_short）
- 止损/止盈触发
- 手动平仓

**写入位置**:

#### A. 策略执行引擎
`app/services/trading_executor.py`

```python
def _handle_sell_signal(self, strategy_id, symbol, ...):
    """处理卖出信号（平仓）"""
    # 1. 获取持仓信息
    position = self._get_position(strategy_id, symbol)
    
    # 2. 计算盈亏
    profit = (exit_price - entry_price) * size
    
    # 3. 记录交易
    # INSERT INTO qd_strategy_trades
    self._record_trade(
        strategy_id=strategy_id,
        symbol=symbol,
        type='close_long',
        entry_price=position['entry_price'],
        exit_price=current_price,
        size=position['size'],
        profit=profit
    )
    
    # 4. 删除持仓
    # DELETE FROM qd_strategy_positions
```

#### B. 实盘交易记录器
`app/services/live_trading/records.py`

```python
def record_trade(fill_info):
    """记录交易到数据库"""
    # INSERT INTO qd_strategy_trades
    cur.execute("""
        INSERT INTO qd_strategy_trades
        (user_id, strategy_id, symbol, type, price, amount, value, commission, profit, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, ...)
```

**关键字段**:
```sql
CREATE TABLE qd_strategy_trades (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    strategy_id INTEGER,
    symbol VARCHAR(50),
    type VARCHAR(20),              -- 'open_long', 'close_long', 'open_short', 'close_short'
    price DECIMAL(20,8),           -- 成交价格
    amount DECIMAL(20,8),          -- 成交数量
    value DECIMAL(20,8),           -- 成交金额
    commission DECIMAL(20,8),      -- 手续费
    commission_ccy VARCHAR(10),    -- 手续费币种
    profit DECIMAL(20,8),          -- 盈亏（仅平仓时有值）
    created_at TIMESTAMP
);
```

**数据流**:
```
策略生成卖出信号（平仓）
    ↓
TradingExecutor._handle_sell_signal()
    ↓
计算盈亏
    ↓
INSERT INTO qd_strategy_trades (profit=...)
    ↓
DELETE FROM qd_strategy_positions
    ↓
Dashboard 查询显示历史交易
```

---

### 4. pending_orders - 待处理订单表

**作用**: 存储待执行的交易订单（队列）

**数据来源**: 策略生成信号时写入

**写入时机**:
- 策略生成买入/卖出信号
- 止损/止盈触发

**写入位置**:

#### A. 策略执行引擎
`app/services/trading_executor.py`

```python
def _handle_buy_signal(self, strategy_id, symbol, ...):
    """处理买入信号"""
    # 1. 构建订单信息
    order = {
        'strategy_id': strategy_id,
        'symbol': symbol,
        'signal_type': 'open_long',
        'order_type': 'market',
        'amount': calculated_amount,
        'price': current_price,
        'execution_mode': 'signal',  # 或 'live'
        'status': 'pending'
    }
    
    # 2. 写入待处理订单表
    # INSERT INTO pending_orders
    cur.execute("""
        INSERT INTO pending_orders
        (user_id, strategy_id, symbol, signal_type, order_type, amount, price, 
         execution_mode, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, ...)
```

**处理流程**:

#### B. 挂单处理器 (PendingOrderWorker)
`app/services/pending_order_worker.py`

```python
class PendingOrderWorker:
    def _tick(self):
        """每秒执行一次"""
        # 1. 查询待处理订单
        orders = self._fetch_pending_orders()
        
        # 2. 逐个处理
        for order in orders:
            # 标记为处理中
            # UPDATE pending_orders SET status='processing'
            
            # 执行订单
            if order['execution_mode'] == 'signal':
                # 发送通知（不实际交易）
                self._send_notification(order)
            elif order['execution_mode'] == 'live':
                # 调用交易所 API
                self._execute_on_exchange(order)
            
            # 更新状态
            # UPDATE pending_orders SET status='completed'
```

**关键字段**:
```sql
CREATE TABLE pending_orders (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    strategy_id INTEGER,
    symbol VARCHAR(50),
    signal_type VARCHAR(20),       -- 'open_long', 'close_long', 'open_short', 'close_short'
    signal_ts BIGINT,              -- 信号时间戳
    market_type VARCHAR(20),       -- 'swap', 'spot'
    order_type VARCHAR(20),        -- 'market', 'limit'
    amount DECIMAL(20,8),          -- 订单数量
    price DECIMAL(20,8),           -- 订单价格
    execution_mode VARCHAR(20),    -- 'signal', 'live'
    status VARCHAR(20),            -- 'pending', 'processing', 'completed', 'failed'
    priority INTEGER,              -- 优先级
    attempts INTEGER,              -- 尝试次数
    max_attempts INTEGER,          -- 最大尝试次数
    last_error TEXT,               -- 最后错误信息
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    executed_at TIMESTAMP
);
```

**数据流**:
```
策略生成信号
    ↓
TradingExecutor._handle_buy_signal()
    ↓
INSERT INTO pending_orders (status='pending')
    ↓
PendingOrderWorker 每秒轮询
    ↓
UPDATE pending_orders SET status='processing'
    ↓
执行订单（交易所 API 或通知）
    ↓
UPDATE pending_orders SET status='completed'
    ↓
Dashboard 查询显示订单状态
```

---

## 🔄 完整数据流图

```
用户创建策略
    ↓
INSERT INTO qd_strategies_trading
    ↓
用户启动策略
    ↓
TradingExecutor 启动策略线程
    ↓
    ┌─────────────────────────────────┐
    │  策略主循环（每 N 秒执行一次）    │
    └─────────────────────────────────┘
              ↓
    1. 获取最新 K 线数据
       ├─ DataSourceFactory
       └─ KlineService (带缓存)
              ↓
    2. 执行指标代码
       ├─ 执行用户的 Python 代码
       └─ 生成买入/卖出信号
              ↓
    3. 处理信号
       ├─ 买入信号 → INSERT INTO pending_orders
       └─ 卖出信号 → INSERT INTO pending_orders
              ↓
    ┌─────────────────────────────────┐
    │  PendingOrderWorker (每秒轮询)   │
    └─────────────────────────────────┘
              ↓
    1. SELECT * FROM pending_orders WHERE status='pending'
              ↓
    2. 执行订单
       ├─ signal 模式 → 发送通知
       └─ live 模式 → 调用交易所 API
              ↓
    3. 更新持仓和交易记录
       ├─ 开仓 → INSERT INTO qd_strategy_positions
       ├─ 平仓 → DELETE FROM qd_strategy_positions
       └─ 平仓 → INSERT INTO qd_strategy_trades (记录盈亏)
              ↓
    4. UPDATE pending_orders SET status='completed'
              ↓
    ┌─────────────────────────────────┐
    │  Dashboard 前端轮询（每 5 秒）   │
    └─────────────────────────────────┘
              ↓
    GET /api/dashboard/summary
              ↓
    查询数据库
       ├─ SELECT * FROM qd_strategies_trading
       ├─ SELECT * FROM qd_strategy_positions
       ├─ SELECT * FROM qd_strategy_trades
       └─ SELECT * FROM pending_orders
              ↓
    计算统计数据
       ├─ 总权益 = 初始资金 + 已实现盈亏 + 未实现盈亏
       ├─ 胜率 = 盈利次数 / 总交易次数
       └─ 最大回撤 = ...
              ↓
    返回 JSON 给前端
              ↓
    前端渲染图表和数据
```

---

## 🎯 关键组件

### 1. TradingExecutor - 策略执行引擎

**文件**: `app/services/trading_executor.py`

**职责**:
- 管理所有运行中的策略（每个策略一个线程）
- 定期获取 K 线数据
- 执行指标代码生成信号
- 将信号写入 `pending_orders` 表

**核心方法**:
```python
class TradingExecutor:
    def start_strategy(self, strategy_id):
        """启动策略（创建新线程）"""
        thread = threading.Thread(
            target=self._execute_strategy_loop,
            args=(strategy_id,)
        )
        thread.start()
    
    def _execute_strategy_loop(self, strategy_id):
        """策略主循环"""
        while True:
            # 1. 获取 K 线
            klines = self._fetch_klines(...)
            
            # 2. 执行指标
            signals = self._execute_indicator(...)
            
            # 3. 处理信号
            if signals['buy']:
                self._handle_buy_signal(...)
            
            time.sleep(tick_interval)
```

---

### 2. PendingOrderWorker - 挂单处理器

**文件**: `app/services/pending_order_worker.py`

**职责**:
- 每秒轮询 `pending_orders` 表
- 执行待处理订单
- 更新持仓和交易记录

**核心方法**:
```python
class PendingOrderWorker:
    def _run_loop(self):
        """主循环"""
        while True:
            self._tick()
            time.sleep(1)  # 每秒执行一次
    
    def _tick(self):
        """处理一批订单"""
        orders = self._fetch_pending_orders()
        for order in orders:
            self._dispatch_one(order)
    
    def _dispatch_one(self, order):
        """处理单个订单"""
        # 1. 标记为处理中
        self._mark_processing(order['id'])
        
        # 2. 执行订单
        if order['execution_mode'] == 'signal':
            self._send_notification(order)
        else:
            self._execute_on_exchange(order)
        
        # 3. 更新持仓
        self._update_position(order)
        
        # 4. 标记为完成
        self._mark_completed(order['id'])
```

---

### 3. LiveTrading Records - 实盘交易记录器

**文件**: `app/services/live_trading/records.py`

**职责**:
- 记录实盘交易到数据库
- 更新持仓信息

**核心方法**:
```python
def record_trade(fill_info):
    """记录交易"""
    # INSERT INTO qd_strategy_trades

def apply_fill_to_local_position(fill_info):
    """更新持仓"""
    # INSERT/UPDATE qd_strategy_positions
```

---

## 📝 数据表关系

```
qd_strategies_trading (策略配置)
    ↓ 1:N
qd_strategy_positions (当前持仓)
    ↓ 平仓时
qd_strategy_trades (历史交易)

qd_strategies_trading (策略配置)
    ↓ 1:N
pending_orders (待处理订单)
    ↓ 执行后
qd_strategy_positions (更新持仓)
qd_strategy_trades (记录交易)
```

---

## 🔍 数据查询示例

### Dashboard 查询策略统计

```python
# 查询运行中的策略
cur.execute("""
    SELECT id, strategy_name, status, initial_capital
    FROM qd_strategies_trading
    WHERE user_id = ? AND status = 'running'
""", (user_id,))
```

### Dashboard 查询当前持仓

```python
# 查询所有持仓
cur.execute("""
    SELECT p.*, s.strategy_name
    FROM qd_strategy_positions p
    LEFT JOIN qd_strategies_trading s ON s.id = p.strategy_id
    WHERE p.user_id = ?
    ORDER BY p.updated_at DESC
""", (user_id,))
```

### Dashboard 查询历史交易

```python
# 查询最近 500 笔交易
cur.execute("""
    SELECT t.*, s.strategy_name
    FROM qd_strategy_trades t
    LEFT JOIN qd_strategies_trading s ON s.id = t.strategy_id
    WHERE t.user_id = ?
    ORDER BY t.created_at DESC
    LIMIT 500
""", (user_id,))
```

### Dashboard 查询待处理订单

```python
# 查询待处理订单
cur.execute("""
    SELECT o.*, s.strategy_name
    FROM pending_orders o
    LEFT JOIN qd_strategies_trading s ON s.id = o.strategy_id
    WHERE o.user_id = ?
    ORDER BY o.id DESC
    LIMIT 20
""", (user_id,))
```

---

## 💡 总结

### 数据来源链路

1. **用户创建策略** → `qd_strategies_trading`
2. **策略生成信号** → `pending_orders`
3. **Worker 执行订单** → `qd_strategy_positions` (持仓)
4. **策略平仓** → `qd_strategy_trades` (交易记录)
5. **Dashboard 查询** → 显示所有数据

### 核心流程

```
策略执行 → 生成信号 → 写入订单队列 → Worker 处理 → 更新持仓/交易 → Dashboard 显示
```

所有数据都是**实时生成**的，没有预先计算或缓存，完全由策略执行引擎驱动。
