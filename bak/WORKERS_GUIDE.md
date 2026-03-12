# Worker 定时任务实现指南

## 概述

项目中的 `*_worker.py` 文件都是后台定时任务，使用 **Python 线程** 实现，在 Flask 应用启动时自动启动。

## 🔧 实现原理

### 核心机制

所有 worker 都遵循相同的设计模式：

1. **线程模式**: 使用 `threading.Thread` 在后台运行
2. **轮询模式**: 使用 `while` 循环 + `time.sleep()` 实现定时执行
3. **单例模式**: 全局只有一个实例，避免重复启动
4. **优雅停止**: 使用 `threading.Event` 实现安全停止

### 标准实现模板

```python
import threading
import time
from typing import Optional

class MyWorker:
    def __init__(self, poll_interval_sec: float = 60.0):
        """初始化 worker"""
        self.poll_interval_sec = poll_interval_sec
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
    
    def start(self) -> bool:
        """启动 worker"""
        with self._lock:
            if self._thread and self._thread.is_alive():
                return True  # 已经在运行
            
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run_loop,
                name="MyWorker",
                daemon=True  # 守护线程，主进程退出时自动结束
            )
            self._thread.start()
            return True
    
    def stop(self, timeout_sec: float = 5.0) -> None:
        """停止 worker"""
        with self._lock:
            self._stop_event.set()
            th = self._thread
        
        if th and th.is_alive():
            th.join(timeout=timeout_sec)
    
    def _run_loop(self) -> None:
        """主循环（在独立线程中运行）"""
        while not self._stop_event.is_set():
            try:
                self._tick()  # 执行一次任务
            except Exception as e:
                logger.error(f"Worker tick error: {e}")
            
            # 等待下一次执行
            time.sleep(self.poll_interval_sec)
    
    def _tick(self) -> None:
        """单次任务执行逻辑"""
        # 在这里实现具体的业务逻辑
        pass

# 全局单例
_my_worker: Optional[MyWorker] = None
_worker_lock = threading.Lock()

def get_my_worker() -> MyWorker:
    """获取 worker 单例"""
    global _my_worker
    with _worker_lock:
        if _my_worker is None:
            _my_worker = MyWorker(poll_interval_sec=60.0)
        return _my_worker
```

---

## 📦 现有的 Worker

### 1. PendingOrderWorker - 挂单处理器

**文件**: `app/services/pending_order_worker.py`

**功能**: 处理待执行的交易订单

**执行间隔**: 1 秒（可配置）

**工作流程**:
```
1. 从数据库查询待处理订单 (qd_pending_orders)
2. 标记订单为 "processing"
3. 根据 execution_mode 执行:
   - signal: 发送通知（不实际交易）
   - live: 调用交易所 API 执行订单
4. 更新订单状态 (completed/failed)
5. 同步持仓信息（可选）
```

**配置**:
```env
ENABLE_PENDING_ORDER_WORKER=true  # 是否启用
PENDING_ORDER_STALE_SEC=90        # 订单超时时间
POSITION_SYNC_ENABLED=true        # 是否同步持仓
POSITION_SYNC_INTERVAL_SEC=10     # 持仓同步间隔
```

**启动方式**:
```python
from app import get_pending_order_worker
get_pending_order_worker().start()
```

**数据表**:
- `qd_pending_orders` - 待处理订单
- `qd_strategy_positions` - 策略持仓
- `qd_strategy_trades` - 交易记录

---

### 2. PolymarketWorker - 预测市场数据更新

**文件**: `app/services/polymarket_worker.py`

**功能**: 定期更新 Polymarket 预测市场数据并分析机会

**执行间隔**: 30 分钟（可配置）

**工作流程**:
```
1. 从 Polymarket API 获取热门市场
2. 按分类获取数据（crypto, politics, economics 等）
3. 去重和数据清洗
4. 规则筛选高价值机会（交易量 > 5000 + 概率偏差 > 8%）
5. 对筛选出的机会调用 LLM 分析（最多 30 个）
6. 保存分析结果到数据库
```

