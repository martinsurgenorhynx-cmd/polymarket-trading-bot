"""
本地调试示例脚本 - 无需启动服务器

直接调用核心服务和功能进行测试
"""
import os
import sys

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 加载环境变量
from dotenv import load_dotenv
load_dotenv()


def test_backtest_service():
    """测试回测服务"""
    print("\n=== 测试回测服务 ===")
    from app.services.backtest import BacktestService
    
    # 简单的策略代码
    strategy_code = """
def initialize(context):
    context.symbol = 'BTCUSDT'
    
def handle_bar(context, bar_dict):
    # 简单的均线策略
    if len(context.history_bars) < 20:
        return
    
    close_prices = [bar['close'] for bar in context.history_bars[-20:]]
    ma20 = sum(close_prices) / 20
    current_price = bar_dict['close']
    
    if current_price > ma20 and context.portfolio.cash > 0:
        # 买入
        context.order_target_percent(context.symbol, 0.5)
    elif current_price < ma20 and context.portfolio.positions.get(context.symbol, 0) > 0:
        # 卖出
        context.order_target_percent(context.symbol, 0)
"""
    
    service = BacktestService()
    
    # 注意：这需要市场数据，如果数据源不可用会失败
    try:
        result = service.run_backtest(
            strategy_code=strategy_code,
            market='Crypto',
            symbol='BTC/USDT',
            start_date='2024-01-01',
            end_date='2024-01-31',
            initial_capital=10000,
            timeframe='1h'
        )
        print(f"回测结果: {result}")
    except Exception as e:
        print(f"回测失败 (可能需要数据源): {e}")


def test_strategy_compiler():
    """测试策略编译器"""
    print("\n=== 测试策略编译器 ===")
    from app.services.strategy_compiler import compile_strategy
    
    strategy_code = """
def initialize(context):
    context.symbol = 'BTCUSDT'
    print("策略初始化")
    
def handle_bar(context, bar_dict):
    print(f"处理K线: {bar_dict}")
"""
    
    try:
        compiled = compile_strategy(strategy_code)
        print(f"编译成功: {compiled}")
        
        # 测试执行
        context = type('Context', (), {'symbol': None})()
        compiled['initialize'](context)
        print(f"初始化后 context.symbol = {context.symbol}")
        
    except Exception as e:
        print(f"编译失败: {e}")


def test_safe_exec():
    """测试安全执行环境"""
    print("\n=== 测试安全执行环境 ===")
    from app.utils.safe_exec import safe_exec
    
    # 测试正常代码
    code1 = """
result = 1 + 1
print(f"计算结果: {result}")
"""
    
    print("测试1: 正常代码")
    try:
        namespace = {}
        safe_exec(code1, namespace)
        print(f"执行成功, result = {namespace.get('result')}")
    except Exception as e:
        print(f"执行失败: {e}")
    
    # 测试危险代码
    code2 = """
import os
os.system('ls')
"""
    
    print("\n测试2: 危险代码 (应该被阻止)")
    try:
        namespace = {}
        safe_exec(code2, namespace)
        print("执行成功 (不应该到这里!)")
    except Exception as e:
        print(f"执行被阻止: {e}")


def test_indicator_calculation():
    """测试指标计算"""
    print("\n=== 测试指标计算 ===")
    import pandas as pd
    import numpy as np
    
    # 创建模拟数据
    dates = pd.date_range('2024-01-01', periods=100, freq='1h')
    prices = 100 + np.cumsum(np.random.randn(100) * 2)
    
    df = pd.DataFrame({
        'timestamp': dates,
        'open': prices + np.random.randn(100) * 0.5,
        'high': prices + abs(np.random.randn(100) * 1),
        'low': prices - abs(np.random.randn(100) * 1),
        'close': prices,
        'volume': np.random.randint(1000, 10000, 100)
    })
    
    print(f"生成了 {len(df)} 条K线数据")
    print(f"价格范围: {df['close'].min():.2f} - {df['close'].max():.2f}")
    
    # 计算简单移动平均
    df['ma20'] = df['close'].rolling(window=20).mean()
    df['ma50'] = df['close'].rolling(window=50).mean()
    
    print(f"\nMA20 最新值: {df['ma20'].iloc[-1]:.2f}")
    print(f"MA50 最新值: {df['ma50'].iloc[-1]:.2f}")
    
    # 计算 RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    print(f"RSI 最新值: {df['rsi'].iloc[-1]:.2f}")


