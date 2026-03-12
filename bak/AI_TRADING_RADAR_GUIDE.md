# AI 交易机会雷达 - 代码指南

## 📍 代码位置

### 主要文件
**`backend_api_python/app/routes/global_market.py`**

这是AI交易机会雷达的核心代码文件。

---

## 🎯 功能概述

AI交易机会雷达自动扫描多个市场，识别潜在的交易机会：

- **加密货币市场** (Crypto)
- **美股市场** (US Stocks)
- **外汇市场** (Forex)
- **预测市场** (Polymarket) - 有独立页面

---

## 📊 API端点

### 1. 获取交易机会

**端点**: `GET /api/global-market/opportunities`

**功能**: 扫描所有市场，返回交易机会列表

**参数**:
- `force` (可选): `true` 或 `1` - 强制刷新，跳过缓存

**缓存**: 1小时

**响应示例**:
```json
{
  "code": 1,
  "msg": "success",
  "data": [
    {
      "symbol": "BTC/USDT",
      "name": "Bitcoin",
      "price": 70680.02,
      "change_24h": 5.8,
      "change_7d": 12.3,
      "signal": "bullish_momentum",
      "strength": "medium",
      "reason": "24h涨幅5.8%，上涨动能强劲",
      "impact": "bullish",
      "market": "Crypto",
      "timestamp": 1709740800
    }
  ]
}
```

---

## 🔍 核心函数

### 1. 主函数: `trading_opportunities()`

**位置**: 第1891行

**功能**: 
- 协调所有市场的机会扫描
- 合并结果并排序
- 缓存结果（1小时）

**代码**:
```python
@global_market_bp.route("/opportunities", methods=["GET"])
@login_required
def trading_opportunities():
    """
    Scan for trading opportunities across Crypto, US Stocks, and Forex.
    """
    opportunities = []
    
    # 1) 扫描加密货币
    _analyze_opportunities_crypto(opportunities)
    
    # 2) 扫描美股
    _analyze_opportunities_stocks(opportunities)
    
    # 3) 扫描外汇
    _analyze_opportunities_forex(opportunities)
    
    # 按24h涨跌幅排序
    opportunities.sort(key=lambda x: abs(x.get("change_24h", 0)), reverse=True)
    
    return jsonify({"code": 1, "msg": "success", "data": opportunities})
```

---

### 2. 加密货币机会分析: `_analyze_opportunities_crypto()`

**位置**: 第1652行

**功能**: 扫描加密货币市场，识别交易机会

**信号类型**:
- `overbought` - 超买（24h涨幅 > 15%）
- `bullish_momentum` - 看涨动能（24h涨幅 > 5%）
- `oversold` - 超卖（24h跌幅 > 15%）
- `bearish_momentum` - 看跌动能（24h跌幅 > 5%）

**代码逻辑**:
```python
def _analyze_opportunities_crypto(opportunities: list):
    """Scan crypto market for trading opportunities."""
    crypto_data = _get_cached("crypto_prices")
    
    for coin in crypto_data[:20]:  # 分析前20个币种
        change = coin.get("change_24h", 0)
        
        if change > 15:
            signal = "overbought"
            strength = "strong"
            reason = f"24h涨幅{change:.1f}%，短期超买风险"
            impact = "bearish"
        elif change > 5:
            signal = "bullish_momentum"
            strength = "medium"
            reason = f"24h涨幅{change:.1f}%，上涨动能强劲"
            impact = "bullish"
        elif change < -15:
            signal = "oversold"
            strength = "strong"
            reason = f"24h跌幅{abs(change):.1f}%，可能超卖反弹"
            impact = "bullish"
        elif change < -5:
            signal = "bearish_momentum"
            strength = "medium"
            reason = f"24h跌幅{abs(change):.1f}%，下跌趋势明显"
            impact = "bearish"
        
        if signal:
            opportunities.append({
                "symbol": coin["symbol"],
                "name": coin["name"],
                "price": coin["price"],
                "change_24h": change,
                "signal": signal,
                "strength": strength,
                "reason": reason,
                "impact": impact,
                "market": "Crypto",
                "timestamp": int(time.time())
            })
```

---

### 3. 美股机会分析: `_analyze_opportunities_stocks()`

**位置**: 第1716行

**功能**: 扫描美股市场，识别交易机会

