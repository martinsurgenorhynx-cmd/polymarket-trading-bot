"""
最简单的调试脚本 - 测试核心功能
"""
import os
import sys

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 加载环境变量
from dotenv import load_dotenv
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
load_dotenv(env_path)

print("=" * 60)
print("QuantDinger 简单测试")
print("=" * 60)

# 验证环境变量加载
print("\n[环境检查]")
print(f"Python版本: {sys.version}")
print(f"工作目录: {os.getcwd()}")
print(f".env文件: {env_path}")
print(f".env存在: {os.path.exists(env_path)}")
print(f"DATABASE_URL: {os.getenv('DATABASE_URL', '未设置')[:50]}...")
print(f"ADMIN_USER: {os.getenv('ADMIN_USER', '未设置')}")
print(f"LLM_PROVIDER: {os.getenv('LLM_PROVIDER', '未设置')}")

# 测试1: 数据库连接
print("\n[测试1] 数据库连接")
try:
    from app.utils.db import get_db_connection
    with get_db_connection() as db:
        cur = db.cursor()
        cur.execute("SELECT COUNT(*) as count FROM qd_users")
        count = cur.fetchone()['count']
        cur.close()
        print(f"✓ 成功 - 找到 {count} 个用户")
except Exception as e:
    print(f"✗ 失败: {e}")

# 测试2: 用户服务
print("\n[测试2] 用户服务")
try:
    from app.services.user_service import get_user_service
    service = get_user_service()
    user = service.get_user_by_username('quantdinger')
    if user:
        print(f"✓ 成功 - 用户: {user['username']}, 角色: {user['role']}")
    else:
        print("✗ 未找到用户")
except Exception as e:
    print(f"✗ 失败: {e}")

# 测试3: 安全执行环境
print("\n[测试3] 安全执行环境")
try:
    from app.utils.safe_exec import safe_exec_code
    
    code = """
result = 10 + 20
message = f"计算结果: {result}"
"""
    namespace = {}
    safe_exec_code(code, namespace)
    print(f"✓ 成功 - {namespace.get('message')}")
except Exception as e:
    print(f"✗ 失败: {e}")

# 测试4: 策略编译器
print("\n[测试4] 策略编译器")
try:
    from app.services.strategy_compiler import StrategyCompiler
    
    compiler = StrategyCompiler()
    config = {
        'name': '测试策略',
        'position_config': {'mode': 'fixed', 'size': 1},
        'rules': []
    }
    
    code = compiler.compile(config)
    print(f"✓ 成功 - 生成了 {len(code)} 字符的策略代码")
    print(f"  前100字符: {code[:100]}...")
except Exception as e:
    print(f"✗ 失败: {e}")

# 测试5: K线服务
print("\n[测试5] K线服务")
try:
    from app.services.kline import KlineService
    
    service = KlineService()
    print(f"✓ 成功 - K线服务已初始化")
    print(f"  提示: 获取实际数据需要配置数据源")
except Exception as e:
    print(f"✗ 失败: {e}")

# 测试6: 回测服务
print("\n[测试6] 回测服务")
try:
    from app.services.backtest import BacktestService
    
    service = BacktestService()
    print(f"✓ 成功 - 回测服务已初始化")
    print(f"  提示: 运行回测需要市场数据")
except Exception as e:
    print(f"✗ 失败: {e}")

# 测试7: 快速分析服务
print("\n[测试7] 快速分析服务")
try:
    from app.services.fast_analysis import get_fast_analysis_service
    
    service = get_fast_analysis_service()
    print(f"✓ 成功 - 快速分析服务已初始化")
    print(f"  提示: 分析需要LLM和市场数据")
except Exception as e:
    print(f"✗ 失败: {e}")

# 测试8: 数据源工厂
print("\n[测试8] 数据源工厂")
try:
    from app.data_sources.factory import DataSourceFactory
    
    factory = DataSourceFactory()
    print(f"✓ 成功 - 数据源工厂已初始化")
    
    # 尝试获取加密货币数据源
    try:
        crypto_source = factory.get_source('Crypto')
        print(f"  - Crypto数据源: {type(crypto_source).__name__}")
    except:
        print(f"  - Crypto数据源: 未配置")
        
except Exception as e:
    print(f"✗ 失败: {e}")

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)
print("\n提示:")
print("  - 所有核心服务都可以直接导入和使用")
print("  - 不需要启动Flask服务器")
print("  - 可以在Python交互式环境中调试")
print("  - 使用 'python -i simple_test.py' 进入交互模式")
print()
