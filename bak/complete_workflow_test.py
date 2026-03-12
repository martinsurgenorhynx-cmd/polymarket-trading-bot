"""
完整业务流程测试 - 端到端测试

包含：
1. 数据获取（K线数据）
2. AI生成策略
3. 策略编译
4. 回测执行
5. 快速分析（AI市场分析）
6. 结果可视化
"""
import os
import sys
import json
from datetime import datetime, timedelta

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 加载环境变量
from dotenv import load_dotenv
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
load_dotenv(env_path)

print("=" * 80)
print("QuantDinger 完整业务流程测试")
print("=" * 80)

# ============================================================================
# 流程1: 数据获取 - 获取K线数据
# ============================================================================
print("\n" + "=" * 80)
print("流程1: 数据获取 - 获取K线数据")
print("=" * 80)

try:
    from app.data_sources.factory import DataSourceFactory
    
    factory = DataSourceFactory()
    crypto_source = factory.get_source('Crypto')
    
    print("\n[1.1] 获取BTC/USDT的K线数据...")
    klines = crypto_source.get_kline(
        symbol='BTC/USDT',
        timeframe='1h',
        limit=100
    )
    
    if klines and len(klines) > 0:
        print(f"✓ 成功获取 {len(klines)} 条K线数据")
        print(f"\n最新K线数据:")
        latest = klines[-1]
        print(f"  时间: {latest.get('timestamp', 'N/A')}")
        print(f"  开盘: {latest.get('open', 0):.2f}")
        print(f"  最高: {latest.get('high', 0):.2f}")
        print(f"  最低: {latest.get('low', 0):.2f}")
        print(f"  收盘: {latest.get('close', 0):.2f}")
        print(f"  成交量: {latest.get('volume', 0):.2f}")
        
        # 保存数据供后续使用
        kline_data = klines
        current_price = float(latest.get('close', 0))
    else:
        print("✗ 未能获取K线数据")
        print("提示: 可能需要配置数据源API密钥")
        kline_data = None
        current_price = 50000  # 使用模拟价格
        
except Exception as e:
    print(f"✗ 数据获取失败: {e}")
    import traceback
    traceback.print_exc()
    kline_data = None
    current_price = 50000

# ============================================================================
# 流程2: K线数据本地化展示
# ============================================================================
print("\n" + "=" * 80)
print("流程2: K线数据本地化展示")
print("=" * 80)

if kline_data:
    try:
        import pandas as pd
        
        print("\n[2.1] 转换为DataFrame...")
        df = pd.DataFrame(kline_data)
        
        # 转换时间戳为可读格式
        if 'time' in df.columns:
            df['datetime'] = pd.to_datetime(df['time'], unit='s')
        
        # 计算基本统计
        print(f"\n数据统计:")
        print(f"  数据条数: {len(df)}")
        if 'datetime' in df.columns:
            print(f"  时间范围: {df['datetime'].iloc[0]} 到 {df['datetime'].iloc[-1]}")
        print(f"  价格范围: {df['close'].min():.2f} - {df['close'].max():.2f}")
        print(f"  平均价格: {df['close'].mean():.2f}")
        print(f"  价格标准差: {df['close'].std():.2f}")
        
        # 计算技术指标
        print(f"\n[2.2] 计算技术指标...")
        
        # MA均线
        df['ma5'] = df['close'].rolling(window=5).mean()
        df['ma10'] = df['close'].rolling(window=10).mean()
        df['ma20'] = df['close'].rolling(window=20).mean()
        
        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # MACD
        exp1 = df['close'].ewm(span=12, adjust=False).mean()
        exp2 = df['close'].ewm(span=26, adjust=False).mean()
        df['macd'] = exp1 - exp2
        df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
        df['macd_hist'] = df['macd'] - df['macd_signal']
        
        print(f"✓ 技术指标计算完成")
        print(f"\n最新指标值:")
        print(f"  MA5: {df['ma5'].iloc[-1]:.2f}")
        print(f"  MA10: {df['ma10'].iloc[-1]:.2f}")
        print(f"  MA20: {df['ma20'].iloc[-1]:.2f}")
        print(f"  RSI: {df['rsi'].iloc[-1]:.2f}")
        print(f"  MACD: {df['macd'].iloc[-1]:.4f}")
        print(f"  MACD Signal: {df['macd_signal'].iloc[-1]:.4f}")
        
        # 简单的可视化（文本形式）
        print(f"\n[2.3] 价格趋势（最近20条）:")
        recent = df.tail(20)
        for idx, row in recent.iterrows():
            price = row['close']
            ma20 = row['ma20']
            time_str = row['datetime'].strftime('%m-%d %H:%M') if 'datetime' in row else str(row.get('time', ''))
            if pd.notna(ma20):
                if price > ma20:
                    trend = "↑"
                else:
                    trend = "↓"
                bar_length = int((price - recent['close'].min()) / (recent['close'].max() - recent['close'].min()) * 40)
                bar = "█" * bar_length
                print(f"  {time_str} {trend} {bar} {price:.2f}")
        
    except Exception as e:
        print(f"✗ 数据展示失败: {e}")
        import traceback
        traceback.print_exc()