**信号类型**:
- `overbought` - 超买（日涨幅 > 5%）
- `bullish_momentum` - 看涨动能（日涨幅 > 2%）
- `oversold` - 超卖（日跌幅 > 5%）
- `bearish_momentum` - 看跌动能（日跌幅 > 2%）

**特点**:
- 美股阈值比加密货币更低（因为波动性较小）
- 扫描热门美股（AAPL, MSFT, GOOGL, AMZN, TSLA等）

**代码逻辑**:
```python
def _analyze_opportunities_stocks(opportunities: list):
    """Scan US stocks for trading opportunities."""
    stock_data = _get_cached("stock_opportunity_prices")
    
    for stock in stock_data:
        change = stock.get("change", 0)
        
        # 美股阈值更低
        if change > 5:
            signal = "overbought"
        elif change > 2:
            signal = "bullish_momentum"
        elif change < -5:
            signal = "oversold"
        elif change < -2:
            signal = "bearish_momentum"
        
        if signal:
            opportunities.append({...})
```

---

### 4. 外汇机会分析: `_analyze_opportunities_forex()`

**位置**: 第1778行

**功能**: 扫描外汇市场，识别交易机会

**信号类型**:
- `overbought` - 超买（日涨幅 > 2%）
- `bullish_momentum` - 看涨动能（日涨幅 > 0.5%）
- `oversold` - 超卖（日跌幅 > 2%）
- `bearish_momentum` - 看跌动能（日跌幅 > 0.5%）

**特点**:
- 外汇阈值最低（因为波动性最小）
- 扫描主要货币对（EUR/USD, GBP/USD, USD/JPY等）

---

### 5. 预测市场机会分析: `_analyze_opportunities_polymarket()`

**位置**: 第1840行

**功能**: 扫描Polymarket预测市场，识别高价值机会

**筛选条件**:
- `opportunity_score > 75` - 只显示高分机会

**特点**:
- 使用AI分析预测市场
- 计算AI预测概率 vs 市场概率的差异
- 提供YES/NO/HOLD建议

**注意**: 预测市场有独立页面 `/polymarket`，不在主雷达中显示

---

## 📈 信号强度

### Strength（强度）
- `strong` - 强信号（大幅波动）
- `medium` - 中等信号（适度波动）

### Impact（影响）
- `bullish` - 看涨（建议买入）
- `bearish` - 看跌（建议卖出）
- `neutral` - 中性

---

## 🔄 数据流程

```
1. 前端请求 GET /api/global-market/opportunities
   ↓
2. 检查缓存（1小时有效期）
   ↓
3. 如果缓存失效或force=true：
   ├─ 调用 _analyze_opportunities_crypto()
   ├─ 调用 _analyze_opportunities_stocks()
   └─ 调用 _analyze_opportunities_forex()
   ↓
4. 合并所有机会
   ↓
5. 按24h涨跌幅绝对值排序
   ↓
6. 缓存结果（1小时）
   ↓
7. 返回JSON响应
```

---

## 🎨 前端集成

### 前端代码位置
- **Vue组件**: `frontend/src/views/dashboard/GlobalMarket.vue`
- **语言文件**: `frontend/src/locales/zh-CN.json`

### 前端显示
- 轮播卡片展示
- 按市场分类（Crypto/USStock/Forex）
- 显示信号类型、强度、原因
- 一键分析按钮（跳转到快速分析）

---

## 🔧 配置和优化

### 阈值调整

如果想调整信号触发的阈值，修改以下位置：

**加密货币** (第1652行):
```python
if change > 15:      # 超买阈值
    signal = "overbought"
elif change > 5:     # 看涨动能阈值
    signal = "bullish_momentum"
elif change < -15:   # 超卖阈值
    signal = "oversold"
elif change < -5:    # 看跌动能阈值
    signal = "bearish_momentum"
```

**美股** (第1716行):
```python
if change > 5:       # 超买阈值
    signal = "overbought"
elif change > 2:     # 看涨动能阈值
    signal = "bullish_momentum"
elif change < -5:    # 超卖阈值
    signal = "oversold"
elif change < -2:    # 看跌动能阈值
    signal = "bearish_momentum"
```

**外汇** (第1778行):
```python
if change > 2:       # 超买阈值
    signal = "overbought"
elif change > 0.5:   # 看涨动能阈值
    signal = "bullish_momentum"
elif change < -2:    # 超卖阈值
    signal = "oversold"
elif change < -0.5:  # 看跌动能阈值
    signal = "bearish_momentum"
```

### 缓存时间调整

