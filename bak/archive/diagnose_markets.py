#!/usr/bin/env python
"""
诊断市场数据，找出限制因素
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

from app.utils.db import get_db_connection

print("=" * 80)
print("Polymarket 市场诊断")
print("=" * 80)

with get_db_connection() as conn:
    cursor = conn.cursor()
    
    # 总体统计
    cursor.execute("""
        SELECT 
            COUNT(*) as total_with_ai,
            COUNT(*) FILTER (WHERE m.condition_id IS NOT NULL) as has_trading_data,
            COUNT(*) FILTER (WHERE m.condition_id IS NOT NULL AND m.accepting_orders = true) as accepting_orders,
            COUNT(*) FILTER (WHERE m.condition_id IS NOT NULL AND m.accepting_orders = false) as not_accepting
        FROM qd_polymarket_ai_analysis a
        INNER JOIN qd_polymarket_markets m ON a.market_id = m.market_id
        WHERE a.opportunity_score BETWEEN 60 AND 85
          AND m.liquidity > 10000
          AND m.volume_24h > 1000
          AND m.status = 'active'
    """)
    
    stats = cursor.fetchone()
    
    print(f"\n📊 市场统计:")
    print(f"  有 AI 分析的市场: {stats['total_with_ai']}")
    print(f"  有交易数据 (condition_id): {stats['has_trading_data']}")
    print(f"  接受订单: {stats['accepting_orders']}")
    print(f"  不接受订单: {stats['not_accepting']}")
    
    # 需要增强的市场
    cursor.execute("""
        SELECT COUNT(*) as need_enrich
        FROM qd_polymarket_ai_analysis a
        INNER JOIN qd_polymarket_markets m ON a.market_id = m.market_id
        WHERE a.opportunity_score BETWEEN 60 AND 85
          AND m.liquidity > 10000
          AND m.volume_24h > 1000
          AND m.status = 'active'
          AND m.condition_id IS NULL
    """)
    
    need_enrich = cursor.fetchone()['need_enrich']
    
    print(f"\n💡 建议:")
    if need_enrich > 0:
        print(f"  - 还有 {need_enrich} 个市场需要增强交易数据")
        print(f"    运行: python enrich_analyzed_markets.py")
    
    if stats['not_accepting'] > 0:
        print(f"  - {stats['not_accepting']} 个市场不接受订单（可能已关闭）")
        print(f"    这些市场无法交易")
    
    if stats['accepting_orders'] == 0:
        print(f"  - 当前没有可交易的市场")
        print(f"    需要增强更多市场数据或等待市场重新开放")

print("\n" + "=" * 80)
