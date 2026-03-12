#!/usr/bin/env python
"""
查询 Polymarket 系列市场

显示同一主题的多个时间期限市场
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv('.env')

from app.utils.db import get_db_connection

print("=" * 100)
print("Polymarket 系列市场查询")
print("=" * 100)

print("\n" + "=" * 100)
print("MicroStrategy 卖出比特币 - 系列市场")
print("=" * 100)

try:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # 查询所有 MicroStrategy 相关市场
        cursor.execute("""
            SELECT 
                m.market_id,
                m.question,
                m.current_probability,
                m.volume_24h,
                m.liquidity,
                m.end_date_iso,
                a.recommendation,
                a.confidence_score,
                a.opportunity_score,
                a.ai_predicted_probability,
                a.divergence,
                a.reasoning,
                a.created_at as analysis_time
            FROM qd_polymarket_markets m
            LEFT JOIN LATERAL (
                SELECT *
                FROM qd_polymarket_ai_analysis
                WHERE market_id = m.market_id
                ORDER BY created_at DESC
                LIMIT 1
            ) a ON true
            WHERE m.question LIKE '%MicroStrategy%Bitcoin%'
            ORDER BY m.end_date_iso, m.current_probability
        """)
        
        results = cursor.fetchall()
        
        if not results:
            print("\n没有找到相关市场")
        else:
            print(f"\n找到 {len(results)} 个相关市场\n")
            
            print("=" * 100)
            print("市场概览")
            print("=" * 100)
            print(f"\n{'期限':<20} {'Market ID':<10} {'市场概率':<12} {'YES价格':<12} {'NO价格':<12} {'AI推荐':<10}")
            print("-" * 100)
            
            for row in results:
                end_date = row['end_date_iso']
                if end_date:
                    end_date_str = end_date.strftime('%Y-%m-%d')
                else:
                    end_date_str = 'N/A'
                
                market_prob = row['current_probability'] if row['current_probability'] else 0
                yes_price = f"{market_prob:.1f}¢"
                no_price = f"{100 - market_prob:.1f}¢"
                
                recommendation = row['recommendation'] if row['recommendation'] else 'N/A'
                
                print(f"{end_date_str:<20} {row['market_id']:<10} {market_prob:<12.1f}% {yes_price:<12} {no_price:<12} {recommendation:<10}")
            
            print("\n" + "=" * 100)
            print("详细分析")
            print("=" * 100)
            
            for i, row in enumerate(results, 1):
                question = row['question']
                end_date = row['end_date_iso']
                if end_date:
                    end_date_str = end_date.strftime('%Y年%m月%d日')
                else:
                    end_date_str = 'N/A'
                
                market_prob = row['current_probability'] if row['current_probability'] else 0
                yes_price = market_prob
                no_price = 100 - market_prob
                
                print(f"\n{'=' * 100}")
                print(f"[{i}] {question}")
                print(f"期限：{end_date_str}")
                print(f"{'=' * 100}")
                
                print(f"\n📊 市场信息:")
                print(f"  Market ID: {row['market_id']}")
                print(f"  市场概率: {market_prob:.1f}%")
                print(f"  YES 代币价格: {yes_price:.1f}¢")
                print(f"  NO 代币价格: {no_price:.1f}¢")
                
                if row['volume_24h']:
                    print(f"  24h交易量: ${row['volume_24h']:,.0f}")
                if row['liquidity']:
                    print(f"  流动性: ${row['liquidity']:,.0f}")
                
                if row['recommendation']:
                    ai_prob = row['ai_predicted_probability'] if row['ai_predicted_probability'] else 0
                    divergence = row['divergence'] if row['divergence'] else 0
                    
                    print(f"\n🤖 AI分析:")
                    print(f"  AI预测概率: {ai_prob:.1f}%")
                    print(f"  市场概率: {market_prob:.1f}%")
                    print(f"  概率差异: {divergence:+.1f}%")
                    print(f"  置信度: {row['confidence_score']:.0f}%")
                    print(f"  机会评分: {row['opportunity_score']:.0f}/100")
                    
                    print(f"\n💡 推荐决策: {row['recommendation']}")
                    
                    if row['recommendation'] == 'YES':
                        print(f"""
    ✓ 推荐：买入 YES 代币（{yes_price:.1f}¢）
    含义：认为 MicroStrategy 会在 {end_date_str} 前卖出比特币
    理由：AI预测概率({ai_prob:.1f}%) 比市场概率({market_prob:.1f}%) 高 {divergence:.1f}%
    操作：买入 YES 代币，如果在期限前卖出，你将获利""")
                    elif row['recommendation'] == 'NO':
                        print(f"""
    ✓ 推荐：买入 NO 代币（{no_price:.1f}¢）
    含义：认为 MicroStrategy 不会在 {end_date_str} 前卖出比特币
    理由：AI预测概率({ai_prob:.1f}%) 比市场概率({market_prob:.1f}%) 低 {abs(divergence):.1f}%
    操作：买入 NO 代币，如果在期限前没有卖出，你将获利""")
                    else:
                        print(f"""
    ⊙ 推荐：观望
    理由：AI预测概率({ai_prob:.1f}%) 与市场概率({market_prob:.1f}%) 差异不大
    操作：暂不交易，继续观察""")
                    
                    if row['reasoning']:
                        print(f"\n📝 分析理由:")
                        reasoning = row['reasoning']
                        # 分段显示
                        lines = reasoning.split('\n')
                        for line in lines:
                            if line.strip():
                                print(f"  {line.strip()}")
                    
                    if row['analysis_time']:
                        print(f"\n⏰ 分析时间: {row['analysis_time']}")
                else:
                    print(f"\n⚠️  暂无 AI 分析")
            
            # 总结
            print("\n" + "=" * 100)
            print("投资建议总结")
            print("=" * 100)
            
            print("""
这是一个多结果市场，有多个不同期限的选项。每个选项是独立的市场：

1. 如果你认为 MicroStrategy 不会在某个期限前卖出比特币：
   → 买入该期限的 NO 代币
   → 期限越短，NO 代币价格越高（风险越低）
   → 期限越长，NO 代币价格越低（风险越高）

2. 如果你认为 MicroStrategy 会在某个期限前卖出比特币：
   → 买入该期限的 YES 代币
   → 期限越长，YES 代币价格越高（概率越大）

3. 风险提示：
   - 只要在任何一个期限前卖出，所有 YES 代币都会获利
   - 只有在所有期限都没有卖出，NO 代币才会获利
   - 建议根据自己的风险偏好选择合适的期限

4. 当前 AI 推荐：
   - 所有期限都推荐买入 NO 代币
   - 认为 MicroStrategy 在2026年底前都不会卖出比特币
   - 最安全的选择：买入 2025年12月31日的 NO 代币（99¢，风险最低）
""")
        
        cursor.close()
    
    print("\n" + "=" * 100)
    print("查询完成")
    print("=" * 100)
    
except Exception as e:
    print(f"\n✗ 查询失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
