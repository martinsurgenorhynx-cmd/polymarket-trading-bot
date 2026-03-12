# Polymarket Worker 使用指南

## 📍 文件位置

**`backend_api_python/app/services/polymarket_worker.py`**

---

## 🎯 功能概述

Polymarket Worker 是一个后台任务服务，用于：

1. **自动更新市场数据** - 从Polymarket获取最新的预测市场数据
2. **AI批量分析** - 使用LLM分析市场机会，识别高价值交易机会
3. **智能筛选** - 先用规则筛选，再用AI分析，节省token
4. **结果存储** - 将分析结果保存到数据库

---

## 🚀 运行方式

### 方式1: 单次运行（推荐用于测试）

```bash
cd backend_api_python
python -m app.services.polymarket_worker
```

**说明**: 立即执行一次市场数据更新和AI分析，完成后退出。

---

### 方式2: 持续运行（后台服务模式）

```bash
cd backend_api_python
python -m app.services.polymarket_worker --daemon
```

**说明**: 作为后台服务持续运行，每30分钟自动更新一次。按 `Ctrl+C` 停止。

---

### 方式3: 自定义更新间隔

```bash
# 每10分钟更新一次
python -m app.services.polymarket_worker --daemon --interval 10

# 每60分钟更新一次
python -m app.services.polymarket_worker --daemon --interval 60
```

---

### 方式4: 仅更新数据（不分析）

```bash
python -m app.services.polymarket_worker --update-only
```

**说明**: 只从Polymarket获取市场数据，不进行AI分析。适合快速更新数据。

---

### 方式5: 指定分析的分类

```bash
# 只分析加密货币和政治相关市场
python -m app.services.polymarket_worker --categories crypto,politics

# 只分析加密货币，每个分类获取100个市场
python -m app.services.polymarket_worker --categories crypto --limit 100
```

---

### 方式6: 控制分析数量

```bash
# 最多分析50个市场（默认30个）
python -m app.services.polymarket_worker --max-analyze 50

# 每个分类获取100个市场，最多分析20个
python -m app.services.polymarket_worker --limit 100 --max-analyze 20
```

---

## 📋 命令行参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--daemon` | flag | - | 持续运行模式（后台服务） |
| `--interval` | int | 30 | 更新间隔（分钟） |
| `--update-only` | flag | - | 仅更新市场数据，不进行AI分析 |
| `--analyze-only` | flag | - | 仅分析已有市场，不更新数据（暂不支持） |
| `--categories` | str | all | 指定分析的分类，用逗号分隔 |
| `--limit` | int | 50 | 每个分类获取的市场数量 |
| `--max-analyze` | int | 30 | 最多分析的市场数量 |

---

## 📊 支持的市场分类

默认分析以下10个分类：

1. `crypto` - 加密货币
2. `politics` - 政治
3. `economics` - 经济
4. `sports` - 体育
5. `tech` - 科技
6. `finance` - 金融
7. `geopolitics` - 地缘政治
8. `culture` - 文化
9. `climate` - 气候
10. `entertainment` - 娱乐

---

## 🔍 工作流程

### 完整流程（默认）

```
1. 获取市场数据
   ├─ 从10个分类获取市场（每个50个）
   ├─ 去重（按market_id）
   └─ 总计约500个市场
   
2. 规则筛选
   ├─ 条件: 24h交易量 > $5,000 且 概率偏差 > 8%
   └─ 筛选出高价值机会
   
3. AI分析
   ├─ 按交易量和概率偏差排序
   ├─ 取前30个（可配置）
   └─ 调用LLM批量分析
   
4. 保存结果
   └─ 存储到数据库（qd_polymarket_ai_analysis表）
```

### 仅更新模式（--update-only）

```
1. 获取市场数据
   └─ 从指定分类获取市场
   
2. 完成（跳过AI分析）
```

---

## 💡 使用示例

### 示例1: 快速测试

