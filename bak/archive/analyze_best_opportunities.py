#!/usr/bin/env python
"""
深度分析最佳机会

调用大模型对数据库中的所有机会进行综合分析，给出最有把握的推荐
只选择价格合理、可实际交易的市场
"""
import os
import sys
import json
import subprocess
from datetime import datetime

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 加载环境变量
from dotenv import load_dotenv
load_dotenv()

from app.utils.db import get_db_connection
from app.services.llm import LLMService


def run_cli(cmd):
    """运行 CLI 命令"""
    env = os.environ.copy()
    # 删除环境变量，让 CLI 使用配置文件
    if 'POLYMARKET_PRIVATE_KEY' in env:
        del env['POLYMARKET_PRIVATE_KEY']
    
    result = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        timeout=30,
        env=env
    )
    
    if result.returncode == 0 and result.stdout:
        return result.stdout
    return None


def check_market_tradeable(market_id, question, recommendation):
    """检查市场是否可交易（价格合理）"""
    try:
        # 搜索市场
        search_query = question[:30].replace('"', '\\"')
        result = run_cli(f'polymarket -o json markets search "{search_query}"')
        
        if not result:
            return None, None
        
        markets = json.loads(result)
        
        # 找到匹配的市场
        market_data = None
        for m in markets:
            if m.get('id') == market_id:
                market_data = m
                break
        
        if not market_data:
            return None, None
        
        condition_id = market_data.get('conditionId')
        if not condition_id:
            return None, None
        
        # 获取市场详情
        market_result = run_cli(f'polymarket -o json clob market {condition_id}')
        if not market_result:
            return None, None
        
        market_info = json.loads(market_result)
        tokens = market_info.get('tokens', [])
        
        if len(tokens) < 2:
            return None, None
        
        # 根据推荐选择 token
        if recommendation.upper() == 'YES':
            token = tokens[0]
        else:
            token = tokens[1]
        
        token_id = token.get('token_id')
        token_price = float(token.get('price', 0))
        
        # 检查价格是否合理（0.10 - 0.90）
        if token_price < 0.10 or token_price > 0.90:
            return None, None
        
        # 检查买入价
        price_result = run_cli(f'polymarket -o json clob price {token_id} --side buy')
        if not price_result:
            return None, None
        
        price_data = json.loads(price_result)
        buy_price = float(price_data.get('price', 0))
        
        if buy_price < 0.10 or buy_price > 0.90:
            return None, None
        
        return token_id, buy_price
        
    except Exception as e:
        return None, None


def get_all_opportunities():
    """从数据库获取所有机会，并验证可交易性"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
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
                a.created_at,
                m.question,
                m.slug,
                m.category,
                m.volume_24h,
                m.liquidity,
                m.end_date_iso,
                m.status
            FROM qd_polymarket_ai_analysis a
            INNER JOIN qd_polymarket_markets m ON a.market_id = m.market_id
            WHERE a.opportunity_score >= 60
              AND m.liquidity > 5000
              AND m.volume_24h > 500
              AND m.status = 'active'
              AND m.end_date_iso > NOW()
            ORDER BY a.market_id, a.opportunity_score DESC, a.created_at DESC
            LIMIT 30
        """
        
        cursor.execute(query)
        rows = cursor.fetchall()
        
        print(f"\n从数据库获取到 {len(rows)} 个候选机会")
        print("正在验证可交易性（价格在 0.10-0.90 之间）...")
        print("提示: 这可能需要几分钟，每个市场需要 2-3 秒验证\n")
        
        opportunities = []
        checked = 0
        for i, row in enumerate(rows, 1):
            market_id = row['market_id']
            question = row['question']
            recommendation = row['recommendation']
            
            print(f"[{i}/{len(rows)}] {question[:50]}...", end=" ", flush=True)
            
            # 检查市场是否可交易
            token_id, buy_price = check_market_tradeable(market_id, question, recommendation)
            
            checked += 1
            
            if token_id and buy_price:
                print(f"✓ ${buy_price:.4f}")
                opportunities.append({
                    'market_id': market_id,
                    'question': question,
                    'slug': row['slug'],
                    'category': row['category'],
                    'recommendation': recommendation,
                    'opportunity_score': float(row['opportunity_score']),
                    'confidence_score': float(row['confidence_score']),
                    'ai_predicted_probability': float(row['ai_predicted_probability']),
                    'market_probability': float(row['market_probability']),
                    'divergence': float(row['divergence']),
                    'volume_24h': float(row['volume_24h']),
                    'liquidity': float(row['liquidity']),
                    'reasoning': row['reasoning'],
                    'end_date': row['end_date_iso'],
                    'created_at': str(row['created_at']),
                    'token_id': token_id,
                    'buy_price': buy_price
                })
            else:
                print("✗ 价格不合理或无法交易")
            
            # 找到足够的可交易机会就停止
            if len(opportunities) >= 10:
                print(f"\n✓ 已找到 {len(opportunities)} 个可交易机会，停止搜索")
                print(f"  （已检查 {checked}/{len(rows)} 个市场）")
                break
            
            # 如果检查了很多还没找到足够的，也停止
            if checked >= 30 and len(opportunities) < 5:
                print(f"\n⚠️  已检查 {checked} 个市场，只找到 {len(opportunities)} 个可交易")
                print(f"  大部分市场价格太极端，停止搜索")
                break
        
        return opportunities


