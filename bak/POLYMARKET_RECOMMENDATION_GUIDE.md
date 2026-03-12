# Polymarket 推荐决策指南

## 什么是 Polymarket？

Polymarket 是一个去中心化的预测市场平台，用户可以对未来事件的结果进行交易。

每个市场有两个选项：
- **YES 代币** - 认为事件会发生
- **NO 代币** - 认为事件不会发生

## AI 推荐系统

我们的 AI 系统会分析市场数据，并给出三种推荐：

### 1. YES - 买入 YES 代币

**含义：** AI 认为事件会发生

**判断标准：**
- AI 预测概率 > 市场概率 + 5%
- 置信度 > 60%

**操作建议：**
- 买入 YES 代币
- 如果事件发生，你将获利
- 如果事件不发生，你将损失投入的资金

**示例：**
```
问题："特朗普会赢得2024年大选吗？"
AI预测概率：65%
市场概率：55%
差异：+10%
推荐：YES

解释：AI认为特朗普获胜的概率(65%)比市场定价(55%)高10%，
     市场低估了特朗普获胜的可能性，存在套利机会。
     建议买入 YES 代币。
```

### 2. NO - 买入 NO 代币

**含义：** AI 认为事件不会发生

**判断标准：**
- AI 预测概率 < 市场概率 - 5%
- 置信度 > 60%

**操作建议：**
- 买入 NO 代币
- 如果事件不发生，你将获利
- 如果事件发生，你将损失投入的资金

**示例：**
```
问题："MicroStrategy 会在2025年卖出比特币吗？"
AI预测概率：5%
市场概率：15%
差异：-10%
推荐：NO

解释：AI认为MicroStrategy卖出比特币的概率(5%)比市场定价(15%)低10%，
     市场高估了卖出的可能性，存在套利机会。
     建议买入 NO 代币。
```

### 3. HOLD - 观望

**含义：** AI 认为市场定价合理

**判断标准：**
- AI 预测概率与市场概率差异 < 5%
- 或置信度 < 60%

**操作建议：**
- 暂不交易
- 继续观察市场变化
- 等待更好的机会

**示例：**
```
问题："比特币会在2025年突破10万美元吗？"
AI预测概率：52%
市场概率：50%
差异：+2%
推荐：HOLD

解释：AI预测概率(52%)与市场概率(50%)差异很小(2%)，
     市场定价相对合理，没有明显套利机会。
     建议观望。
```

## 关键指标说明

### 1. AI 预测概率
AI 基于多种数据源（新闻、市场数据、历史趋势等）预测的事件发生概率。

### 2. 市场概率
当前市场上 YES 代币的价格，反映了市场参与者的集体预期。

### 3. 概率差异（Divergence）
```
差异 = AI预测概率 - 市场概率
```
- **正值**：AI 比市场更乐观（推荐 YES）
- **负值**：AI 比市场更悲观（推荐 NO）
- **接近0**：AI 与市场看法一致（推荐 HOLD）

### 4. 置信度（Confidence Score）
AI 对自己预测的信心程度（0-100%）
- **> 80%**：非常有信心
- **60-80%**：比较有信心
- **< 60%**：信心不足，建议观望

### 5. 机会评分（Opportunity Score）
综合评估的交易机会质量（0-100分）

计算公式：
```python
opportunity_score = (
    abs(divergence) * 0.5 +      # 概率差异权重 50%
    confidence * 0.3 +            # 置信度权重 30%
    liquidity_score * 0.2         # 流动性权重 20%
)
```

评分标准：
- **> 85分**：优质机会 ⭐⭐⭐
- **75-85分**：良好机会 ⭐⭐
- **60-75分**：一般机会 ⭐
- **< 60分**：机会不明显

## 实际案例分析

### 案例 1：MicroStrategy 卖出比特币

