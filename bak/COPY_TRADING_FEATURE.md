# Polymarket 跟单功能 - 高置信度交易机会

## 功能概述

`trade_best_opportunity.py` 现在支持跟单功能，可以识别并优先推荐同时满足以下条件的市场：
1. AI 评分高（≥70分）
2. 有顶级用户（排名前20）在交易
3. AI 推荐方向与顶级用户交易方向一致

## 配置选项

在 `trade_best_opportunity.py` 文件顶部有两个配置选项：

```python
# 筛选严格程度（1-10）
FILTER_LEVEL = 4  # 默认中等筛选

# 是否启用跟单功能
USE_COPY_TRADING = True  # 默认启用
```

### FILTER_LEVEL（筛选级别）

- **1-3**: 宽松 - 更多机会，质量参差不齐
- **4-6**: 中等 - 平衡数量和质量（推荐）
- **7-10**: 严格 - 只要最好的机会，数量较少

### USE_COPY_TRADING（跟单功能）

- **True**: 优先选择有顶级用户交易的市场（推荐）
- **False**: 只按 AI 评分选择市场

## 优先级排序

当 `USE_COPY_TRADING = True` 时，市场按以下优先级排序：

### 1. 最高优先级 ⭐
- 有顶级用户交易
- AI 推荐方向与用户交易方向一致
- 综合得分 = 1000 + (用户数量 × 50) + (AI评分 × 0.7) + (交易量权重 × 0.3)

**示例**：
```
AI 推荐: YES
顶级用户交易: YES, YES, NO
方向一致: ✓ (2个用户买YES)
```

### 2. 次优先级
- 有顶级用户交易
- 但方向不一致或未知
- 综合得分 = 500 + (用户数量 × 30) + (AI评分 × 0.7) + (交易量权重 × 0.3)

**示例**：
```
AI 推荐: YES
顶级用户交易: NO, NO
方向一致: ✗
```

### 3. 基础优先级
- 只有 AI 推荐，无顶级用户交易
- 综合得分 = (AI评分 × 0.7) + (交易量权重 × 0.3)

## 使用方法

### 1. 运行跟单数据收集

首先需要收集顶级用户的交易活动：

```bash
cd backend_api_python
python polymarket/run_once_copy_trading.py
```

这将：
- 获取排行榜前5名用户
- 收集他们最近的交易活动
- 保存到数据库

### 2. 运行市场数据收集和 AI 分析

```bash
python polymarket/run_once_polymarket_worker.py
```

这将：
- 获取热门市场数据
- 运行 AI 分析
- 保存分析结果

### 3. 查找高置信度交易机会

```bash
python polymarket/trade_best_opportunity.py
```

脚本会：
1. 从数据库查询符合条件的市场
2. 优先显示有顶级用户交易且方向一致的市场（⭐标记）
3. 验证价格和流动性
4. 让用户选择要交易的市场

### 4. 测试查询功能

```bash
python polymarket/test_copy_trading_opportunities.py
```

这将显示所有高置信度机会，包括：
- 顶级用户交易信息
- AI 推荐方向
- 方向是否一致

## 输出示例

### 有跟单信号且方向一致 ⭐

```
机会 #1 ⭐:
  问题: Will Bitcoin reach $100,000 by end of 2025?
  推荐: YES
  评分: 85/100
  置信度: 75%
  价格: $0.6500
  流动性: $500,000
  🎯 顶级用户: 3 人交易
     排名: 1, 3, 5
     方向: YES, YES, YES
     ⭐ AI 推荐方向与顶级用户一致（高置信度）
  AI理由: 比特币价格趋势强劲，技术指标看涨...
```

### 有跟单信号但方向不一致

```
机会 #2:
  问题: Will Ethereum reach $5,000 by end of 2025?
  推荐: YES
  评分: 78/100
  置信度: 70%
  价格: $0.5500
  流动性: $300,000
  🎯 顶级用户: 2 人交易
     排名: 2, 7
     方向: NO, NO
  AI理由: 以太坊升级预期...
```

