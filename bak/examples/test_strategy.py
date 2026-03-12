"""
策略测试示例 - 不需要启动服务器

演示如何直接测试策略逻辑
"""
import os
import sys

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.services.strategy_compiler import compile_strategy
from app.utils.safe_exec import safe_exec


def test_simple_strategy():
    """测试简单策略"""
    print("=" * 60)
    print("测试简单策略")
    print("=" * 60)
    
    strategy_code = """
def initialize(context):
    '''策略初始化'''
    context.symbol = 'BTCUSDT'
    context.ma_period = 20
    print(f"策略初始化: 交易对={context.symbol}, MA周期={context.ma_period}")

def handle_bar(context, bar_dict):
    '''处理每根K线'''
    timestamp = bar_dict.get('timestamp', 'N/A')
    close = bar_dict.get('close', 0)
    
    print(f"[{timestamp}] 收盘价: {close}")
    
    # 计算简单移动平均
    if len(context.history_bars) >= context.ma_period:
        prices = [bar['close'] for bar in context.history_bars[-context.ma_period:]]
        ma = sum(prices) / len(prices)
        print(f"  MA{context.ma_period}: {ma:.2f}")
        
        # 交易逻辑
        if close > ma:
            print(f"  信号: 买入 (价格 {close} > MA {ma:.2f})")
        elif close < ma:
            print(f"  信号: 卖出 (价格 {close} < MA {ma:.2f})")
"""
    
    try:
        # 编译策略
        print("\n1. 编译策略...")
        compiled = compile_strategy(strategy_code)
        print("   ✓ 编译成功")
        
        # 创建模拟上下文
        print("\n2. 创建模拟上下文...")
        class MockContext:
            def __init__(self):
                self.symbol = None
                self.ma_period = None
                self.history_bars = []
        
        context = MockContext()
        
        # 初始化策略
        print("\n3. 初始化策略...")
        compiled['initialize'](context)
        
        # 模拟K线数据
        print("\n4. 模拟K线数据...")
        mock_bars = [
            {'timestamp': '2024-01-01 00:00', 'close': 45000, 'volume': 100},
            {'timestamp': '2024-01-01 01:00', 'close': 45200, 'volume': 120},
            {'timestamp': '2024-01-01 02:00', 'close': 45100, 'volume': 110},
            {'timestamp': '2024-01-01 03:00', 'close': 45300, 'volume': 130},
            {'timestamp': '2024-01-01 04:00', 'close': 45500, 'volume': 140},
        ]
        
        # 处理每根K线
        print("\n5. 处理K线...")
        for bar in mock_bars:
            context.history_bars.append(bar)
            compiled['handle_bar'](context, bar)
            print()
        
        print("=" * 60)
        print("测试完成")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()


def test_indicator_strategy():
    """测试带指标的策略"""
    print("\n" + "=" * 60)
    print("测试带指标的策略")
    print("=" * 60)
    
    strategy_code = """
def initialize(context):
    context.symbol = 'BTCUSDT'
    context.rsi_period = 14
    context.rsi_overbought = 70
    context.rsi_oversold = 30

def calculate_rsi(prices, period=14):
    '''计算RSI指标'''
    if len(prices) < period + 1:
        return None
    
    gains = []
    losses = []
    
    for i in range(1, len(prices)):
        change = prices[i] - prices[i-1]
        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))
    
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    
    if avg_loss == 0:
        return 100
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def handle_bar(context, bar_dict):
    close = bar_dict['close']
    
    # 需要足够的历史数据
    if len(context.history_bars) < context.rsi_period + 1:
        print(f"等待数据... ({len(context.history_bars)}/{context.rsi_period + 1})")
        return
    
    # 计算RSI
    prices = [bar['close'] for bar in context.history_bars]
    rsi = calculate_rsi(prices, context.rsi_period)
    
    print(f"价格: {close:.2f}, RSI: {rsi:.2f}")
    
    # 交易信号
    if rsi < context.rsi_oversold:
        print(f"  → 超卖信号 (RSI={rsi:.2f} < {context.rsi_oversold})")
    elif rsi > context.rsi_overbought:
        print(f"  → 超买信号 (RSI={rsi:.2f} > {context.rsi_overbought})")
"""
    
    try:
        compiled = compile_strategy(strategy_code)
        
        class MockContext:
            def __init__(self):
                self.symbol = None
                self.rsi_period = None
                self.rsi_overbought = None
                self.rsi_oversold = None
                self.history_bars = []
        
        context = MockContext()
        compiled['initialize'](context)
        
        # 生成模拟价格数据（模拟超买超卖）
        import random
        base_price = 45000
        prices = [base_price]
        
        # 先上涨（制造超买）
        for i in range(10):
            prices.append(prices[-1] + random.uniform(50, 200))
        
        # 再下跌（制造超卖）
        for i in range(10):
            prices.append(prices[-1] - random.uniform(50, 200))
        
        # 处理K线
        for i, price in enumerate(prices):
            bar = {
                'timestamp': f'2024-01-01 {i:02d}:00',
                'close': price,
                'volume': random.randint(100, 200)
            }
            context.history_bars.append(bar)
            compiled['handle_bar'](context, bar)
        
        print("\n" + "=" * 60)
        print("测试完成")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    test_simple_strategy()
    test_indicator_strategy()
