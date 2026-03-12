#!/usr/bin/env python
"""
Polymarket 跟单系统 - 单次执行脚本

追踪排行榜顶级用户的交易活动，复用AI分析能力

使用方法:
    python polymarket/run_once_copy_trading.py
"""
import os
import sys
from datetime import datetime
from typing import List, Dict

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 加载环境变量
from dotenv import load_dotenv
load_dotenv()

from app.data_sources.polymarket import PolymarketDataSource
from app.services.polymarket_batch_analyzer import PolymarketBatchAnalyzer
from app.utils.db import get_db_connection
from app.utils.logger import get_logger

logger = get_logger(__name__)


def print_header(title: str):
    """打印标题"""
    print("\n" + "=" * 80)
    print(f" {title}")
    print("=" * 80)


def save_top_users(users: List[Dict], period: str):
    """保存排行榜用户到数据库"""
    if not users:
        return 0
    
    saved = 0
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            for user in users:
                try:
                    cursor.execute("""
                        INSERT INTO qd_polymarket_top_users 
                        (user_address, period, rank, volume, profit, trades, win_rate)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (user_address, period, (created_at::date))
                        DO UPDATE SET
                            rank = EXCLUDED.rank,
                            volume = EXCLUDED.volume,
                            profit = EXCLUDED.profit,
                            trades = EXCLUDED.trades,
                            win_rate = EXCLUDED.win_rate
                    """, (
                        user.get('user'),
                        period,
                        user.get('rank'),
                        user.get('volume'),
                        user.get('profit'),
                        user.get('trades'),
                        user.get('win_rate')
                    ))
                    saved += 1
                except Exception as e:
                    logger.error(f"Failed to save user {user.get('user')}: {e}")
                    continue
            
            conn.commit()
    except Exception as e:
        logger.error(f"Failed to save top users: {e}")
    
    return saved


