# AI 记忆与反思系统

## 概览

QuantDinger 拥有完整的 **AI 记忆与反思系统**，能够：
1. ✅ 存储每次分析决策
2. ✅ 追踪历史表现
3. ✅ 自动验证预测准确性
4. ✅ 从错误中学习
5. ✅ 提供相似模式参考

---

## 系统架构

### 核心组件

```
┌─────────────────────────────────────────────────────────────┐
│                    AI 分析服务                                │
│              (FastAnalysisService)                           │
└────────────────────┬────────────────────────────────────────┘
                     │
                     │ 1. 生成分析
                     │ 2. 存储到记忆
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                   记忆系统                                    │
│              (AnalysisMemory)                                │
│                                                              │
│  • 存储分析决策和市场快照                                      │
│  • 检索相似历史模式                                           │
│  • 记录用户反馈                                               │
│  • 自动验证预测结果                                           │
│  • 计算准确率统计                                             │
└────────────────────┬────────────────────────────────────────┘
                     │
                     │ 定期验证
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                 反思验证任务                                   │
│           (run_reflection_task.py)                           │
│                                                              │
│  • 每天自动运行                                               │
│  • 对比预测 vs 实际结果                                       │
│  • 更新准确率统计                                             │
│  • 标记正确/错误的决策                                        │
└─────────────────────────────────────────────────────────────┘
```

---

## 1. 记忆存储 (Memory Storage)

### 数据库表结构

**表名**: `qd_analysis_memory`

| 字段 | 类型 | 说明 |
|-----|------|------|
| `id` | SERIAL | 记忆ID |
| `user_id` | INT | 用户ID |
| `market` | VARCHAR(50) | 市场类型 (Crypto, US_Stock, Forex) |
| `symbol` | VARCHAR(50) | 交易对 (BTCUSDT, AAPL, EURUSD) |
| `decision` | VARCHAR(10) | 决策 (BUY, SELL, HOLD) |
| `confidence` | INT | 置信度 (0-100) |
| `price_at_analysis` | DECIMAL | 分析时价格 |
| `entry_price` | DECIMAL | 建议入场价 |
| `stop_loss` | DECIMAL | 止损价 |
| `take_profit` | DECIMAL | 止盈价 |
| `summary` | TEXT | 分析摘要 |
| `reasons` | JSONB | 决策理由列表 |
| `risks` | JSONB | 风险因素列表 |
| `scores` | JSONB | 各项评分 |
| `indicators_snapshot` | JSONB | 技术指标快照 |
| `raw_result` | JSONB | 完整分析结果 |
| `created_at` | TIMESTAMP | 创建时间 |
| `validated_at` | TIMESTAMP | 验证时间 |
| `actual_outcome` | VARCHAR(20) | 实际结果 |
| `actual_return_pct` | DECIMAL | 实际收益率 (%) |
| `was_correct` | BOOLEAN | 预测是否正确 |
| `user_feedback` | VARCHAR(20) | 用户反馈 |
| `feedback_at` | TIMESTAMP | 反馈时间 |

### 存储流程

```python
# 1. AI 分析完成后自动存储
result = fast_analysis_service.analyze(market="Crypto", symbol="BTCUSDT")

# 2. 存储到记忆系统
memory = get_analysis_memory()
memory_id = memory.store(result, user_id=123)

# 3. 返回给用户（包含 memory_id）
result["memory_id"] = memory_id
```

### 存储的信息

每次分析都会存储：
- **决策信息**: BUY/SELL/HOLD + 置信度
- **市场快照**: 当时的价格、技术指标
- **交易计划**: 入场价、止损、止盈
- **分析理由**: 为什么做出这个决策
- **风险因素**: 需要注意的风险
- **完整结果**: 原始 JSON 数据

---

## 2. 相似模式检索 (Pattern Matching)

### 功能说明

在生成新分析时，系统会自动查找历史上相似的市场情况，作为参考。

### 匹配条件

1. **相同交易对**: 同一个 symbol
2. **相似 RSI**: RSI 值相差 ±15 以内
3. **相同 MACD 信号**: 金叉/死叉/中性
4. **已验证结果**: 优先显示已验证的历史记录
5. **正确决策优先**: 优先显示预测正确的案例

### 使用示例

```python
# 获取相似历史模式
patterns = memory.get_similar_patterns(
    market="Crypto",
    symbol="BTCUSDT",
    current_indicators={
        "rsi": {"value": 65},
        "macd": {"signal": "bullish"}
    },
    limit=3
)

# 返回结果
[
    {
        "id": 123,
        "decision": "BUY",
        "confidence": 75,
        "price": 45000.0,
        "was_correct": True,
        "actual_return_pct": 8.5,
        "similarity": {
            "rsi_match": True,
            "macd_match": True
        }
    },
    ...
]
```

### 在分析中的应用

AI 分析时会自动包含历史模式：

```
Historical patterns with similar conditions:
1. [2024-01-15] BUY at $45,000 → +8.5% (Correct)
   - RSI: 67 (similar to current 65)
   - MACD: Bullish (same as current)
   
2. [2024-01-10] BUY at $43,500 → +5.2% (Correct)
   - RSI: 62 (similar to current 65)
   - MACD: Bullish (same as current)
```

