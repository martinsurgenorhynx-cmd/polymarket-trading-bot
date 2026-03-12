#!/usr/bin/env python
"""
查询Polymarket预测结果（详细版）

显示完整的分析结果，包括推荐的具体含义
"""
import os
import sys
from datetime import datetime, timedelta

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 加载环境变量
from dotenv import load_dotenv
load_dotenv('.env')

from app.utils.db import get_db_connection

def explain_recommendation(recommendation, divergence, ai_prob, market_prob):
    """解释推荐的含义"""
    if recommendation == "YES":
        return f"""
    ✓ 推荐：买入 YES（认为事件会发生）
    理由：AI预测概率({ai_prob:.1f}%) 比市场概率({market_prob:.1f}%) 高 {divergence:.1f}%
    含义：市场低估了事件发生的可能性，存在套利机会
    操作：买入 YES 代币，如果事件发生可获利
"""
    elif recommendation == "NO":
        return f"""
    ✓ 推荐：买入 NO（认为事件不会发生）
    理由：AI预测概率({ai_prob:.1f}%) 比市场概率({market_prob:.1f}%) 低 {abs(divergence):.1f}%
    含义：市场高估了事件发生的可能性，存在套利机会
    操作：买入 NO 代币，如果事件不发生可获利
"""
    else:  # HOLD
        return f"""
    ⊙ 推荐：观望（暂不交易）
    理由：AI预测概率({ai_prob:.1f}%) 与市场概率({market_prob:.1f}%) 差异不大 ({divergence:+.1f}%)
    含义：市场定价相对合理，没有明显套利机会
    操作：暂不交易，继续观察
"""

print("=" * 100)
print("Polymarket AI分析结果查询（详细版）")
print("=" * 100)

print("\n" + "=" * 100)
print("推荐说明")
print("=" * 100)
print("""
Polymarket 是一个预测市场，每个市场有两个选项：YES 和 NO

推荐逻辑：
- YES：AI认为事件会发生，建议买入 YES 代币
- NO：AI认为事件不会发生，建议买入 NO 代币  
- HOLD：AI认为市场定价合理，建议观望

判断标准：
- YES：AI预测概率 > 市场概率 + 5% 且置信度 > 60%
- NO：AI预测概率 < 市场概率 - 5% 且置信度 > 60%
- HOLD：其他情况

示例：
问题："MicroStrategy 会在2025年卖出比特币吗？"
- 推荐 YES = 认为会卖出，买入 YES 代币
- 推荐 NO = 认为不会卖出，买入 NO 代币
""")

try:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # 查询最近的分析结果
        print("\n" + "=" * 100)
        print("最近的分析结果（详细）")
        print("=" * 100)
        
        cursor.execute("""
            SELECT 
                a.market_id,
                a.recommendation,
                a.confidence_score,
                a.opportunity_score,
                a.ai_predicted_probability,
                a.market_probability,
                a.divergence,
                a.reasoning,
                a.created_at,
                m.question,
                m.slug,
                m.category,
                m.end_date_iso,
                m.volume_24h,
                m.liquidity
            FROM qd_polymarket_ai_analysis a
            LEFT JOIN qd_polymarket_markets m ON a.market_id = m.market_id
            WHERE a.created_at > NOW() - INTERVAL '24 hours'
            ORDER BY a.opportunity_score DESC, a.created_at DESC
            LIMIT 10
        """)
        
        results = cursor.fetchall()
        
        if not results:
            print("\n没有找到最近24小时的分析记录")
        else:
            print(f"\n找到 {len(results)} 条记录\n")
            
            for i, row in enumerate(results, 1):
                question = row['question'] if row['question'] else 'N/A'
                slug = row['slug'] if row['slug'] else ''
                url = f"https://polymarket.com/event/{slug}" if slug else 'N/A'
                
                print("=" * 100)
                print(f"[{i}] {question}")
                print("=" * 100)
                
                print(f"\n📊 市场信息:")
                print(f"  Market ID: {row['market_id']}")
                print(f"  URL: {url}")
                print(f"  分类: {row['category'] if row['category'] else 'N/A'}")
                print(f"  结束时间: {row['end_date_iso'] if row['end_date_iso'] else 'N/A'}")
                print(f"  24h交易量: ${row['volume_24h']:,.0f}" if row['volume_24h'] else "  24h交易量: N/A")
                print(f"  流动性: ${row['liquidity']:,.0f}" if row['liquidity'] else "  流动性: N/A")
                
                print(f"\n🤖 AI分析:")
                print(f"  AI预测概率: {row['ai_predicted_probability']:.1f}%")
                print(f"  市场当前概率: {row['market_probability']:.1f}%")
                print(f"  概率差异: {row['divergence']:+.1f}%")
                print(f"  置信度: {row['confidence_score']:.0f}%")
                print(f"  机会评分: {row['opportunity_score']:.0f}/100")
                
                print(f"\n💡 推荐决策: {row['recommendation']}")
                print(explain_recommendation(
                    row['recommendation'],
                    row['divergence'],
                    row['ai_predicted_probability'],
                    row['market_probability']
                ))
                
                if row['reasoning']:
                    print(f"📝 分析理由:")
                    reasoning = row['reasoning']
                    # 分段显示，每行最多80字符
                    lines = reasoning.split('\n')
                    for line in lines:
                        if line.strip():
                            print(f"  {line.strip()}")
                
                print(f"\n⏰ 分析时间: {row['created_at']}")
                print()
        
        # 按推荐类型统计
        print("\n" + "=" * 100)
        print("推荐分布统计")
        print("=" * 100)
        
        cursor.execute("""
            SELECT 
                recommendation,
                COUNT(*) as count,
                ROUND(AVG(confidence_score), 1) as avg_confidence,
                ROUND(AVG(opportunity_score), 1) as avg_opportunity,
                ROUND(AVG(ABS(divergence)), 1) as avg_divergence
            FROM qd_polymarket_ai_analysis
            WHERE created_at > NOW() - INTERVAL '7 days'
            GROUP BY recommendation
            ORDER BY count DESC
        """)
        
        print(f"\n{'推荐':<10} {'数量':<10} {'平均置信度':<15} {'平均机会评分':<15} {'平均差异':<15}")
        print("-" * 100)
        for row in cursor.fetchall():
            rec = row['recommendation'] if row['recommendation'] else 'N/A'
            print(f"{rec:<10} {row['count']:<10} {row['avg_confidence'] if row['avg_confidence'] else 0:<15.1f} {row['avg_opportunity'] if row['avg_opportunity'] else 0:<15.1f} {row['avg_divergence'] if row['avg_divergence'] else 0:<15.1f}%")
        
        cursor.close()
    
    print("\n" + "=" * 100)
    print("查询完成")
    print("=" * 100)
    
except Exception as e:
    print(f"\n✗ 查询失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
