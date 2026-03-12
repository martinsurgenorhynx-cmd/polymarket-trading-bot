"""
快速调试脚本 - 交互式测试

使用方法:
    python quick_debug.py
    
或者在 Python 交互式环境中:
    >>> exec(open('quick_debug.py').read())
"""
import os
import sys

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 加载环境变量
from dotenv import load_dotenv
load_dotenv()

print("=" * 60)
print("QuantDinger 快速调试环境")
print("=" * 60)

# 导入常用模块
print("\n正在导入模块...")

from app.utils.db import get_db_connection
from app.services.user_service import get_user_service
from app.services.kline import get_kline_service
from app.services.backtest import BacktestService
from app.services.strategy_compiler import compile_strategy
from app.utils.safe_exec import safe_exec

print("✓ 数据库工具")
print("✓ 用户服务")
print("✓ K线服务")
print("✓ 回测服务")
print("✓ 策略编译器")
print("✓ 安全执行环境")

# 创建服务实例
user_service = get_user_service()
kline_service = get_kline_service()
backtest_service = BacktestService()

print("\n" + "=" * 60)
print("可用的对象和函数:")
print("=" * 60)
print("""
数据库:
  - get_db_connection()          # 获取数据库连接
  
服务实例:
  - user_service                 # 用户服务
  - kline_service                # K线数据服务
  - backtest_service             # 回测服务
  
函数:
  - compile_strategy(code)       # 编译策略代码
  - safe_exec(code, namespace)   # 安全执行代码
  
示例用法:
  >>> # 查询用户
  >>> user = user_service.get_user_by_username('quantdinger')
  >>> print(user)
  
  >>> # 查询数据库
  >>> with get_db_connection() as db:
  ...     cur = db.cursor()
  ...     cur.execute("SELECT * FROM qd_users LIMIT 1")
  ...     print(cur.fetchone())
  ...     cur.close()
  
  >>> # 编译策略
  >>> code = '''
  ... def initialize(context):
  ...     context.symbol = 'BTCUSDT'
  ... '''
  >>> strategy = compile_strategy(code)
  >>> print(strategy)
""")

print("\n" + "=" * 60)
print("快速测试:")
print("=" * 60)

# 测试数据库连接
try:
    with get_db_connection() as db:
        cur = db.cursor()
        cur.execute("SELECT COUNT(*) as count FROM qd_users")
        count = cur.fetchone()['count']
        cur.close()
        print(f"✓ 数据库连接成功 (用户数: {count})")
except Exception as e:
    print(f"✗ 数据库连接失败: {e}")

# 测试用户服务
try:
    user = user_service.get_user_by_username('quantdinger')
    if user:
        print(f"✓ 用户服务正常 (找到用户: {user['username']})")
    else:
        print("✗ 未找到默认用户")
except Exception as e:
    print(f"✗ 用户服务失败: {e}")

print("\n" + "=" * 60)
print("环境准备完成！现在可以开始调试了")
print("=" * 60)
print("\n提示: 在 Python 交互式环境中，你可以直接使用上面列出的对象和函数\n")
