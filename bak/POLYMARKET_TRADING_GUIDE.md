# Polymarket 交易完整指南

## 概览

本指南展示如何使用 Polymarket CLOB API 进行自动化交易，包括：
1. 环境配置
2. 基础交易操作
3. AI 驱动的自动交易
4. 风险管理

---

## 1. 环境配置

### 1.1 安装依赖

```bash
pip install py-clob-client
```

### 1.2 获取钱包和私钥

**选项 A: 使用现有钱包（推荐）**
1. 使用 MetaMask 或其他 Web3 钱包
2. 导出私钥（Settings → Security & Privacy → Reveal Private Key）
3. 确保钱包在 Polygon 网络上有 USDC.e 余额

**选项 B: 创建新钱包**
```python
from eth_account import Account

# 创建新钱包
account = Account.create()
print(f"Address: {account.address}")
print(f"Private Key: {account.key.hex()}")
```

### 1.3 配置环境变量

在 `.env` 文件中添加：

```bash
# Polymarket 配置
POLYMARKET_PRIVATE_KEY=your_private_key_without_0x_prefix
POLYMARKET_FUNDER_ADDRESS=your_wallet_address
```

**重要提示**:
- 私钥不要包含 `0x` 前缀
- 永远不要将私钥提交到 Git
- 使用测试钱包进行开发

---

## 2. 基础交易操作

### 2.1 初始化客户端

```python
from py_clob_client.client import ClobClient

client = ClobClient(
    host="https://clob.polymarket.com",
    chain_id=137,  # Polygon Mainnet
    key=private_key,
    signature_type=2,  # GNOSIS_SAFE (最常用)
    funder=funder_address
)
```

**Signature Types**:
- `0` - EOA (标准钱包，如 MetaMask)
- `1` - POLY_PROXY (Magic Link 用户)
- `2` - GNOSIS_SAFE (推荐，最常用)

### 2.2 获取市场信息

```python
# 通过 condition_id 获取市场
market = client.get_market("0xbd31dc8a...")

print(f"Question: {market['question']}")
print(f"Tick Size: {market['minimum_tick_size']}")
print(f"Neg Risk: {market['neg_risk']}")
print(f"YES Token: {market['tokens'][0]['token_id']}")
print(f"NO Token: {market['tokens'][1]['token_id']}")
```

### 2.3 下限价单

```python
from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY, SELL

# 买入 YES 代币
response = client.create_and_post_order(
    OrderArgs(
        token_id="YOUR_YES_TOKEN_ID",
        price=0.65,  # 65% 概率
        size=10.0,   # $10 美元
        side=BUY,
        order_type=OrderType.GTC  # Good-Til-Cancelled
    ),
    options={
        "tick_size": "0.01",
        "neg_risk": False
    }
)

print(f"Order ID: {response['orderID']}")
print(f"Status: {response['status']}")
```

### 2.4 下市价单

```python
# 市价买入（立即成交）
response = client.create_market_order(
    OrderArgs(
        token_id="YOUR_YES_TOKEN_ID",
        amount=10.0,  # 花费 $10
        side=BUY
    ),
    options={
        "tick_size": "0.01",
        "neg_risk": False
    }
)
```

### 2.5 批量下单

```python
from py_clob_client.clob_types import PostOrdersArgs

# 创建多个订单
orders = []
for price in [0.48, 0.49, 0.50]:
    signed_order = client.create_order(
        OrderArgs(
            token_id="YOUR_TOKEN_ID",
            price=price,
            size=10.0,
            side=BUY
        ),
        options={"tick_size": "0.01", "neg_risk": False}
    )
    orders.append(PostOrdersArgs(
        order=signed_order,
        order_type=OrderType.GTC
    ))

# 批量提交（最多 15 个）
response = client.post_orders(orders)
```

### 2.6 取消订单

```python
# 取消单个订单
client.cancel(order_id)

# 取消某个市场的所有订单
client.cancel_market_orders(market_id)

# 取消所有订单
client.cancel_all()
```

### 2.7 查询订单和余额

