#!/usr/bin/env python
"""
自动交易最佳机会

从数据库中选择最好的可交易机会并执行交易
"""
import os
import sys
import subprocess
import json
from datetime import datetime

# ============================================================================
# 配置区域：调整这个值来控制筛选严格程度
# ============================================================================
# FILTER_LEVEL: 筛选严格程度（1-10）
#   1-3:  宽松 - 更多机会，质量参差不齐
#   4-6:  中等 - 平衡数量和质量（推荐）
#   7-10: 严格 - 只要最好的机会，数量较少
# ============================================================================
FILTER_LEVEL = 4  # 默认中等筛选

# ============================================================================
# USE_COPY_TRADING: 是否优先选择顶级用户也在交易的市场
#   True:  优先选择有顶级用户交易的市场（高置信度，推荐）
#   False: 只按 AI 评分选择市场
# ============================================================================
USE_COPY_TRADING = True  # 默认启用跟单信号
# ============================================================================

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

# 加载 .env 文件（指定完整路径）
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
load_dotenv(env_path)

from app.utils.db import get_db_connection
from app.utils.logger import get_logger

logger = get_logger(__name__)


def enrich_market_trading_data(market_id: str, question: str) -> dict:
    """
    增强单个市场的交易数据
    
    Args:
        market_id: 市场ID
        question: 市场问题
        
    Returns:
        包含 condition_id, yes_token_id, no_token_id 的字典，失败返回空字典
    """
    import requests
    
    try:
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json'
        })
        
        gamma_api = "https://gamma-api.polymarket.com"
        clob_api = "https://clob.polymarket.com"
        
        # 1. 通过 Gamma API 获取 condition_id
        search_url = f"{gamma_api}/markets"
        params = {"id": market_id}
        
        response = session.get(search_url, params=params, timeout=10)
        
        if response.status_code != 200:
            logger.warning(f"Failed to search market {market_id}: HTTP {response.status_code}")
            return {}
        
        search_results = response.json()
        
        # 找到匹配的市场
        matched_market = None
        if isinstance(search_results, list):
            for m in search_results:
                if m.get('id') == market_id:
                    matched_market = m
                    break
        elif isinstance(search_results, dict):
            if search_results.get('id') == market_id:
                matched_market = search_results
        
        if not matched_market:
            logger.warning(f"Market {market_id} not found in search results")
            return {}
        
        condition_id = matched_market.get('conditionId')
        if not condition_id:
            logger.warning(f"No condition_id for market {market_id}")
            return {}
        
        # 2. 通过 CLOB API 获取 token_id
        market_url = f"{clob_api}/markets/{condition_id}"
        
        response = session.get(market_url, timeout=10)
        
        if response.status_code != 200:
            logger.warning(f"Failed to get market details for {condition_id}: HTTP {response.status_code}")
            return {}
        
        market_info = response.json()
        
        # 提取交易数据
        accepting_orders = market_info.get('accepting_orders', True)
        tokens = market_info.get('tokens', [])
        
        if len(tokens) < 2:
            logger.warning(f"Insufficient tokens for market {market_id}: {len(tokens)} tokens")
            return {}
        
        yes_token_id = tokens[0].get('token_id')
        no_token_id = tokens[1].get('token_id')
        
        # 确保 token_id 是十六进制格式（0x开头）
        if yes_token_id and not str(yes_token_id).startswith('0x'):
            try:
                yes_token_id = hex(int(yes_token_id))
            except (ValueError, TypeError):
                pass
        
        if no_token_id and not str(no_token_id).startswith('0x'):
            try:
                no_token_id = hex(int(no_token_id))
            except (ValueError, TypeError):
                pass
        
        result = {
            'condition_id': condition_id,
            'yes_token_id': yes_token_id,
            'no_token_id': no_token_id,
            'accepting_orders': accepting_orders,
            'tokens_data': json.dumps(tokens)
        }
        
        logger.info(f"Enriched market {market_id}: condition_id={condition_id[:20]}..., yes_token={str(yes_token_id)[:20] if yes_token_id else 'None'}...")
        
        # 3. 更新数据库
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE qd_polymarket_markets
                    SET condition_id = %s,
                        yes_token_id = %s,
                        no_token_id = %s,
                        accepting_orders = %s,
                        tokens_data = %s,
                        updated_at = NOW()
                    WHERE market_id = %s
                """, (
                    condition_id,
                    yes_token_id,
                    no_token_id,
                    accepting_orders,
                    result['tokens_data'],
                    market_id
                ))
                conn.commit()
                logger.info(f"Updated market {market_id} in database")
        except Exception as e:
            logger.warning(f"Failed to update database for market {market_id}: {e}")
        
        return result
        
    except requests.RequestException as e:
        logger.warning(f"Request error enriching market {market_id}: {e}")
        return {}
    except Exception as e:
        logger.warning(f"Failed to enrich market {market_id}: {e}")
        return {}


def run_cli(cmd, timeout=10):
    """运行 CLI 命令，带超时控制"""
    # 直接使用系统环境，不做任何修改
    # 让 Polymarket CLI 使用它自己的配置（~/.polymarket/config.json 或系统配置）
    try:
        # 使用 Popen 以便更好地控制进程
        process = subprocess.Popen(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # 等待进程完成或超时
        try:
            stdout, stderr = process.communicate(timeout=timeout)
            if process.returncode == 0 and stdout:
                return stdout
            return None
        except subprocess.TimeoutExpired:
            # 超时后强制终止进程
            process.kill()
            # 清理僵尸进程
            try:
                process.communicate(timeout=1)
            except:
                pass
            return None
            
    except Exception as e:
        return None


def check_balance():
    """检查余额"""
    print("检查账户余额...")
    result = run_cli("polymarket -o json clob balance --asset-type collateral", timeout=10)
    
    if result:
        try:
            balance_data = json.loads(result)
            balance = float(balance_data.get('balance', 0))
            print(f"💰 当前余额: ${balance:.2f} USDC\n")
            return balance
        except:
            print("⚠️  无法解析余额")
            return 0
    return 0


def get_traded_markets():
    """获取已交易过的市场 token ID 列表（十进制格式）"""
    try:
        # 从 Polymarket CLI 获取交易历史
        result = run_cli("polymarket -o json clob trades", timeout=10)
        if not result:
            return set()
        
        trades_data = json.loads(result)
        
        # 数据在 'data' 字段中
        trades = trades_data.get('data', []) if isinstance(trades_data, dict) else trades_data
        
        # 提取已交易的 asset_id (十进制字符串)
        traded_tokens = set()
        for trade in trades:
            if isinstance(trade, dict):
                # asset_id 是十进制字符串
                asset_id = trade.get('asset_id')
                if asset_id:
                    traded_tokens.add(str(asset_id))
        
        return traded_tokens
    except Exception as e:
        print(f"⚠️  获取交易历史失败: {e}")
        return set()


def get_filter_params(level):
    """
    根据筛选级别返回对应的参数
    
    Args:
        level: 筛选级别 1-10
        
    Returns:
        dict: 包含所有筛选参数
    """
    # 基础参数映射
    params_map = {
        1:  {'min_score': 60, 'min_confidence': 50, 'min_liquidity': 10000,  'min_volume': 1000,  'min_price': 0.05, 'max_price': 0.95},
        2:  {'min_score': 65, 'min_confidence': 55, 'min_liquidity': 20000,  'min_volume': 2000,  'min_price': 0.08, 'max_price': 0.92},
        3:  {'min_score': 70, 'min_confidence': 58, 'min_liquidity': 30000,  'min_volume': 3000,  'min_price': 0.10, 'max_price': 0.90},
        4:  {'min_score': 73, 'min_confidence': 60, 'min_liquidity': 40000,  'min_volume': 4000,  'min_price': 0.12, 'max_price': 0.88},
        5:  {'min_score': 75, 'min_confidence': 60, 'min_liquidity': 50000,  'min_volume': 5000,  'min_price': 0.15, 'max_price': 0.85},
        6:  {'min_score': 77, 'min_confidence': 65, 'min_liquidity': 75000,  'min_volume': 7500,  'min_price': 0.18, 'max_price': 0.82},
        7:  {'min_score': 80, 'min_confidence': 65, 'min_liquidity': 100000, 'min_volume': 10000, 'min_price': 0.20, 'max_price': 0.80},
        8:  {'min_score': 82, 'min_confidence': 70, 'min_liquidity': 150000, 'min_volume': 15000, 'min_price': 0.25, 'max_price': 0.75},
        9:  {'min_score': 85, 'min_confidence': 70, 'min_liquidity': 200000, 'min_volume': 20000, 'min_price': 0.30, 'max_price': 0.70},
        10: {'min_score': 88, 'min_confidence': 75, 'min_liquidity': 300000, 'min_volume': 30000, 'min_price': 0.35, 'max_price': 0.65},
    }
    
    # 限制范围
    level = max(1, min(10, level))
    return params_map[level]


def get_best_opportunities(max_count=3, filter_level=5, use_copy_trading=True):
    """
    从数据库获取最佳可交易机会（返回前N个）
    
    Args:
        max_count: 最多返回多少个机会
        filter_level: 筛选严格程度（1-10）
        use_copy_trading: 是否优先选择顶级用户也在交易的市场（高置信度）
    """
    # 获取筛选参数
    params = get_filter_params(filter_level)
    min_score = params['min_score']
    min_confidence = params['min_confidence']
    min_liquidity = params['min_liquidity']
    min_volume = params['min_volume']
    min_price = params['min_price']
    max_price = params['max_price']
    
    level_desc = "宽松" if filter_level <= 3 else ("严格" if filter_level >= 7 else "中等")
    
    print(f"🔍 从数据库搜索前 {max_count} 个最佳机会...")
    print(f"   筛选级别: {filter_level}/10 ({level_desc})")
    print(f"   评分≥{min_score}, 置信度≥{min_confidence}%, 流动性≥${min_liquidity:,}, 交易量≥${min_volume:,}")
    print(f"   价格范围: ${min_price:.2f} - ${max_price:.2f}")
    if use_copy_trading:
        print(f"   🎯 优先选择: 顶级用户也在交易的市场（高置信度机会）")
    
    # 获取已交易过的市场
    print("检查交易历史...")
    traded_tokens = get_traded_markets()
    if traded_tokens:
        print(f"✓ 找到 {len(traded_tokens)} 个已交易的市场，将自动排除\n")
    else:
        print("✓ 无交易历史或无法获取\n")
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        if use_copy_trading:
            # 查询6: 高分 AI 推荐 + 顶级用户也在交易的市场（高置信度机会）
            query = """
                WITH top_user_markets AS (
                    -- 获取顶级用户最近24小时交易的市场
                    SELECT DISTINCT
                        a.market_id,
                        COUNT(DISTINCT a.user_address) as top_users_count,
                        STRING_AGG(DISTINCT u.rank::text, ', ' ORDER BY u.rank::text) as user_ranks,
                        STRING_AGG(DISTINCT a.outcome, ', ') as user_outcomes
                    FROM qd_polymarket_user_activities a
                    LEFT JOIN qd_polymarket_top_users u ON u.user_address = a.user_address
                        AND DATE(u.created_at) = CURRENT_DATE
                        AND u.rank <= 20
                    WHERE a.timestamp > NOW() - INTERVAL '24 hours'
                    GROUP BY a.market_id
                    HAVING COUNT(DISTINCT a.user_address) > 0
                )
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
                    m.liquidity,
                    m.slug,
                    m.condition_id,
                    m.yes_token_id,
                    m.no_token_id,
                    m.accepting_orders,
                    m.tokens_data,
                    m.outcome_tokens,
                    COALESCE(tum.top_users_count, 0) as top_users_count,
                    tum.user_ranks,
                    tum.user_outcomes
                FROM qd_polymarket_ai_analysis a
                INNER JOIN qd_polymarket_markets m ON a.market_id = m.market_id
                LEFT JOIN top_user_markets tum ON tum.market_id = a.market_id
                WHERE a.recommendation IN ('YES', 'NO')
                  AND a.opportunity_score >= %s
                  AND a.confidence_score >= %s
                  AND m.liquidity >= %s
                  AND m.volume_24h >= %s
                  AND m.status = 'active'
                  AND (m.end_date_iso IS NULL OR m.end_date_iso > NOW())
                  AND a.created_at > NOW() - INTERVAL '24 hours'
                ORDER BY a.market_id,
                         COALESCE(tum.top_users_count, 0) DESC,  -- 优先顶级用户交易的市场
                         a.opportunity_score DESC,
                         a.created_at DESC
            """
        else:
            # 原始查询：只按 AI 评分排序
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
                    m.liquidity,
                    m.slug,
                    m.condition_id,
                    m.yes_token_id,
                    m.no_token_id,
                    m.accepting_orders,
                    m.tokens_data,
                    m.outcome_tokens,
                    0 as top_users_count,
                    NULL as user_ranks,
                    NULL as user_outcomes
                FROM qd_polymarket_ai_analysis a
                INNER JOIN qd_polymarket_markets m ON a.market_id = m.market_id
                WHERE a.opportunity_score >= %s
                  AND a.confidence_score >= %s
                  AND m.liquidity >= %s
                  AND m.volume_24h >= %s
                  AND m.status = 'active'
                  AND (m.end_date_iso IS NULL OR m.end_date_iso > NOW())
                ORDER BY a.market_id,
                         a.created_at DESC
            """
        
        cursor.execute(query, (min_score, min_confidence, min_liquidity, min_volume))
        all_candidates = cursor.fetchall()
        
        # 按综合评分排序：
        # 优先级：
        # 1. 有顶级用户交易 + AI 推荐方向一致（最高优先级）
        # 2. 有顶级用户交易（次优先级）
        # 3. AI 评分高（基础优先级）
        if use_copy_trading:
            def calculate_priority(x):
                top_users_count = int(x.get('top_users_count', 0))
                ai_score = float(x['opportunity_score'])
                volume_weight = float(x['volume_24h']) / 100000
                
                # 检查 AI 推荐方向是否与顶级用户一致
                recommendation = x['recommendation']
                user_outcomes = x.get('user_outcomes', '')
                direction_match = recommendation in user_outcomes if user_outcomes else False
                
                # 计算综合得分
                if top_users_count > 0:
                    if direction_match:
                        # 最高优先级：有跟单 + 方向一致
                        # 基础分 1000 + 用户数量权重 + AI评分
                        return 1000 + (top_users_count * 50) + (ai_score * 0.7) + (volume_weight * 0.3)
                    else:
                        # 次优先级：有跟单但方向不一致或未知
                        # 基础分 500 + 用户数量权重 + AI评分
                        return 500 + (top_users_count * 30) + (ai_score * 0.7) + (volume_weight * 0.3)
                else:
                    # 基础优先级：只有 AI 推荐
                    return (ai_score * 0.7) + (volume_weight * 0.3)
            
            candidates = sorted(all_candidates, key=calculate_priority, reverse=True)
        else:
            candidates = sorted(
                all_candidates,
                key=lambda x: (
                    float(x['opportunity_score']) * 0.7 +     # 70%权重给AI评分
                    (float(x['volume_24h']) / 100000) * 0.3   # 30%权重给交易量
                ),
                reverse=True
            )
        
        if not candidates:
            print("❌ 数据库中没有找到符合条件的机会")
            print("💡 提示: 运行 run_once_polymarket_worker.py 收集更多数据")
            return []
        
        # 统计顶级用户交易的市场数量
        if use_copy_trading:
            top_user_markets = [c for c in candidates if c.get('top_users_count', 0) > 0]
            direction_match_markets = []
            
            for c in top_user_markets:
                recommendation = c['recommendation']
                user_outcomes = c.get('user_outcomes', '')
                if recommendation in user_outcomes:
                    direction_match_markets.append(c)
            
            if direction_match_markets:
                print(f"找到 {len(candidates)} 个预筛选的候选机会")
                print(f"  其中 {len(direction_match_markets)} 个有顶级用户交易且方向一致 ⭐")
                print(f"  其中 {len(top_user_markets) - len(direction_match_markets)} 个有顶级用户交易但方向不一致")
            elif top_user_markets:
                print(f"找到 {len(candidates)} 个预筛选的候选机会，其中 {len(top_user_markets)} 个有顶级用户交易")
            else:
                print(f"找到 {len(candidates)} 个预筛选的候选机会（无顶级用户交易数据）")
        else:
            print(f"找到 {len(candidates)} 个预筛选的候选机会")
        
        print(f"将遍历直到找到 {max_count} 个可交易机会...\n")
    
    # 验证每个候选市场的价格，收集可交易的机会
    valid_opportunities = []
    checked_count = 0
    skipped_reasons = {
        'traded': 0,
        'price_low': 0,
        'price_high': 0,
        'no_db_price': 0,
        'buy_price_timeout': 0,
        'buy_price_invalid': 0,
        'enrich_failed': 0,
        'not_accepting': 0,
        'error': 0
    }
    
    for i, candidate in enumerate(candidates, 1):
        market_id = candidate['market_id']
        question = candidate['question']
        recommendation = candidate['recommendation']
        condition_id = candidate['condition_id']
        yes_token_id = candidate['yes_token_id']
        no_token_id = candidate['no_token_id']
        
        # 如果已经找到足够的机会，停止搜索
        if len(valid_opportunities) >= max_count:
            print(f"\n✓ 已找到 {max_count} 个可交易机会，停止搜索")
            break
        
        checked_count += 1
        print(f"[{checked_count}/{len(candidates)}] {question[:50]}...")
        print(f"  评分: {candidate['opportunity_score']:.0f} | 置信度: {candidate['confidence_score']:.0f}%")
        print(f"  推荐: {recommendation} | 流动性: ${candidate['liquidity']:,.0f}")
        
        # 显示顶级用户交易信息
        top_users_count = candidate.get('top_users_count', 0)
        if top_users_count > 0:
            user_ranks = candidate.get('user_ranks', '')
            user_outcomes = candidate.get('user_outcomes', '')
            
            # 检查方向是否一致
            direction_match = recommendation in user_outcomes if user_outcomes else False
            match_indicator = "⭐ 方向一致" if direction_match else "方向不同"
            
            print(f"  🎯 顶级用户: {top_users_count} 人交易 (排名: {user_ranks}, 方向: {user_outcomes}) {match_indicator}")
        
        # 调试：检查reasoning字段
        reasoning = candidate.get('reasoning', '')
        if reasoning:
            print(f"  AI理由预览: {reasoning[:80]}...")
        else:
            print(f"  ⚠️  数据库中无AI理由")
        
        # 检查是否有交易数据，如果没有则增强
        if not condition_id or not yes_token_id or not no_token_id:
            print(f"  ⚠️  缺少交易数据，正在增强...")
            enriched_data = enrich_market_trading_data(market_id, question)
            
            if enriched_data:
                # 更新候选市场的数据1
                condition_id = enriched_data.get('condition_id')
                yes_token_id = enriched_data.get('yes_token_id')
                no_token_id = enriched_data.get('no_token_id')
                candidate['condition_id'] = condition_id
                candidate['yes_token_id'] = yes_token_id
                candidate['no_token_id'] = no_token_id
                candidate['accepting_orders'] = enriched_data.get('accepting_orders', True)
                candidate['tokens_data'] = enriched_data.get('tokens_data')
                print(f"  ✓ 增强成功")
            else:
                print(f"  ✗ 增强失败，跳过\n")
                skipped_reasons['enrich_failed'] += 1
                continue
        
        # 检查市场是否接受订单
        if not candidate.get('accepting_orders', True):
            print(f"  ⚠️  市场不接受订单，跳过\n")
            skipped_reasons['not_accepting'] += 1
            continue
        
        try:
            # 根据推荐选择 token
            if recommendation.upper() == 'YES':
                token_id = yes_token_id
            else:
                token_id = no_token_id
            
            # 检查是否已交易过这个 token
            token_id_dec = str(int(token_id, 16)) if token_id else None
            if token_id_dec and token_id_dec in traded_tokens:
                print(f"  ⊗ 已交易过此市场，跳过\n")
                skipped_reasons['traded'] += 1
                continue
            
            # 从数据库获取 token 价格（如果有）
            tokens_data = candidate.get('tokens_data')
            token_price = None
            
            if tokens_data:
                try:
                    import json as json_lib
                    if isinstance(tokens_data, str):
                        tokens_data = json_lib.loads(tokens_data)
                    
                    # token_id 可能是十六进制或十进制格式，需要都尝试
                    token_id_hex = token_id
                    token_id_dec = str(int(token_id, 16)) if token_id and token_id.startswith('0x') else token_id
                    
                    for token in tokens_data:
                        tid = token.get('token_id')
                        # 比较时统一转换为字符串
                        if str(tid) == token_id_hex or str(tid) == token_id_dec:
                            token_price = float(token.get('price', 0))
                            break
                except Exception as e:
                    logger.debug(f"Failed to parse tokens_data: {e}")
            
            # 如果数据库没有价格，从 outcome_tokens 获取
            if token_price is None:
                outcome_tokens = candidate.get('outcome_tokens')
                if outcome_tokens:
                    try:
                        import json as json_lib
                        if isinstance(outcome_tokens, str):
                            outcome_tokens = json_lib.loads(outcome_tokens)
                        
                        token_data = outcome_tokens.get(recommendation.upper(), {})
                        token_price = float(token_data.get('price', 0))
                    except:
                        pass
            
            if token_price:
                print(f"  Token 价格: ${token_price:.4f} (来自数据库)")
            else:
                print(f"  ⚠️  数据库无价格，跳过")
                skipped_reasons['no_db_price'] += 1
                continue
            
            # 检查价格是否合理（使用配置的阈值）
            if token_price < min_price:
                print(f"  ✗ 价格太低 ({token_price:.4f} < {min_price:.2f})\n")
                skipped_reasons['price_low'] += 1
                continue
            elif token_price > max_price:
                print(f"  ✗ 价格太高 ({token_price:.4f} > {max_price:.2f})\n")
                skipped_reasons['price_high'] += 1
                continue
            
            # 获取实时买入价（这是唯一需要的 CLI 查询）
            price_result = run_cli(f'polymarket -o json clob price {token_id} --side buy', timeout=10)
            if not price_result:
                print(f"  ✗ 获取实时价格超时，跳过\n")
                skipped_reasons['buy_price_timeout'] += 1
                continue
            
            price_data = json.loads(price_result)
            buy_price = float(price_data.get('price', 0))
            
            print(f"  实时买入价: ${buy_price:.4f}")
            
            if buy_price < min_price or buy_price > max_price:
                print(f"  ✗ 买入价不合理 ({buy_price:.4f} 不在 {min_price:.2f}-{max_price:.2f} 范围)\n")
                skipped_reasons['buy_price_invalid'] += 1
                continue
            
            # 找到合适的市场！
            print(f"  ✅ 可交易！\n")
            
            # 构建Polymarket URL
            slug = candidate.get('slug')
            polymarket_url = f"https://polymarket.com/event/{slug}" if slug else f"https://polymarket.com/markets?id={market_id}"
            
            valid_opportunities.append({
                'market_id': market_id,
                'question': question,
                'category': candidate['category'],
                'recommendation': recommendation,
                'opportunity_score': float(candidate['opportunity_score']),
                'confidence_score': float(candidate['confidence_score']),
                'reasoning': candidate.get('reasoning', '暂无AI分析理由'),
                'volume_24h': float(candidate['volume_24h']),
                'liquidity': float(candidate['liquidity']),
                'token_id': token_id,
                'buy_price': buy_price,
                'condition_id': condition_id,
                'polymarket_url': polymarket_url,
                'top_users_count': candidate.get('top_users_count', 0),
                'user_ranks': candidate.get('user_ranks', ''),
                'user_outcomes': candidate.get('user_outcomes', '')
            })
            
        except json.JSONDecodeError:
            print(f"  ✗ JSON 解析错误，跳过\n")
            skipped_reasons['error'] += 1
            continue
        except ValueError:
            print(f"  ✗ 数值转换错误，跳过\n")
            skipped_reasons['error'] += 1
            continue
        except Exception as e:
            print(f"  ✗ 错误: {e}，跳过\n")
            skipped_reasons['error'] += 1
            continue
    
    # 打印统计信息
    print("=" * 80)
    print(f"搜索统计:")
    print(f"  检查市场数: {checked_count}/{len(candidates)}")
    print(f"  找到可交易: {len(valid_opportunities)}")
    if skipped_reasons['enrich_failed'] > 0:
        print(f"  增强失败: {skipped_reasons['enrich_failed']}")
    if skipped_reasons['not_accepting'] > 0:
        print(f"  不接受订单: {skipped_reasons['not_accepting']}")
    if skipped_reasons['traded'] > 0:
        print(f"  已交易过: {skipped_reasons['traded']}")
    if skipped_reasons['price_low'] > 0:
        print(f"  价格太低: {skipped_reasons['price_low']}")
    if skipped_reasons['price_high'] > 0:
        print(f"  价格太高: {skipped_reasons['price_high']}")
    if skipped_reasons['no_db_price'] > 0:
        print(f"  无数据库价格: {skipped_reasons['no_db_price']}")
    if skipped_reasons['buy_price_timeout'] > 0:
        print(f"  获取价格超时: {skipped_reasons['buy_price_timeout']}")
    if skipped_reasons['buy_price_invalid'] > 0:
        print(f"  买入价不合理: {skipped_reasons['buy_price_invalid']}")
    if skipped_reasons['error'] > 0:
        print(f"  其他错误: {skipped_reasons['error']}")
    print("=" * 80)
    
    if valid_opportunities:
        print(f"\n✅ 找到 {len(valid_opportunities)} 个可交易机会！\n")
    else:
        print("\n❌ 没有找到价格合理的可交易机会")
        print("💡 提示:")
        if skipped_reasons['enrich_failed'] > 0:
            print(f"   - {skipped_reasons['enrich_failed']} 个市场无法获取交易数据（API可能不可用）")
        if skipped_reasons['not_accepting'] > 0:
            print(f"   - {skipped_reasons['not_accepting']} 个市场不接受订单（市场可能已关闭或暂停交易）")
        if skipped_reasons['price_high'] > 0 or skipped_reasons['price_low'] > 0:
            print(f"   - 大部分市场价格太高或太低（不在 0.10-0.90 范围）")
        print("   - 降低筛选标准或手动选择市场交易")
    
    return valid_opportunities