**配置**:
```env
POLYMARKET_UPDATE_INTERVAL_MIN=30  # 更新间隔（分钟）
POLYMARKET_ANALYSIS_CACHE_MIN=30   # 分析缓存时间（分钟）
```

**启动方式**:
```python
from app.services.polymarket_worker import get_polymarket_worker
get_polymarket_worker().start()
```

**数据表**:
- `qd_polymarket_markets` - 市场数据
- `qd_polymarket_analysis` - AI 分析结果

**优化策略**:
- 规则筛选 + LLM 分析结合，减少 token 消耗
- 只分析高价值机会（交易量大 + 概率偏差明显）
- 批量分析，一次 LLM 调用处理多个市场

---

### 3. USDTOrderWorker - USDT 支付订单监控

**文件**: `app/services/usdt_payment_service.py`

**功能**: 监控 USDT 支付订单的链上确认状态

**执行间隔**: 30 秒（可配置）

**工作流程**:
```
1. 查询待确认的 USDT 订单
2. 调用区块链浏览器 API 检查交易状态
3. 确认后更新订单状态
4. 给用户充值积分/VIP
5. 发送确认通知
```

**配置**:
```env
USDT_PAY_ENABLED=true              # 是否启用 USDT 支付
USDT_ORDER_WORKER_INTERVAL_SEC=30  # 检查间隔
```

**启动方式**:
```python
from app.services.usdt_payment_service import get_usdt_order_worker
get_usdt_order_worker().start()
```

**数据表**:
- `qd_usdt_orders` - USDT 订单

---

### 4. PortfolioMonitor - 投资组合监控（非 worker 文件）

**文件**: `app/services/portfolio_monitor.py`

**功能**: 定期生成投资组合 AI 分析报告

**执行间隔**: 可配置（默认每小时）

**工作流程**:
```
1. 获取用户的所有持仓
2. 收集市场数据和新闻
3. 调用 LLM 生成分析报告
4. 保存报告到数据库
5. 发送通知（可选）
```

**配置**:
```env
ENABLE_PORTFOLIO_MONITOR=true  # 是否启用
```

**启动方式**:
```python
from app.services.portfolio_monitor import start_monitor_service
start_monitor_service()
```

---

## 🚀 Worker 启动流程

### 1. Flask 应用启动时自动启动

在 `app/__init__.py` 的 `create_app()` 函数中：

```python
def create_app(config_name='default'):
    app = Flask(__name__)
    
    # ... 其他初始化代码 ...
    
    # 在应用上下文中启动所有 worker
    with app.app_context():
        start_pending_order_worker()      # 挂单处理
        start_portfolio_monitor()         # 投资组合监控
        start_usdt_order_worker()         # USDT 支付监控
        start_polymarket_worker()         # Polymarket 数据更新
        restore_running_strategies()      # 恢复运行中的策略
    
    return app
```

### 2. 启动函数实现

每个 worker 都有对应的启动函数：

```python
def start_pending_order_worker():
    """启动挂单处理器"""
    import os
    
    # 检查是否启用
    if os.getenv('ENABLE_PENDING_ORDER_WORKER', 'true').lower() != 'true':
        logger.info("Pending order worker is disabled")
        return
    
    try:
        get_pending_order_worker().start()
    except Exception as e:
        logger.error(f"Failed to start pending order worker: {e}")
```

### 3. 避免重复启动（Flask Reloader）

在开发模式下，Flask 的 reloader 会启动两个进程，需要避免重复启动：

```python
def start_usdt_order_worker():
    import os
    
    # 检查是否启用
    if os.getenv("USDT_PAY_ENABLED", "false").lower() != "true":
        return
    
    # 避免 Flask reloader 重复启动
    debug = os.getenv("PYTHON_API_DEBUG", "false").lower() == "true"
    if debug:
        if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
            return  # 只在主进程中启动
    
    try:
        get_usdt_order_worker().start()
    except Exception as e:
        logger.error(f"Failed to start USDT order worker: {e}")
```

