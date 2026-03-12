#!/usr/bin/env python
"""
批量增强所有市场数据
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

from app.utils.db import get_db_connection
from app.services.polymarket_worker import PolymarketWorker
from app.data_sources.polymarket import PolymarketDataSource


print("=" * 80)
print("批量增强所有 Polymarket 市场数据")
print("=" * 80)

# 获取需要增强的总数
with get_db_connection() as conn:
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COUNT(*) as total
        FROM qd_polymarket_ai_analysis a
        INNER JOIN qd_polymarket_markets m ON a.market_id = m.market_id
        WHERE a.opportunity_score > 60
          AND m.condition_id IS NULL
          AND m.status = 'active'
          AND m.volume_24h > 1000
    """)
    total_need = cursor.fetchone()['total']

print(f"\n需要增强的市场总数: {total_need}")

if total_need == 0:
    print("\n✓ 所有市场都已有交易数据！")
    sys.exit(0)

batch_size = 20
total_enriched = 0
batch_num = 0

print(f"批次大小: {batch_size}")
print(f"预计批次: {(total_need + batch_size - 1) // batch_size}")
print("\n开始增强...\n")

worker = PolymarketWorker()
data_source = PolymarketDataSource()

while True:
    batch_num += 1
    
    # 获取一批市场
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT 
                m.market_id, 
                m.question, 
                m.category,
                m.volume_24h,
                m.liquidity
            FROM qd_polymarket_ai_analysis a
            INNER JOIN qd_polymarket_markets m ON a.market_id = m.market_id
            WHERE a.opportunity_score > 60
              AND m.condition_id IS NULL
              AND m.status = 'active'
              AND m.volume_24h > 1000
            ORDER BY m.volume_24h DESC
            LIMIT %s
        """, (batch_size,))
        
        markets = cursor.fetchall()
    
    if not markets:
        break
    
    markets_list = [dict(m) for m in markets]
    
    print(f"[批次 {batch_num}] 增强 {len(markets_list)} 个市场...")
    
    # 增强
    enriched = worker._enrich_markets_with_trading_data(markets_list)
    
    # 保存
    if enriched > 0:
        data_source._save_markets_to_db(markets_list)
    
    total_enriched += enriched
    remaining = total_need - total_enriched
    
    print(f"  成功: {enriched}/{len(markets_list)} | 总计: {total_enriched}/{total_need} | 剩余: {remaining}")
    
    if remaining <= 0:
        break
    
    time.sleep(1)

print("\n" + "=" * 80)
print(f"完成！共增强 {total_enriched} 个市场")
print("=" * 80)