def save_activities(activities: List[Dict]) -> tuple:
    """
    保存交易活动到数据库（自动去重）
    如果市场不存在，从 API 获取并保存
    
    Returns:
        (新增数量, 重复数量)
    """
    if not activities:
        return 0, 0
    
    import hashlib
    from app.data_sources.polymarket import PolymarketDataSource
    
    polymarket = PolymarketDataSource()
    new_count = 0
    duplicate_count = 0
    
    # 先批量查询所有需要的 market_id（通过 slug 或 conditionId）
    market_id_map = {}  # conditionId -> numeric market_id
    missing_condition_ids = set()  # 需要从 API 获取的 condition_id
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 收集所有唯一的 conditionId 和 slug
            condition_ids = set()
            slugs = set()
            for activity in activities:
                condition_id = activity.get('conditionId')
                slug = activity.get('slug')
                if condition_id:
                    condition_ids.add(condition_id)
                if slug:
                    slugs.add(slug)
            
            # 批量查询 market_id（通过 slug）
            if slugs:
                cursor.execute("""
                    SELECT market_id, slug, condition_id
                    FROM qd_polymarket_markets
                    WHERE slug = ANY(%s)
                """, (list(slugs),))
                
                for row in cursor.fetchall():
                    if row['condition_id']:
                        market_id_map[row['condition_id']] = row['market_id']
                    if row['slug']:
                        market_id_map[row['slug']] = row['market_id']
            
            # 如果通过 slug 没找到，尝试通过 conditionId 查询
            if condition_ids:
                cursor.execute("""
                    SELECT market_id, condition_id
                    FROM qd_polymarket_markets
                    WHERE condition_id = ANY(%s)
                """, (list(condition_ids),))
                
                for row in cursor.fetchall():
                    if row['condition_id']:
                        market_id_map[row['condition_id']] = row['market_id']
            
            # 找出缺失的 condition_id
            for condition_id in condition_ids:
                if condition_id not in market_id_map:
                    missing_condition_ids.add(condition_id)
            
            # 从 API 获取缺失的市场
            if missing_condition_ids:
                logger.info(f"Found {len(missing_condition_ids)} markets not in database, fetching from API...")
                
                for condition_id in list(missing_condition_ids)[:10]:  # 限制最多获取10个
                    try:
                        market = polymarket.get_market_by_condition_id(condition_id)
                        if market:
                            market_id = market.get('market_id')
                            if market_id:
                                market_id_map[condition_id] = market_id
                                logger.info(f"Fetched market {market_id} for condition_id {condition_id[:20]}...")
                    except Exception as e:
                        logger.warning(f"Failed to fetch market for condition_id {condition_id}: {e}")
    
    except Exception as e:
        logger.error(f"Failed to query market_ids: {e}")
    
    # 保存每个活动
    for activity in activities:
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                # 生成唯一ID：使用 transactionHash 或组合字段的哈希
                tx_hash = activity.get('transactionHash')
                if tx_hash:
                    unique_str = f"{tx_hash}_{activity.get('asset', '')}_{activity.get('side', '')}"
                    activity_id = hashlib.md5(unique_str.encode()).hexdigest()
                else:
                    unique_str = f"{activity.get('proxyWallet', '')}_{activity.get('timestamp', '')}_{activity.get('conditionId', '')}_{activity.get('side', '')}"
                    activity_id = hashlib.md5(unique_str.encode()).hexdigest()
                
                # 获取数字 market_id
                condition_id = activity.get('conditionId')
                slug = activity.get('slug')
                
                # 优先使用 conditionId 查找，其次使用 slug
                market_id = None
                if condition_id and condition_id in market_id_map:
                    market_id = market_id_map[condition_id]
                elif slug and slug in market_id_map:
                    market_id = market_id_map[slug]
                
                # 如果找不到 market_id，使用 conditionId 作为 fallback
                # 这样至少能保存数据，后续可以通过更新脚本修复
                if not market_id:
                    market_id = condition_id
                    logger.warning(f"Could not find numeric market_id for condition_id {condition_id}, using condition_id as fallback")
                
                # 使用activity_id作为唯一标识
                cursor.execute("""
                    INSERT INTO qd_polymarket_user_activities 
                    (activity_id, user_address, market_id, asset_id, side, outcome, 
                     size, price, fee_rate_bps, timestamp)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, to_timestamp(%s))
                    ON CONFLICT (activity_id) DO NOTHING
                """, (
                    activity_id,
                    activity.get('proxyWallet'),
                    market_id,  # 使用数字 market_id 或 conditionId
                    activity.get('asset'),
                    activity.get('side'),
                    activity.get('outcome'),
                    activity.get('size'),
                    activity.get('price'),
                    activity.get('feeRateBps'),
                    activity.get('timestamp')
                ))
                
                if cursor.rowcount > 0:
                    new_count += 1
                else:
                    duplicate_count += 1
                
                conn.commit()
                    
        except Exception as e:
            logger.error(f"Failed to save activity: {e}")
            continue
    
    return new_count, duplicate_count


def get_markets_by_ids(market_ids: List[str]) -> List[Dict]:
    """根据market_id列表获取市场详情"""
    if not market_ids:
        return []
    
    markets = []
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 去重
            unique_ids = list(set(market_ids))
            
            cursor.execute("""
                SELECT 
                    market_id,
                    question,
                    category,
                    current_probability,
                    volume_24h,
                    liquidity,
                    slug
                FROM qd_polymarket_markets
                WHERE market_id = ANY(%s)
            """, (unique_ids,))
            
            rows = cursor.fetchall()
            
            for row in rows:
                # 使用 slug 动态构建 URL
                slug = row.get('slug', '')
                polymarket_url = f"https://polymarket.com/event/{slug}" if slug else None
                
                markets.append({
                    'market_id': row['market_id'],
                    'question': row['question'],
                    'category': row['category'],
                    'current_probability': float(row['current_probability']) if row['current_probability'] else 50.0,
                    'volume_24h': float(row['volume_24h']) if row['volume_24h'] else 0,
                    'liquidity': float(row['liquidity']) if row['liquidity'] else 0,
                    'polymarket_url': polymarket_url
                })
    except Exception as e:
        logger.error(f"Failed to get markets by ids: {e}")
    
    return markets