```bash
# 只分析加密货币市场，最多分析5个
python -m app.services.polymarket_worker \
  --categories crypto \
  --limit 20 \
  --max-analyze 5
```

**输出示例**:
```
================================================================================
Polymarket Worker - 市场数据更新和AI分析
================================================================================
运行模式: 单次运行
更新间隔: 30 分钟
操作模式: 更新+分析
================================================================================

分类: crypto
每个分类获取: 20 个市场
最多分析: 5 个市场

================================================================================
步骤 1: 获取市场数据
================================================================================
[1/1] 获取 crypto 分类...
  ✓ 获取 20 个市场

总计: 20 个市场（去重后 20 个）

================================================================================
步骤 2: AI分析市场机会
================================================================================

[2.1] 规则筛选高价值机会...
  ✓ 筛选出 8 个高价值机会

[2.2] AI分析前 5 个机会...
  （这可能需要几分钟，请耐心等待）

  [1/5] Will Bitcoin reach $100,000 by end of 2024?...
       概率: 65.3%, 24h交易量: $125,430
  [2/5] Will Ethereum surpass $5,000 in 2024?...
       概率: 42.1%, 24h交易量: $89,250
  ...

开始AI分析...

  ✓ 分析完成: 5 个市场

[2.3] 保存分析结果到数据库...
  ✓ 已保存 5 个分析结果

================================================================================
分析摘要
================================================================================

决策分布:
  HOLD: 2 个
  NO: 1 个
  YES: 2 个

高分机会（机会评分 > 75）:
  • Will Bitcoin reach $100,000 by end of 2024?
    机会评分: 82.5
    建议: YES
    置信度: 75.0%

================================================================================
执行完成！耗时: 125.3 秒
================================================================================
```

---

### 示例2: 生产环境部署

```bash
# 作为后台服务运行，每小时更新一次
nohup python -m app.services.polymarket_worker \
  --daemon \
  --interval 60 \
  > polymarket_worker.log 2>&1 &

# 查看日志
tail -f polymarket_worker.log

# 停止服务
pkill -f polymarket_worker
```

---

### 示例3: 定时任务（Cron）

```bash
# 编辑crontab
crontab -e

# 添加定时任务（每天凌晨2点运行）
0 2 * * * cd /path/to/backend_api_python && python -m app.services.polymarket_worker >> /var/log/polymarket_worker.log 2>&1
```

---

## 🔧 配置

### 环境变量

在 `.env` 文件中配置：

```bash
# Polymarket Worker配置
POLYMARKET_UPDATE_INTERVAL_MIN=30    # 更新间隔（分钟）
POLYMARKET_ANALYSIS_CACHE_MIN=30     # 分析结果缓存时间（分钟）

# LLM配置（用于AI分析）
LLM_PROVIDER=openai
OPENAI_API_KEY=your-api-key-here
OPENAI_BASE_URL=https://coding.dashscope.aliyuncs.com/v1
OPENAI_MODEL=glm-5
```

---

## 📊 数据库表结构

分析结果保存在 `qd_polymarket_ai_analysis` 表：

```sql
CREATE TABLE qd_polymarket_ai_analysis (
    id SERIAL PRIMARY KEY,
    market_id VARCHAR(100) NOT NULL,
    user_id INTEGER,
    ai_predicted_probability DECIMAL(5,2),
    market_probability DECIMAL(5,2),
    divergence DECIMAL(5,2),
    recommendation VARCHAR(20),  -- YES/NO/HOLD
    confidence_score DECIMAL(5,2),
    opportunity_score DECIMAL(5,2),
    risk_level VARCHAR(20),
    reasoning TEXT,
    key_factors JSONB,
    related_assets JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);
```

---

## 🎯 优化策略

### 1. 规则筛选（节省Token）

在调用LLM之前，先用规则筛选：

```python
# 筛选条件
volume > $5,000 AND |probability - 50%| > 8%
```

