# Dashboard 监控页面数据流说明

## 概述

Dashboard 监控页面**没有使用定时任务**，而是采用**前端轮询 + 实时查询数据库**的方式获取数据。

## 🔄 数据流架构

```
前端 Vue 页面
    ↓ (定时轮询，如每 5 秒)
GET /api/dashboard/summary
    ↓
dashboard.py 路由
    ↓
实时查询数据库
    ├─ qd_strategies_trading (策略列表)
    ├─ qd_strategy_positions (当前持仓)
    ├─ qd_strategy_trades (交易记录)
    └─ pending_orders (待处理订单)
    ↓
计算统计数据
    ├─ 总权益、总盈亏
    ├─ 胜率、盈亏比
    ├─ 最大回撤
    └─ 各种图表数据
    ↓
返回 JSON 给前端
    ↓
前端渲染图表和数据
```

---

## 📡 API 端点

### 1. GET /api/dashboard/summary

**功能**: 获取 Dashboard 主页的所有数据

**路由文件**: `app/routes/dashboard.py`

**请求**: 
```http
GET /api/dashboard/summary
Authorization: Bearer <token>
```

**响应数据结构**:
```json
{
  "code": 1,
  "msg": "success",
  "data": {
    // 策略统计
    "ai_strategy_count": 3,           // AI 策略数量
    "indicator_strategy_count": 5,    // 指标策略数量
    
    // 资金统计
    "total_equity": 12500.50,         // 总权益
    "total_pnl": 2500.50,             // 总盈亏
    "total_realized_pnl": 2000.00,    // 已实现盈亏
    "total_unrealized_pnl": 500.50,   // 未实现盈亏
    
    // 绩效指标
    "performance": {
      "total_trades": 150,            // 总交易次数
      "winning_trades": 90,           // 盈利次数
      "losing_trades": 60,            // 亏损次数
      "win_rate": 60.0,               // 胜率 (%)
      "total_profit": 5000.0,         // 总盈利
      "total_loss": 2500.0,           // 总亏损
      "profit_factor": 2.0,           // 盈亏比
      "avg_win": 55.56,               // 平均盈利
      "avg_loss": 41.67,              // 平均亏损
      "avg_trade": 16.67,             // 平均每笔
      "max_win": 500.0,               // 最大盈利
      "max_loss": -300.0,             // 最大亏损
      "max_drawdown": 800.0,          // 最大回撤
      "max_drawdown_pct": 8.5,        // 最大回撤 (%)
      "best_day": 1200.0,             // 最佳单日
      "worst_day": -500.0             // 最差单日
    },
    
    // 策略级别统计
    "strategy_stats": [
      {
        "strategy_id": 1,
        "strategy_name": "BTC Trend",
        "total_trades": 50,
        "win_rate": 65.0,
        "profit_factor": 2.5,
        "total_pnl": 1500.0,
        "roi": 15.0,
        "max_drawdown": 300.0
      }
    ],
    
    // 图表数据
    "daily_pnl_chart": [              // 每日盈亏曲线
      {"date": "2024-01-01", "profit": 100.0},
      {"date": "2024-01-02", "profit": -50.0}
    ],
    
    "strategy_pnl_chart": [           // 策略盈亏饼图
      {"name": "BTC Trend", "value": 1500.0},
      {"name": "ETH Grid", "value": 800.0}
    ],
    
    "monthly_returns": [              // 月度收益
      {"month": "2024-01", "profit": 2500.0},
      {"month": "2024-02", "profit": 1800.0}
    ],
    
    "hourly_distribution": [          // 小时分布
      {"hour": 0, "count": 5, "profit": 100.0},
      {"hour": 1, "count": 3, "profit": -20.0}
    ],
    
    "calendar_months": [              // 日历热力图数据
      {
        "month_key": "2024-01",
        "year": 2024,
        "month": 1,
        "days_in_month": 31,
        "first_weekday": 0,           // 0=周一
        "days": {
          "01": 123.45,
          "02": -50.0,
          "03": 200.0
        },
        "total": 2500.0,
        "win_days": 20,
        "lose_days": 8
      }
    ],
    
    // 列表数据
    "recent_trades": [                // 最近交易 (最多 100 条)
      {
        "id": 1,
        "strategy_id": 1,
        "strategy_name": "BTC Trend",
        "symbol": "BTC/USDT",
        "side": "long",
        "entry_price": 50000.0,
        "exit_price": 51000.0,
        "size": 0.1,
        "profit": 100.0,
        "created_at": 1704067200
      }
    ],
    
    "current_positions": [            // 当前持仓
      {
        "id": 1,
        "strategy_id": 1,
        "strategy_name": "BTC Trend",
        "symbol": "BTC/USDT",
        "side": "long",
        "entry_price": 50000.0,
        "current_price": 50500.0,
        "size": 0.1,
        "unrealized_pnl": 50.0,
        "pnl_percent": 1.0
      }
    ]
  }
}
```