else:
    print("⚠️ 跳过（无K线数据）")

# ============================================================================
# 流程3: AI生成策略
# ============================================================================
print("\n" + "=" * 80)
print("流程3: AI生成策略（使用策略编译器）")
print("=" * 80)

try:
    from app.services.strategy_compiler import StrategyCompiler
    
    print("\n[3.1] 创建策略配置...")
    
    # 创建一个简单的均线交叉策略
    strategy_config = {
        'name': 'MA交叉策略',
        'description': '当短期均线上穿长期均线时买入，下穿时卖出',
        'position_config': {
            'mode': 'percent',  # 按百分比开仓
            'size': 50  # 50%仓位
        },
        'pyramid_rules': {
            'enabled': False
        },
        'risk_management': {
            'stop_loss_pct': 2.0,  # 止损2%
            'take_profit_pct': 5.0  # 止盈5%
        },
        'rules': [
            {
                'type': 'entry',
                'direction': 'long',
                'conditions': [
                    {
                        'indicator': 'ma',
                        'params': {'period': 5},
                        'operator': '>',
                        'compare_to': 'ma',
                        'compare_params': {'period': 20}
                    }
                ]
            },
            {
                'type': 'exit',
                'direction': 'long',
                'conditions': [
                    {
                        'indicator': 'ma',
                        'params': {'period': 5},
                        'operator': '<',
                        'compare_to': 'ma',
                        'compare_params': {'period': 20}
                    }
                ]
            }
        ]
    }
    
    print("\n[3.2] 编译策略代码...")
    compiler = StrategyCompiler()
    strategy_code = compiler.compile(strategy_config)
    
    print(f"✓ 策略编译成功")
    print(f"  代码长度: {len(strategy_code)} 字符")
    print(f"\n策略代码预览（前500字符）:")
    print("-" * 80)
    print(strategy_code[:500])
    print("...")
    print("-" * 80)
    
    # 保存策略代码
    with open('generated_strategy.py', 'w', encoding='utf-8') as f:
        f.write(strategy_code)
    print(f"\n✓ 策略代码已保存到: generated_strategy.py")
    
except Exception as e:
    print(f"✗ 策略生成失败: {e}")
    import traceback
    traceback.print_exc()
    strategy_code = None

# ============================================================================
# 流程4: 回测真实策略
# ============================================================================
print("\n" + "=" * 80)
print("流程4: 回测真实策略")
print("=" * 80)

