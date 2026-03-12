#!/usr/bin/env python
"""
修复缺失的市场数据
从 API 获取用户活动中引用但数据库中不存在的市场
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
    print(" 修复缺失的市场数据")
    print("=" * 80)
    
    polymarket = PolymarketDataSource()
    
    # 1. 找出所有无法关联的活动
    print("\n[1] 查找无法关联的活动...")
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 查找无法关联到市场的活动
            cursor.execute("""
                SELECT DISTINCT a.market_id as condition_id
                FROM qd_polymarket_user_activities a
                LEFT JOIN qd_polymarket_markets m ON m.condition_id = a.market_id
                WHERE m.market_id IS NULL
            """)
            
            missing_condition_ids = [row['condition_id'] for row in cursor.fetchall()]
            
            if not missing_condition_ids:
                print("  ✓ 所有活动都能关联到市场")
                return
            
            print(f"  ✓ 找到 {len(missing_condition_ids)} 个缺失的市场")
    
    except Exception as e:
        print(f"  ✗ 查询失败: {e}")
        return
    
    # 2. 从 API 获取缺失的市场
    print(f"\n[2] 从 API 获取缺失的市场...")
    
    fetched_count = 0
    failed_count = 0
    
    for i, condition_id in enumerate(missing_condition_ids, 1):
        print(f"\n  [{i}/{len(missing_condition_ids)}] {condition_id[:20]}...")
        
        try:
            market = polymarket.get_market_by_condition_id(condition_id)
            
            if market:
                market_id = market.get('market_id')
                question = market.get('question', '')[:60]
                print(f"    ✓ 找到市场: {market_id} - {question}")
                fetched_count += 1
            else:
                print(f"    ✗ API 中未找到此市场（可能已关闭或结算）")
                failed_count += 1
        
        except Exception as e:
            print(f"    ✗ 获取失败: {e}")
            failed_count += 1
            continue
    
    # 3. 统计
    print("\n" + "=" * 80)
    print("修复统计:")
    print(f"  缺失市场数: {len(missing_condition_ids)}")
    print(f"  成功获取: {fetched_count}")
    print(f"  获取失败: {failed_count}")
    print("=" * 80)
    
    if fetched_count > 0:
        print(f"\n✅ 成功获取 {fetched_count} 个市场数据")
        print(f"   现在可以重新运行 trade_best_opportunity.py 查看跟单信号")
    
    if failed_count > 0:
        print(f"\n⚠️  {failed_count} 个市场无法获取（可能已关闭或结算）")
        print(f"   这些活动将无法关联到 AI 分析")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ 修复失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