修改缓存时间（默认1小时 = 3600秒）：

```python
# 第1943行
_set_cached("trading_opportunities", opportunities, 3600)  # 改为你想要的秒数
```

### 扫描币种数量

修改扫描的加密货币数量（默认前20个）：

```python
# 第1667行
for coin in (crypto_data or [])[:20]:  # 改为你想要的数量
```

---

## 🧪 测试

### 手动测试

```bash
# 1. 启动后端服务
cd backend_api_python
python run.py

# 2. 测试API（需要登录token）
curl -H "Authorization: Bearer YOUR_TOKEN" \
     http://localhost:5001/api/global-market/opportunities

# 3. 强制刷新
curl -H "Authorization: Bearer YOUR_TOKEN" \
     http://localhost:5001/api/global-market/opportunities?force=true
```

### Python测试脚本

```python
import requests

# 登录获取token
login_response = requests.post(
    "http://localhost:5001/api/auth/login",
    json={"username": "quantdinger", "password": "123456"}
)
token = login_response.json()["data"]["token"]

# 获取交易机会
headers = {"Authorization": f"Bearer {token}"}
response = requests.get(
    "http://localhost:5001/api/global-market/opportunities",
    headers=headers
)

opportunities = response.json()["data"]
print(f"找到 {len(opportunities)} 个交易机会")

for opp in opportunities[:5]:
    print(f"{opp['market']} - {opp['symbol']}: {opp['signal']} ({opp['reason']})")
```

---

## 📊 数据源

### 加密货币数据
- **来源**: Coinbase API
- **函数**: `_fetch_crypto_prices()`
- **位置**: 第1500行左右

### 美股数据
- **来源**: yfinance
- **函数**: `_fetch_stock_opportunity_prices()`
- **位置**: 第1595行

### 外汇数据
- **来源**: yfinance
- **函数**: `_fetch_forex_pairs()`
- **位置**: 第1400行左右

---

## 🚀 扩展建议

### 1. 添加更多信号类型

可以添加基于技术指标的信号：

```python
# 添加RSI信号
if rsi > 70:
    signal = "rsi_overbought"
elif rsi < 30:
    signal = "rsi_oversold"

# 添加MACD信号
if macd_cross == "golden":
    signal = "macd_bullish"
elif macd_cross == "death":
    signal = "macd_bearish"
```

### 2. 添加AI评分

集成FastAnalysisService进行AI评分：

```python
from app.services.fast_analysis import get_fast_analysis_service

analysis_service = get_fast_analysis_service()
result = analysis_service.analyze(
    market="Crypto",
    symbol=symbol,
    language="zh-CN"
)

ai_score = result.get("scores", {}).get("overall", 0)
```

### 3. 添加通知功能

当发现高价值机会时发送通知：

```python
if strength == "strong" and abs(change) > 20:
    # 发送邮件/Telegram通知
    send_notification(
        title=f"发现强信号: {symbol}",
        message=reason
    )
```

### 4. 添加历史记录

保存机会到数据库，用于回测和分析：

```python
# 保存到数据库
cursor.execute("""
    INSERT INTO qd_trading_opportunities
    (symbol, market, signal, strength, reason, price, change_24h, created_at)
    VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
""", (symbol, market, signal, strength, reason, price, change_24h))
```

---

## 📝 相关文档

- `FAST_ANALYSIS_FLOW.md` - AI分析流程
- `COMPLETE_WORKFLOW_GUIDE.md` - 完整业务流程
- `API_ENDPOINTS.md` - API端点文档
- `README.md` - 项目总览

---

## 🐛 常见问题

### Q1: 为什么没有显示任何机会？
**A**: 可能原因：
1. 市场波动较小，没有达到阈值
2. 数据源API失败
3. 缓存中的数据过期

**解决方法**: 使用 `?force=true` 强制刷新

### Q2: 如何调整信号灵敏度？
**A**: 降低阈值可以显示更多机会，提高阈值可以只显示强信号。参考上面的"阈值调整"部分。

### Q3: 可以添加其他市场吗？
**A**: 可以！参考现有的 `_analyze_opportunities_*` 函数，创建新的分析函数即可。

### Q4: 机会雷达多久更新一次？
**A**: 默认1小时更新一次（缓存时间）。可以通过 `?force=true` 手动刷新。

---

**文档版本**: 1.0  
**最后更新**: 2026-03-06  
**维护者**: QuantDinger Team
