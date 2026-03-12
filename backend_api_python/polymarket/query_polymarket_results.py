#!/usr/bin/env python
"""
查询Polymarket预测结果

查看数据库中保存的AI分析结果
"""
import os
import sys
from datetime import datetime, timedelta

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 加载环境变量
from dotenv import load_dotenv
load_dotenv()

from app.utils.db import get_db_connection

def explain_recommendation(recommendation, divergence, ai_prob, market_prob):
    """解释推荐的含义"""
    if recommendation == "YES":
        return f"""
    ✓ 推荐：买入 YES（认为事件会发生）
    理由：AI预测概率({ai_prob:.1f}%) 比市场概率({market_prob:.1f}%) 高 {divergence:.1f}%
    含义：市场低估了事件发生的可能性，存在套利机会
    操作：买入 YES 代币，如果事件发生可获利"""
    elif recommendation == "NO":
        return f"""
    ✓ 推荐：买入 NO（认为事件不会发生）
    理由：AI预测概率({ai_prob:.1f}%) 比市场概率({market_prob:.1f}%) 低 {abs(divergence):.1f}%
    含义：市场高估了事件发生的可能性，存在套利机会
    操作：买入 NO 代币，如果事件不发生可获利"""
    else:  # HOLD
        return f"""
    ⊙ 推荐：观望（暂不交易）
    理由：AI预测概率({ai_prob:.1f}%) 与市场概率({market_prob:.1f}%) 差异不大 ({divergence:+.1f}%)
    含义：市场定价相对合理，没有明显套利机会
    操作：暂不交易，继续观察"""

print("=" * 80)
print("Polymarket AI分析结果查询")
print("=" * 80)

print("\n" + "=" * 80)
print("📖 推荐说明")
print("=" * 80)
print("""
Polymarket 是一个预测市场，每个市场有两个选项：YES 和 NO

推荐逻辑：
  • YES：AI认为事件会发生，建议买入 YES 代币
  • NO：AI认为事件不会发生，建议买入 NO 代币  
  • HOLD：AI认为市场定价合理，建议观望

判断标准：
  • YES：AI预测概率 > 市场概率 + 5% 且置信度 > 60%
  • NO：AI预测概率 < 市场概率 - 5% 且置信度 > 60%
  • HOLD：其他情况

示例：
  问题："MicroStrategy 会在2025年卖出比特币吗？"
  • 推荐 YES = 认为会卖出，买入 YES 代币
  • 推荐 NO = 认为不会卖出，买入 NO 代币
""")

try:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # 1. 统计总数
        print("\n[1] 统计信息")
        print("-" * 80)
        
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                COUNT(DISTINCT market_id) as unique_markets,
                MIN(created_at) as first_analysis,
                MAX(created_at) as last_analysis
            FROM qd_polymarket_ai_analysis
        """)
        
        stats = cursor.fetchone()
        if stats:
            print(f"总分析记录数: {stats['total']}")
            print(f"唯一市场数: {stats['unique_markets']}")
            print(f"首次分析时间: {stats['first_analysis'] if stats['first_analysis'] else 'N/A'}")
            print(f"最新分析时间: {stats['last_analysis'] if stats['last_analysis'] else 'N/A'}")
        
        # 2. 决策分布
        print("\n[2] 决策分布")
        print("-" * 80)
        
        cursor.execute("""
            SELECT 
                recommendation,
                COUNT(*) as count,
                ROUND(AVG(confidence_score), 2) as avg_confidence,
                ROUND(AVG(opportunity_score), 2) as avg_opportunity
            FROM qd_polymarket_ai_analysis
            WHERE created_at > NOW() - INTERVAL '7 days'
            GROUP BY recommendation
            ORDER BY count DESC
        """)
        
        print(f"{'决策':<10} {'数量':<10} {'平均置信度':<15} {'平均机会评分':<15}")
        print("-" * 80)
        for row in cursor.fetchall():
            print(f"{row['recommendation'] if row['recommendation'] else 'N/A':<10} {row['count']:<10} {row['avg_confidence'] if row['avg_confidence'] else 0:<15} {row['avg_opportunity'] if row['avg_opportunity'] else 0:<15}")
        
        # 3. 最近24小时的分析
        print("\n[3] 最近24小时的分析（详细）")
        print("-" * 80)
        
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
                m.volume_24h,
                m.liquidity,
                m.end_date_iso
            FROM qd_polymarket_ai_analysis a
            LEFT JOIN qd_polymarket_markets m ON a.market_id = m.market_id
            WHERE a.created_at > NOW() - INTERVAL '24 hours'
            ORDER BY a.created_at DESC
            LIMIT 10
        """)
        
        results = cursor.fetchall()
        if results:
            print(f"找到 {len(results)} 条记录\n")
            for i, row in enumerate(results, 1):
                question = row['question'] if row['question'] else 'N/A'
                slug = row['slug'] if row['slug'] else ''
                url = f"https://polymarket.com/event/{slug}" if slug else 'N/A'
                
                # 检查是否是多选项市场（通过问题中的关键词判断）
                is_multi_option = False
                option_name = None
                option_deadline = None
                
                # 类型1: 时间期限多选项（如 MicroStrategy 系列）
                if row['end_date_iso']:
                    end_date_str = row['end_date_iso'].strftime('%Y年%m月%d日')
                    if any(keyword in question.lower() for keyword in ['by ', 'before ', 'in 2025', 'in 2026', 'march', 'june', 'december']):
                        is_multi_option = True
                        option_deadline = end_date_str
                
                # 类型2: 多国家/多选手选项（如世界杯、欧冠等）
                if any(keyword in question.lower() for keyword in ['will ', 'win the', 'winner', 'champion']):
                    # 尝试提取国家/队伍名称
                    import re
                    # 匹配 "Will XXX win" 或 "Will XXX be" 模式
                    match = re.search(r'Will\s+([A-Za-z\s\-]+?)\s+(?:win|be|become)', question, re.IGNORECASE)
                    if match:
                        option_name = match.group(1).strip()
                        is_multi_option = True
                        
                        # 检查数据库中是否有同类型的其他选项
                        cursor_check = conn.cursor()
                        # 提取比赛/事件名称
                        event_match = re.search(r'(?:win|be|become)\s+(?:the\s+)?(.+?)(?:\?|$)', question, re.IGNORECASE)
                        if event_match:
                            event_name = event_match.group(1).strip()
                            cursor_check.execute("""
                                SELECT COUNT(*) as count
                                FROM qd_polymarket_markets
                                WHERE question LIKE %s AND market_id != %s
                            """, (f'%{event_name}%', row['market_id']))
                            result = cursor_check.fetchone()
                            if result and result['count'] > 0:
                                is_multi_option = True
                        cursor_check.close()
                
                print("=" * 80)
                print(f"[{i}] {question}")
                print("=" * 80)
                print(f"Market ID: {row['market_id']}")
                print(f"URL: {url}")
                print(f"分类: {row['category'] if row['category'] else 'N/A'}")
                
                if is_multi_option and option_deadline:
                    print(f"\n⚠️  这是一个多选项市场的其中一个选项")
                    print(f"   本选项的期限: {option_deadline}")
                    print(f"   可能还有其他期限的选项，请查看完整市场")
                elif is_multi_option and option_name:
                    print(f"\n⚠️  这是一个多选项市场的其中一个选项")
                    print(f"   本选项: {option_name}")
                    print(f"   这个市场有多个选项（如不同国家、队伍等）")
                    print(f"   只有 {option_name} 获胜，YES 代币才会获利")
                
                if row['volume_24h']:
                    print(f"24h交易量: ${row['volume_24h']:,.0f}")
                if row['liquidity']:
                    print(f"流动性: ${row['liquidity']:,.0f}")
                
                market_prob = row['market_probability'] if row['market_probability'] else 0
                yes_price = market_prob
                no_price = 100 - market_prob
                
                print(f"\n📊 市场定价:")
                print(f"  市场概率: {market_prob:.1f}%")
                print(f"  YES 代币价格: {yes_price:.1f}¢")
                print(f"  NO 代币价格: {no_price:.1f}¢")
                
                print(f"\n🤖 AI分析:")
                print(f"  AI预测概率: {row['ai_predicted_probability']:.1f}%")
                print(f"  市场概率: {market_prob:.1f}%")
                print(f"  概率差异: {row['divergence']:+.1f}%")
                print(f"  置信度: {row['confidence_score']:.0f}%")
                print(f"  机会评分: {row['opportunity_score']:.0f}/100")
                
                print(f"\n💡 推荐决策: {row['recommendation']}")
                
                if row['recommendation'] == 'YES':
                    option_desc = f" ({option_name})" if option_name else ""
                    deadline_desc = f"（在{option_deadline}前）" if option_deadline else ""
                    print(f"""
    ✓ 推荐：买入 YES 代币（{yes_price:.1f}¢）{option_desc}
    含义：认为事件会发生{deadline_desc}
    理由：AI预测概率({row['ai_predicted_probability']:.1f}%) 比市场概率({market_prob:.1f}%) 高 {row['divergence']:.1f}%
    操作：买入 YES 代币，如果事件发生可获利""")
                elif row['recommendation'] == 'NO':
                    option_desc = f" ({option_name})" if option_name else ""
                    deadline_desc = f"（在{option_deadline}前）" if option_deadline else ""
                    if option_name:
                        event_desc = f"{option_name} 不会获胜"
                    else:
                        event_desc = "事件不会发生"
                    print(f"""
    ✓ 推荐：买入 NO 代币（{no_price:.1f}¢）{option_desc}
    含义：认为{event_desc}{deadline_desc}
    理由：AI预测概率({row['ai_predicted_probability']:.1f}%) 比市场概率({market_prob:.1f}%) 低 {abs(row['divergence']):.1f}%
    操作：买入 NO 代币，如果{event_desc}可获利""")
                else:
                    print(f"""
    ⊙ 推荐：观望
    理由：AI预测概率({row['ai_predicted_probability']:.1f}%) 与市场概率({market_prob:.1f}%) 差异不大
    操作：暂不交易，继续观察""")
                
                if row['reasoning']:
                    print(f"\n📝 分析理由: {row['reasoning'][:200]}{'...' if len(row['reasoning']) > 200 else ''}")
                
                print(f"\n⏰ 分析时间: {row['created_at']}")
                
                # 如果是多选项市场，提示查看完整信息
                if is_multi_option:
                    if option_name:
                        print(f"\n💡 提示: 这是多选项市场（如世界杯有多个国家选项）")
                        print(f"   当前选项: {option_name}")
                        print(f"   查看所有选项: 访问 {url}")
                    else:
                        print(f"\n💡 提示: 这是多选项市场，运行以下命令查看所有选项:")
                        print(f"   python query_polymarket_series.py")
                
                print()
        else:
            print("最近24小时没有新的分析记录")
        
        # 4. 高分机会（机会评分 > 75）
        print("\n[4] 高分机会（机会评分 > 75）- 详细")
        print("-" * 80)
        
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
                m.end_date_iso
            FROM qd_polymarket_ai_analysis a
            LEFT JOIN qd_polymarket_markets m ON a.market_id = m.market_id
            WHERE a.opportunity_score > 75
            ORDER BY a.opportunity_score DESC, a.created_at DESC
            LIMIT 5
        """)
        
        high_score_results = cursor.fetchall()
        if high_score_results:
            print(f"找到 {len(high_score_results)} 个高分机会\n")
            for i, row in enumerate(high_score_results, 1):
                question = row['question'] if row['question'] else 'N/A'
                slug = row['slug'] if row['slug'] else ''
                url = f"https://polymarket.com/event/{slug}" if slug else 'N/A'
                
                # 检查是否是多选项市场
                is_multi_option = False
                option_name = None
                option_deadline = None
                
                # 类型1: 时间期限多选项
                if row['end_date_iso']:
                    end_date_str = row['end_date_iso'].strftime('%Y年%m月%d日')
                    if any(keyword in question.lower() for keyword in ['by ', 'before ', 'in 2025', 'in 2026', 'march', 'june', 'december']):
                        is_multi_option = True
                        option_deadline = end_date_str
                
                # 类型2: 多国家/多选手选项
                if any(keyword in question.lower() for keyword in ['will ', 'win the', 'winner', 'champion']):
                    import re
                    match = re.search(r'Will\s+([A-Za-z\s\-]+?)\s+(?:win|be|become)', question, re.IGNORECASE)
                    if match:
                        option_name = match.group(1).strip()
                        is_multi_option = True
                
                market_prob = row['market_probability'] if row['market_probability'] else 0
                yes_price = market_prob
                no_price = 100 - market_prob
                
                print("=" * 80)
                print(f"[{i}] {question}")
                print("=" * 80)
                print(f"Market ID: {row['market_id']}")
                print(f"URL: {url}")
                print(f"分类: {row['category'] if row['category'] else 'N/A'}")
                
                if is_multi_option and option_deadline:
                    print(f"\n⚠️  多选项市场 - 本选项期限: {option_deadline}")
                elif is_multi_option and option_name:
                    print(f"\n⚠️  多选项市场 - 本选项: {option_name}")
                    print(f"   （这个市场有多个选项，如不同国家、队伍等）")
                
                print(f"\n📊 市场定价:")
                print(f"  市场概率: {market_prob:.1f}%")
                print(f"  YES 代币价格: {yes_price:.1f}¢")
                print(f"  NO 代币价格: {no_price:.1f}¢")
                
                print(f"\n🤖 AI分析:")
                print(f"  机会评分: {row['opportunity_score']:.0f}/100 ⭐")
                print(f"  置信度: {row['confidence_score']:.0f}%")
                print(f"  AI预测概率: {row['ai_predicted_probability']:.1f}%")
                print(f"  市场概率: {market_prob:.1f}%")
                print(f"  概率差异: {row['divergence']:+.1f}%")
                
                print(f"\n💡 推荐决策: {row['recommendation']}")
                
                if row['recommendation'] == 'YES':
                    option_desc = f" - {option_name}" if option_name else ""
                    deadline_desc = f"（在{option_deadline}前）" if option_deadline else ""
                    print(f"""
    ✓ 推荐：买入 YES 代币（{yes_price:.1f}¢）{option_desc}
    含义：认为事件会发生{deadline_desc}
    理由：AI预测概率({row['ai_predicted_probability']:.1f}%) 比市场概率({market_prob:.1f}%) 高 {row['divergence']:.1f}%
    潜在收益：{100 - yes_price:.1f}¢ ({(100 - yes_price) / yes_price * 100:.1f}% 回报率)
    操作：买入 YES 代币，如果事件发生可获利""")
                elif row['recommendation'] == 'NO':
                    option_desc = f" - {option_name}" if option_name else ""
                    deadline_desc = f"（在{option_deadline}前）" if option_deadline else ""
                    if option_name:
                        event_desc = f"{option_name} 不会获胜"
                    else:
                        event_desc = "事件不会发生"
                    print(f"""
    ✓ 推荐：买入 NO 代币（{no_price:.1f}¢）{option_desc}
    含义：认为{event_desc}{deadline_desc}
    理由：AI预测概率({row['ai_predicted_probability']:.1f}%) 比市场概率({market_prob:.1f}%) 低 {abs(row['divergence']):.1f}%
    潜在收益：{100 - no_price:.1f}¢ ({(100 - no_price) / no_price * 100:.1f}% 回报率)
    操作：买入 NO 代币，如果{event_desc}可获利""")
                else:
                    print(f"""
    ⊙ 推荐：观望
    理由：AI预测概率({row['ai_predicted_probability']:.1f}%) 与市场概率({market_prob:.1f}%) 差异不大
    操作：暂不交易，继续观察""")
                
                if row['reasoning']:
                    print(f"\n📝 分析理由:")
                    reasoning = row['reasoning']
                    # 分段显示
                    lines = reasoning.split('\n')
                    for line in lines[:5]:  # 只显示前5行
                        if line.strip():
                            print(f"  {line.strip()}")
                    if len(lines) > 5:
                        print(f"  ...")
                
                print(f"\n⏰ 分析时间: {row['created_at']}")
                
                if is_multi_option:
                    if option_name:
                        print(f"\n💡 提示: 多选项市场 - 当前选项: {option_name}")
                        print(f"   访问 {url} 查看所有选项")
                    else:
                        print(f"\n💡 提示: 运行 python query_polymarket_series.py 查看所有期限选项")
                
                print()
        else:
            print("没有找到机会评分 > 75 的记录")
        
        # 5. 按市场ID分组，显示最新的分析
        print("\n[5] 最新分析的市场（按机会评分排序）")
        print("-" * 80)
        
        cursor.execute("""
            WITH latest_analysis AS (
                SELECT DISTINCT ON (a.market_id)
                    a.market_id,
                    a.recommendation,
                    a.confidence_score,
                    a.opportunity_score,
                    a.ai_predicted_probability,
                    a.market_probability,
                    a.divergence,
                    a.created_at,
                    m.question,
                    m.slug
                FROM qd_polymarket_ai_analysis a
                LEFT JOIN qd_polymarket_markets m ON a.market_id = m.market_id
                ORDER BY a.market_id, a.created_at DESC
            )
            SELECT * FROM latest_analysis
            ORDER BY opportunity_score DESC
            LIMIT 10
        """)
        
        latest_results = cursor.fetchall()
        if latest_results:
            print(f"找到 {len(latest_results)} 个市场\n")
            for i, row in enumerate(latest_results, 1):
                question = row['question'] if row['question'] else 'N/A'
                slug = row['slug'] if row['slug'] else ''
                url = f"https://polymarket.com/event/{slug}" if slug else 'N/A'
                
                print(f"[{i}] {question[:80]}{'...' if len(question) > 80 else ''}")
                print(f"    URL: {url}")
                print(f"    决策: {row['recommendation']} | 置信度: {row['confidence_score']}% | 机会评分: {row['opportunity_score']}")
                print(f"    AI预测: {row['ai_predicted_probability']}% | 市场概率: {row['market_probability']}% | 差异: {row['divergence']}%")
                print(f"    分析时间: {row['created_at']}")
                print()
        else:
            print("没有找到分析记录")
        
        # 6. 概率差异最大的市场
        print("\n[6] 概率差异最大的市场（AI vs 市场）")
        print("-" * 80)
        
        cursor.execute("""
            SELECT 
                a.market_id,
                a.recommendation,
                a.confidence_score,
                a.opportunity_score,
                a.ai_predicted_probability,
                a.market_probability,
                a.divergence,
                a.created_at,
                m.question,
                m.slug
            FROM qd_polymarket_ai_analysis a
            LEFT JOIN qd_polymarket_markets m ON a.market_id = m.market_id
            WHERE a.created_at > NOW() - INTERVAL '7 days'
            ORDER BY ABS(a.divergence) DESC
            LIMIT 5
        """)
        
        divergence_results = cursor.fetchall()
        if divergence_results:
            print(f"找到 {len(divergence_results)} 个高差异市场\n")
            for i, row in enumerate(divergence_results, 1):
                question = row['question'] if row['question'] else 'N/A'
                slug = row['slug'] if row['slug'] else ''
                url = f"https://polymarket.com/event/{slug}" if slug else 'N/A'
                
                print(f"[{i}] {question[:80]}{'...' if len(question) > 80 else ''}")
                print(f"    URL: {url}")
                print(f"    决策: {row['recommendation']}")
                print(f"    AI预测概率: {row['ai_predicted_probability']}%")
                print(f"    市场概率: {row['market_probability']}%")
                print(f"    概率差异: {row['divergence']}% ⚠️")
                print(f"    机会评分: {row['opportunity_score']}")
                print(f"    分析时间: {row['created_at']}")
                print()
        else:
            print("没有找到记录")
        
        # 7. 每日分析数量趋势
        print("\n[7] 每日分析数量趋势（最近7天）")
        print("-" * 80)
        
        cursor.execute("""
            SELECT 
                DATE(created_at) as analysis_date,
                COUNT(*) as count,
                COUNT(DISTINCT market_id) as unique_markets,
                ROUND(AVG(opportunity_score), 2) as avg_opportunity_score
            FROM qd_polymarket_ai_analysis
            WHERE created_at > NOW() - INTERVAL '7 days'
            GROUP BY DATE(created_at)
            ORDER BY analysis_date DESC
        """)
        
        print(f"{'日期':<15} {'分析数':<10} {'唯一市场':<12} {'平均机会评分':<15}")
        print("-" * 80)
        for row in cursor.fetchall():
            print(f"{str(row['analysis_date']):<15} {row['count']:<10} {row['unique_markets']:<12} {row['avg_opportunity_score'] if row['avg_opportunity_score'] else 0:<15}")
        
        cursor.close()
    
    print("\n" + "=" * 80)
    print("查询完成")
    print("=" * 80)
    
except Exception as e:
    print(f"\n✗ 查询失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