---

## 🔍 Worker 的优缺点

### 优点

1. **简单直接**: 不需要额外的任务队列（Celery, RQ）
2. **低延迟**: 适合需要快速响应的任务（如订单处理）
3. **易于调试**: 日志直接输出到主进程
4. **资源占用小**: 不需要额外的 Redis/RabbitMQ

### 缺点

1. **不适合长时间任务**: 会阻塞线程
2. **无法分布式**: 只能在单机运行
3. **无任务队列**: 不支持任务重试、优先级等高级特性
4. **进程重启丢失状态**: 任务状态不持久化

---

## 🆚 对比其他定时任务方案

### 1. APScheduler

**优点**:
- 支持 cron 表达式
- 支持任务持久化
- 更灵活的调度策略

**缺点**:
- 需要额外依赖
- 配置相对复杂

**示例**:
```python
from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler()
scheduler.add_job(my_task, 'interval', seconds=60)
scheduler.start()
```

### 2. Celery

**优点**:
- 分布式任务队列
- 支持任务重试、优先级
- 成熟的生态系统

**缺点**:
- 需要 Redis/RabbitMQ
- 配置复杂
- 资源占用大

**示例**:
```python
from celery import Celery

app = Celery('tasks', broker='redis://localhost:6379')

@app.task
def my_task():
    pass

# 定时任务
app.conf.beat_schedule = {
    'my-task': {
        'task': 'tasks.my_task',
        'schedule': 60.0,
    },
}
```

### 3. Cron + 独立脚本

**优点**:
- 系统级调度，稳定可靠
- 独立进程，不影响主应用

**缺点**:
- 需要系统权限
- 不适合高频任务（< 1分钟）
- 难以共享应用状态

**示例**:
```bash
# crontab -e
*/5 * * * * cd /path/to/app && python scripts/my_task.py
```

---

## 📝 创建新的 Worker

### 步骤 1: 创建 Worker 类

```python
# app/services/my_worker.py
import threading
import time
from typing import Optional
from app.utils.logger import get_logger

logger = get_logger(__name__)

class MyWorker:
    def __init__(self, interval_sec: float = 60.0):
        self.interval_sec = interval_sec
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
    
    def start(self) -> bool:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return True
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run_loop,
                name="MyWorker",
                daemon=True
            )
            self._thread.start()
            logger.info(f"MyWorker started (interval={self.interval_sec}s)")
            return True
    
    def stop(self, timeout_sec: float = 5.0) -> None:
        with self._lock:
            self._stop_event.set()
            th = self._thread
        if th and th.is_alive():
            th.join(timeout=timeout_sec)
            logger.info("MyWorker stopped")
    
    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._do_work()
            except Exception as e:
                logger.error(f"MyWorker error: {e}", exc_info=True)
            
            # 使用 Event.wait() 代替 time.sleep()，支持优雅停止
            if self._stop_event.wait(self.interval_sec):
                break
    
    def _do_work(self) -> None:
        """实现具体的业务逻辑"""
        logger.info("MyWorker: doing work...")
        # TODO: 实现你的任务逻辑

# 全局单例
_my_worker: Optional[MyWorker] = None
_worker_lock = threading.Lock()

def get_my_worker() -> MyWorker:
    global _my_worker
    with _worker_lock:
        if _my_worker is None:
            import os
            interval = float(os.getenv("MY_WORKER_INTERVAL_SEC", "60"))
            _my_worker = MyWorker(interval_sec=interval)
        return _my_worker
```

### 步骤 2: 添加启动函数

在 `app/__init__.py` 中添加：

```python
def start_my_worker():
    """启动我的 worker"""
    import os
    
    # 检查是否启用
    if os.getenv('ENABLE_MY_WORKER', 'false').lower() != 'true':
        logger.info("MyWorker is disabled")
        return
    
    # 避免 Flask reloader 重复启动
    debug = os.getenv("PYTHON_API_DEBUG", "false").lower() == "true"
    if debug:
        if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
            return
    
    try:
        from app.services.my_worker import get_my_worker
        get_my_worker().start()
    except Exception as e:
        logger.error(f"Failed to start MyWorker: {e}")
```