```python
# 获取未成交订单
orders = client.get_orders()

# 获取某个市场的订单
market_orders = client.get_orders(market=market_id)

# 获取余额
balance = client.get_balance()
print(f"USDC Balance: ${balance['usdc']}")
```

---

## 3. AI 驱动的自动交易

### 3.1 完整流程

```
1. AI 分析 → 2. 存储结果 → 3. 读取高分机会 → 4. 自动下单 → 5. 监控执行
```

### 3.2 从数据库读取 AI 分析

```python
from app.utils.db import get_db_connection

def get_high_opportunity_markets(min_score=80, hours=1):
    """获取高分机会市场"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                a.market_id,
                a.recommendation,
                a.confidence_score,
                a.opportunity_score,
                a.ai_predicted_probability,
                a.market_probability,
                a.divergence,
                a.reasoning,
                m.question,
                m.slug,
                m.outcome_tokens
            FROM qd_polymarket_ai_analysis a
            LEFT JOIN qd_polymarket_markets m ON a.market_id = m.market_id
            WHERE a.opportunity_score > %s
            AND a.created_at > NOW() - INTERVAL '%s hours'
            ORDER BY a.opportunity_score DESC
        """, (min_score, hours))
        
        return cursor.fetchall()
```

### 3.3 自动交易逻辑

```python
def execute_ai_recommendations(min_confidence=70, max_amount=10.0):
    """
    根据 AI 建议自动交易
    
    Args:
        min_confidence: 最低置信度阈值
        max_amount: 单笔最大交易金额
    """
    # 1. 获取高分机会
    opportunities = get_high_opportunity_markets(min_score=80, hours=1)
    
    if not opportunities:
        print("没有找到高分机会")
        return
    
    # 2. 初始化交易客户端
    trader = PolymarketTrader()
    
    # 3. 遍历机会并执行交易
    for opp in opportunities:
        market_id = opp['market_id']
        recommendation = opp['recommendation']
        confidence = opp['confidence_score']
        opportunity_score = opp['opportunity_score']
        ai_prob = opp['ai_predicted_probability']
        market_prob = opp['market_probability']
        outcome_tokens = opp['outcome_tokens']  # JSON: [{"token_id": "...", "outcome": "YES"}, ...]
        
        # 4. 检查置信度
        if confidence < min_confidence:
            print(f"跳过: 置信度太低 ({confidence}%)")
            continue
        
        # 5. 解析 token_id
        tokens = json.loads(outcome_tokens) if outcome_tokens else []
        yes_token = next((t['token_id'] for t in tokens if t['outcome'] == 'YES'), None)
        no_token = next((t['token_id'] for t in tokens if t['outcome'] == 'NO'), None)
        
        if not yes_token or not no_token:
            print(f"跳过: 无法获取 token_id")
            continue
        
        # 6. 根据建议执行交易
        try:
            if recommendation == "BUY_YES":
                # 买入 YES 代币
                print(f"执行: 买入 YES @ {market_prob}%")
                trader.place_limit_order(
                    token_id=yes_token,
                    side="BUY",
                    price=market_prob / 100,  # 转换为 0-1
                    size=max_amount,
                    tick_size="0.01",
                    neg_risk=False
                )
                
            elif recommendation == "BUY_NO":
                # 买入 NO 代币
                print(f"执行: 买入 NO @ {100 - market_prob}%")
                trader.place_limit_order(
                    token_id=no_token,
                    side="BUY",
                    price=(100 - market_prob) / 100,
                    size=max_amount,
                    tick_size="0.01",
                    neg_risk=False
                )
            
            # 7. 记录交易到数据库
            record_trade_execution(market_id, recommendation, max_amount)
            
        except Exception as e:
            print(f"交易失败: {e}")
            continue
```

### 3.4 记录交易执行

```python
def record_trade_execution(market_id, recommendation, amount):
    """记录交易执行到数据库"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO qd_polymarket_trades (
                market_id,
                recommendation,
                amount,
                executed_at
            ) VALUES (%s, %s, %s, NOW())
        """, (market_id, recommendation, amount))
        
        conn.commit()
```

