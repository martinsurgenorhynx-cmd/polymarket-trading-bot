# Fast Analysis 调用流程说明

## 概述

`FastAnalysisService.analyze()` 是 AI 市场分析的核心方法，被多个模块调用。

---

## 🎯 调用位置

### 1. API 路由 - 前端直接调用

**文件**: `app/routes/fast_analysis.py`

**端点**: `POST /api/fast-analysis/analyze`

**调用场景**: 用户在前端点击"AI 分析"按钮

**代码**:
```python
@fast_analysis_bp.route('/analyze', methods=['POST'])
@login_required
def analyze():
    """用户主动请求 AI 分析"""
    data = request.get_json()
    
    service = get_fast_analysis_service()
    result = service.analyze(
        market=data['market'],      # 'Crypto', 'USStock', 'Forex'
        symbol=data['symbol'],      # 'BTC/USDT', 'AAPL'
        language=data.get('language', 'en-US'),
        model=data.get('model'),
        timeframe=data.get('timeframe', '1D'),
        user_id=g.user_id
    )
    
    return jsonify(result)
```

**请求示例**:
```bash
curl -X POST http://localhost:5000/api/fast-analysis/analyze \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "market": "Crypto",
    "symbol": "BTC/USDT",
    "language": "zh-CN",
    "timeframe": "1D"
  }'
```

**响应示例**:
```json
{
  "code": 1,
  "msg": "success",
  "data": {
    "recommendation": "BUY",
    "confidence": 75,
    "entry_price": 50000,
    "stop_loss": 48000,
    "take_profit": 55000,
    "analysis": {
      "technical": "RSI 超卖，MACD 金叉...",
      "fundamental": "比特币基本面强劲...",
      "sentiment": "市场情绪积极..."
    },
    "risks": ["风险1", "风险2"],
    "memory_id": 123
  }
}
```

---

### 2. 策略执行引擎 - AI 过滤信号

**文件**: `app/services/trading_executor.py`

**调用场景**: 策略启用 AI 过滤时，在执行信号前先调用 AI 分析

**代码**:
```python
class TradingExecutor:
    def _execute_strategy_loop(self, strategy_id):
        """策略主循环"""
        while True:
            # 1. 执行指标代码，生成信号
            signals = self._execute_indicator(...)
            
            # 2. 如果启用了 AI 过滤
            if trading_config.get('enable_ai_filter'):
                # 调用 AI 分析
                from app.services.fast_analysis import get_fast_analysis_service
                service = get_fast_analysis_service()
                
                ai_result = service.analyze(
                    market=market,
                    symbol=symbol,
                    language=language,
                    model=model
                )
                
                # 3. 根据 AI 建议决定是否执行信号
                if signals['buy'] and ai_result['recommendation'] == 'BUY':
                    self._handle_buy_signal(...)  # 执行买入
                elif signals['buy'] and ai_result['recommendation'] == 'SELL':
                    logger.info("AI 建议卖出，忽略买入信号")
                    # 不执行
            else:
                # 直接执行信号（不使用 AI 过滤）
                if signals['buy']:
                    self._handle_buy_signal(...)
            
            time.sleep(tick_interval)
```

**配置**:
```json
{
  "trading_config": {
    "enable_ai_filter": true,
    "ai_model": "openai/gpt-4o"
  }
}
```

**流程**:
```
策略生成买入信号
    ↓
检查是否启用 AI 过滤
    ↓ (是)
调用 FastAnalysisService.analyze()
    ↓
AI 返回建议 (BUY/SELL/HOLD)
    ↓
如果 AI 建议与信号一致 → 执行
如果 AI 建议与信号冲突 → 忽略
```

---

### 3. 投资组合监控 - 定期分析持仓

**文件**: `app/services/portfolio_monitor.py`

**调用场景**: 定期监控用户持仓，生成 AI 分析报告

**代码**:
```python
def run_single_monitor(monitor_id: int):
    """运行单个监控任务"""
    # 1. 获取监控配置
    monitor = get_monitor_config(monitor_id)
    
    # 2. 获取持仓列表
    positions = get_positions(monitor['position_ids'])
    
    # 3. 对每个持仓调用 AI 分析
    service = get_fast_analysis_service()
    
    analyses = []
    for position in positions:
        result = service.analyze(
            market=position['market'],
            symbol=position['symbol'],
            language=monitor['language'],
            timeframe='1D'
        )
        analyses.append(result)
    
    # 4. 生成综合报告
    report = generate_portfolio_report(analyses)
    
    # 5. 发送通知
    send_notification(report)
```

