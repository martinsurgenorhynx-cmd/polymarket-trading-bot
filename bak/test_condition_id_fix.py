#!/usr/bin/env python
"""
测试 condition_id 修复
验证从 API 获取的市场数据是否包含 condition_id
"""
import os
import sys

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.data_sources.polymarket import PolymarketDataSource
from app.utils.logger import get_logger

logger = get_logger(__name__)


def main():
    print("=" * 80)
    print(" 测试 condition_id 修复")
    print("=" * 80)
    
    polymarket = PolymarketDataSource()
    
    # 测试1: 获取热门市场，检查是否包含 condition_id
    print("\n[测试1] 获取热门市场...")
    markets = polymarket.get_trending_markets(category="crypto", limit=5)
    
    if markets:
        print(f"✓ 获取到 {len(markets)} 个市场")
        
        for i, market in enumerate(markets[:3], 1):
            market_id = market.get('market_id')
            condition_id = market.get('condition_id')
            question = market.get('question', '')[:60]
            
            print(f"\n  [{i}] {question}")
            print(f"      market_id: {market_id}")
            print(f"      condition_id: {condition_id if condition_id else '❌ 缺失'}")
            
            if condition_id:
                print(f"      ✓ condition_id 存在")
            else:
                print(f"      ✗ condition_id 缺失（需要修复）")
    else:
        print("✗ 未获取到市场")
        return
    
    # 测试2: 保存市场到数据库，验证 condition_id 是否被保存
    print("\n[测试2] 保存市场到数据库...")
    
    try:
        polymarket._save_markets_to_db(markets[:3])
        print("✓ 市场已保存到数据库")
    except Exception as e:
        print(f"✗ 保存失败: {e}")
        return
    
    # 测试3: 从数据库读取，验证 condition_id 是否存在
    print("\n[测试3] 从数据库读取市场...")
    
    from app.utils.db import get_db_connection
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            for market in markets[:3]:
                market_id = market.get('market_id')
                
                cursor.execute("""
                    SELECT market_id, condition_id, question
                    FROM qd_polymarket_markets
                    WHERE market_id = %s
                """, (market_id,))
                
                row = cursor.fetchone()
                
                if row:
                    db_market_id = row['market_id']
                    db_condition_id = row['condition_id']
                    db_question = row['question'][:60]
                    
                    print(f"\n  ✓ {db_question}")
                    print(f"      market_id: {db_market_id}")
                    print(f"      condition_id: {db_condition_id if db_condition_id else '❌ NULL'}")
                    
                    if db_condition_id:
                        print(f"      ✓ condition_id 已保存到数据库")
                    else:
                        print(f"      ✗ condition_id 在数据库中为 NULL")
                else:
                    print(f"  ✗ 市场 {market_id} 未找到")
    
    except Exception as e:
        print(f"✗ 数据库查询失败: {e}")
        return
    
    print("\n" + "=" * 80)
    print(" 测试完成")
    print("=" * 80)


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