---

### 2. GET /api/dashboard/pendingOrders

**功能**: 获取待处理订单列表（分页）

**请求**:
```http
GET /api/dashboard/pendingOrders?page=1&pageSize=20
Authorization: Bearer <token>
```

**响应**:
```json
{
  "code": 1,
  "msg": "success",
  "data": {
    "list": [
      {
        "id": 1,
        "strategy_id": 1,
        "strategy_name": "BTC Trend",
        "symbol": "BTC/USDT",
        "side": "buy",
        "order_type": "market",
        "price": 50000.0,
        "amount": 0.1,
        "status": "pending",          // pending/processing/completed/failed
        "filled_amount": 0.0,
        "filled_price": 0.0,
        "error_message": "",
        "exchange_id": "binance",
        "exchange_display": "binance",
        "notify_channels": ["browser", "email"],
        "market_type": "swap",
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00"
      }
    ],
    "page": 1,
    "pageSize": 20,
    "total": 50
  }
}
```

---

### 3. DELETE /api/dashboard/pendingOrders/:id

**功能**: 删除待处理订单

**请求**:
```http
DELETE /api/dashboard/pendingOrders/123
Authorization: Bearer <token>
```

**响应**:
```json
{
  "code": 1,
  "msg": "success",
  "data": {"id": 123}
}
```

---

## 🎯 数据来源

### 数据库表

Dashboard 数据来自以下数据库表：

1. **qd_strategies_trading** - 策略配置
   - 策略数量统计
   - 初始资金
   - 策略类型（IndicatorStrategy / AI）

2. **qd_strategy_positions** - 当前持仓
   - 持仓列表
   - 未实现盈亏计算

3. **qd_strategy_trades** - 交易记录
   - 历史交易
   - 已实现盈亏
   - 绩效指标计算

4. **pending_orders** - 待处理订单
   - 订单列表
   - 订单状态

### 实时计算

所有统计数据都是**实时计算**的，不存储在数据库中：

```python
# 示例：计算未实现盈亏
def _calc_unrealized_pnl(side, entry_price, current_price, size):
    if side == "long":
        return (current_price - entry_price) * size
    else:  # short
        return (entry_price - current_price) * size

# 示例：计算绩效指标
def _compute_performance_stats(trades):
    profits = [t['profit'] for t in trades]
    wins = [p for p in profits if p > 0]
    losses = [p for p in profits if p < 0]
    
    win_rate = len(wins) / len(trades) * 100
    profit_factor = sum(wins) / abs(sum(losses))
    # ... 更多计算
```

---

## 🔄 前端轮询机制

### Vue 组件实现

前端通过定时器实现数据轮询：

```javascript
// quantdinger_vue/src/views/dashboard/index.vue

export default {
  data() {
    return {
      refreshInterval: null,
      refreshRate: 5000,  // 5 秒刷新一次
    }
  },
  
  mounted() {
    this.loadDashboardData()
    this.startAutoRefresh()
  },
  
  beforeUnmount() {
    this.stopAutoRefresh()
  },
  
  methods: {
    async loadDashboardData() {
      const response = await axios.get('/api/dashboard/summary')
      this.dashboardData = response.data.data
    },
    
    startAutoRefresh() {
      this.refreshInterval = setInterval(() => {
        this.loadDashboardData()
      }, this.refreshRate)
    },
    
    stopAutoRefresh() {
      if (this.refreshInterval) {
        clearInterval(this.refreshInterval)
      }
    }
  }
}
```

### 轮询优化

1. **页面可见性检测**: 页面不可见时停止轮询
```javascript
document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    this.stopAutoRefresh()
  } else {
    this.startAutoRefresh()
  }
})
```

2. **用户可配置刷新频率**:
```javascript
// 用户可以在设置中调整刷新频率
refreshRate: localStorage.getItem('dashboardRefreshRate') || 5000
```

3. **错误重试机制**:
```javascript
async loadDashboardData() {
  try {
    const response = await axios.get('/api/dashboard/summary')
    this.dashboardData = response.data.data
    this.errorCount = 0
  } catch (error) {
    this.errorCount++
    if (this.errorCount > 3) {
      this.stopAutoRefresh()  // 连续失败 3 次后停止轮询
    }
  }
}
```

---

## 🆚 为什么不用 Worker？

### 当前方案（前端轮询）

**优点**:
- ✅ 简单直接，无需后台任务
- ✅ 数据实时性高（用户主动拉取）
- ✅ 服务器压力可控（用户不在页面时不请求）
- ✅ 易于调试和维护

**缺点**:
- ❌ 多用户同时访问时数据库压力大
- ❌ 前端需要管理轮询逻辑
- ❌ 网络请求频繁

### 如果使用 Worker

**优点**:
- ✅ 减少数据库查询次数（缓存结果）
- ✅ 前端只需订阅数据（WebSocket）
- ✅ 可以预计算复杂指标