### 只有 AI 推荐

```
机会 #3:
  问题: Will Solana reach $200 by end of 2025?
  推荐: YES
  评分: 75/100
  置信度: 68%
  价格: $0.4500
  流动性: $250,000
  AI理由: Solana 生态系统增长...
```

## 数据库查询

可以使用 SQL 查询高置信度机会：

```sql
-- 查询6: 高分 AI 推荐 + 顶级用户也在交易的市场
WITH top_user_markets AS (
    SELECT DISTINCT
        m.market_id,
        COUNT(DISTINCT a.user_address) as top_users_count,
        STRING_AGG(DISTINCT u.rank::text, ', ') as user_ranks,
        STRING_AGG(DISTINCT a.outcome, ', ') as user_outcomes
    FROM qd_polymarket_user_activities a
    JOIN qd_polymarket_markets m ON m.condition_id = a.market_id
    LEFT JOIN qd_polymarket_top_users u ON u.user_address = a.user_address
        AND DATE(u.created_at) = CURRENT_DATE
        AND u.rank <= 20
    WHERE a.timestamp > NOW() - INTERVAL '24 hours'
    GROUP BY m.market_id
    HAVING COUNT(DISTINCT a.user_address) > 0
)
SELECT 
    m.market_id,
    m.question,
    ai.recommendation,
    ai.opportunity_score,
    ai.confidence_score,
    tum.top_users_count,
    tum.user_ranks,
    tum.user_outcomes
FROM qd_polymarket_ai_analysis ai
JOIN qd_polymarket_markets m ON m.market_id = ai.market_id
JOIN top_user_markets tum ON tum.market_id = ai.market_id
WHERE ai.recommendation IN ('YES', 'NO')
    AND ai.opportunity_score >= 70
    AND ai.created_at > NOW() - INTERVAL '24 hours'
ORDER BY tum.top_users_count DESC, ai.opportunity_score DESC
LIMIT 10;
```

## 注意事项

1. **数据时效性**：
   - 跟单数据每次运行 `run_once_copy_trading.py` 更新
   - AI 分析数据有24小时缓存
   - 建议每天运行一次数据收集

2. **方向一致性判断**：
   - 只要有一个顶级用户的交易方向与 AI 推荐一致，就认为方向一致
   - 例如：AI 推荐 YES，用户交易 "YES, YES, NO"，判定为一致

3. **风险提示**：
   - 顶级用户的交易不代表一定盈利
   - 方向一致只是增加置信度，不保证成功
   - 仍需结合 AI 分析理由和市场情况判断

4. **性能优化**：
   - 查询使用了 CTE 和索引优化
   - 只查询24小时内的活动和分析
   - 限制顶级用户排名前20

## 故障排除

### 问题1: 没有找到跟单信号

**原因**：
- 数据库中没有跟单活动数据
- 顶级用户最近24小时没有交易

**解决**：
```bash
python polymarket/run_once_copy_trading.py
```

### 问题2: 方向都不一致

**原因**：
- 顶级用户的交易方向与 AI 推荐相反
- 可能是市场情绪变化

**解决**：
- 仔细阅读 AI 分析理由
- 考虑是否跟随顶级用户的方向
- 或者等待方向一致的机会

### 问题3: condition_id 关联失败

**原因**：
- 市场表中 condition_id 字段为 NULL

**解决**：
```bash
python polymarket/run_once_polymarket_worker.py
```

这将更新市场数据并填充 condition_id 字段。

## 相关文件

- `trade_best_opportunity.py`: 主交易脚本
- `run_once_copy_trading.py`: 跟单数据收集
- `test_copy_trading_opportunities.py`: 测试查询
- `query_copy_trading_with_ai.sql`: SQL 查询示例
- `CONDITION_ID_FIX_SUMMARY.md`: condition_id 修复文档

## 更新日志

### 2024-03-09
- ✅ 添加跟单功能
- ✅ 实现方向一致性判断
- ✅ 优化排序算法（方向一致的排最前）
- ✅ 添加 ⭐ 标记高置信度机会
- ✅ 修复 condition_id 关联问题


