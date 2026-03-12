# Polymarket 跟单系统 - condition_id 修复总结

## 问题描述

跟单系统中存在 market_id 格式不一致的问题：

- **跟单活动表** (`qd_polymarket_user_activities`): 使用 `condition_id` 格式（66字符十六进制哈希，如 `0x812d368...`）
- **AI 分析表** (`qd_polymarket_ai_analysis`): 使用数字 `market_id` 格式（6位数字，如 `564176`）
- **市场表** (`qd_polymarket_markets`): 同时包含数字 `market_id` 和 `condition_id` 字段，但大部分记录的 `condition_id` 为 NULL

这导致无法关联查询跟单活动和 AI 分析结果。

## 根本原因

1. Polymarket API 返回的数据中，`market` 对象包含 `conditionId` 字段
2. 但在 `_parse_gamma_events` 方法中，虽然提取了 `conditionId` 用于获取价格，但没有将其保存到返回的 market_data 字典中
3. 导致保存到数据库时，`condition_id` 字段为 NULL

## 修复方案

### 1. 修改 `_parse_gamma_events` 方法

**文件**: `backend_api_python/app/data_sources/polymarket.py`

**修改内容**:
- 将 `condition_id` 的提取移到 try 块外部，确保它在整个方法中可用
- 在返回的 `market_data` 字典中添加 `condition_id` 字段

**代码变更**:

```python
# 在解析市场数据时，提前提取 condition_id
condition_id = market.get("conditionId") or event.get("conditionId")

# ... 其他处理逻辑 ...

# 在构建 market_data 时包含 condition_id
market_data = {
    "market_id": market_id,
    "question": question,
    "category": inferred_category,
    "current_probability": round(current_probability, 2),
    "volume_24h": volume_24h,
    "liquidity": liquidity,
    "end_date_iso": end_date_iso,
    "status": "active" if market.get("active", event.get("active", True)) else "closed",
    "outcome_tokens": outcome_tokens,
    "polymarket_url": polymarket_url,
    "slug": slug if slug else None,
    "condition_id": condition_id  # 新增：保存 condition_id
}
```

### 2. 数据库表结构

`qd_polymarket_markets` 表已经包含 `condition_id` 字段（通过之前的迁移添加），无需修改表结构。

### 3. 跟单活动保存逻辑

**文件**: `backend_api_python/polymarket/run_once_copy_trading.py`

**现有逻辑**:
- 从 API 获取的活动包含 `conditionId` 字段
- 通过 `conditionId` 查询数据库获取数字 `market_id`
- 如果找不到，使用 `conditionId` 作为 fallback

**优化建议**:
- 如果数据库中没有对应的 `condition_id`，可以调用 `get_market_by_condition_id` 从 API 获取并保存
- 这样可以确保后续查询能够关联到正确的数字 `market_id`

## 测试结果

### 测试1: condition_id 提取和保存

```bash
python polymarket/test_condition_id_fix_v2.py
```

**结果**: ✓ 通过
- 从 API 获取的市场包含 `condition_id`
- 保存到数据库后，`condition_id` 字段正确填充

### 测试2: 跟单活动关联

```bash
python polymarket/test_copy_trading_market_id.py
```

**结果**: ✓ 通过
- 用户活动包含 `conditionId`
- 可以通过 `conditionId` 查询到数字 `market_id`
- 可以关联 AI 分析结果

## 数据迁移

### 更新现有市场数据

对于数据库中已有的市场（`condition_id` 为 NULL），需要运行 Polymarket Worker 更新：

```bash
python polymarket/run_once_polymarket_worker.py
```

这将：
1. 从 API 获取最新的市场数据
2. 提取 `condition_id` 并保存到数据库
3. 更新现有记录的 `condition_id` 字段

### 验证数据

```sql
-- 检查有多少市场已填充 condition_id
SELECT COUNT(*) FROM qd_polymarket_markets WHERE condition_id IS NOT NULL;

-- 检查跟单活动是否能关联到市场
SELECT 
    a.activity_id,
    a.market_id as activity_market_id,
    m.market_id as db_market_id,
    m.question
FROM qd_polymarket_user_activities a
LEFT JOIN qd_polymarket_markets m ON m.condition_id = a.market_id
LIMIT 10;
```

## 后续工作

1. **运行 Worker 更新数据**: 确保所有市场都有 `condition_id`
2. **修改跟单脚本**: 当找不到 `condition_id` 时，自动从 API 获取并保存
3. **创建关联查询**: 编写 SQL 查询，通过 `condition_id` 关联跟单活动和 AI 分析结果

## 关联查询示例

```sql
-- 查询跟单活动及其 AI 分析结果
SELECT 
    a.user_address,
    a.side,
    a.outcome,
    a.size,
    a.price,
    a.timestamp,
    m.market_id,
    m.question,
    ai.recommendation,
    ai.opportunity_score,
    ai.confidence_score,
    ai.reasoning
FROM qd_polymarket_user_activities a
JOIN qd_polymarket_markets m ON m.condition_id = a.market_id
LEFT JOIN qd_polymarket_ai_analysis ai ON ai.market_id = m.market_id
WHERE a.timestamp > NOW() - INTERVAL '24 hours'
ORDER BY a.timestamp DESC
LIMIT 20;
```

## 总结

修复已完成，现在系统可以：
1. 从 API 获取市场时正确提取和保存 `condition_id`
2. 通过 `condition_id` 关联跟单活动和市场数据
3. 通过数字 `market_id` 关联市场数据和 AI 分析结果
4. 实现完整的数据流：用户活动 → condition_id → 数字 market_id → AI 分析结果

下一步需要运行 Worker 更新现有数据，并测试完整的跟单流程。
