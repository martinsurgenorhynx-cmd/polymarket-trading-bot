#!/usr/bin/env python
"""
检查特定市场的跟单情况
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.utils.db import get_db_connection


def main():
    # 从命令行参数获取 market_id
    if len(sys.argv) < 2:
        print("用法: python check_market_copy_trading.py <market_id>")
        print("示例: python check_market_copy_trading.py 564205")
        sys.exit(1)
    
    market_id = sys.argv[1]
    
    print("=" * 80)
    print(f" 检查市场 {market_id} 的跟单情况")
    print("=" * 80)
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 1. 获取市场信息
            cursor.execute("""
                SELECT market_id, question, condition_id
                FROM qd_polymarket_markets
                WHERE market_id = %s
            """, (market_id,))
            
            market = cursor.fetchone()
            
            if not market:
                print(f"\n✗ 市场 {market_id} 不存在")
                return
            
            question = market['question']
            condition_id = market['condition_id']
            
            print(f"\n市场信息:")
            print(f"  Market ID: {market_id}")
            print(f"  问题: {question}")
            print(f"  Condition ID: {condition_id}")
            
            # 2. 检查是否有用户活动
            if condition_id:
                cursor.execute("""
                    SELECT 
                        a.user_address,
                        a.outcome,
                        a.side,
                        a.timestamp,
                        u.rank
                    FROM qd_polymarket_user_activities a
                    LEFT JOIN qd_polymarket_top_users u ON u.user_address = a.user_address
                        AND DATE(u.created_at) = CURRENT_DATE
                    WHERE a.market_id = %s
                    ORDER BY a.timestamp DESC
                """, (condition_id,))
                
                activities = cursor.fetchall()
                
                if activities:
                    print(f"\n✓ 找到 {len(activities)} 条用户活动:")
                    
                    top_users = [a for a in activities if a['rank'] is not None and a['rank'] <= 20]
                    
                    if top_users:
                        print(f"\n  🎯 顶级用户活动 ({len(top_users)} 条):")
                        for activity in top_users:
                            user = activity['user_address'][:10]
                            rank = activity['rank']
                            outcome = activity['outcome']
                            side = activity['side']
                            timestamp = activity['timestamp']
                            print(f"    排名 #{rank} | {user}... | {side} {outcome} | {timestamp}")
                    else:
                        print(f"\n  ⚠️  没有顶级用户（排名前20）的活动")
                    
                    # 统计方向
                    outcomes = {}
                    for activity in activities:
                        outcome = activity['outcome']
                        outcomes[outcome] = outcomes.get(outcome, 0) + 1
                    
                    print(f"\n  方向统计:")
                    for outcome, count in outcomes.items():
                        print(f"    {outcome}: {count} 条")
                else:
                    print(f"\n✗ 没有用户活动")
            else:
                print(f"\n✗ 市场没有 condition_id，无法查询活动")
            
            # 3. 检查 AI 分析
            cursor.execute("""
                SELECT recommendation, opportunity_score, confidence_score
                FROM qd_polymarket_ai_analysis
                WHERE market_id = %s
                ORDER BY created_at DESC
                LIMIT 1
            """, (market_id,))
            
            ai_analysis = cursor.fetchone()
            
            if ai_analysis:
                print(f"\n✓ AI 分析:")
                print(f"  推荐: {ai_analysis['recommendation']}")
                print(f"  评分: {ai_analysis['opportunity_score']:.0f}/100")
                print(f"  置信度: {ai_analysis['confidence_score']:.0f}%")
            else:
                print(f"\n✗ 没有 AI 分析")
    
    except Exception as e:
        print(f"\n✗ 检查失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
