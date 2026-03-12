#!/usr/bin/env python
"""
诊断跟单系统数据
检查数据库中的跟单数据和关联情况
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.utils.db import get_db_connection
from app.utils.logger import get_logger

logger = get_logger(__name__)


def main():
    print("=" * 80)
    print(" 诊断跟单系统数据")
    print("=" * 80)
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 1. 检查排行榜用户数据
            print("\n[1] 检查排行榜用户数据...")
            cursor.execute("""
                SELECT COUNT(*) as total,
                       COUNT(DISTINCT user_address) as unique_users,
                       MAX(created_at) as latest_update
                FROM qd_polymarket_top_users
            """)
            row = cursor.fetchone()
            
            if row['total'] > 0:
                print(f"  ✓ 找到 {row['total']} 条记录")
                print(f"  ✓ {row['unique_users']} 个唯一用户")
                print(f"  ✓ 最新更新: {row['latest_update']}")
            else:
                print(f"  ✗ 没有排行榜用户数据")
                print(f"  💡 运行: python polymarket/run_once_copy_trading.py")
                return
            
            # 2. 检查用户活动数据
            print("\n[2] 检查用户活动数据...")
            cursor.execute("""
                SELECT COUNT(*) as total,
                       COUNT(DISTINCT user_address) as unique_users,
                       COUNT(DISTINCT market_id) as unique_markets,
                       MAX(timestamp) as latest_activity
                FROM qd_polymarket_user_activities
            """)
            row = cursor.fetchone()
            
            if row['total'] > 0:
                print(f"  ✓ 找到 {row['total']} 条活动记录")
                print(f"  ✓ {row['unique_users']} 个唯一用户")
                print(f"  ✓ {row['unique_markets']} 个唯一市场")
                print(f"  ✓ 最新活动: {row['latest_activity']}")
            else:
                print(f"  ✗ 没有用户活动数据")
                print(f"  💡 运行: python polymarket/run_once_copy_trading.py")
                return
            
            # 3. 检查市场表的 condition_id 填充情况
            print("\n[3] 检查市场表 condition_id 填充情况...")
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_markets,
                    COUNT(condition_id) as markets_with_condition_id,
                    COUNT(*) - COUNT(condition_id) as markets_without_condition_id
                FROM qd_polymarket_markets
            """)
            row = cursor.fetchone()
            
            print(f"  总市场数: {row['total_markets']}")
            print(f"  有 condition_id: {row['markets_with_condition_id']}")
            print(f"  缺 condition_id: {row['markets_without_condition_id']}")
            
            if row['markets_without_condition_id'] > 0:
                print(f"  ⚠️  部分市场缺少 condition_id")
                print(f"  💡 运行: python polymarket/run_once_polymarket_worker.py")
            
            # 4. 检查活动能否关联到市场
            print("\n[4] 检查活动能否关联到市场...")
            cursor.execute("""
                SELECT 
                    COUNT(DISTINCT a.activity_id) as total_activities,
                    COUNT(DISTINCT CASE WHEN m.market_id IS NOT NULL THEN a.activity_id END) as activities_with_market
                FROM qd_polymarket_user_activities a
                LEFT JOIN qd_polymarket_markets m ON m.condition_id = a.market_id
            """)
            row = cursor.fetchone()
            
            total = row['total_activities']
            matched = row['activities_with_market']
            
            print(f"  总活动数: {total}")
            print(f"  能关联到市场: {matched}")
            print(f"  无法关联: {total - matched}")
            
            if matched < total:
                print(f"  ⚠️  部分活动无法关联到市场（可能是 condition_id 不匹配）")
            
            # 5. 检查 AI 分析数据
            print("\n[5] 检查 AI 分析数据...")
            cursor.execute("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(DISTINCT market_id) as unique_markets,
                    MAX(created_at) as latest_analysis
                FROM qd_polymarket_ai_analysis
                WHERE created_at > NOW() - INTERVAL '24 hours'
            """)
            row = cursor.fetchone()
            
            if row['total'] > 0:
                print(f"  ✓ 找到 {row['total']} 条 AI 分析（24小时内）")
                print(f"  ✓ {row['unique_markets']} 个唯一市场")
                print(f"  ✓ 最新分析: {row['latest_analysis']}")
            else:
                print(f"  ✗ 没有最近的 AI 分析数据")
                print(f"  💡 运行: python polymarket/run_once_polymarket_worker.py")
            
            # 6. 检查高置信度机会（有跟单 + AI 推荐）
            print("\n[6] 检查高置信度机会（有跟单 + AI 推荐）...")
            cursor.execute("""
                WITH top_user_markets AS (
                    SELECT DISTINCT
                        m.market_id,
                        COUNT(DISTINCT a.user_address) as top_users_count
                    FROM qd_polymarket_user_activities a
                    JOIN qd_polymarket_markets m ON m.condition_id = a.market_id
                    LEFT JOIN qd_polymarket_top_users u ON u.user_address = a.user_address
                        AND DATE(u.created_at) = CURRENT_DATE
                        AND u.rank <= 20
                    WHERE a.timestamp > NOW() - INTERVAL '24 hours'
                    GROUP BY m.market_id
                    HAVING COUNT(DISTINCT a.user_address) > 0
                )
                SELECT COUNT(*) as count
                FROM qd_polymarket_ai_analysis ai
                JOIN qd_polymarket_markets m ON m.market_id = ai.market_id
                JOIN top_user_markets tum ON tum.market_id = ai.market_id
                WHERE ai.recommendation IN ('YES', 'NO')
                    AND ai.opportunity_score >= 70
                    AND ai.created_at > NOW() - INTERVAL '24 hours'
            """)
            row = cursor.fetchone()
            
            count = row['count']
            
            if count > 0:
                print(f"  ✓ 找到 {count} 个高置信度机会")
            else:
                print(f"  ✗ 没有找到高置信度机会")
                print(f"\n  可能原因:")
                print(f"    1. 顶级用户最近24小时没有交易高分市场")
                print(f"    2. AI 分析的市场与用户交易的市场不重叠")
                print(f"    3. condition_id 关联失败")
            
            # 7. 显示一些示例数据
            print("\n[7] 示例数据...")
            
            # 显示最近的用户活动
            cursor.execute("""
                SELECT 
                    a.user_address,
                    a.market_id as condition_id,
                    a.outcome,
                    a.timestamp,
                    m.market_id as numeric_market_id,
                    m.question
                FROM qd_polymarket_user_activities a
                LEFT JOIN qd_polymarket_markets m ON m.condition_id = a.market_id
                ORDER BY a.timestamp DESC
                LIMIT 3
            """)
            
            print(f"\n  最近3条用户活动:")
            for row in cursor.fetchall():
                user = row['user_address'][:10]
                condition_id = row['condition_id'][:20] if row['condition_id'] else 'None'
                numeric_id = row['numeric_market_id']
                question = row['question'][:50] if row['question'] else 'N/A'
                outcome = row['outcome']
                
                print(f"    用户: {user}... | 方向: {outcome}")
                print(f"    condition_id: {condition_id}...")
                print(f"    numeric_id: {numeric_id} | 问题: {question}")
                print()
            
            # 显示高分 AI 分析
            cursor.execute("""
                SELECT 
                    ai.market_id,
                    m.question,
                    ai.recommendation,
                    ai.opportunity_score,
                    m.condition_id
                FROM qd_polymarket_ai_analysis ai
                JOIN qd_polymarket_markets m ON m.market_id = ai.market_id
                WHERE ai.opportunity_score >= 70
                    AND ai.created_at > NOW() - INTERVAL '24 hours'
                ORDER BY ai.opportunity_score DESC
                LIMIT 3
            """)
            
            print(f"  高分 AI 分析（前3个）:")
            for row in cursor.fetchall():
                market_id = row['market_id']
                question = row['question'][:50] if row['question'] else 'N/A'
                recommendation = row['recommendation']
                score = row['opportunity_score']
                condition_id = row['condition_id'][:20] if row['condition_id'] else 'None'
                
                print(f"    市场: {market_id} | 评分: {score:.0f}")
                print(f"    推荐: {recommendation} | 问题: {question}")
                print(f"    condition_id: {condition_id}...")
                print()
    
    except Exception as e:
        print(f"✗ 诊断失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ 诊断失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