def analyze_with_llm(opportunities):
    """使用大模型分析所有机会"""
    
    # 按评分排序
    top_opportunities = sorted(opportunities, key=lambda x: x['opportunity_score'], reverse=True)
    
    # 准备简洁的数据摘要
    data_summary = f"## 待分析的 Polymarket 可交易机会（共 {len(top_opportunities)} 个）\n\n"
    data_summary += "**重要**: 以下所有市场都已验证价格合理（0.10-0.90），可以实际交易\n\n"
    
    for i, opp in enumerate(top_opportunities, 1):
        data_summary += f"### 机会 {i}: {opp['question'][:100]}\n\n"
        data_summary += f"- Market ID: {opp['market_id']}\n"
        data_summary += f"- 分类: {opp['category']}\n"
        data_summary += f"- 推荐: {opp['recommendation']}\n"
        data_summary += f"- 当前价格: ${opp['buy_price']:.4f} ✓ 可交易\n"
        data_summary += f"- 机会评分: {opp['opportunity_score']:.0f}/100\n"
        data_summary += f"- 置信度: {opp['confidence_score']:.0f}%\n"
        data_summary += f"- AI预测: {opp['ai_predicted_probability']:.1f}% | 市场: {opp['market_probability']:.1f}% | 差异: {opp['divergence']:+.1f}%\n"
        data_summary += f"- 交易量: ${opp['volume_24h']:,.0f} | 流动性: ${opp['liquidity']:,.0f}\n"
        data_summary += f"- 理由: {opp['reasoning'][:150]}...\n"
        data_summary += f"- Token ID: {opp['token_id'][:20]}...\n\n"
    
    # 构建提示词
    prompt = f"""你是专业的预测市场分析师，请分析以下 Polymarket 机会，选出最有把握的 5-8 个投资建议。

{data_summary}

## 重要说明

以上所有市场都已经过验证：
- ✓ 价格在 0.10-0.90 之间（可实际交易）
- ✓ 市场状态为活跃（active）
- ✓ 有足够的流动性和交易量
- ✓ 提供了 Token ID（可直接下单）

## 分析维度

1. 机会评分：评分越高，潜在收益越大
2. 置信度：置信度越高，预测越可靠
3. 当前价格：价格越低，潜在收益越高（对于 NO 推荐）
4. 概率差异：差异大说明存在套利空间
5. 交易量和流动性：影响进出便利性
6. 市场类型：crypto > sports > politics（可预测性）
7. 分析理由的合理性

## 输出要求

请选出 5-8 个最有把握的机会，按把握程度排序，每个机会包含：

1. 排名和市场问题
2. 推荐操作（YES/NO）和当前价格
3. 把握程度（高/中/低）
4. 预期收益率（基于当前价格）
5. 风险等级（低/中/高）
6. 核心理由（3-5条）
7. 风险因素（2-3条）
8. 具体操作建议（包括建议投入金额）

最后给出：
- 整体投资策略
- 风险管理建议
- 资金分配方案（假设总资金 $100）
- 执行命令示例（使用提供的 Token ID）

请用清晰的中文输出，格式友好。
"""
    
    print(f"\n正在分析前 {len(top_opportunities)} 个高分机会...")
    print("=" * 80)
    
    llm_service = LLMService()
    
    messages = [
        {
            "role": "user",
            "content": prompt
        }
    ]
    
    try:
        response = llm_service.call_llm_api(
            messages=messages,
            temperature=0.3,
            use_json_mode=False  # DeepSeek 不支持 JSON 模式
        )
        
        return response
    except Exception as e:
        print(f"\n❌ 大模型调用失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def print_analysis_results(analysis):
    """打印分析结果"""
    if not analysis:
        return
    
    print("\n" + "=" * 80)
    print("🎯 大模型深度分析结果")
    print("=" * 80)
    print(f"\n{analysis}")


def main():
    print("=" * 80)
    print("Polymarket 最佳机会深度分析")
    print("=" * 80)
    print(f"\n⏰ 分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 1. 获取所有机会
    print("\n[1/3] 从数据库获取并验证机会...")
    opportunities = get_all_opportunities()
    print(f"\n✓ 获取到 {len(opportunities)} 个可交易机会")
    
    if not opportunities:
        print("\n⚠️  没有找到可交易的机会")
        print("   原因: 所有高评分市场的价格都太极端（接近 0 或 1）")
        print("   建议:")
        print("   1. 降低机会评分阈值（当前 >= 60）")
        print("   2. 运行 worker 获取更多市场数据")
        print("   3. 手动选择价格合理的市场")
        return
    
    # 2. 大模型分析
    print("\n[2/3] 调用大模型进行深度分析...")
    analysis = analyze_with_llm(opportunities)
    
    if not analysis:
        print("\n❌ 分析失败")
        return
    
    print("✓ 分析完成")
    
    # 3. 打印结果
    print("\n[3/3] 生成分析报告...")
    print_analysis_results(analysis)
    
    # 4. 保存结果
    output_file = f"polymarket_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f"Polymarket 最佳机会深度分析（可交易版本）\n")
        f.write(f"分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"可交易机会数: {len(opportunities)}\n")
        f.write(f"价格范围: 0.10 - 0.90\n")
        f.write("=" * 80 + "\n\n")
        f.write(analysis)
        f.write("\n\n" + "=" * 80 + "\n")
        f.write("附录: 所有可交易机会详情\n")
        f.write("=" * 80 + "\n\n")
        for i, opp in enumerate(opportunities, 1):
            f.write(f"{i}. {opp['question']}\n")
            f.write(f"   Market ID: {opp['market_id']}\n")
            f.write(f"   Token ID: {opp['token_id']}\n")
            f.write(f"   推荐: {opp['recommendation']} @ ${opp['buy_price']:.4f}\n")
            f.write(f"   评分: {opp['opportunity_score']:.0f} | 置信度: {opp['confidence_score']:.0f}%\n")
            f.write(f"   执行命令: polymarket clob market-order --token {opp['token_id']} --side buy --amount 1.0\n")
            f.write("\n")
    
    print(f"\n{'=' * 80}")
    print("✓ 分析完成")
    print(f"{'=' * 80}")
    print(f"\n📄 完整报告已保存到: {output_file}")
    print(f"\n💡 下一步:")
    print(f"   1. 查看报告中的推荐机会")
    print(f"   2. 使用报告中的执行命令直接下单")
    print(f"   3. 或运行自动化测试: python polymarket/simple_trade_test.py")
    print(f"\n⚠️  注意:")
    print(f"   - 所有推荐的市场都已验证可交易（价格 0.10-0.90）")
    print(f"   - 最小订单金额: $1.00 USDC")
    print(f"   - 执行前请确认钱包余额充足")
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