**缺点**:
- ❌ 增加系统复杂度
- ❌ 需要 WebSocket 或 SSE
- ❌ 缓存数据可能不够实时
- ❌ 多用户数据隔离复杂

---

## 🚀 性能优化建议

### 1. 添加 Redis 缓存

```python
from app.utils.cache import CacheManager

cache = CacheManager()

@dashboard_bp.route("/summary", methods=["GET"])
@login_required
def summary():
    user_id = g.user_id
    cache_key = f"dashboard:summary:{user_id}"
    
    # 尝试从缓存获取
    cached = cache.get(cache_key)
    if cached:
        return jsonify(cached)
    
    # 查询数据库并计算
    data = compute_dashboard_data(user_id)
    
    # 缓存 5 秒
    cache.set(cache_key, data, ttl=5)
    
    return jsonify(data)
```

### 2. 数据库查询优化

```python
# 使用索引
CREATE INDEX idx_trades_user_created ON qd_strategy_trades(user_id, created_at DESC);
CREATE INDEX idx_positions_user ON qd_strategy_positions(user_id);

# 限制查询范围
cur.execute("""
    SELECT * FROM qd_strategy_trades
    WHERE user_id = ? AND created_at > ?
    ORDER BY created_at DESC
    LIMIT 500
""", (user_id, thirty_days_ago))
```

### 3. 分页加载

```python
# 只返回必要的数据
"recent_trades": recent_trades[:100],  # 限制 100 条
"current_positions": current_positions,  # 持仓通常不多
```

### 4. 增量更新

前端可以只请求变化的数据：

```javascript
// 首次加载完整数据
const fullData = await axios.get('/api/dashboard/summary')

// 后续只请求增量
const updates = await axios.get('/api/dashboard/updates?since=' + lastUpdateTime)
```

---

## 🔄 可选：使用 WebSocket 实时推送

如果需要更实时的数据更新，可以考虑使用 WebSocket：

### 后端实现（Flask-SocketIO）

```python
from flask_socketio import SocketIO, emit

socketio = SocketIO(app, cors_allowed_origins="*")

@socketio.on('subscribe_dashboard')
def handle_subscribe(data):
    user_id = data.get('user_id')
    # 加入用户专属房间
    join_room(f'dashboard_{user_id}')

# 在交易发生时推送更新
def on_trade_executed(trade):
    user_id = trade['user_id']
    socketio.emit('trade_update', trade, room=f'dashboard_{user_id}')
```

### 前端实现

```javascript
import io from 'socket.io-client'

const socket = io('http://localhost:5000')

socket.emit('subscribe_dashboard', { user_id: this.userId })

socket.on('trade_update', (trade) => {
  this.updateDashboard(trade)
})
```

---

## 📊 数据流时序图

```
用户打开 Dashboard 页面
    ↓
前端发起首次请求
    ↓
GET /api/dashboard/summary
    ↓
后端查询数据库
    ├─ 查询策略列表
    ├─ 查询持仓
    ├─ 查询交易记录
    └─ 计算统计数据
    ↓
返回完整数据
    ↓
前端渲染页面
    ↓
启动定时器（5秒）
    ↓
    ├─ 5秒后 → GET /api/dashboard/summary
    ├─ 10秒后 → GET /api/dashboard/summary
    ├─ 15秒后 → GET /api/dashboard/summary
    └─ ...
    ↓
用户离开页面
    ↓
停止定时器
```

---

## 🔍 调试技巧

### 1. 查看 API 响应时间

```bash
# 在浏览器开发者工具的 Network 标签中查看
# 或使用 curl 测试
time curl -H "Authorization: Bearer <token>" \
  http://localhost:5000/api/dashboard/summary
```

### 2. 监控数据库查询

```python
# 在 dashboard.py 中添加日志
import time

start = time.time()
cur.execute("SELECT * FROM qd_strategy_trades WHERE user_id = ?", (user_id,))
trades = cur.fetchall()
logger.info(f"Query trades took {time.time() - start:.3f}s, got {len(trades)} rows")
```

### 3. 检查前端轮询

```javascript
// 在浏览器控制台
console.log('Dashboard refresh rate:', this.refreshRate)
console.log('Last update:', this.lastUpdateTime)
```

---

## 📚 相关文档

- [Worker 定时任务指南](WORKERS_GUIDE.md)
- [Services 目录说明](app/services/README.md)
- [API 路由文档](app/routes/README.md)

---

## 💡 总结

Dashboard 监控页面采用**前端轮询 + 实时查询**的方式，而不是后台 Worker：

1. **数据获取**: 前端每 5 秒调用 `/api/dashboard/summary`
2. **数据计算**: 后端实时查询数据库并计算统计指标
3. **数据展示**: 前端渲染图表和列表

这种方式简单直接，适合中小规模应用。如果用户量大，可以考虑添加 Redis 缓存或使用 WebSocket 推送。