**触发方式**:
- 用户手动触发
- 定时任务（如果启用）

**流程**:
```
用户创建投资组合监控
    ↓
设置监控频率（每天/每周）
    ↓
定时触发或手动触发
    ↓
对每个持仓调用 FastAnalysisService.analyze()
    ↓
生成综合报告
    ↓
发送邮件/通知
```

---

### 4. 其他 API 端点

#### A. 遗留格式分析

**端点**: `POST /api/fast-analysis/analyze-legacy`

**用途**: 兼容旧版前端，返回多代理格式的结果

**代码**:
```python
@fast_analysis_bp.route('/analyze-legacy', methods=['POST'])
def analyze_legacy():
    service = get_fast_analysis_service()
    result = service.analyze_legacy_format(...)  # 调用不同的方法
    return jsonify(result)
```

#### B. 相似模式查询

**端点**: `GET /api/fast-analysis/similar-patterns`

**用途**: 查找历史相似的市场模式

**代码**:
```python
@fast_analysis_bp.route('/similar-patterns', methods=['GET'])
def get_similar_patterns():
    service = get_fast_analysis_service()
    
    # 收集当前市场数据
    data = service._collect_market_data(market, symbol)
    
    # 查找相似模式
    patterns = memory.get_similar_patterns(...)
    return jsonify(patterns)
```

---

## 🔄 完整调用流程图

```
┌─────────────────────────────────────────────────────────┐
│                    调用入口                              │
└─────────────────────────────────────────────────────────┘
                          ↓
        ┌─────────────────┼─────────────────┐
        ↓                 ↓                  ↓
   前端 API          策略执行引擎        投资组合监控
        ↓                 ↓                  ↓
POST /api/fast-    TradingExecutor    PortfolioMonitor
analysis/analyze   (AI 过滤信号)      (定期分析持仓)
        ↓                 ↓                  ↓
        └─────────────────┼─────────────────┘
                          ↓
        ┌─────────────────────────────────┐
        │  FastAnalysisService.analyze()  │
        └─────────────────────────────────┘
                          ↓
        ┌─────────────────────────────────┐
        │  1. 收集市场数据                 │
        │     - K线数据                    │
        │     - 技术指标 (RSI, MACD)       │
        │     - 宏观数据 (DXY, VIX)        │
        │     - 新闻情绪                   │
        │     - 基本面数据                 │
        └─────────────────────────────────┘
                          ↓
        ┌─────────────────────────────────┐
        │  2. 构建分析 Prompt              │
        │     - 整合所有数据               │
        │     - 添加历史记忆               │
        │     - 设置输出格式               │
        └─────────────────────────────────┘
                          ↓
        ┌─────────────────────────────────┐
        │  3. 调用 LLM                     │
        │     - OpenRouter / OpenAI        │
        │     - 单次调用                   │
        │     - 结构化输出                 │
        └─────────────────────────────────┘
                          ↓
        ┌─────────────────────────────────┐
        │  4. 解析结果                     │
        │     - 提取建议 (BUY/SELL/HOLD)   │
        │     - 提取价格 (入场/止损/止盈)  │
        │     - 提取分析文本               │
        └─────────────────────────────────┘
                          ↓
        ┌─────────────────────────────────┐
        │  5. 存储到记忆系统               │
        │     - qd_analysis_memory 表      │
        │     - 用于学习和改进             │
        └─────────────────────────────────┘
                          ↓
        ┌─────────────────────────────────┐
        │  6. 返回结果                     │
        └─────────────────────────────────┘
                          ↓
        ┌─────────────────┼─────────────────┐
        ↓                 ↓                  ↓
   返回给前端        策略决策            生成报告
   (JSON 响应)      (执行/忽略信号)     (发送通知)
```

---

## 📊 调用统计

### 调用频率

1. **前端 API**: 按需调用（用户点击）
   - 频率：不定期
   - 并发：低（单用户）