## 常见问题

### Q1: 为什么有些市场没有显示跟单信息？

**A**: 有以下几种可能：

1. **没有顶级用户交易这个市场**
   - 这是最常见的情况
   - 顶级用户可能专注于特定类型的市场

2. **顶级用户交易的市场已经关闭/结算**
   - 顶级用户往往交易短期市场
   - 这些市场很快就结算了，无法关联到当前活跃市场

3. **跟单数据还没有收集**
   - 需要运行 `run_once_copy_trading.py` 收集数据

**检查方法**：
```bash
# 检查特定市场的跟单情况
python polymarket/check_market_copy_trading.py <market_id>

# 诊断整体数据情况
python polymarket/diagnose_copy_trading.py
```

### Q2: 如何增加跟单信号的覆盖率？

**A**: 可以采取以下措施：

1. **增加排行榜用户数量**
   ```python
   # 在 run_once_copy_trading.py 中修改
   users = polymarket.get_leaderboard(period, limit=10)  # 从5改为10
   ```

2. **增加活动数量**
   ```python
   # 获取每个用户更多的活动
   activities = polymarket.get_user_activities(address, limit=10)  # 从5改为10
   ```

3. **更频繁地收集数据**
   - 每小时运行一次 `run_once_copy_trading.py`
   - 使用定时任务（cron）自动化

4. **扩大时间范围**
   - 修改查询条件，从24小时扩展到48小时或更长

### Q3: 为什么大部分活动无法关联到市场？

**A**: 这是正常现象：

- 诊断显示：89 条活动，只有 11 条能关联到市场
- 原因：78 条活动对应的市场已经关闭/结算
- 顶级用户交易的市场往往是短期市场（几小时到几天）
- 这些市场结算后就不在活跃市场列表中了

**解决方案**：
- 实时跟踪：发现跟单信号后立即交易
- 不要等待：短期市场机会稍纵即逝
- 自动化：使用脚本自动检测和交易

### Q4: 如何找到更多高置信度机会？

**A**: 优化策略：

1. **降低筛选标准**
   ```python
   # 在 trade_best_opportunity.py 中
   FILTER_LEVEL = 3  # 从4降到3，更宽松
   ```

2. **扩大市场范围**
   - 不限制类别
   - 降低流动性要求
   - 扩大价格范围

3. **多样化数据源**
   - 获取多个排行榜（day, week, month）
   - 关注不同类别的顶级用户

4. **实时监控**
   - 设置定时任务每小时检查
   - 发现机会立即通知

## 工具脚本

### 诊断脚本
```bash
# 全面诊断跟单系统数据
python polymarket/diagnose_copy_trading.py
```

输出包括：
- 排行榜用户数据统计
- 用户活动数据统计
- 市场 condition_id 填充情况
- 活动关联情况
- AI 分析数据统计
- 高置信度机会数量
- 示例数据

### 市场检查脚本
```bash
# 检查特定市场的跟单情况
python polymarket/check_market_copy_trading.py <market_id>
```

输出包括：
- 市场基本信息
- 用户活动列表
- 顶级用户活动
- 方向统计
- AI 分析结果

### 修复脚本
```bash
# 修复缺失的市场数据
python polymarket/fix_missing_markets.py
```

功能：
- 查找无法关联的活动
- 从 API 获取缺失的市场
- 自动保存到数据库

## 最佳实践

1. **定期更新数据**
   ```bash
   # 每小时运行一次
   0 * * * * cd /path/to/backend_api_python && python polymarket/run_once_copy_trading.py
   ```

2. **及时交易**
   - 发现高置信度机会后立即交易
   - 不要等待，短期市场机会稍纵即逝

3. **分散风险**
   - 不要只依赖跟单信号
   - 结合 AI 分析和自己的判断
   - 控制仓位，分散投资

4. **监控效果**
   - 记录跟单交易的结果
   - 分析哪些顶级用户更可靠
   - 优化跟单策略