**效果**: 
- 从500个市场筛选到约30-50个
- 节省90%的LLM调用
- 只分析最有价值的机会

### 2. 批量分析（提高效率）

使用 `PolymarketBatchAnalyzer` 批量分析：

```python
analyzed_markets = batch_analyzer.batch_analyze_markets(
    markets,
    max_opportunities=30
)
```

**效果**:
- 一次LLM调用分析多个市场
- 减少API调用次数
- 提高分析速度

### 3. 智能排序

按交易量和概率偏差排序：

```python
markets.sort(
    key=lambda x: (x['volume_24h'] * abs(x['current_probability'] - 50)),
    reverse=True
)
```

**效果**:
- 优先分析高价值机会
- 确保分析最有潜力的市场

---

## 🐛 故障排查

### 问题1: 无法连接到Polymarket API

**症状**: 
```
Failed to fetch markets for category crypto: Connection timeout
```

**解决方法**:
1. 检查网络连接
2. 配置代理（如果需要）
3. 检查Polymarket API状态

---

### 问题2: LLM API返回401错误

**症状**:
```
openai API HTTP error: 401 Client Error: Unauthorized
```

**解决方法**:
1. 检查 `.env` 中的 `OPENAI_API_KEY` 是否正确
2. 确认API密钥有效且有余额
3. 检查 `OPENAI_BASE_URL` 配置

---

### 问题3: 分析速度太慢

**症状**: 分析30个市场需要10分钟以上

**解决方法**:
1. 减少分析数量: `--max-analyze 10`
2. 使用更快的LLM模型
3. 增加规则筛选的严格度

---

### 问题4: 数据库连接失败

**症状**:
```
Failed to save batch analysis: connection refused
```

**解决方法**:
1. 检查PostgreSQL是否运行
2. 检查 `.env` 中的 `DATABASE_URL`
3. 确认数据库表已创建（运行 `migrations/init.sql`）

---

## 📈 性能指标

### 典型运行时间

| 操作 | 市场数量 | 耗时 |
|------|---------|------|
| 获取市场数据 | 500个 | ~30秒 |
| 规则筛选 | 500→50个 | <1秒 |
| AI分析 | 30个 | ~2-5分钟 |
| 保存结果 | 30个 | <1秒 |
| **总计** | - | **~3-6分钟** |

### Token消耗

- 单个市场分析: ~500-1000 tokens
- 30个市场批量分析: ~15,000-30,000 tokens
- 每天运行2次: ~60,000 tokens/天

---

## 🔐 安全建议

1. **API密钥保护**: 不要将 `.env` 文件提交到Git
2. **数据库权限**: 使用专用数据库用户，限制权限
3. **日志管理**: 定期清理日志文件，避免磁盘占满
4. **错误处理**: 所有异常都已捕获，不会导致服务崩溃

---

## 📚 相关文档

- `POLYMARKET_BATCH_ANALYZER.md` - 批量分析器文档
- `AI_ANALYSIS_EXAMPLE.md` - AI分析示例
- `COMPLETE_WORKFLOW_GUIDE.md` - 完整业务流程

---

## 🎓 最佳实践

### 1. 测试环境

```bash
# 先用小数据集测试
python -m app.services.polymarket_worker \
  --categories crypto \
  --limit 10 \
  --max-analyze 3
```

### 2. 生产环境

```bash
# 使用systemd管理服务
sudo systemctl start polymarket-worker
sudo systemctl enable polymarket-worker
```

### 3. 监控

```bash
# 监控日志
tail -f polymarket_worker.log | grep "ERROR\|WARNING"

# 监控数据库
psql -d quantdinger -c "SELECT COUNT(*) FROM qd_polymarket_ai_analysis WHERE created_at > NOW() - INTERVAL '1 hour';"
```

---

**文档版本**: 1.0  
**最后更新**: 2026-03-06  
**维护者**: QuantDinger Team