---

## 4. 风险管理

### 4.1 仓位管理

```python
class PositionManager:
    """仓位管理器"""
    
    def __init__(self, max_total_exposure=100.0, max_per_market=10.0):
        self.max_total_exposure = max_total_exposure
        self.max_per_market = max_per_market
    
    def can_trade(self, market_id, amount):
        """检查是否可以交易"""
        # 1. 检查单个市场限额
        current_exposure = self.get_market_exposure(market_id)
        if current_exposure + amount > self.max_per_market:
            return False, f"超过单市场限额 (${self.max_per_market})"
        
        # 2. 检查总限额
        total_exposure = self.get_total_exposure()
        if total_exposure + amount > self.max_total_exposure:
            return False, f"超过总限额 (${self.max_total_exposure})"
        
        return True, "OK"
    
    def get_market_exposure(self, market_id):
        """获取单个市场的敞口"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COALESCE(SUM(amount), 0) as total
                FROM qd_polymarket_trades
                WHERE market_id = %s
                AND executed_at > NOW() - INTERVAL '7 days'
            """, (market_id,))
            row = cursor.fetchone()
            return float(row['total']) if row else 0.0
    
    def get_total_exposure(self):
        """获取总敞口"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COALESCE(SUM(amount), 0) as total
                FROM qd_polymarket_trades
                WHERE executed_at > NOW() - INTERVAL '7 days'
            """)
            row = cursor.fetchone()
            return float(row['total']) if row else 0.0
```

### 4.2 使用仓位管理

```python
def safe_execute_trade(market_id, recommendation, amount):
    """安全执行交易（带仓位管理）"""
    # 1. 检查仓位限制
    pm = PositionManager(max_total_exposure=100.0, max_per_market=10.0)
    can_trade, reason = pm.can_trade(market_id, amount)
    
    if not can_trade:
        print(f"拒绝交易: {reason}")
        return False
    
    # 2. 执行交易
    try:
        trader = PolymarketTrader()
        # ... 执行交易逻辑 ...
        return True
    except Exception as e:
        print(f"交易失败: {e}")
        return False
```

### 4.3 止损和止盈

```python
def monitor_positions():
    """监控持仓并执行止损/止盈"""
    trader = PolymarketTrader()
    
    # 获取所有持仓
    positions = get_open_positions()
    
    for pos in positions:
        market_id = pos['market_id']
        entry_price = pos['entry_price']
        current_price = pos['current_price']
        
        # 计算盈亏
        pnl_pct = ((current_price - entry_price) / entry_price) * 100
        
        # 止损: -10%
        if pnl_pct < -10:
            print(f"触发止损: {market_id} ({pnl_pct:.2f}%)")
            trader.place_market_order(
                token_id=pos['token_id'],
                side="SELL",
                amount=pos['size']
            )
        
        # 止盈: +20%
        elif pnl_pct > 20:
            print(f"触发止盈: {market_id} ({pnl_pct:.2f}%)")
            trader.place_market_order(
                token_id=pos['token_id'],
                side="SELL",
                amount=pos['size']
            )
```

---

## 5. 完整示例：自动交易 Worker