def get_existing_users() -> tuple:
    """
    从数据库获取现有用户
    
    Returns:
        (用户列表, 每个period的最新时间字典)
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 获取去重后的用户列表
            cursor.execute("""
                SELECT DISTINCT user_address
                FROM qd_polymarket_top_users
            """)
            
            rows = cursor.fetchall()
            users = [row['user_address'] for row in rows]
            
            # 获取每个period的最新记录时间
            cursor.execute("""
                SELECT period, MAX(created_at) as latest_time
                FROM qd_polymarket_top_users
                GROUP BY period
            """)
            
            period_times = {}
            for row in cursor.fetchall():
                period_times[row['period']] = row['latest_time']
            
            return users, period_times
    except Exception as e:
        logger.error(f"Failed to get existing users: {e}")
        return [], {}


def get_periods_to_refresh(period_times: Dict[str, datetime]) -> List[str]:
    """
    判断哪些period需要刷新
    
    Args:
        period_times: 每个period的最新时间字典
        
    Returns:
        需要刷新的period列表
    """
    all_periods = ['day', 'week', 'month', 'all']
    periods_to_refresh = []
    
    now = datetime.now()
    
    for period in all_periods:
        if period not in period_times:
            # 如果该period没有记录，需要刷新
            periods_to_refresh.append(period)
        else:
            # 计算时间差
            time_diff = now - period_times[period]
            # 如果超过1天，需要刷新
            if time_diff.total_seconds() > 86400:  # 24小时
                periods_to_refresh.append(period)
    
    return periods_to_refresh


def main():
    print_header("Polymarket 跟单系统 - 单次执行")
    print(f"\n⏰ 执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 初始化
    polymarket = PolymarketDataSource()
    batch_analyzer = PolymarketBatchAnalyzer()
    
    # 第1步: 检查现有用户并决定哪些period需要刷新
    print_header("第1步: 检查用户列表")
    
    existing_users, period_times = get_existing_users()
    
    if existing_users:
        print(f"\n  ✓ 数据库中已有 {len(existing_users)} 个用户")
        
        # 显示每个period的状态
        if period_times:
            print(f"\n  📊 各排行榜状态:")
            now = datetime.now()
            for period in ['day', 'week', 'month', 'all']:
                if period in period_times:
                    time_diff = now - period_times[period]
                    hours = time_diff.total_seconds() / 3600
                    status = "✓" if hours < 24 else "⚠️"
                    print(f"    {status} {period}榜: {period_times[period].strftime('%Y-%m-%d %H:%M:%S')} ({hours:.1f}小时前)")
                else:
                    print(f"    ⚠️ {period}榜: 无记录")
    else:
        print(f"\n  ⚠️  数据库中暂无用户")
    
    # 判断哪些period需要刷新
    periods_to_refresh = get_periods_to_refresh(period_times)
    
    all_users = {}  # 用字典去重
    
    if periods_to_refresh:
        print(f"\n  🔄 需要刷新的排行榜: {', '.join(periods_to_refresh)}")
        print_header("第2步: 获取排行榜Top5用户")
        
        for period in periods_to_refresh:
            print(f"\n  获取 {period} 榜...")
            users = polymarket.get_leaderboard(period, limit=5)
            
            if users:
                saved = save_top_users(users, period)
                print(f"  ✓ {period}榜: {len(users)} 个用户，保存 {saved} 条记录")
                
                # 收集所有唯一用户
                for user in users:
                    address = user.get('user')
                    if address:
                        if address not in all_users:
                            all_users[address] = {
                                'address': address,
                                'periods': []
                            }
                        all_users[address]['periods'].append(f"{period}#{user.get('rank')}")
            else:
                print(f"  ✗ {period}榜: 获取失败")
        
        # 合并现有用户
        for address in existing_users:
            if address not in all_users:
                all_users[address] = {
                    'address': address,
                    'periods': ['existing']
                }
        
        print(f"\n  ✓ 总用户数: {len(all_users)} 个（新增 + 现有）")
    else:
        print(f"\n  ✓ 所有排行榜都是最新的（24小时内），使用现有用户")
        
        # 使用现有用户
        for address in existing_users:
            all_users[address] = {
                'address': address,
                'periods': ['existing']
            }
        
        print(f"  ✓ 共 {len(all_users)} 个用户")
    
    if not all_users:
        print("\n⚠️  未获取到任何用户，退出")
        return
    
    # 第3步: 收集交易活动
    print_header(f"第{'3' if periods_to_refresh else '2'}步: 收集交易活动（每人最近5条）")
    
    all_activities = []
    
    for i, (address, user_info) in enumerate(all_users.items(), 1):
        periods_str = ", ".join(user_info['periods'])
        print(f"\n  [{i}/{len(all_users)}] {address[:10]}... ({periods_str})")
        
        activities = polymarket.get_user_activities(address, limit=5)
        
        if activities:
            print(f"    ✓ 获取 {len(activities)} 条活动")
            all_activities.extend(activities)
        else:
            print(f"    ✗ 未获取到活动")
    
    # 保存活动（自动去重）
    if all_activities:
        new_count, dup_count = save_activities(all_activities)
        print(f"\n  ✓ 总活动数: {len(all_activities)}")
        print(f"  ✓ 新增: {new_count} 条")
        print(f"  ✓ 重复: {dup_count} 条")
    else:
        print(f"\n  ⚠️  未获取到任何活动")
        return
    
    # 第4步: 提取市场并调用AI分析
    print_header(f"第{'4' if periods_to_refresh else '3'}步: 提取市场并调用AI分析")
    
    # 提取所有涉及的市场ID（使用 conditionId 字段）
    market_ids = [a.get('conditionId') for a in all_activities if a.get('conditionId')]
    unique_market_ids = list(set(market_ids))
    
    print(f"\n  ✓ 涉及 {len(unique_market_ids)} 个不同市场")
    
    # 从数据库获取市场详情
    markets = get_markets_by_ids(unique_market_ids)
    
    if not markets:
        print(f"  ⚠️  数据库中未找到这些市场，从API获取...")
        
        # 从 API 获取市场详情
        markets = []
        for i, market_id in enumerate(unique_market_ids[:20], 1):  # 限制最多20个市场
            print(f"    [{i}/{min(len(unique_market_ids), 20)}] 获取市场 {market_id[:20]}...")
            
            try:
                # 使用 Gamma API 获取市场详情
                market_data = polymarket.get_market_by_condition_id(market_id)
                
                if market_data:
                    # 转换为标准格式
                    markets.append({
                        'market_id': market_id,
                        'question': market_data.get('question', ''),
                        'category': market_data.get('category', ''),
                        'current_probability': float(market_data.get('outcomePrices', [0.5, 0.5])[0]) * 100,
                        'volume_24h': float(market_data.get('volume24hr', 0)),
                        'liquidity': float(market_data.get('liquidity', 0)),
                        'polymarket_url': f"https://polymarket.com/event/{market_data.get('slug', '')}"
                    })
                    print(f"      ✓ {market_data.get('question', 'N/A')[:50]}")
                else:
                    print(f"      ✗ 未找到")
            except Exception as e:
                logger.error(f"Failed to get market {market_id}: {e}")
                print(f"      ✗ 获取失败: {e}")
                continue
    
    print(f"\n  ✓ 获取到 {len(markets)} 个市场详情")
    
    if markets:
        # 先检查哪些市场已经有 AI 分析结果（避免重复分析）
        print(f"  ✓ 检查已有的 AI 分析结果...")
        
        analyzed = []
        markets_to_analyze = []
        
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                for market in markets:
                    market_id = market.get('market_id')
                    
                    # 查询是否已有分析结果（24小时内的）
                    cursor.execute("""
                        SELECT 
                            market_id,
                            recommendation,
                            opportunity_score,
                            confidence_score,
                            ai_predicted_probability,
                            market_probability,
                            divergence,
                            reasoning,
                            created_at
                        FROM qd_polymarket_ai_analysis
                        WHERE market_id = %s
                        AND created_at > NOW() - INTERVAL '24 hours'
                        ORDER BY created_at DESC
                        LIMIT 1
                    """, (market_id,))
                    
                    row = cursor.fetchone()
                    
                    if row:
                        # 已有分析结果，直接使用
                        analyzed.append({
                            'market_id': row['market_id'],
                            'question': market.get('question'),
                            'recommendation': row['recommendation'],
                            'opportunity_score': float(row['opportunity_score']) if row['opportunity_score'] else 0,
                            'confidence_score': float(row['confidence_score']) if row['confidence_score'] else 0,
                            'market_probability': float(row['market_probability']) if row['market_probability'] else 0,
                            'reasoning': row['reasoning'],
                            'from_cache': True
                        })
                    else:
                        # 没有分析结果，需要分析
                        markets_to_analyze.append(market)
        
        except Exception as e:
            logger.error(f"Failed to check existing analysis: {e}")
            # 如果查询失败，全部重新分析
            markets_to_analyze = markets
        
        print(f"    - 已有分析: {len(analyzed)} 个")
        print(f"    - 需要分析: {len(markets_to_analyze)} 个")
        
        # 对需要分析的市场调用 AI
        if markets_to_analyze:
            print(f"  ✓ 调用 batch_analyze_markets 分析 {len(markets_to_analyze)} 个新市场...")
            
            try:
                # 调用批量分析
                new_analyzed = batch_analyzer.batch_analyze_markets(markets_to_analyze)
                
                # 合并结果
                analyzed.extend(new_analyzed)
                
                print(f"  ✓ 新分析完成: {len(new_analyzed)} 个市场")
                
            except Exception as e:
                logger.error(f"Batch analysis failed: {e}", exc_info=True)
                print(f"  ✗ 分析失败: {e}")
        
        # 统计推荐结果
        if analyzed:
            recommendations = {}
            for result in analyzed:
                rec = result.get('recommendation', 'SKIP')
                recommendations[rec] = recommendations.get(rec, 0) + 1
            
            print(f"\n  ✓ 总分析结果: {len(analyzed)} 个市场")
            print(f"    - YES推荐: {recommendations.get('YES', 0)} 个")
            print(f"    - NO推荐: {recommendations.get('NO', 0)} 个")
            print(f"    - SKIP: {recommendations.get('SKIP', 0)} 个")
            
            # 显示高分机会
            opportunities = [r for r in analyzed if r.get('recommendation') in ['YES', 'NO']]
            opportunities.sort(key=lambda x: x.get('opportunity_score', 0), reverse=True)
            
            if opportunities:
                print(f"\n  🎯 发现 {len(opportunities)} 个交易机会:")
                
                for i, opp in enumerate(opportunities[:10], 1):  # 只显示前10个
                    cache_mark = " [缓存]" if opp.get('from_cache') else ""
                    print(f"\n    [{i}] {opp.get('question', 'N/A')[:60]}{cache_mark}")
                    print(f"        推荐: {opp.get('recommendation')} | 评分: {opp.get('opportunity_score', 0):.0f}/100")
                    print(f"        置信度: {opp.get('confidence_score', 0):.0f}% | 市场概率: {opp.get('market_probability', 0):.1f}%")
                    reasoning = opp.get('reasoning', '无')[:100]
                    print(f"        理由: {reasoning}...")
    
    # 执行统计
    print_header("执行统计")
    print(f"\n  刷新的排行榜: {', '.join(periods_to_refresh) if periods_to_refresh else '无（使用现有）'}")
    print(f"  总用户数: {len(all_users)}")
    print(f"  总活动数: {len(all_activities)}")
    print(f"  新增活动: {new_count}")
    print(f"  重复活动: {dup_count}")
    print(f"  涉及市场: {len(unique_market_ids)}")
    if markets:
        if 'analyzed' in locals() and analyzed:
            print(f"  AI分析: {len(analyzed)} 个市场")
            opportunities = [r for r in analyzed if r.get('recommendation') in ['YES', 'NO']]
            print(f"  AI推荐: {len(opportunities)} 个机会")
        else:
            print(f"  AI分析: 0 个市场")
    
    print_header("执行完成")
    print(f"\n✅ 执行完成！")
    print(f"\n💡 下一步:")
    print(f"   - 查看数据库中的跟单数据")
    print(f"   - 分析顶级用户的交易模式")
    print(f"   - 参考AI推荐进行交易决策")
    print()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n⚠️  用户中断执行")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ 执行异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
