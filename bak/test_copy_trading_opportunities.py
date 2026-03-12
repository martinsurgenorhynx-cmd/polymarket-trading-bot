#!/usr/bin/env python
"""
测试跟单系统 - 高置信度机会查询
验证"查询6"的功能：高分 AI 推荐 + 顶级用户也在交易的市场
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
    print(" 测试跟单系统 - 高置信度机会查询")
    print("=" * 80)
    
    print("\n[查询6] 高分 AI 推荐 + 顶级用户也在交易的市场\n")
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 执行查询6
            query = """
                WITH top_user_markets AS (
                    -- 获取顶级用户最近24小时交易的市场
                    SELECT DISTINCT
                        m.market_id,
                        COUNT(DISTINCT a.user_address) as top_users_count,
                        STRING_AGG(DISTINCT u.rank::text, ', ' ORDER BY u.rank::text) as user_ranks,
                        STRING_AGG(DISTINCT a.outcome, ', ') as user_outcomes
                    FROM qd_polymarket_user_activities a
                    JOIN qd_polymarket_markets m ON m.condition_id = a.market_id
                    LEFT JOIN qd_polymarket_top_users u ON u.user_address = a.user_address
                        AND DATE(u.created_at) = CURRENT_DATE
                        AND u.rank <= 20
                    WHERE a.timestamp > NOW() - INTERVAL '24 hours'
                    GROUP BY m.market_id
                    HAVING COUNT(DISTINCT a.user_address) > 0
                )
                SELECT 
                    m.market_id,
                    m.question,
                    ai.recommendation,
                    ai.opportunity_score,
                    ai.confidence_score,
                    tum.top_users_count,
                    tum.user_ranks,
                    tum.user_outcomes,
                    ai.reasoning
                FROM qd_polymarket_ai_analysis ai
                JOIN qd_polymarket_markets m ON m.market_id = ai.market_id
                JOIN top_user_markets tum ON tum.market_id = ai.market_id
                WHERE ai.recommendation IN ('YES', 'NO')
                    AND ai.opportunity_score >= 70
                    AND ai.created_at > NOW() - INTERVAL '24 hours'
                ORDER BY tum.top_users_count DESC, ai.opportunity_score DESC
                LIMIT 10;
            """
            
            cursor.execute(query)
            results = cursor.fetchall()
            
            if not results:
                print("❌ 未找到符合条件的机会")
                print("\n可能原因:")
                print("  1. 数据库中没有 AI 分析数据（运行 run_once_polymarket_worker.py）")
                print("  2. 数据库中没有跟单活动数据（运行 run_once_copy_trading.py）")
                print("  3. 没有顶级用户在最近24小时交易过高分市场")
                return
            
            print(f"✓ 找到 {len(results)} 个高置信度机会\n")
            
            for i, row in enumerate(results, 1):
                market_id = row['market_id']
                question = row['question']
                recommendation = row['recommendation']
                opportunity_score = row['opportunity_score']
                confidence_score = row['confidence_score']
                top_users_count = row['top_users_count']
                user_ranks = row['user_ranks']
                user_outcomes = row['user_outcomes']
                reasoning = row['reasoning']
                
                print(f"[{i}] {question[:70]}")
                print(f"    Market ID: {market_id}")
                print(f"    AI 推荐: {recommendation}")
                print(f"    AI 评分: {opportunity_score:.0f}/100")
                print(f"    AI 置信度: {confidence_score:.0f}%")
                print(f"    🎯 顶级用户: {top_users_count} 人交易")
                print(f"       排名: {user_ranks}")
                print(f"       方向: {user_outcomes}")
                
                # 显示 AI 理由预览
                if reasoning:
                    reasoning_preview = reasoning[:100] + "..." if len(reasoning) > 100 else reasoning
                    print(f"    AI 理由: {reasoning_preview}")
                
                print()
            
            # 统计信息
            print("=" * 80)
            print("统计信息:")
            print(f"  总机会数: {len(results)}")
            
            # 按顶级用户数量分组
            user_count_groups = {}
            for row in results:
                count = row['top_users_count']
                user_count_groups[count] = user_count_groups.get(count, 0) + 1
            
            print(f"\n  按顶级用户数量分组:")
            for count in sorted(user_count_groups.keys(), reverse=True):
                print(f"    {count} 人交易: {user_count_groups[count]} 个市场")
            
            # 按 AI 推荐分组
            recommendation_groups = {}
            for row in results:
                rec = row['recommendation']
                recommendation_groups[rec] = recommendation_groups.get(rec, 0) + 1
            
            print(f"\n  按 AI 推荐分组:")
            for rec, count in recommendation_groups.items():
                print(f"    {rec}: {count} 个市场")
            
            print("=" * 80)
            
            print("\n💡 使用建议:")
            print("  1. 这些市场同时满足:")
            print("     - AI 评分 ≥ 70")
            print("     - 有顶级用户（排名前20）在交易")
            print("     - AI 分析在24小时内")
            print("  2. 顶级用户越多，置信度越高")
            print("  3. 如果 AI 推荐方向与顶级用户一致，更值得关注")
            print("  4. 使用 trade_best_opportunity.py 自动交易这些机会")
    
    except Exception as e:
        print(f"✗ 查询失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
