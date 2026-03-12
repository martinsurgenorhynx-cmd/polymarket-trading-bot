#!/usr/bin/env python
"""
增强已有 AI 分析的市场的交易数据
"""
import os
import sys

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

from app.utils.db import get_db_connection
from app.services.polymarket_worker import PolymarketWorker
from app.data_sources.polymarket import PolymarketDataSource


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='增强已有 AI 分析的市场的交易数据')
    parser.add_argument('--limit', type=int, default=20, help='最多增强的市场数量（默认20）')
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("增强已有 AI 分析的市场")
    print("=" * 80)
    
    # 查找有 AI 分析但缺少交易数据的市场
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT DISTINCT 
                m.market_id, 
                m.question, 
                m.category,
                m.volume_24h,
                m.liquidity,
                a.opportunity_score
            FROM qd_polymarket_ai_analysis a
            INNER JOIN qd_polymarket_markets m ON a.market_id = m.market_id
            WHERE a.opportunity_score > 60
              AND m.condition_id IS NULL
              AND m.status = 'active'
              AND m.volume_24h > 1000
            ORDER BY a.opportunity_score DESC, m.volume_24h DESC
            LIMIT %s
        """, (args.limit,))
        
        markets = cursor.fetchall()
        
        if not markets:
            print("\n✓ 所有有 AI 分析的市场都已有交易数据")
            return
        
        print(f"\n找到 {len(markets)} 个需要增强的市场:\n")
        
        for i, market in enumerate(markets, 1):
            print(f"[{i}] {market['question'][:60]}")
            print(f"    评分: {market['opportunity_score']:.0f} | 交易量: ${market['volume_24h']:,.0f}")
            print()
    
    # 转换为字典列表
    markets_list = [dict(m) for m in markets]
    
    # 增强数据
    print("=" * 80)
    print("开始增强交易数据...")
    print("=" * 80)
    print()
    
    worker = PolymarketWorker()
    enriched_count = worker._enrich_markets_with_trading_data(markets_list)
    
    print(f"\n✓ 成功增强 {enriched_count}/{len(markets_list)} 个市场")
    
    # 保存到数据库
    if enriched_count > 0:
        print("\n保存到数据库...")
        
        data_source = PolymarketDataSource()
        data_source._save_markets_to_db(markets_list)
        
        print("✓ 保存完成")
        
        # 统计
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM qd_polymarket_ai_analysis a
                INNER JOIN qd_polymarket_markets m ON a.market_id = m.market_id
                WHERE a.opportunity_score BETWEEN 60 AND 85
                  AND m.liquidity > 10000
                  AND m.volume_24h > 1000
                  AND m.status = 'active'
                  AND (m.end_date_iso IS NULL OR m.end_date_iso > NOW())
                  AND m.accepting_orders = true
                  AND m.condition_id IS NOT NULL
                  AND m.yes_token_id IS NOT NULL
                  AND m.no_token_id IS NOT NULL
            """)
            
            result = cursor.fetchone()
            count = result['count']
            
            print(f"\n📊 现在有 {count} 个完全可交易的机会（有 AI 分析 + 交易数据）")
            
            if count > 0:
                print("\n💡 可以运行 trade_best_opportunity.py 进行交易了！")


if __name__ == '__main__':
    try:
        main()
        
        print("\n" + "=" * 80)
        print("完成")
        print("=" * 80)
        
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ 失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