```
问题：MicroStrategy sells any Bitcoin in 2025?
URL：https://polymarket.com/event/microstrategy-sell-any-bitcoin-in-2025

AI分析：
  AI预测概率：0.0%
  市场概率：0.0%
  概率差异：0.0%
  置信度：60%
  机会评分：85/100

推荐决策：NO

解释：
  ✓ 推荐：买入 NO（认为事件不会发生）
  理由：AI预测概率(0.0%) 比市场概率(0.0%) 低 0.0%
  含义：市场高估了事件发生的可能性，存在套利机会
  操作：买入 NO 代币，如果事件不发生可获利

分析理由：
  MicroStrategy 的 CEO Michael Saylor 一直坚持长期持有比特币的策略，
  公司将比特币作为主要储备资产，没有任何迹象表明会在2025年卖出。
  市场定价可能因流动性不足导致定价错误。
```

### 案例 2：高差异机会

```
问题：Will Bitcoin reach $100,000 in 2025?

AI分析：
  AI预测概率：75%
  市场概率：60%
  概率差异：+15%
  置信度：72%
  机会评分：78/100

推荐决策：YES

解释：
  ✓ 推荐：买入 YES（认为事件会发生）
  理由：AI预测概率(75%) 比市场概率(60%) 高 15%
  含义：市场低估了事件发生的可能性，存在套利机会
  操作：买入 YES 代币，如果事件发生可获利

分析理由：
  基于历史减半周期、机构采用趋势、宏观经济环境等因素，
  AI认为比特币在2025年突破10万美元的概率被市场低估。
```

## 风险提示

### 1. AI 预测不是保证
- AI 分析基于历史数据和当前信息
- 未来事件存在不确定性
- 预测可能出错

### 2. 市场风险
- 价格波动风险
- 流动性风险
- 智能合约风险

### 3. 资金管理
- 不要投入超过你能承受损失的资金
- 分散投资，不要把所有资金投入单一市场
- 设置止损点

### 4. 信息更新
- 市场情况随时变化
- 定期查看最新分析
- 关注重大新闻事件

## 如何使用

### 1. 查看分析结果

```bash
# 查看所有分析结果
python query_polymarket_results.py

# 查看详细分析
python query_polymarket_detailed.py
```

### 2. 通过 API 获取

```bash
# 获取用户分析历史
GET /api/polymarket/history?page=1&page_size=20

# 分析特定市场
POST /api/polymarket/analyze
{
  "input": "https://polymarket.com/event/xxx",
  "language": "zh-CN"
}
```

### 3. 自动化交易（开发中）

```python
# 未来功能：基于 AI 推荐自动交易
from app.services.polymarket_trader import PolymarketTrader

trader = PolymarketTrader()

# 获取高分机会
opportunities = trader.get_high_score_opportunities(min_score=85)

# 自动执行交易
for opp in opportunities:
    if opp['recommendation'] == 'YES':
        trader.buy_yes(opp['market_id'], amount=10)
    elif opp['recommendation'] == 'NO':
        trader.buy_no(opp['market_id'], amount=10)
```

## 常见问题

### Q1: 为什么有些推荐是 NO？
A: NO 不是"不推荐"，而是"推荐买入 NO 代币"。如果 AI 认为事件不会发生，就会推荐买入 NO 代币。

### Q2: 机会评分高就一定能赚钱吗？
A: 不一定。机会评分只是综合评估，不保证盈利。投资有风险，需谨慎决策。

### Q3: 如何理解概率差异？
A: 概率差异是 AI 预测与市场定价的差距。差异越大，理论上套利空间越大，但也可能意味着 AI 判断错误。

### Q4: 置信度低于 60% 怎么办？
A: 置信度低说明 AI 对预测不够确定，建议观望或等待更多信息。

### Q5: 可以同时买入 YES 和 NO 吗？
A: 技术上可以，但没有意义。YES + NO 的总价格约等于 $1，同时买入不会盈利。

## 相关文档

- [Polymarket Worker 指南](POLYMARKET_WORKER_GUIDE.md)
- [Polymarket 交易指南](POLYMARKET_TRADING_GUIDE.md)
- [Polymarket 钱包设置](POLYMARKET_WALLET_SETUP.md)
- [Polymarket 快速开始](POLYMARKET_QUICK_START.md)

## 技术支持

如有问题，请查看：
- 数据库查询脚本：`query_polymarket_results.py`
- 详细查询脚本：`query_polymarket_detailed.py`
- API 路由：`app/routes/polymarket.py`
- 分析器：`app/services/polymarket_analyzer.py`