def execute_trade(opportunity, amount=1.0):
    """执行交易（实际下单部分）"""
    # 执行市价单
    print(f"\n正在执行市价单...")
    cmd = f"polymarket clob market-order --token {opportunity['token_id']} --side buy --amount {amount}"
    
    print(f"执行命令: {cmd}")
    
    # 直接执行命令，不传递任何环境变量
    # 让 Polymarket CLI 使用它自己的配置
    try:
        process = subprocess.Popen(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        try:
            stdout, stderr = process.communicate(timeout=30)
            
            if process.returncode == 0 and stdout:
                print(f"\n✅ 交易成功！")
                print(stdout)
                
                # 等待几秒后查询持仓
                import time
                print(f"\n等待 5 秒后查询持仓...")
                time.sleep(5)
                
                # 查询持仓
                wallet_result = run_cli("polymarket wallet address", timeout=10)
                if wallet_result:
                    wallet_address = wallet_result.strip()
                    positions_result = run_cli(f"polymarket data positions {wallet_address}", timeout=10)
                    if positions_result:
                        print(f"\n📊 当前持仓:")
                        print(positions_result)
                
                # 查询余额
                balance_result = run_cli("polymarket -o json clob balance --asset-type collateral", timeout=10)
                if balance_result:
                    try:
                        balance_data = json.loads(balance_result)
                        balance = float(balance_data.get('balance', 0))
                        print(f"\n💰 剩余余额: ${balance:.2f} USDC")
                    except:
                        pass
                
                return True
            else:
                # 交易失败，显示详细错误
                print(f"\n❌ 交易失败")
                print(f"\n返回码: {process.returncode}")
                
                if stdout:
                    print(f"\n标准输出:")
                    print(stdout)
                
                if stderr:
                    print(f"\n错误输出:")
                    print(stderr)
                
                # 分析常见错误
                error_text = (stdout + stderr).lower()
                print(f"\n可能的原因:")
                
                if 'insufficient' in error_text or 'balance' in error_text:
                    print("  • 余额不足")
                    print("  • 建议: 检查钱包余额 (polymarket clob balance)")
                elif 'timeout' in error_text or 'timed out' in error_text:
                    print("  • 网络超时")
                    print("  • 建议: 检查网络连接，稍后重试")
                elif 'price' in error_text or 'slippage' in error_text:
                    print("  • 价格滑点过大或价格已变化")
                    print("  • 建议: 市场价格波动，重新获取机会")
                elif 'not found' in error_text or '404' in error_text:
                    print("  • 市场或代币不存在")
                    print("  • 建议: 市场可能已关闭或结算")
                elif 'unauthorized' in error_text or 'auth' in error_text:
                    print("  • 认证失败")
                    print("  • 建议: 检查私钥配置 (polymarket wallet address)")
                elif 'order' in error_text and 'reject' in error_text:
                    print("  • 订单被拒绝")
                    print("  • 建议: 可能是价格、数量或市场状态问题")
                else:
                    print("  • 未知错误")
                    print("  • 建议: 查看上方错误输出，或手动执行命令测试")
                
                return False
                
        except subprocess.TimeoutExpired:
            process.kill()
            try:
                process.communicate(timeout=1)
            except:
                pass
            
            print(f"\n❌ 交易超时（30秒）")
            print(f"\n可能的原因:")
            print("  • 网络连接缓慢")
            print("  • Polymarket API 响应慢")
            print("  • 建议: 检查网络连接，稍后重试")
            return False
            
    except Exception as e:
        print(f"\n❌ 执行命令时发生异常")
        print(f"错误类型: {type(e).__name__}")
        print(f"错误信息: {str(e)}")
        return False



def main():
    print("=" * 80)
    print("Polymarket 自动交易最佳机会")
    print("=" * 80)
    print(f"\n⏰ 执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"\n⚠️  这是真实交易，会使用真实资金")
    print(f"   交易金额: $1.00 USDC (最小订单金额)\n")
    
    # # 1. 检查余额
    # balance = check_balance()
    # if balance < 1.0:
    #     print("❌ 余额不足 $1.00 USDC")
    #     print("   请先充值到钱包")
    #     return
    
    # 2. 获取最佳机会（使用全局配置的筛选级别和跟单设置）
    print("=" * 80)
    opportunities = get_best_opportunities(
        max_count=3, 
        filter_level=FILTER_LEVEL,
        use_copy_trading=USE_COPY_TRADING
    )
    
    if not opportunities:
        print("\n💡 建议:")
        print("   1. 运行 worker 获取更多市场数据")
        print("   2. 降低筛选标准（评分阈值）")
        print("   3. 手动选择市场交易")
        return
    
    # 3. 显示所有机会
    print("=" * 80)
    print(f"找到 {len(opportunities)} 个可交易机会")
    print("=" * 80)
    
    for i, opp in enumerate(opportunities, 1):
        # 检查方向是否一致
        direction_match = False
        if opp.get('top_users_count', 0) > 0:
            user_outcomes = opp.get('user_outcomes', '')
            direction_match = opp['recommendation'] in user_outcomes if user_outcomes else False
        
        match_indicator = " ⭐" if direction_match else ""
        
        print(f"\n机会 #{i}{match_indicator}:")
        print(f"  问题: {opp['question'][:60]}")
        print(f"  推荐: {opp['recommendation']}")
        print(f"  评分: {opp['opportunity_score']:.0f}/100")
        print(f"  置信度: {opp['confidence_score']:.0f}%")
        print(f"  价格: ${opp['buy_price']:.4f}")
        print(f"  流动性: ${opp['liquidity']:,.0f}")
        
        # 显示顶级用户交易信息
        if opp.get('top_users_count', 0) > 0:
            print(f"  🎯 顶级用户: {opp['top_users_count']} 人交易")
            print(f"     排名: {opp.get('user_ranks', 'N/A')}")
            print(f"     方向: {opp.get('user_outcomes', 'N/A')}")
            if direction_match:
                print(f"     ⭐ AI 推荐方向与顶级用户一致（高置信度）")
        
        # 显示AI理由的前150个字符作为预览
        reasoning_preview = opp['reasoning'][:150] + "..." if len(opp['reasoning']) > 150 else opp['reasoning']
        print(f"  AI理由: {reasoning_preview}")
        print(f"  交易命令: polymarket clob market-order --token {opp['token_id']} --side buy --amount 1.0")
        print(f"  链接: {opp.get('polymarket_url', 'N/A')}")
    
    # 4. 让用户选择
    print(f"\n{'=' * 80}")
    print("请选择要交易的机会（输入编号 1-{}, 或 'all' 交易所有, 或 'q' 退出）:".format(len(opportunities)))
    print("⚠️  选择后将直接执行交易，请仔细查看上述信息")
    choice = input("选择: ").strip().lower()
    
    if choice == 'q':
        print("\n❌ 取消交易")
        return
    
    # 确定要交易的机会
    selected_opportunities = []
    if choice == 'all':
        selected_opportunities = opportunities
    else:
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(opportunities):
                selected_opportunities = [opportunities[idx]]
            else:
                print(f"\n❌ 无效选择")
                return
        except ValueError:
            print(f"\n❌ 无效输入")
            return
    
    # 5. 执行交易
    successful_trades = 0
    failed_trades = 0
    
    for i, opportunity in enumerate(selected_opportunities, 1):
        print(f"\n{'=' * 80}")
        print(f"执行交易 {i}/{len(selected_opportunities)}")
        print(f"{'=' * 80}")
        
        # 显示完整信息
        print(f"\n📊 市场信息:")
        print(f"   问题: {opportunity['question']}")
        print(f"   分类: {opportunity['category']}")
        print(f"   Market ID: {opportunity['market_id']}")
        print(f"   链接: {opportunity.get('polymarket_url', 'N/A')}")
        
        print(f"\n🤖 AI 分析:")
        print(f"   机会评分: {opportunity['opportunity_score']:.0f}/100")
        print(f"   置信度: {opportunity['confidence_score']:.0f}%")
        print(f"   推荐: 买入 {opportunity['recommendation']}")
        print(f"\n   📝 AI 理由:")
        # 格式化显示理由，每行缩进
        reasoning_lines = opportunity['reasoning'].split('\n')
        for line in reasoning_lines:
            print(f"      {line}")
        
        print(f"\n💹 市场数据:")
        print(f"   流动性: ${opportunity['liquidity']:,.0f}")
        print(f"   24h交易量: ${opportunity['volume_24h']:,.0f}")
        print(f"   当前价格: ${opportunity['buy_price']:.4f}")
        
        # 显示顶级用户交易信息
        if opportunity.get('top_users_count', 0) > 0:
            user_outcomes = opportunity.get('user_outcomes', '')
            direction_match = opportunity['recommendation'] in user_outcomes if user_outcomes else False
            
            print(f"\n🎯 顶级用户跟单信号:")
            print(f"   交易人数: {opportunity['top_users_count']} 位顶级用户")
            print(f"   用户排名: {opportunity.get('user_ranks', 'N/A')}")
            print(f"   交易方向: {opportunity.get('user_outcomes', 'N/A')}")
            
            if direction_match:
                print(f"   ⭐ AI 推荐方向与顶级用户一致（高置信度机会）")
                print(f"   💡 这些顶级用户也在交易此市场，且方向与 AI 推荐一致")
            else:
                print(f"   💡 这些顶级用户也在交易此市场，但方向可能不同")
        
        print(f"\n💰 订单详情:")
        print(f"   Token ID: {opportunity['token_id']}")
        print(f"   方向: BUY {opportunity['recommendation']}")
        print(f"   金额: $1.00 USDC")
        print(f"   预计份额: {1.0 / opportunity['buy_price']:.2f}")
        
        # 计算预期收益
        potential_return = (1.0 - opportunity['buy_price']) / opportunity['buy_price'] * 100
        print(f"   预期收益率: {potential_return:.1f}%")
        
        # 直接执行交易
        success = execute_trade(opportunity, amount=1.0)
        
        if success:
            successful_trades += 1
        else:
            failed_trades += 1
        
        # 如果还有更多交易，等待一下
        if i < len(selected_opportunities):
            import time
            print("\n等待 3 秒后继续下一笔交易...")
            time.sleep(3)
    
    # 6. 总结
    print(f"\n{'=' * 80}")
    print("交易总结")
    print(f"{'=' * 80}")
    print(f"  成功: {successful_trades}")
    print(f"  失败: {failed_trades}")
    print(f"  总计: {len(selected_opportunities)}")
    
    if successful_trades > 0:
        print(f"\n💡 下一步:")
        print(f"   1. 查看订单: polymarket clob orders")
        print(f"   2. 查看交易: polymarket clob trades")
        print(f"   3. 查看持仓: polymarket data positions <YOUR_ADDRESS>")


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
