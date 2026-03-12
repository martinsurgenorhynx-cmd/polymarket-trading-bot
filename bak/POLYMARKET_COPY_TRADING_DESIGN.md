# Polymarket 跟单系统设计文档（简化版）

## 概述

追踪 Polymarket 排行榜顶级用户的交易活动，复用现有的 AI 分析能力，为跟单提供参考。

## 系统架构

```
排行榜API → Top5用户 → 活动API → 交易记录 → 复用batch_analyze_markets → 存储
```

## 数据流程

### 1. 获取所有排行榜Top5用户

**支持的排行榜类型：**
- `day`: 日榜
- `week`: 周榜  
- `month`: 月榜
- `all`: 总榜

**API端点：**
```
https://data-api.polymarket.com/leaderboard?period={period}&limit=5
```

**返回数据结构：**
```json
{
  "data": [
    {
      "user": "0x204f72f35326db932158cba6adff0b9a1da95e14",
      "volume": 1234567.89,
      "profit": 12345.67,
      "trades": 123,
      "win_rate": 0.65,
      "rank": 1
    }
  ]
}
```

### 2. 获取用户最近交易活动

**API端点：**
```
https://data-api.polymarket.com/activity?user={address}&limit=5
```

**返回数据结构：**
```json
[
  {
    "id": "activity_123",
    "user": "0x204f...",
    "market": "0xmarket123...",
    "asset_id": "token_456",
    "side": "BUY",
    "outcome": "YES",
    "size": "100.0",
    "price": "0.65",
    "timestamp": 1234567890,
    "feeRateBps": "200"
  }
]
```

### 3. AI分析

**复用现有的 `batch_analyze_markets` 方法**，不需要单独的分析逻辑。

## 数据库设计（简化版）

### 表1: qd_polymarket_top_users (排行榜用户)

```sql
CREATE TABLE qd_polymarket_top_users (
    id SERIAL PRIMARY KEY,
    user_address VARCHAR(42) NOT NULL,
    period VARCHAR(20) NOT NULL,  -- 'day', 'week', 'month', 'all'
    rank INT NOT NULL,
    volume DECIMAL(20, 2),
    profit DECIMAL(20, 2),
    trades INT,
    win_rate DECIMAL(5, 4),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_address, period, created_at::date)
);

CREATE INDEX idx_top_users_address ON qd_polymarket_top_users(user_address);
CREATE INDEX idx_top_users_period ON qd_polymarket_top_users(period);
```

### 表2: qd_polymarket_user_activities (用户交易活动)

```sql
CREATE TABLE qd_polymarket_user_activities (
    id SERIAL PRIMARY KEY,
    activity_id VARCHAR(100) UNIQUE NOT NULL,  -- 防止重复
    user_address VARCHAR(42) NOT NULL,
    market_id VARCHAR(100),
    asset_id VARCHAR(100),
    side VARCHAR(10) NOT NULL,  -- 'BUY' 或 'SELL'
    outcome VARCHAR(10),  -- 'YES' 或 'NO'
    size DECIMAL(20, 8),
    price DECIMAL(10, 6),
    fee_rate_bps INT,
    timestamp TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_activities_user ON qd_polymarket_user_activities(user_address);
CREATE INDEX idx_activities_market ON qd_polymarket_user_activities(market_id);
CREATE INDEX idx_activities_timestamp ON qd_polymarket_user_activities(timestamp DESC);
CREATE UNIQUE INDEX idx_activities_unique ON qd_polymarket_user_activities(activity_id);
```

**注意：** AI分析结果不存储，每次查询时实时计算。

## 核心功能

### 1. PolymarketDataSource 新增方法

在 `app/data_sources/polymarket.py` 中添加：

```python
def get_leaderboard(self, period='month', limit=5):
    """
    获取排行榜
    
    Args:
        period: 'day', 'week', 'month', 'all'
        limit: 返回数量（默认5）
    """
    
def get_user_activities(self, user_address, limit=5):
    """
    获取用户交易活动
    
    Args:
        user_address: 用户地址
        limit: 返回数量（默认5）
    """
```

