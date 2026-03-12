#!/usr/bin/env python
"""
快速可交易机会分析

直接使用已验证的可交易市场（价格 0.10-0.90）
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.utils.db import get_db_connection
from app.services.llm import LLMService


def get_tradeable_opportunities():
    """从数据库获取可能可交易的机会（基于历史数据）"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # 选择评分适中的市场（60-85分），这些市场价格更可能合理
        query = """
            SELECT DISTINCT ON (a.market_id)
                a.market_id,
                a.recommendation,
                a.opportunity_score,
                a.confidence_score,
                a.ai_predicted_probability,
                a.market_probability,
                a.divergence,
                a.reasoning,
                m.question,
                m.category,
                m.volume_24h,
                m.liquidity
            FROM qd_polymarket_ai_analysis a
            INNER JOIN qd_polymarket_markets m ON a.market_id = m.market_id
            WHERE a.opportunity_score BETWEEN 60 AND 85
              AND m.liquidity > 10000
              AND m.volume_24h > 1000
              AND m.status = 'active'
              AND m.end_date_iso > NOW()
            ORDER BY a.market_id, a.created_at DESC
            LIMIT 20
        """
        
        cursor.execute(query)
        rows = cursor.fetchall()
        
        opportunities = []
        for row in rows:
            opportunities.append({
                'market_id': row['market_id'],
                'question': row['question'],
                'category': row['category'],
                'recommendation': row['recommendation'],
                'opportunity_score': float(row['opportunity_score']),
                'confidence_score': float(row['confidence_score']),
                'ai_predicted_probability': float(row['ai_predicted_probability']),
                'market_probability': float(row['market_probability']),
                'divergence': float(row['divergence']),
                'volume_24h': float(row['volume_24h']),
                'liquidity': float(row['liquidity']),
                'reasoning': row['reasoning']
            })
        
        return opportunities


def analyze_with_llm(opportunities):
    """使用大模型分析机会"""
    
    data_summary = f"## Polymarket 可交易机会分析（共 {len(opportunities)} 个）\n\n"
    data_summary += "**筛选标准**: 评分 60-85 分（价格更可能合理）+ 高流动性 + 活跃交易\n\n"
    
    for i, opp in enumerate(opportunities, 1):
        data_summary += f"### {i}. {opp['question']}\n\n"
        data_summary += f"- 分类: {opp['category']}\n"
        data_summary += f"- 推荐: {opp['recommendation']}\n"
        data_summary += f"- 评分: {opp['opportunity_score']:.0f}/100 | 置信度: {opp['confidence_score']:.0f}%\n"
        data_summary += f"- AI预测: {opp['ai_predicted_probability']:.1f}% vs 市场: {opp['market_probability']:.1f}% (差异: {opp['divergence']:+.1f}%)\n"
        data_summary += f"- 流动性: ${opp['liquidity']:,.0f} | 24h交易量: ${opp['volume_24h']:,.0f}\n"
        data_summary += f"- 理由: {opp['reasoning'][:200]}\n\n"
    
    prompt = f"""你是专业的预测市场分析师。以下是 Polymarket 上经过筛选的机会，这些市场的评分适中（60-85分），价格更可能在合理范围内（0.10-0.90），适合实际交易。

{data_summary}

请分析并选出 5-8 个最值得投资的机会，按推荐程度排序。

对每个机会，请提供：

1. 市场问题和推荐操作
2. 推荐理由（3-5点）
3. 风险提示（2-3点）
4. 预期收益率估算
5. 建议投入金额（假设总资金 $100）

最后给出：
- 整体投资策略
- 风险管理建议
- 资金分配方案

注意：
- 这些市场都经过筛选，流动性和交易量充足
- 评分适中意味着价格更可能合理，不会太极端
- 请基于市场基本面和概率分析给出建议

用清晰的中文输出。
"""
    
    print("\n正在调用大模型分析...")
    
    llm_service = LLMService()
    
    messages = [{"role": "user", "content": prompt}]
    
    try:
        response = llm_service.call_llm_api(
            messages=messages,
            temperature=0.3,
            use_json_mode=False
        )
        return response
    except Exception as e:
        print(f"\n❌ 大模型调用失败: {e}")
        return None


def main():
    print("=" * 80)
    print("Polymarket 快速可交易机会分析")
    print("=" * 80)
    print(f"\n⏰ 分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 1. 获取机会
    print("\n[1/3] 从数据库获取候选机会...")
    opportunities = get_tradeable_opportunities()
    print(f"✓ 获取到 {len(opportunities)} 个候选机会")
    
    if not opportunities:
        print("\n⚠️  没有找到符合条件的机会")
        return
    
    # 2. 大模型分析
    print("\n[2/3] 调用大模型进行分析...")
    analysis = analyze_with_llm(opportunities)
    
    if not analysis:
        print("\n❌ 分析失败")
        return
    
    print("✓ 分析完成")
    
    # 3. 显示和保存结果
    print("\n[3/3] 生成分析报告...")
    print("\n" + "=" * 80)
    print("🎯 分析结果")
    print("=" * 80)
    print(f"\n{analysis}")
    
    # 保存结果
    output_file = f"polymarket_quick_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f"Polymarket 快速可交易机会分析\n")
        f.write(f"分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"候选机会数: {len(opportunities)}\n")
        f.write(f"筛选标准: 评分 60-85 分 + 高流动性\n")
        f.write("=" * 80 + "\n\n")
        f.write(analysis)
        f.write("\n\n" + "=" * 80 + "\n")
        f.write("附录: 所有候选机会\n")
        f.write("=" * 80 + "\n\n")
        for i, opp in enumerate(opportunities, 1):
            f.write(f"{i}. {opp['question']}\n")
            f.write(f"   Market ID: {opp['market_id']}\n")
            f.write(f"   推荐: {opp['recommendation']}\n")
            f.write(f"   评分: {opp['opportunity_score']:.0f} | 置信度: {opp['confidence_score']:.0f}%\n")
            f.write(f"   流动性: ${opp['liquidity']:,.0f} | 交易量: ${opp['volume_24h']:,.0f}\n")
            f.write("\n")
    
    print(f"\n{'=' * 80}")
    print("✓ 分析完成")
    print(f"{'=' * 80}")
    print(f"\n📄 完整报告已保存到: {output_file}")
    print(f"\n💡 下一步:")
    print(f"   1. 查看报告中的推荐机会")
    print(f"   2. 使用 simple_trade_test.py 验证价格并交易")
    print(f"   3. 命令: python polymarket/simple_trade_test.py")
    print()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 执行失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