if kline_data:
    try:
        from app.services.backtest import BacktestService
        
        print("\n[4.1] 初始化回测服务...")
        backtest_service = BacktestService()
        
        # 创建指标代码（用于生成买卖信号）
        # 注意：这是指标代码，不是完整的策略代码
        # 指标代码需要生成 df['buy'] 和 df['sell'] 信号列
        indicator_code = """
# MA交叉策略指标代码
# 当短期均线上穿长期均线时买入，下穿时卖出

# 计算均线
df['ma5'] = df['close'].rolling(window=5).mean()
df['ma20'] = df['close'].rolling(window=20).mean()

# 初始化信号列
df['buy'] = False
df['sell'] = False

# 生成买卖信号
for i in range(1, len(df)):
    # 金叉：短期均线上穿长期均线 -> 买入信号
    if df['ma5'].iloc[i-1] <= df['ma20'].iloc[i-1] and df['ma5'].iloc[i] > df['ma20'].iloc[i]:
        df.loc[df.index[i], 'buy'] = True
    
    # 死叉：短期均线下穿长期均线 -> 卖出信号
    elif df['ma5'].iloc[i-1] >= df['ma20'].iloc[i-1] and df['ma5'].iloc[i] < df['ma20'].iloc[i]:
        df.loc[df.index[i], 'sell'] = True
"""
        
        print("\n[4.2] 执行回测...")
        print(f"  市场: Crypto")
        print(f"  交易对: BTC/USDT")
        print(f"  初始资金: $10,000")
        print(f"  时间周期: 1D (日线)")
        print(f"  策略: MA5/MA20交叉策略")
        
        # 计算日期范围（使用K线数据的实际时间范围）
        if kline_data and len(kline_data) > 0:
            # K线数据使用 'time' 字段（Unix时间戳）
            start_timestamp = kline_data[0].get('time', 0)
            end_timestamp = kline_data[-1].get('time', 0)
            
            # 转换为datetime对象
            start_date_obj = datetime.fromtimestamp(start_timestamp)
            end_date_obj = datetime.fromtimestamp(end_timestamp)
            
            # 格式化为字符串用于显示
            start_date = start_date_obj.strftime('%Y-%m-%d')
            end_date = end_date_obj.strftime('%Y-%m-%d')
        else:
            # 如果没有K线数据，使用最近30天
            end_date_obj = datetime.now()
            start_date_obj = end_date_obj - timedelta(days=30)
            start_date = start_date_obj.strftime('%Y-%m-%d')
            end_date = end_date_obj.strftime('%Y-%m-%d')
        
        print(f"  开始日期: {start_date}")
        print(f"  结束日期: {end_date}")
        
        try:
            result = backtest_service.run(
                indicator_code=indicator_code,  # 使用指标代码，不是完整策略代码
                market='Crypto',
                symbol='BTC/USDT',
                timeframe='1D',  # 使用日线数据
                start_date=start_date_obj,  # 使用datetime对象
                end_date=end_date_obj,      # 使用datetime对象
                initial_capital=10000,
                commission=0.001,
                leverage=1
            )
        except Exception as backtest_error:
            result = {
                'success': False,
                'error': str(backtest_error)
            }
            print(f"\n✗ 回测执行异常: {backtest_error}")
            import traceback as tb
            tb.print_exc()
        
        # Check if backtest succeeded (has totalReturn key)
        if 'totalReturn' in result or 'total_return' in result:
            print(f"\n✓ 回测完成")
            print(f"\n回测结果:")
            # Handle both camelCase and snake_case
            total_return = result.get('totalReturn') or result.get('total_return', 0)
            annual_return = result.get('annualReturn') or result.get('annual_return', 0)
            sharpe_ratio = result.get('sharpeRatio') or result.get('sharpe_ratio', 0)
            max_drawdown = result.get('maxDrawdown') or result.get('max_drawdown', 0)
            win_rate = result.get('winRate') or result.get('win_rate', 0)
            total_trades = result.get('totalTrades') or result.get('total_trades', 0)
            profit_factor = result.get('profitFactor') or result.get('profit_factor', 0)
            
            print(f"  总收益率: {total_return:.2%}")
            print(f"  年化收益率: {annual_return:.2%}")
            print(f"  夏普比率: {sharpe_ratio:.2f}")
            print(f"  最大回撤: {max_drawdown:.2%}")
            print(f"  胜率: {win_rate:.2%}")
            print(f"  盈利因子: {profit_factor:.2f}")
            print(f"  交易次数: {total_trades}")
            
            # 显示交易记录
            trades = result.get('trades', [])
            if trades:
                print(f"\n交易记录（共{len(trades)}笔）:")
                for i, trade in enumerate(trades[:10], 1):  # 显示前10笔
                    trade_type = trade.get('type', 'N/A')
                    price = trade.get('price', 0)
                    amount = trade.get('amount', 0)
                    profit = trade.get('profit', 0)
                    time_str = trade.get('time', 'N/A')
                    print(f"  {i}. {time_str} - {trade_type} @ ${price:.2f} "
                          f"x {amount:.4f} (盈亏: ${profit:.2f})")
        elif result.get('success'):
            # Old format with success key
            print(f"\n✓ 回测完成")
            print(f"\n回测结果:")
            print(f"  总收益率: {result.get('total_return', 0):.2%}")
            print(f"  年化收益率: {result.get('annual_return', 0):.2%}")
            print(f"  夏普比率: {result.get('sharpe_ratio', 0):.2f}")
            print(f"  最大回撤: {result.get('max_drawdown', 0):.2%}")
            print(f"  胜率: {result.get('win_rate', 0):.2%}")
            print(f"  交易次数: {result.get('total_trades', 0)}")
            print(f"  盈利交易: {result.get('winning_trades', 0)}")
            print(f"  亏损交易: {result.get('losing_trades', 0)}")
            
            # 显示交易记录
            trades = result.get('trades', [])
            if trades:
                print(f"\n最近5笔交易:")
                for i, trade in enumerate(trades[-5:], 1):
                    print(f"  {i}. {trade.get('type', 'N/A')} @ {trade.get('price', 0):.2f} "
                          f"- 数量: {trade.get('amount', 0):.4f} "
                          f"- 时间: {trade.get('timestamp', 'N/A')}")
        else:
            error_msg = result.get('error', '未知错误')
            print(f"✗ 回测失败: {error_msg}")
            if 'traceback' in result:
                print(f"\n详细错误信息:")
                print(result['traceback'])
            
    except Exception as e:
        print(f"✗ 回测执行失败: {e}")
        import traceback
        traceback.print_exc()
else:
    print("⚠️ 跳过（缺少K线数据）")
    print("提示: 可以使用模拟数据进行回测测试")