def test_database_connection():
    """测试数据库连接"""
    print("\n=== 测试数据库连接 ===")
    from app.utils.db import get_db_connection
    
    try:
        with get_db_connection() as db:
            cur = db.cursor()
            
            # 查询用户表
            cur.execute("SELECT COUNT(*) as count FROM qd_users")
            user_count = cur.fetchone()['count']
            print(f"用户数量: {user_count}")
            
            # 查询策略表
            cur.execute("SELECT COUNT(*) as count FROM qd_strategies")
            strategy_count = cur.fetchone()['count']
            print(f"策略数量: {strategy_count}")
            
            # 查询回测记录表
            cur.execute("SELECT COUNT(*) as count FROM qd_backtest_results")
            backtest_count = cur.fetchone()['count']
            print(f"回测记录数量: {backtest_count}")
            
            cur.close()
            
    except Exception as e:
        print(f"数据库连接失败: {e}")


def test_kline_service():
    """测试K线数据服务"""
    print("\n=== 测试K线数据服务 ===")
    from app.services.kline import get_kline_service
    
    service = get_kline_service()
    
    try:
        # 获取K线数据
        klines = service.get_klines(
            market='Crypto',
            symbol='BTC/USDT',
            interval='1h',
            limit=10
        )
        
        if klines:
            print(f"获取到 {len(klines)} 条K线数据")
            print(f"最新K线: {klines[-1]}")
        else:
            print("未获取到K线数据 (可能需要配置数据源)")
            
    except Exception as e:
        print(f"获取K线失败: {e}")


def test_user_service():
    """测试用户服务"""
    print("\n=== 测试用户服务 ===")
    from app.services.user_service import get_user_service
    
    service = get_user_service()
    
    try:
        # 获取用户信息
        user = service.get_user_by_username('quantdinger')
        if user:
            print(f"用户ID: {user['id']}")
            print(f"用户名: {user['username']}")
            print(f"角色: {user['role']}")
            print(f"状态: {user['status']}")
        else:
            print("未找到用户")
            
    except Exception as e:
        print(f"获取用户失败: {e}")


def test_strategy_execution():
    """测试策略执行逻辑（不需要真实数据）"""
    print("\n=== 测试策略执行逻辑 ===")
    
    # 模拟策略上下文
    class MockContext:
        def __init__(self):
            self.symbol = None
            self.portfolio = type('Portfolio', (), {
                'cash': 10000,
                'positions': {}
            })()
            self.history_bars = []
            
        def order_target_percent(self, symbol, percent):
            print(f"下单: {symbol}, 目标仓位 {percent*100}%")
    
    # 简单策略
    strategy_code = """
def initialize(context):
    context.symbol = 'BTCUSDT'
    print("策略初始化完成")
    
def handle_bar(context, bar_dict):
    print(f"处理K线: 价格={bar_dict['close']}, 时间={bar_dict['timestamp']}")
    
    # 简单逻辑：价格上涨买入
    if bar_dict['close'] > 50000:
        context.order_target_percent(context.symbol, 0.5)
"""
    
    try:
        from app.services.strategy_compiler import compile_strategy
        
        compiled = compile_strategy(strategy_code)
        context = MockContext()
        
        # 初始化
        compiled['initialize'](context)
        
        # 模拟几个K线
        mock_bars = [
            {'timestamp': '2024-01-01 00:00:00', 'close': 45000, 'volume': 100},
            {'timestamp': '2024-01-01 01:00:00', 'close': 48000, 'volume': 120},
            {'timestamp': '2024-01-01 02:00:00', 'close': 51000, 'volume': 150},
        ]
        
        for bar in mock_bars:
            compiled['handle_bar'](context, bar)
            
    except Exception as e:
        print(f"策略执行失败: {e}")


def main():
    """主函数"""
    print("=" * 60)
    print("QuantDinger 本地调试工具")
    print("=" * 60)
    
    # 选择要测试的功能
    tests = {
        '1': ('数据库连接', test_database_connection),
        '2': ('用户服务', test_user_service),
        '3': ('策略编译器', test_strategy_compiler),
        '4': ('安全执行环境', test_safe_exec),
        '5': ('指标计算', test_indicator_calculation),
        '6': ('策略执行逻辑', test_strategy_execution),
        '7': ('K线数据服务', test_kline_service),
        '8': ('回测服务', test_backtest_service),
        '0': ('运行所有测试', None),
    }
    
    print("\n可用的测试:")
    for key, (name, _) in tests.items():
        print(f"  {key}. {name}")
    
    choice = input("\n请选择测试 (直接回车运行所有): ").strip()
    
    if not choice or choice == '0':
        # 运行所有测试
        for key, (name, func) in tests.items():
            if func:
                try:
                    func()
                except Exception as e:
                    print(f"\n测试 {name} 出错: {e}")
                    import traceback
                    traceback.print_exc()
    elif choice in tests:
        name, func = tests[choice]
        if func:
            try:
                func()
            except Exception as e:
                print(f"\n测试 {name} 出错: {e}")
                import traceback
                traceback.print_exc()
    else:
        print("无效的选择")
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == '__main__':
    main()