2. **策略执行引擎**: 每次信号触发时调用
   - 频率：取决于策略周期（1分钟 - 1天）
   - 并发：中（多个策略并行）

3. **投资组合监控**: 定期调用
   - 频率：每天/每周
   - 并发：低（后台任务）

### 性能考虑

- **LLM 调用成本**: 每次分析消耗 ~2000-5000 tokens
- **响应时间**: 3-10 秒（取决于 LLM 速度）
- **缓存策略**: 无缓存（每次实时分析）
- **并发限制**: 受 LLM API 限流影响

---

## 🔧 配置选项

### 环境变量

```env
# LLM 配置
LLM_PROVIDER=openrouter
LLM_API_KEY=sk-xxx
LLM_MODEL=openai/gpt-4o
LLM_FALLBACK_MODEL=openai/gpt-4o-mini

# 分析配置
FAST_ANALYSIS_TIMEOUT=30
FAST_ANALYSIS_MAX_RETRIES=3
```

### 策略配置

```json
{
  "trading_config": {
    "enable_ai_filter": true,        // 是否启用 AI 过滤
    "ai_model": "openai/gpt-4o",     // 使用的模型
    "ai_confidence_threshold": 60    // 最低置信度阈值
  }
}
```

---

## 📝 使用示例

### 1. 前端调用

```javascript
// Vue 组件
async analyzeSymbol() {
  const response = await axios.post('/api/fast-analysis/analyze', {
    market: 'Crypto',
    symbol: 'BTC/USDT',
    language: 'zh-CN',
    timeframe: '1D'
  })
  
  const result = response.data.data
  console.log('AI 建议:', result.recommendation)
  console.log('入场价:', result.entry_price)
  console.log('止损:', result.stop_loss)
  console.log('止盈:', result.take_profit)
}
```

### 2. 策略中使用

```python
# 在策略配置中启用 AI 过滤
strategy_config = {
    'trading_config': {
        'enable_ai_filter': True,
        'ai_model': 'openai/gpt-4o'
    }
}

# 策略执行时自动调用 AI 分析
# 无需手动编码
```

### 3. Python 脚本调用

```python
from app.services.fast_analysis import get_fast_analysis_service

service = get_fast_analysis_service()

result = service.analyze(
    market='Crypto',
    symbol='BTC/USDT',
    language='zh-CN',
    timeframe='1D'
)

print(f"建议: {result['recommendation']}")
print(f"置信度: {result['confidence']}%")
print(f"入场价: {result['entry_price']}")
```

---

## 🔍 调试技巧

### 1. 查看分析日志

```bash
# 查看 AI 分析日志
tail -f logs/app.log | grep "FastAnalysis"
```

### 2. 测试 API

```bash
# 测试分析 API
curl -X POST http://localhost:5000/api/fast-analysis/analyze \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "market": "Crypto",
    "symbol": "BTC/USDT",
    "language": "zh-CN"
  }' | jq
```

### 3. 查看分析历史

```bash
# 查看分析历史
curl http://localhost:5000/api/fast-analysis/history?market=Crypto&symbol=BTC/USDT \
  -H "Authorization: Bearer <token>" | jq
```

### 4. 检查数据库记录

```sql
-- 查看最近的分析记录
SELECT * FROM qd_analysis_memory 
ORDER BY created_at DESC 
LIMIT 10;

-- 查看特定交易对的分析
SELECT * FROM qd_analysis_memory 
WHERE market = 'Crypto' AND symbol = 'BTC/USDT'
ORDER BY created_at DESC;
```

---

## 💡 总结

### 调用位置

1. **前端 API** - 用户主动请求分析
2. **策略执行引擎** - AI 过滤信号
3. **投资组合监控** - 定期分析持仓

### 核心流程

```
调用入口 → 收集数据 → 调用 LLM → 解析结果 → 存储记忆 → 返回结果
```

### 关键特性

- **单次 LLM 调用**: 快速高效
- **结构化输出**: 易于解析和使用
- **记忆系统**: 学习和改进
- **多场景支持**: API、策略、监控

所有调用最终都通过 `FastAnalysisService.analyze()` 方法，确保分析逻辑的一致性。