# ============================================================================
# 流程5: 快速分析（AI市场分析）
# ============================================================================
print("\n" + "=" * 80)
print("流程5: 快速分析（AI市场分析）")
print("=" * 80)

try:
    from app.services.fast_analysis import get_fast_analysis_service
    
    print("\n[5.1] 初始化快速分析服务...")
    analysis_service = get_fast_analysis_service()
    
    print("\n[5.2] 执行AI市场分析...")
    print(f"  市场: Crypto")
    print(f"  交易对: BTC/USDT")
    print(f"  时间周期: 1D")
    print(f"  语言: 中文")
    
    # 注意：这需要配置LLM API密钥
    result = analysis_service.analyze(
        market='Crypto',
        symbol='BTC/USDT',
        language='zh-CN',
        timeframe='1D'
    )
    
    if result.get('error'):
        print(f"\n⚠️ 分析失败: {result['error']}")
        print("提示: 可能需要配置LLM API密钥（OPENAI_API_KEY）")
        print(f"当前LLM提供商: {os.getenv('LLM_PROVIDER', '未设置')}")
        print(f"API密钥状态: {'已设置' if os.getenv('OPENAI_API_KEY') else '未设置'}")
    else:
        print(f"\n✓ AI分析完成")
        print(f"\n分析结果:")
        print(f"  决策: {result.get('decision', 'N/A')}")
        print(f"  置信度: {result.get('confidence', 0)}%")
        print(f"  分析时间: {result.get('analysis_time_ms', 0)}ms")
        
        print(f"\n摘要:")
        print(f"  {result.get('summary', 'N/A')}")
        
        # 交易计划
        trading_plan = result.get('trading_plan', {})
        if trading_plan:
            print(f"\n交易计划:")
            print(f"  入场价格: ${trading_plan.get('entry_price', 0):.2f}")
            print(f"  止损价格: ${trading_plan.get('stop_loss', 0):.2f}")
            print(f"  止盈价格: ${trading_plan.get('take_profit', 0):.2f}")
            print(f"  建议仓位: {trading_plan.get('position_size_pct', 0)}%")
            print(f"  持仓周期: {trading_plan.get('timeframe', 'N/A')}")
        
        # 关键原因
        reasons = result.get('reasons', [])
        if reasons:
            print(f"\n关键原因:")
            for i, reason in enumerate(reasons, 1):
                print(f"  {i}. {reason}")
        
        # 风险提示
        risks = result.get('risks', [])
        if risks:
            print(f"\n风险提示:")
            for i, risk in enumerate(risks, 1):
                print(f"  {i}. {risk}")
        
        # 评分
        scores = result.get('scores', {})
        if scores:
            print(f"\n综合评分:")
            print(f"  技术面: {scores.get('technical', 0)}/100")
            print(f"  基本面: {scores.get('fundamental', 0)}/100")
            print(f"  情绪面: {scores.get('sentiment', 0)}/100")
            print(f"  综合分: {scores.get('overall', 0)}/100")
        
        # 市场数据
        market_data = result.get('market_data', {})
        if market_data:
            print(f"\n市场数据:")
            print(f"  当前价格: ${market_data.get('current_price', 0):.2f}")
            print(f"  24h涨跌: {market_data.get('change_24h', 0):.2f}%")
            print(f"  支撑位: ${market_data.get('support', 0):.2f}")
            print(f"  阻力位: ${market_data.get('resistance', 0):.2f}")
        
except Exception as e:
    print(f"✗ 快速分析失败: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# 流程6: 完整流程总结
# ============================================================================
print("\n" + "=" * 80)
print("完整流程总结")
print("=" * 80)

print("""
✓ 已完成的流程:
  1. 数据获取 - 从数据源获取K线数据
  2. 数据展示 - 计算技术指标并可视化
  3. 策略生成 - 使用编译器生成策略代码
  4. 策略回测 - 使用指标代码执行回测并获取结果
  5. AI分析 - 使用LLM进行市场分析

💡 使用建议:
  - 配置数据源API密钥以获取实时数据
  - 配置LLM API密钥以使用AI分析功能（在.env中设置OPENAI_API_KEY）
  - 查看生成的策略代码: generated_strategy.py
  - 使用 'python -i complete_workflow_test.py' 进入交互模式

📝 重要说明:
  - 回测使用的是指标代码（生成buy/sell信号），不是完整的策略代码
  - 指标代码需要在DataFrame中生成 df['buy'] 和 df['sell'] 列
  - 策略编译器生成的是完整策略代码，用于实盘交易

📚 相关文档:
  - DEBUG_GUIDE.md - 调试指南
  - TEST_RESULTS.md - 测试结果
  - DEVELOPMENT_SUMMARY.md - 开发环境总结
  - COMPLETE_WORKFLOW_GUIDE.md - 完整流程指南
""")

print("\n" + "=" * 80)
print("测试完成")
print("=" * 80)
