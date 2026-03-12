#!/usr/bin/env python
"""
查询跟单系统数据

使用方法:
    python polymarket/query_copy_trading.py
"""
import os
import sys
from datetime import datetime

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 加载环境变量
from dotenv import load_dotenv
load_dotenv()

from app.utils.db import get_db_connection


def print_header(title: str):
    """打印标题"""
    print("\n" + "=" * 80)
    print(f" {title}")
    print("=" * 80)


def query_top_users():
    """查询排行榜用户"""
    print_header("排行榜Top用户")
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 按period分组查询最新的记录
            cursor.execute("""
                SELECT DISTINCT ON (period, user_address)
                    user_address,
                    period,
                    rank,
                    volume,
                    profit,
                    trades,
                    win_rate,
                    created_at
                FROM qd_polymarket_top_users
                ORDER BY period, user_address, created_at DESC
            """)
            
            rows = cursor.fetchall()
            
            if not rows:
                print("\n  ⚠️  暂无数据")
                return
            
            # 按period分组显示
            periods = {}
            for row in rows:
                period = row['period']
                if period not in periods:
                    periods[period] = []
                periods[period].append(row)
            
            for period in ['day', 'week', 'month', 'all']:
                if period not in periods:
                    continue
                
                print(f"\n  📊 {period.upper()}榜:")
                users = sorted(periods[period], key=lambda x: x['rank'])
                
                for user in users:
                    print(f"    #{user['rank']} {user['user_address'][:10]}...")
                    print(f"        交易量: ${user['volume']:,.0f} | 利润: ${user['profit']:,.0f}")
                    print(f"        交易次数: {user['trades']} | 胜率: {user['win_rate']*100:.1f}%")
                    print(f"        更新时间: {user['created_at']}")
    
    except Exception as e:
        print(f"\n  ✗ 查询失败: {e}")


def query_recent_activities():
    """查询最近的交易活动"""
    print_header("最近交易活动（前20条）")
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT 
                    a.user_address,
                    a.market_id,
                    a.side,
                    a.outcome,
                    a.size,
                    a.price,
                    a.timestamp,
                    m.question
                FROM qd_polymarket_user_activities a
                LEFT JOIN qd_polymarket_markets m ON a.market_id = m.market_id
                ORDER BY a.timestamp DESC
                LIMIT 20
            """)
            
            rows = cursor.fetchall()
            
            if not rows:
                print("\n  ⚠️  暂无数据")
                return
            
            print(f"\n  找到 {len(rows)} 条活动:\n")
            
            for i, row in enumerate(rows, 1):
                question = row['question'] if row['question'] else '未知市场'
                print(f"  [{i}] {row['user_address'][:10]}... | {row['side']} {row['outcome']}")
                print(f"      市场: {question[:60]}")
                print(f"      数量: {row['size']} @ ${row['price']}")
                print(f"      时间: {row['timestamp']}")
                print()
    
    except Exception as e:
        print(f"\n  ✗ 查询失败: {e}")


def query_user_summary():
    """查询用户活动汇总"""
    print_header("用户活动汇总")
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT 
                    user_address,
                    COUNT(*) as activity_count,
                    COUNT(DISTINCT market_id) as market_count,
                    SUM(CASE WHEN side = 'BUY' THEN 1 ELSE 0 END) as buy_count,
                    SUM(CASE WHEN side = 'SELL' THEN 1 ELSE 0 END) as sell_count,
                    MAX(timestamp) as last_activity
                FROM qd_polymarket_user_activities
                GROUP BY user_address
                ORDER BY activity_count DESC
                LIMIT 20
            """)
            
            rows = cursor.fetchall()
            
            if not rows:
                print("\n  ⚠️  暂无数据")
                return
            
            print(f"\n  找到 {len(rows)} 个活跃用户:\n")
            
            for i, row in enumerate(rows, 1):
                print(f"  [{i}] {row['user_address'][:10]}...")
                print(f"      活动数: {row['activity_count']} | 涉及市场: {row['market_count']}")
                print(f"      买入: {row['buy_count']} | 卖出: {row['sell_count']}")
                print(f"      最后活动: {row['last_activity']}")
                print()
    
    except Exception as e:
        print(f"\n  ✗ 查询失败: {e}")


def query_hot_markets():
    """查询热门市场（被多个顶级用户交易）"""
    print_header("热门市场（被多个顶级用户交易）")
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT 
                    a.market_id,
                    m.question,
                    m.category,
                    COUNT(DISTINCT a.user_address) as trader_count,
                    COUNT(*) as activity_count,
                    SUM(CASE WHEN a.side = 'BUY' THEN 1 ELSE 0 END) as buy_count,
                    SUM(CASE WHEN a.side = 'SELL' THEN 1 ELSE 0 END) as sell_count,
                    m.current_probability,
                    m.volume_24h,
                    m.liquidity
                FROM qd_polymarket_user_activities a
                LEFT JOIN qd_polymarket_markets m ON a.market_id = m.market_id
                GROUP BY a.market_id, m.question, m.category, m.current_probability, m.volume_24h, m.liquidity
                HAVING COUNT(DISTINCT a.user_address) >= 2
                ORDER BY trader_count DESC, activity_count DESC
                LIMIT 15
            """)
            
            rows = cursor.fetchall()
            
            if not rows:
                print("\n  ⚠️  暂无数据")
                return
            
            print(f"\n  找到 {len(rows)} 个热门市场:\n")
            
            for i, row in enumerate(rows, 1):
                question = row['question'] if row['question'] else '未知市场'
                print(f"  [{i}] {question[:60]}")
                print(f"      交易者: {row['trader_count']} 人 | 活动数: {row['activity_count']}")
                print(f"      买入: {row['buy_count']} | 卖出: {row['sell_count']}")
                if row['current_probability']:
                    print(f"      当前概率: {row['current_probability']:.1f}%")
                if row['volume_24h']:
                    print(f"      24h交易量: ${row['volume_24h']:,.0f}")
                print()
    
    except Exception as e:
        print(f"\n  ✗ 查询失败: {e}")


def main():
    print_header("Polymarket 跟单系统 - 数据查询")
    print(f"\n⏰ 查询时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 查询各类数据
    query_top_users()
    query_user_summary()
    query_hot_markets()
    query_recent_activities()
    
    print_header("查询完成")
    print()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n⚠️  用户中断")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ 查询异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