---

## 3. 自动验证 (Automatic Validation)

### 验证机制

系统会定期（建议每天）自动验证历史预测的准确性。

### 验证逻辑

```python
def validate_past_decisions(days_ago=7):
    """
    验证 N 天前的预测
    
    判断标准：
    - BUY 决策: 如果价格上涨 > 2%，则正确
    - SELL 决策: 如果价格下跌 > 2%，则正确
    - HOLD 决策: 如果价格波动 ≤ 5%，则正确
    """
    # 1. 获取 7 天前的未验证记录
    # 2. 获取当前价格
    # 3. 计算实际收益率
    # 4. 判断预测是否正确
    # 5. 更新数据库
```

### 验证结果

```python
{
    "validated": 45,      # 验证了 45 条记录
    "correct": 32,        # 32 条正确
    "incorrect": 13,      # 13 条错误
    "accuracy_pct": 71.1  # 准确率 71.1%
}
```

### 定时任务

**文件**: `scripts/run_reflection_task.py`

```bash
# 手动运行
python scripts/run_reflection_task.py

# 设置 cron 定时任务（每天凌晨 2 点）
0 2 * * * cd /path/to/project && python scripts/run_reflection_task.py
```

---

## 4. 用户反馈 (User Feedback)

### 反馈类型

用户可以对分析结果提供反馈：
- `helpful` - 有帮助
- `not_helpful` - 没帮助
- `accurate` - 准确
- `inaccurate` - 不准确

### 记录反馈

```python
# 用户点击"有帮助"按钮
memory.record_feedback(memory_id=123, feedback="helpful")

# 更新数据库
UPDATE qd_analysis_memory
SET user_feedback = 'helpful', feedback_at = NOW()
WHERE id = 123
```

### 用户满意度统计

```python
stats = memory.get_performance_stats(days=30)

{
    "user_satisfaction_pct": 85.5,  # 85.5% 用户认为有帮助
    "feedback_count": 120,           # 收到 120 条反馈
    "helpful_count": 103             # 103 条"有帮助"
}
```

---

## 5. 性能统计 (Performance Stats)

### 统计指标

```python
stats = memory.get_performance_stats(
    market="Crypto",
    symbol="BTCUSDT",
    days=30
)

# 返回结果
{
    "total_analyses": 150,           # 总分析次数
    "accuracy_pct": 68.5,            # 准确率 68.5%
    "avg_return_pct": 4.2,           # 平均收益率 4.2%
    "decision_distribution": {
        "buy": 85,                   # 85 次 BUY
        "sell": 45,                  # 45 次 SELL
        "hold": 20                   # 20 次 HOLD
    },
    "user_satisfaction_pct": 82.0,  # 用户满意度 82%
    "period_days": 30                # 统计周期 30 天
}
```

### 可视化展示

前端可以展示：
- 📊 准确率趋势图
- 📈 平均收益率
- 🎯 决策分布饼图
- ⭐ 用户满意度
- 📅 历史表现时间线

---

## 6. 从错误中学习 (Learning from Mistakes)

### 错误分析

系统会自动标记错误的预测：

```sql
SELECT * FROM qd_analysis_memory
WHERE was_correct = FALSE
ORDER BY created_at DESC
LIMIT 10;
```

### 错误模式识别

可以分析错误预测的共同特征：
- 哪些市场条件下容易出错？
- 哪些技术指标组合不可靠？
- 哪些决策类型准确率最低？

### 改进建议

基于错误分析，可以：
1. 调整 AI prompt，强调容易出错的场景
2. 增加风险提示
3. 降低某些情况下的置信度
4. 优化技术指标权重

---

## 7. API 接口

### 7.1 获取历史记录

```python
GET /api/analysis/history?page=1&page_size=20

Response:
{
    "code": 1,
    "msg": "success",
    "data": {
        "items": [...],
        "total": 150,
        "page": 1,
        "page_size": 20
    }
}
```

### 7.2 删除记录

```python
DELETE /api/analysis/history/{memory_id}

Response:
{
    "code": 1,
    "msg": "success"
}
```

### 7.3 提交反馈

```python
POST /api/analysis/feedback
{
    "memory_id": 123,
    "feedback": "helpful"
}

Response:
{
    "code": 1,
    "msg": "success"
}
```

### 7.4 获取性能统计

```python
GET /api/analysis/stats?market=Crypto&symbol=BTCUSDT&days=30

Response:
{
    "code": 1,
    "msg": "success",
    "data": {
        "total_analyses": 150,
        "accuracy_pct": 68.5,
        "avg_return_pct": 4.2,
        ...
    }
}
```

---

## 8. Polymarket 的记忆系统

### 当前状态

Polymarket 分析结果**已经**存储到记忆系统：

```python
# polymarket_batch_analyzer.py
def save_batch_analysis(self, analyzed_markets):
    """保存批量分析结果到数据库"""
    for market in analyzed_markets:
        # 存储到 qd_polymarket_ai_analysis 表
        cur.execute("""
            INSERT INTO qd_polymarket_ai_analysis (...)
            VALUES (...)
        """)
```