```python
#!/usr/bin/env python
"""
Polymarket 自动交易 Worker

定期检查 AI 分析结果并自动执行交易
"""

import time
from datetime import datetime

class PolymarketAutoTrader:
    """Polymarket 自动交易器"""
    
    def __init__(self, check_interval_minutes=10):
        self.check_interval_minutes = check_interval_minutes
        self.trader = PolymarketTrader()
        self.position_manager = PositionManager(
            max_total_exposure=100.0,
            max_per_market=10.0
        )
    
    def run(self):
        """主循环"""
        print(f"启动 Polymarket 自动交易器")
        print(f"检查间隔: {self.check_interval_minutes} 分钟")
        
        while True:
            try:
                print(f"\n[{datetime.now()}] 检查新机会...")
                
                # 1. 获取高分机会
                opportunities = get_high_opportunity_markets(
                    min_score=80,
                    hours=1
                )
                
                print(f"找到 {len(opportunities)} 个机会")
                
                # 2. 执行交易
                for opp in opportunities:
                    self.execute_opportunity(opp)
                
                # 3. 监控现有持仓
                monitor_positions()
                
                # 4. 等待下次检查
                time.sleep(self.check_interval_minutes * 60)
                
            except KeyboardInterrupt:
                print("\n停止自动交易器")
                break
            except Exception as e:
                print(f"错误: {e}")
                time.sleep(60)  # 出错后等待 1 分钟
    
    def execute_opportunity(self, opp):
        """执行单个机会"""
        market_id = opp['market_id']
        recommendation = opp['recommendation']
        confidence = opp['confidence_score']
        
        # 检查置信度
        if confidence < 70:
            return
        
        # 检查仓位限制
        amount = 10.0
        can_trade, reason = self.position_manager.can_trade(market_id, amount)
        if not can_trade:
            print(f"跳过 {market_id}: {reason}")
            return
        
        # 执行交易
        try:
            # ... 交易逻辑 ...
            print(f"✓ 执行交易: {market_id} - {recommendation}")
        except Exception as e:
            print(f"✗ 交易失败: {e}")


if __name__ == "__main__":
    trader = PolymarketAutoTrader(check_interval_minutes=10)
    trader.run()
```

---

## 6. 安全最佳实践

### 6.1 私钥安全
- ✅ 使用环境变量存储私钥
- ✅ 永远不要提交私钥到 Git
- ✅ 使用测试钱包进行开发
- ✅ 生产环境使用硬件钱包或 KMS

### 6.2 交易安全
- ✅ 设置单笔交易限额
- ✅ 设置每日交易限额
- ✅ 实施止损和止盈
- ✅ 监控异常交易

### 6.3 资金安全
- ✅ 不要在钱包中存放大量资金
- ✅ 定期提取利润
- ✅ 使用多重签名钱包
- ✅ 购买保险（如果可用）

---

## 7. 故障排查

### 7.1 常见错误

**错误: "Insufficient allowance"**
```python
# 解决: 需要先授权 USDC.e
# 在 Polymarket 网站上完成首次交易即可自动授权
```

**错误: "Invalid signature"**
```python
# 解决: 检查 signature_type 是否正确
# 大多数情况使用 signature_type=2 (GNOSIS_SAFE)
```

**错误: "Insufficient balance"**
```python
# 解决: 确保钱包有足够的 USDC.e 余额
# 在 Polygon 网络上购买 USDC.e
```

### 7.2 调试技巧

```python
# 启用详细日志
import logging
logging.basicConfig(level=logging.DEBUG)

# 测试连接
try:
    balance = client.get_balance()
    print(f"连接成功! 余额: ${balance['usdc']}")
except Exception as e:
    print(f"连接失败: {e}")
```

---

## 8. 相关资源

### 官方文档
- [Polymarket API 文档](https://docs.polymarket.com/)
- [py-clob-client GitHub](https://github.com/Polymarket/py-clob-client)
- [Polymarket 开发者指南](https://docs.polymarket.com/developers)

### 相关文件
- `examples/polymarket_trading_example.py` - 交易示例代码
- `app/services/polymarket_worker.py` - AI 分析 Worker
- `app/services/polymarket_batch_analyzer.py` - 批量分析
- `query_polymarket_results.py` - 查询分析结果

### 数据库表
- `qd_polymarket_markets` - 市场数据
- `qd_polymarket_ai_analysis` - AI 分析结果
- `qd_polymarket_trades` - 交易记录（需要创建）

---

## 总结

Polymarket 交易集成的关键步骤：

1. ✅ 安装 `py-clob-client`
2. ✅ 配置钱包和私钥
3. ✅ 从数据库读取 AI 分析
4. ✅ 根据建议自动下单
5. ✅ 实施风险管理
6. ✅ 监控和优化

通过将 AI 分析与自动交易结合，可以实现完全自动化的 Polymarket 交易策略！
