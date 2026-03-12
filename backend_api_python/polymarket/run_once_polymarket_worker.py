#!/usr/bin/env python
"""
Polymarket 高价值机会单次执行脚本

专注于发现和分析高价值交易机会
"""
import os
import sys
import argparse
from datetime import datetime

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 加载环境变量
from dotenv import load_dotenv
load_dotenv()

from app.services.polymarket_worker import PolymarketWorker


def print_header(title: str):
    """打印标题"""
    print("\n" + "=" * 80)
    print(f" {title}")
    print("=" * 80)


def print_opportunities(opportunities: list):
    """打印高价值机会"""
    if not opportunities:
        print("\n⚠️  未发现高价值机会")
        return
    
    print(f"\n🎯 发现 {len(opportunities)} 个高价值机会:\n")
    
    for i, opp in enumerate(opportunities, 1):
        market = opp['market']
        question = market.get('question', 'N/A')
        prob = market.get('current_probability', 0)
        volume = market.get('volume_24h', 0)
        liquidity = market.get('liquidity', 0)
        category = market.get('category', 'unknown')
        
        # 计算机会指标
        divergence = abs(prob - 50.0)
        opportunity_score = opp.get('opportunity_score', 0)
        
        print(f"[{i}] {question[:70]}")
        print(f"    分类: {category} | 概率: {prob:.1f}% | 偏差: {divergence:.1f}%")
        print(f"    交易量: ${volume:,.0f} | 流动性: ${liquidity:,.0f}")
        print(f"    机会评分: {opportunity_score:.0f}/100")
        print()


def main():
    parser = argparse.ArgumentParser(
        description='Polymarket 高价值机会单次执行',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 分析所有分类，每个分类20个市场，最多分析10个
  python run_once_polymarket_worker.py
  
  # 只分析crypto分类，每个分类30个市场
  python run_once_polymarket_worker.py --categories crypto --limit 30
  
  # 分析多个分类，最多分析20个
  python run_once_polymarket_worker.py --categories crypto sports politics --max-analyze 20
  
  # 查询更多机会（降低评分阈值）
  python run_once_polymarket_worker.py --min-opportunity 70
        """
    )
    
    parser.add_argument(
        '--categories',
        nargs='+',
        # default=["crypto", "politics", "economics", "sports", "tech", 
        #                      "finance", "geopolitics", "culture", "climate", "entertainment",
        #                      "business", "science", "health", "ai", "energy"],
        help='要分析的市场分类 (默认: crypto sports politics tech economics finance geopolitics culture climate entertainment business science)'
    )
    
    parser.add_argument(
        '--limit',
        type=int,
        default=200,
        help='每个分类获取的市场数量 (默认: 20)'
    )
    
    parser.add_argument(
        '--max-analyze',
        type=int,
        default=50,
        help='最多分析的市场数量 (默认: 10)'
    )
    
    parser.add_argument(
        '--min-opportunity',
        type=float,
        default=75.0,
        help='查询结果的最小机会评分阈值 (默认: 75.0)'
    )
    
    args = parser.parse_args()
    
    # 打印配置
    print_header("Polymarket 高价值机会分析")
    print(f"\n⏰ 执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"\n📋 配置:")
    if args.categories != None:
        print(f"   分类: {', '.join(args.categories)}")
    print(f"   每分类市场数: {args.limit}")
    print(f"   最多分析数: {args.max_analyze}")
    print(f"   查询机会评分阈值: {args.min_opportunity}")
    
    # 初始化 Worker
    try:
        worker = PolymarketWorker()
        print(f"\n✓ Worker 初始化成功")
    except Exception as e:
        print(f"\n✗ Worker 初始化失败: {e}")
        sys.exit(1)
    
    # 执行分析
    print_header("开始执行分析")
    
    try:
        result = worker.run_once(
            categories=args.categories,
            limit=args.limit,
            max_analyze=args.max_analyze
        )
        
        if not result['success']:
            print(f"\n✗ 执行失败: {result.get('error', '未知错误')}")
            sys.exit(1)
        
        # 打印统计信息
        print_header("执行统计")
        print(f"\n📊 数据统计:")
        print(f"   获取市场总数: {result['total_markets']}")
        print(f"   去重后市场数: {result['unique_markets']}")
        print(f"   规则筛选出: {result['rule_filtered']} 个高价值机会")
        print(f"   AI分析完成: {result['analyzed']} 个市场")
        print(f"   保存到数据库: {result['saved']} 个结果")
        print(f"   执行耗时: {result['elapsed_seconds']:.1f} 秒")
        
        # 打印高价值机会
        if result.get('opportunities'):
            print_header("高价值机会")
            print_opportunities(result['opportunities'])
        
        # 查询并显示数据库中的高分机会
        print_header("数据库中的高分机会")
        print(f"\n💡 查询机会评分 >= {args.min_opportunity} 的市场...\n")
        
        try:
            from app.utils.db import get_db_connection
            
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
                        m.category,
                        m.volume_24h,
                        m.liquidity
                    FROM qd_polymarket_ai_analysis a
                    INNER JOIN qd_polymarket_markets m ON a.market_id = m.market_id
                    WHERE a.opportunity_score >= %s
                    ORDER BY a.market_id, a.created_at DESC
                    LIMIT 20
                """
                
                cursor.execute(query, (args.min_opportunity,))
                rows = cursor.fetchall()
                
                if rows:
                    print(f"📈 找到 {len(rows)} 个高分机会:\n")
                    
                    for i, row in enumerate(rows, 1):
                        print(f"[{i}] {row['question'][:70]}")
                        print(f"    推荐: {row['recommendation']} | 机会评分: {row['opportunity_score']:.0f} | 置信度: {row['confidence_score']:.0f}%")
                        print(f"    AI预测: {row['ai_predicted_probability']:.1f}% | 市场概率: {row['market_probability']:.1f}% | 差异: {row['divergence']:+.1f}%")
                        print(f"    分类: {row['category']} | 交易量: ${row['volume_24h']:,.0f}")
                        reasoning = row['reasoning'] if row['reasoning'] else "无"
                        print(f"    分析理由: {reasoning[:100]}...")
                        print(f"    分析时间: {row['created_at']}")
                        print()
                else:
                    print(f"⚠️  数据库中暂无评分 >= {args.min_opportunity} 的机会")
                    print(f"   提示: 降低 --min-opportunity 阈值或运行更多分析")
        except Exception as e:
            print(f"⚠️  查询数据库失败: {e}")
            print(f"   提示: 可以使用 query_polymarket_results.py 查看结果")
        
        # 成功提示
        print_header("执行完成")
        print(f"\n✓ 分析完成！")
        print(f"\n💡 下一步:")
        print()
        
    except KeyboardInterrupt:
        print(f"\n\n⚠️  用户中断执行")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ 执行异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