### 2. run_once_copy_trading.py

单一脚本完成所有功能：

```python
#!/usr/bin/env python
"""
单次执行跟单数据收集

使用方法：
    python polymarket/run_once_copy_trading.py
"""

def main():
    # 1. 获取所有排行榜Top5
    periods = ['day', 'week', 'month', 'all']
    all_users = {}
    
    for period in periods:
        users = polymarket.get_leaderboard(period, limit=5)
        save_top_users(users, period)
        for user in users:
            all_users[user['user']] = user
    
    # 2. 获取每个用户的最近5条活动
    all_activities = []
    for address in all_users.keys():
        activities = polymarket.get_user_activities(address, limit=5)
        all_activities.extend(activities)
    
    # 3. 去重并保存
    save_activities(all_activities)  # 内部基于activity_id去重
    
    # 4. 获取涉及的市场ID
    market_ids = [a['market'] for a in all_activities]
    
    # 5. 调用batch_analyze_markets分析
    markets = get_markets_by_ids(market_ids)
    analyzed = batch_analyzer.batch_analyze_markets(markets)
    
    # 6. 显示结果
    print_summary(all_users, all_activities, analyzed)
```

## 执行流程

```
1. 获取4个排行榜（day/week/month/all）各Top5 → 最多20个用户
2. 对每个用户获取最近5条活动 → 最多100条活动
3. 去重保存到数据库
4. 提取涉及的市场ID
5. 调用batch_analyze_markets进行AI分析
6. 显示分析结果
```

## 输出示例

```
================================================================================
Polymarket 跟单系统 - 单次执行
================================================================================

⏰ 执行时间: 2024-01-01 12:00:00

📊 第1步: 获取排行榜Top5用户
  ✓ 日榜: 5 个用户
  ✓ 周榜: 5 个用户
  ✓ 月榜: 5 个用户
  ✓ 总榜: 5 个用户
  ✓ 去重后: 12 个唯一用户

📊 第2步: 收集交易活动（每人最近5条）
  [1/12] 0x204f... (日榜#1, 月榜#3)
    ✓ 获取 5 条活动
    ✓ 新增 4 条（1条已存在）
  [2/12] 0x3a5b... (周榜#2)
    ✓ 获取 5 条活动
    ✓ 新增 5 条
  ...

📊 第3步: 提取市场并调用AI分析
  ✓ 涉及 25 个不同市场
  ✓ 调用 batch_analyze_markets 分析
  ✓ 分析完成: 18 个市场有交易机会

📊 执行统计
  总用户数: 12
  总活动数: 60
  新增活动: 52
  重复活动: 8
  涉及市场: 25
  AI推荐: 18
  耗时: 45.3 秒

✅ 执行完成！

💡 查看结果:
   python polymarket/query_copy_trading.py
```

## 文件结构（简化版）

```
backend_api_python/
├── polymarket/
│   └── run_once_copy_trading.py       # 单一脚本，完成所有功能
├── app/
│   └── data_sources/
│       └── polymarket.py              # 添加2个新方法
└── migrations/
    └── add_copy_trading_tables.sql    # 2张表的迁移
```

## 关键简化点

1. ✅ **只有2张表**：用户表 + 活动表
2. ✅ **AI分析不存储**：每次查询时实时计算
3. ✅ **复用现有分析**：直接调用 `batch_analyze_markets`
4. ✅ **只有1个脚本**：`run_once_copy_trading.py`
5. ✅ **数据源统一**：只在 `data_sources/polymarket.py` 添加方法
6. ✅ **Top5限制**：每个榜只取5个用户，每人只取5条活动
7. ✅ **4个排行榜**：day, week, month, all

## 下一步

1. 创建数据库迁移文件
2. 在 `polymarket.py` 添加2个方法
3. 实现 `run_once_copy_trading.py`