### 步骤 3: 在应用启动时调用

在 `create_app()` 函数中添加：

```python
def create_app(config_name='default'):
    app = Flask(__name__)
    
    # ... 其他初始化代码 ...
    
    with app.app_context():
        start_pending_order_worker()
        start_portfolio_monitor()
        start_usdt_order_worker()
        start_polymarket_worker()
        start_my_worker()  # 添加这一行
        restore_running_strategies()
    
    return app
```

### 步骤 4: 配置环境变量

在 `.env` 文件中添加：

```env
# MyWorker 配置
ENABLE_MY_WORKER=true
MY_WORKER_INTERVAL_SEC=60
```

---

## 🐛 调试技巧

### 1. 查看 Worker 日志

```bash
# 查看所有日志
tail -f logs/app.log

# 只看 worker 相关日志
tail -f logs/app.log | grep Worker
```

### 2. 手动触发 Worker

```python
# 在 Python shell 中
from app.services.polymarket_worker import get_polymarket_worker

worker = get_polymarket_worker()
worker.force_update()  # 立即执行一次
```

### 3. 检查 Worker 状态

```python
from app import get_pending_order_worker

worker = get_pending_order_worker()
print(f"Thread alive: {worker._thread.is_alive()}")
print(f"Stop event set: {worker._stop_event.is_set()}")
```

### 4. 优雅停止 Worker

```python
from app import get_pending_order_worker

worker = get_pending_order_worker()
worker.stop(timeout_sec=10.0)
```

---

## ⚠️ 注意事项

### 1. 线程安全

Worker 在独立线程中运行，访问共享资源时需要加锁：

```python
import threading

class MyWorker:
    def __init__(self):
        self._data_lock = threading.Lock()
        self._shared_data = {}
    
    def _do_work(self):
        with self._data_lock:
            # 安全地访问共享数据
            self._shared_data['key'] = 'value'
```

### 2. 数据库连接

每次任务执行时重新获取数据库连接：

```python
def _do_work(self):
    with get_db_connection() as db:
        cur = db.cursor()
        cur.execute("SELECT * FROM table")
        # ...
```

### 3. 异常处理

始终捕获异常，避免 worker 崩溃：

```python
def _run_loop(self):
    while not self._stop_event.is_set():
        try:
            self._do_work()
        except Exception as e:
            logger.error(f"Worker error: {e}", exc_info=True)
            # 继续运行，不要退出
        
        time.sleep(self.interval_sec)
```

### 4. 避免阻塞

不要在 worker 中执行长时间阻塞的操作：

```python
# ❌ 错误：会阻塞整个线程
def _do_work(self):
    time.sleep(3600)  # 阻塞 1 小时

# ✅ 正确：使用超时
def _do_work(self):
    try:
        result = requests.get(url, timeout=10)
    except requests.Timeout:
        logger.warning("Request timeout")
```

### 5. 资源清理

在 worker 停止时清理资源：

```python
def stop(self, timeout_sec: float = 5.0):
    with self._lock:
        self._stop_event.set()
        th = self._thread
    
    if th and th.is_alive():
        th.join(timeout=timeout_sec)
    
    # 清理资源
    self._cleanup()

def _cleanup(self):
    # 关闭数据库连接、文件句柄等
    pass
```

---

## 📚 相关文档

- [Services 目录说明](app/services/README.md)
- [数据库设计](migrations/README.md)
- [API 路由](app/routes/README.md)

---

## 🔗 参考资料

- [Python threading 文档](https://docs.python.org/3/library/threading.html)
- [Flask 应用工厂模式](https://flask.palletsprojects.com/en/2.3.x/patterns/appfactories/)
- [APScheduler 文档](https://apscheduler.readthedocs.io/)
- [Celery 文档](https://docs.celeryproject.org/)
