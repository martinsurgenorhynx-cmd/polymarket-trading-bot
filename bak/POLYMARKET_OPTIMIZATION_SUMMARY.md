# Polymarket 交易流程优化总结

## 优化目标

减少 `trade_best_opportunity.py` 中的命令行查询次数，提升交易执行速度和成功率。

## 问题分析

### 原有流程的性能瓶颈

在 `trade_best_opportunity.py` 的 `get_best_opportunities()` 函数中，对每个候选市场需要执行 **3次 CLI 查询**：

1. `polymarket markets search` - 搜索市场获取 condition_id
2. `polymarket clob market` - 获取市场详情（accepting_orders, tokens）
3. `polymarket clob price` - 获取实时买入价

如果有10个候选市场，最坏情况：
- 10个市场 × 3次查询 × 10秒超时 = **最多300秒（5分钟）**

### 无法优化的查询

以下查询必须在交易前实时获取：
- **实时买入价格** - 价格波动频繁，必须获取最新价格
- **账户余额** - 交易前必须检查
- **交易历史** - 用于避免重复交易

## 优化方案（方案A）

### 核心思路

在 `run_once_polymarket_worker.py` 运行时，提前收集交易所需的关键信息并存入数据库，这样 `trade_best_opportunity.py` 可以直接从数据库读取，减少 CLI 查询。

### 实施步骤

#### 1. 数据库表结构增强

新增字段到 `qd_polymarket_markets` 表：

```sql
-- 交易必需字段
condition_id VARCHAR(255)          -- Polymarket condition ID
yes_token_id VARCHAR(255)          -- YES 方向的 token ID (十六进制)
no_token_id VARCHAR(255)           -- NO 方向的 token ID (十六进制)
accepting_orders BOOLEAN           -- 市场是否接受订单
tokens_data JSONB                  -- 完整的 tokens 数组数据
```

迁移脚本：`backend_api_python/migrations/add_trading_fields.sql`

#### 2. Worker 增强数据收集

在 `polymarket_worker.py` 中新增 `_enrich_markets_with_trading_data()` 方法：

- 在市场数据更新后，对每个市场执行 CLI 查询
- 获取 `condition_id`、`token_id`、`accepting_orders` 等信息
- 将这些信息存入数据库

关键代码：
```python
def _enrich_markets_with_trading_data(self, markets: List[Dict]) -> int:
    """增强市场数据，获取交易所需的信息"""
    # 对每个市场：
    # 1. 搜索市场获取 condition_id
    # 2. 获取市场详情获取 tokens 和 accepting_orders
    # 3. 更新市场数据
```

#### 3. 优化交易脚本查询逻辑

在 `trade_best_opportunity.py` 中：

**优化前（每个市场3次查询）：**
```python
# 1. 搜索市场
result = run_cli(f'polymarket markets search "{question}"')
# 2. 获取市场详情
market_result = run_cli(f'polymarket clob market {condition_id}')
# 3. 获取买入价
price_result = run_cli(f'polymarket clob price {token_id} --side buy')
```

**优化后（每个市场1次查询）：**
```python
# 从数据库直接读取 condition_id, token_id, accepting_orders
# 只需要获取实时买入价
price_result = run_cli(f'polymarket clob price {token_id} --side buy')
```

#### 4. 数据库查询优化

新增过滤条件，直接排除不可交易的市场：

```sql
WHERE a.opportunity_score BETWEEN 60 AND 85
  AND m.liquidity > 10000
  AND m.volume_24h > 1000
  AND m.status = 'active'
  AND m.end_date_iso > NOW()
  AND m.accepting_orders = true        -- 新增：只查询接受订单的市场
  AND m.condition_id IS NOT NULL       -- 新增：必须有 condition_id
  AND m.yes_token_id IS NOT NULL       -- 新增：必须有 token_id
  AND m.no_token_id IS NOT NULL
```

## 优化效果

### 查询次数对比

| 阶段 | 优化前 | 优化后 | 减少 |
|------|--------|--------|------|
| Worker 运行 | 0次 | N次（一次性） | - |
| 每个候选市场 | 3次 | 1次 | -67% |
| 10个候选市场 | 30次 | 10次 | -67% |

### 性能提升

- **执行速度**：从可能的5分钟减少到30秒左右（提升10倍）
- **超时风险**：更少的 CLI 调用意味着更少的超时可能
- **成功率**：预先过滤不合格市场，只对高质量机会进行验证
- **用户体验**：更快的响应时间，更少的等待

### 数据新鲜度

- Worker 定期运行（如每30分钟），保持数据相对新鲜
- 实时买入价仍然在交易前获取，确保价格准确性
- 可以手动运行 `run_once_polymarket_worker.py` 立即更新数据

## 使用方法

### 1. 运行数据库迁移

```bash
cd backend_api_python
psql -U your_user -d your_database -f migrations/add_trading_fields.sql
```

### 2. 运行 Worker 收集数据

```bash
cd backend_api_python/polymarket
python run_once_polymarket_worker.py --max-analyze 50
```

这会：
- 获取市场数据
- 增强交易信息（condition_id, token_id 等）
- 执行 AI 分析
- 保存到数据库

### 3. 执行交易

```bash
cd backend_api_python/polymarket
python trade_best_opportunity.py
```

现在交易脚本会：
- 从数据库读取预筛选的市场（已有 condition_id, token_id）
- 只需查询实时买入价
- 快速完成交易验证

## 注意事项

### 数据时效性

- 增强的交易数据（condition_id, token_id）相对稳定，不会频繁变化
- 价格数据会实时变化，因此仍需在交易前查询
- `accepting_orders` 状态可能变化，但概率较低

### 建议运行频率

- **Worker**：每30分钟运行一次（自动）或手动运行
- **交易脚本**：根据需要随时运行

### 回退方案

如果数据库中没有增强数据（condition_id 为空），交易脚本会：
- 显示提示信息
- 建议运行 Worker 收集数据
- 不会执行交易（避免错误）

## 未来优化方向

1. **增量更新**：只更新变化的市场，而不是全量更新
2. **价格缓存**：对价格数据进行短期缓存（如5分钟），进一步减少查询
3. **并行查询**：使用异步/并发方式加速 CLI 查询
4. **API 直接调用**：研究是否可以直接调用 Polymarket API，避免 CLI 开销

## 相关文件

- `backend_api_python/migrations/add_trading_fields.sql` - 数据库迁移脚本
- `backend_api_python/app/services/polymarket_worker.py` - Worker 增强逻辑
- `backend_api_python/app/data_sources/polymarket.py` - 数据保存逻辑
- `backend_api_python/polymarket/trade_best_opportunity.py` - 优化后的交易脚本
- `backend_api_python/polymarket/run_once_polymarket_worker.py` - Worker 运行脚本