### 数据库表

**表名**: `qd_polymarket_ai_analysis`

| 字段 | 说明 |
|-----|------|
| `market_id` | Polymarket 市场 ID |
| `recommendation` | BUY_YES / BUY_NO / HOLD |
| `confidence_score` | 置信度 |
| `opportunity_score` | 机会评分 |
| `ai_predicted_probability` | AI 预测概率 |
| `market_probability` | 市场当前概率 |
| `divergence` | 概率差异 |
| `reasoning` | 分析理由 |
| `key_factors` | 关键因素 |
| `created_at` | 创建时间 |

### 需要添加的功能

为了完整的反思系统，Polymarket 还需要：

1. **结果验证**
   ```python
   def validate_polymarket_predictions():
       """
       事件结束后，验证预测是否正确
       - 获取事件最终结果（YES=1 或 NO=0）
       - 对比 AI 的建议
       - 计算准确率
       """
   ```

2. **性能统计**
   ```python
   def get_polymarket_stats():
       """
       统计 Polymarket 预测表现
       - 总预测数
       - 准确率
       - 平均机会评分
       - 最佳/最差预测
       """
   ```

3. **相似事件检索**
   ```python
   def find_similar_events(market_id):
       """
       查找历史上相似的预测市场
       - 相同类别（政治、体育、加密货币等）
       - 相似的概率分布
       - 相似的交易量
       """
   ```

---

## 9. 使用示例

### 示例 1: 完整的分析流程

```python
from app.services.fast_analysis import FastAnalysisService
from app.services.analysis_memory import get_analysis_memory

# 1. 执行分析
service = FastAnalysisService()
result = service.analyze(
    market="Crypto",
    symbol="BTCUSDT",
    user_id=123
)

# 2. 自动存储到记忆（已在 analyze() 内部完成）
print(f"Memory ID: {result['memory_id']}")

# 3. 查看相似历史模式（已在分析中包含）
print(result['memory_context'])

# 4. 用户提供反馈
memory = get_analysis_memory()
memory.record_feedback(result['memory_id'], "helpful")
```

### 示例 2: 定期验证任务

```python
from app.services.analysis_memory import get_analysis_memory

# 验证 7 天前的预测
memory = get_analysis_memory()
stats = memory.validate_past_decisions(days_ago=7)

print(f"验证了 {stats['validated']} 条记录")
print(f"准确率: {stats['accuracy_pct']}%")
print(f"正确: {stats['correct']}, 错误: {stats['incorrect']}")
```

### 示例 3: 查看性能统计

```python
from app.services.analysis_memory import get_analysis_memory

memory = get_analysis_memory()

# 查看 BTC 最近 30 天的表现
stats = memory.get_performance_stats(
    market="Crypto",
    symbol="BTCUSDT",
    days=30
)

print(f"总分析次数: {stats['total_analyses']}")
print(f"准确率: {stats['accuracy_pct']}%")
print(f"平均收益: {stats['avg_return_pct']}%")
print(f"用户满意度: {stats['user_satisfaction_pct']}%")
```

---

## 10. 未来改进方向

### 10.1 高级模式识别
- 使用向量数据库（如 pgvector）进行语义相似度匹配
- 机器学习模型识别复杂模式
- 多维度特征匹配（不仅是 RSI/MACD）

### 10.2 自适应学习
- 根据历史准确率动态调整置信度
- 识别 AI 的"强项"和"弱项"市场
- 自动优化分析参数

### 10.3 集成强化学习
- 将交易结果作为奖励信号
- 持续优化决策策略
- A/B 测试不同的分析方法

### 10.4 多模型集成
- 记录不同 LLM 模型的表现
- 自动选择最适合的模型
- 模型投票机制

### 10.5 Polymarket 完整反思
- 事件结束后自动验证
- 计算 Brier Score（概率预测准确度）
- 识别高价值预测机会

---

## 11. 相关文件

### 核心文件
- `app/services/analysis_memory.py` - 记忆系统核心实现
- `app/services/fast_analysis.py` - AI 分析服务（集成记忆）
- `scripts/run_reflection_task.py` - 定期验证任务

### Polymarket 相关
- `app/services/polymarket_batch_analyzer.py` - 批量分析和存储
- `app/services/polymarket_worker.py` - 后台任务
- `query_polymarket_results.py` - 查询分析结果

### 数据库
- `qd_analysis_memory` - 通用分析记忆表
- `qd_polymarket_ai_analysis` - Polymarket 专用表

---

## 总结

QuantDinger 的 AI 记忆与反思系统是一个**完整的学习闭环**：

1. 📝 **记录**: 每次分析都存储详细信息
2. 🔍 **参考**: 查找相似历史模式作为参考
3. ✅ **验证**: 定期自动验证预测准确性
4. 📊 **统计**: 计算准确率和性能指标
5. 💬 **反馈**: 收集用户反馈
6. 🎯 **改进**: 从错误中学习，持续优化

这个系统让 AI 不仅能做出决策，还能**反思自己的决策**，并**从经验中学习**，不断提高预测准确性。
