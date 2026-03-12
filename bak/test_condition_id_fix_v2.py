#!/usr/bin/env python
"""
测试 condition_id 修复 v2
强制从 API 获取新数据
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.data_sources.polymarket import PolymarketDataSource
from app.utils.logger import get_logger

logger = get_logger(__name__)


def main():
    print("=" * 80)
    print(" 测试 condition_id 修复 v2")
    print("=" * 80)
    
    polymarket = PolymarketDataSource()
    
    # 直接调用 _fetch_markets_from_api 绕过缓存
    print("\n[测试1] 从 API 获取市场（绕过缓存）...")
    markets = polymarket._fetch_markets_from_api(category="crypto", limit=5)
    
    if markets:
        print(f"✓ 获取到 {len(markets)} 个市场")
        
        has_condition_id = 0
        missing_condition_id = 0
        
        for i, market in enumerate(markets[:5], 1):
            market_id = market.get('market_id')
            condition_id = market.get('condition_id')
            question = market.get('question', '')[:60]
            
            print(f"\n  [{i}] {question}")
            print(f"      market_id: {market_id}")
            
            if condition_id:
                print(f"      condition_id: {condition_id[:20]}...")
                print(f"      ✓ condition_id 存在")
                has_condition_id += 1
            else:
                print(f"      condition_id: ❌ 缺失")
                print(f"      ✗ condition_id 缺失")
                missing_condition_id += 1
        
        print(f"\n  统计:")
        print(f"    - 有 condition_id: {has_condition_id}/{len(markets[:5])}")
        print(f"    - 缺失 condition_id: {missing_condition_id}/{len(markets[:5])}")
        
        if has_condition_id == 0:
            print(f"\n  ✗ 所有市场都缺失 condition_id，修复失败")
            return
    else:
        print("✗ 未获取到市场")
        return
    
    # 测试2: 保存市场到数据库
    print("\n[测试2] 保存市场到数据库...")
    
    try:
        polymarket._save_markets_to_db(markets[:3])
        print("✓ 市场已保存到数据库")
    except Exception as e:
        print(f"✗ 保存失败: {e}")
        return
    
    # 测试3: 从数据库读取
    print("\n[测试3] 从数据库读取市场...")
    
    from app.utils.db import get_db_connection
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            db_has_condition_id = 0
            db_missing_condition_id = 0
            
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
                    
                    if db_condition_id:
                        print(f"      condition_id: {db_condition_id[:20]}...")
                        print(f"      ✓ condition_id 已保存到数据库")
                        db_has_condition_id += 1
                    else:
                        print(f"      condition_id: ❌ NULL")
                        print(f"      ✗ condition_id 在数据库中为 NULL")
                        db_missing_condition_id += 1
                else:
                    print(f"  ✗ 市场 {market_id} 未找到")
            
            print(f"\n  数据库统计:")
            print(f"    - 有 condition_id: {db_has_condition_id}/3")
            print(f"    - 缺失 condition_id: {db_missing_condition_id}/3")
    
    except Exception as e:
        print(f"✗ 数据库查询失败: {e}")
        return
    
    print("\n" + "=" * 80)
    if has_condition_id > 0 and db_has_condition_id > 0:
        print(" ✓ 测试通过！condition_id 修复成功")
    else:
        print(" ✗ 测试失败！condition_id 仍然缺失")
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
