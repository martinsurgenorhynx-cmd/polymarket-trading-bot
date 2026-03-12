"""
数据库测试示例 - 不需要启动服务器

演示如何直接查询和操作数据库
"""
import os
import sys

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.utils.db import get_db_connection


def show_table_info():
    """显示数据库表信息"""
    print("=" * 60)
    print("数据库表信息")
    print("=" * 60)
    
    try:
        with get_db_connection() as db:
            cur = db.cursor()
            
            # 获取所有表
            cur.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name LIKE 'qd_%'
                ORDER BY table_name
            """)
            
            tables = [row['table_name'] for row in cur.fetchall()]
            
            print(f"\n找到 {len(tables)} 个表:\n")
            
            for table in tables:
                # 获取表的行数
                cur.execute(f"SELECT COUNT(*) as count FROM {table}")
                count = cur.fetchone()['count']
                print(f"  {table:<40} {count:>10} 行")
            
            cur.close()
            
    except Exception as e:
        print(f"✗ 查询失败: {e}")


def show_users():
    """显示用户信息"""
    print("\n" + "=" * 60)
    print("用户列表")
    print("=" * 60)
    
    try:
        with get_db_connection() as db:
            cur = db.cursor()
            
            cur.execute("""
                SELECT id, username, email, role, status, created_at
                FROM qd_users
                ORDER BY id
                LIMIT 10
            """)
            
            users = cur.fetchall()
            
            if users:
                print(f"\n{'ID':<5} {'用户名':<20} {'邮箱':<30} {'角色':<10} {'状态':<10}")
                print("-" * 80)
                for user in users:
                    print(f"{user['id']:<5} {user['username']:<20} {user.get('email', ''):<30} {user['role']:<10} {user['status']:<10}")
            else:
                print("\n没有用户数据")
            
            cur.close()
            
    except Exception as e:
        print(f"✗ 查询失败: {e}")


def show_strategies():
    """显示策略信息"""
    print("\n" + "=" * 60)
    print("策略列表")
    print("=" * 60)
    
    try:
        with get_db_connection() as db:
            cur = db.cursor()
            
            cur.execute("""
                SELECT id, name, market, symbol, status, created_at
                FROM qd_strategies
                ORDER BY created_at DESC
                LIMIT 10
            """)
            
            strategies = cur.fetchall()
            
            if strategies:
                print(f"\n{'ID':<5} {'策略名称':<30} {'市场':<10} {'交易对':<15} {'状态':<10}")
                print("-" * 80)
                for s in strategies:
                    print(f"{s['id']:<5} {s['name']:<30} {s.get('market', ''):<10} {s.get('symbol', ''):<15} {s.get('status', ''):<10}")
            else:
                print("\n没有策略数据")
            
            cur.close()
            
    except Exception as e:
        print(f"✗ 查询失败: {e}")


def show_backtest_results():
    """显示回测结果"""
    print("\n" + "=" * 60)
    print("回测结果")
    print("=" * 60)
    
    try:
        with get_db_connection() as db:
            cur = db.cursor()
            
            cur.execute("""
                SELECT id, strategy_id, total_return, sharpe_ratio, max_drawdown, created_at
                FROM qd_backtest_results
                ORDER BY created_at DESC
                LIMIT 10
            """)
            
            results = cur.fetchall()
            
            if results:
                print(f"\n{'ID':<5} {'策略ID':<10} {'总收益':<12} {'夏普比率':<12} {'最大回撤':<12}")
                print("-" * 60)
                for r in results:
                    total_return = r.get('total_return', 0) or 0
                    sharpe = r.get('sharpe_ratio', 0) or 0
                    drawdown = r.get('max_drawdown', 0) or 0
                    print(f"{r['id']:<5} {r.get('strategy_id', ''):<10} {total_return:<12.2%} {sharpe:<12.2f} {drawdown:<12.2%}")
            else:
                print("\n没有回测数据")
            
            cur.close()
            
    except Exception as e:
        print(f"✗ 查询失败: {e}")


def custom_query():
    """自定义查询"""
    print("\n" + "=" * 60)
    print("自定义查询示例")
    print("=" * 60)
    
    # 示例：查询最活跃的用户
    query = """
        SELECT 
            u.username,
            COUNT(DISTINCT s.id) as strategy_count,
            COUNT(DISTINCT b.id) as backtest_count
        FROM qd_users u
        LEFT JOIN qd_strategies s ON u.id = s.user_id
        LEFT JOIN qd_backtest_results b ON s.id = b.strategy_id
        GROUP BY u.id, u.username
        ORDER BY strategy_count DESC, backtest_count DESC
        LIMIT 5
    """
    
    try:
        with get_db_connection() as db:
            cur = db.cursor()
            cur.execute(query)
            results = cur.fetchall()
            
            if results:
                print(f"\n{'用户名':<20} {'策略数':<10} {'回测数':<10}")
                print("-" * 40)
                for r in results:
                    print(f"{r['username']:<20} {r['strategy_count']:<10} {r['backtest_count']:<10}")
            else:
                print("\n没有数据")
            
            cur.close()
            
    except Exception as e:
        print(f"✗ 查询失败: {e}")


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("QuantDinger 数据库调试工具")
    print("=" * 60)
    
    show_table_info()
    show_users()
    show_strategies()
    show_backtest_results()
    custom_query()
    
    print("\n" + "=" * 60)
    print("完成")
    print("=" * 60)


if __name__ == '__main__':
    main()
