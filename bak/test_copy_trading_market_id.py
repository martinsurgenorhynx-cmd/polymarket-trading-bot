#!/usr/bin/env python
"""
测试跟单系统 market_id 关联
验证活动保存时能否正确使用数字 market_id
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.data_sources.polymarket import PolymarketDataSource
from app.utils.db import get_db_connection
from app.utils.logger import get_logger

logger = get_logger(__name__)


def main():
    print("=" * 80)
    print(" 测试跟单系统 market_id 关联")
    print("=" * 80)
    
    polymarket = PolymarketDataSource()
    
    # 步骤1: 获取一个用户的活动
    print("\n[步骤1] 获取用户活动...")
    
    # 使用一个已知的活跃用户地址（从排行榜获取）
    test_user = "0x0000000000000000000000000000000000000000"  # 占位符
    
    # 先获取排行榜用户
    users = polymarket.get_leaderboard(period='day', limit=1)
    
    if not users:
        print("✗ 未获取到排行榜用户")
        return
    
    test_user = users[0].get('user')
    print(f"✓ 使用用户: {test_user[:10]}...")
    
    # 获取用户活动
    activities = polymarket.get_user_activities(test_user, limit=3)
    
    if not activities:
        print("✗ 未获取到用户活动")
        return
    
    print(f"✓ 获取到 {len(activities)} 条活动")
    
    # 显示活动的 conditionId
    for i, activity in enumerate(activities, 1):
        condition_id = activity.get('conditionId')
        slug = activity.get('slug')
        print(f"\n  [{i}] conditionId: {condition_id[:20] if condition_id else 'None'}...")
        print(f"      slug: {slug}")
    
    # 步骤2: 查询这些 condition_id 对应的数字 market_id
    print("\n[步骤2] 查询 condition_id 对应的数字 market_id...")
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 收集所有 condition_id
            condition_ids = [a.get('conditionId') for a in activities if a.get('conditionId')]
            
            if not condition_ids:
                print("✗ 活动中没有 condition_id")
                return
            
            # 批量查询
            cursor.execute("""
                SELECT market_id, condition_id, question
                FROM qd_polymarket_markets
                WHERE condition_id = ANY(%s)
            """, (condition_ids,))
            
            rows = cursor.fetchall()
            
            print(f"✓ 在数据库中找到 {len(rows)} 个匹配的市场")
            
            if len(rows) == 0:
                print("\n⚠️  数据库中没有这些 condition_id 对应的市场")
                print("   需要先运行 Polymarket Worker 更新市场数据")
                
                # 尝试从 API 获取
                print("\n[步骤3] 从 API 获取市场数据...")
                
                for condition_id in condition_ids[:2]:  # 只测试前2个
                    print(f"\n  获取 condition_id: {condition_id[:20]}...")
                    
                    market = polymarket.get_market_by_condition_id(condition_id)
                    
                    if market:
                        market_id = market.get('market_id')
                        question = market.get('question', '')[:60]
                        print(f"  ✓ 找到市场: {question}")
                        print(f"    market_id: {market_id}")
                        print(f"    condition_id: {condition_id[:20]}...")
                    else:
                        print(f"  ✗ 未找到市场")
                
                return
            
            # 显示匹配结果
            for row in rows:
                market_id = row['market_id']
                condition_id = row['condition_id']
                question = row['question'][:60]
                
                print(f"\n  ✓ {question}")
                print(f"    market_id: {market_id} (数字)")
                print(f"    condition_id: {condition_id[:20]}... (十六进制)")
    
    except Exception as e:
        print(f"✗ 查询失败: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print("\n" + "=" * 80)
    print(" 测试完成")
    print("=" * 80)
    print("\n💡 结论:")
    print("   - 如果数据库中有匹配的市场，说明 condition_id 已正确保存")
    print("   - 跟单活动可以通过 condition_id 关联到数字 market_id")
    print("   - AI 分析结果可以通过数字 market_id 关联到跟单活动")


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
