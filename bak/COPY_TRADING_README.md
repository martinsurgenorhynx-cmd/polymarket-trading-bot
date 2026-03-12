# Polymarket 跟单系统

追踪 Polymarket 排行榜顶级用户的交易活动，复用 AI 分析能力，为跟单提供参考。

## 快速开始

### 1. 运行数据收集

```bash
cd backend_api_python
python polymarket/run_once_copy_trading.py
```

这个脚本会：
- 获取 4 个排行榜（day/week/month/all）各 Top5 用户
- 收集每个用户最近 5 条交易活动
- 自动去重并保存到数据库
- 调用 AI 批量分析涉及的市场
- 显示分析结果和交易机会

### 2. 查询跟单数据

```bash
python polymarket/query_copy_trading.py
```

查看：
- 排行榜 Top 用户
- 用户活动汇总
- 热门市场（被多个顶级用户交易）
- 最近交易活动

## 数据库表

### qd_polymarket_top_users
存储排行榜用户信息

字段：
- `user_address`: 用户地址
- `period`: 排行榜周期（day/week/month/all）
- `rank`: 排名
- `volume`: 交易量
- `profit`: 利润
- `trades`: 交易次数
- `win_rate`: 胜率

### qd_polymarket_user_activities
存储用户交易活动

字段：
- `activity_id`: 活动唯一ID（防重复）
- `user_address`: 用户地址
- `market_id`: 市场ID
- `side`: 买入/卖出（BUY/SELL）
- `outcome`: YES/NO
- `size`: 交易数量
- `price`: 交易价格
- `timestamp`: 交易时间

## 工作流程

```
1. 获取排行榜 → 4个榜 × Top5 = 最多20个用户
2. 获取活动 → 每人5条 = 最多100条活动
3. 去重保存 → 基于activity_id自动去重
4. 提取市场 → 获取涉及的所有市场ID
5. AI分析 → 调用batch_analyze_markets
6. 显示结果 → 推荐、评分、理由
```

## API 端点

### 排行榜 API
```
GET https://data-api.polymarket.com/leaderboard?period={period}&limit=5
```

参数：
- `period`: day, week, month, all
- `limit`: 返回数量（默认5）

### 用户活动 API
```
GET https://data-api.polymarket.com/activity?user={address}&limit=5
```

参数：
- `user`: 用户地址
- `limit`: 返回数量（默认5）

## 代码结构

```
backend_api_python/
├── polymarket/
│   ├── run_once_copy_trading.py    # 主执行脚本
│   ├── query_copy_trading.py       # 数据查询脚本
│   └── COPY_TRADING_README.md      # 本文档
├── app/
│   └── data_sources/
│       └── polymarket.py           # 新增2个方法
└── migrations/
    └── add_copy_trading_tables.sql # 数据库迁移
```

## 新增方法

在 `app/data_sources/polymarket.py` 中：

```python
def get_leaderboard(period='month', limit=5):
    """获取排行榜"""
    
def get_user_activities(user_address, limit=5):
    """获取用户交易活动"""
```

## 使用建议

1. **定期运行**: 每天运行一次收集最新数据
2. **关注热门市场**: 被多个顶级用户交易的市场值得关注
3. **参考AI分析**: 结合AI推荐和顶级用户行为做决策
4. **注意时效性**: 市场变化快，及时更新数据

## 注意事项

- 数据自动去重，重复运行不会产生重复记录
- AI 分析结果不存储，每次实时计算
- 只追踪 Top5 用户，每人最近 5 条活动
- 支持 4 个排行榜周期：day, week, month, all

## 下一步优化

- [ ] 添加定时任务自动运行
- [ ] 增加用户交易模式分析
- [ ] 添加跟单策略推荐
- [ ] 实现自动跟单功能
