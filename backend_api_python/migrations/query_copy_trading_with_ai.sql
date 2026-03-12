-- Polymarket 跟单系统 - 关联查询（跟单活动 + AI 分析）
-- 通过 condition_id 关联跟单活动和市场，再通过 market_id 关联 AI 分析

-- ============================================================================
-- 查询1: 最近的跟单活动及其 AI 分析结果
-- ============================================================================
SELECT 
    a.activity_id,
    a.user_address,
    u.rank as user_rank,
    u.win_rate as user_win_rate,
    a.side,
    a.outcome,
    a.size,
    a.price,
    a.timestamp as activity_time,
    m.market_id,
    m.question,
    m.current_probability as market_probability,
    ai.recommendation as ai_recommendation,
    ai.opportunity_score as ai_score,
    ai.confidence_score as ai_confidence,
    ai.ai_predicted_probability as ai_probability,
    ai.divergence as ai_divergence,
    ai.reasoning as ai_reasoning,
    ai.created_at as ai_analysis_time
FROM qd_polymarket_user_activities a
-- 通过 condition_id 关联市场（活动的 market_id 实际是 condition_id）
LEFT JOIN qd_polymarket_markets m ON m.condition_id = a.market_id
-- 通过数字 market_id 关联 AI 分析
LEFT JOIN qd_polymarket_ai_analysis ai ON ai.market_id = m.market_id
-- 关联用户排名信息
LEFT JOIN qd_polymarket_top_users u ON u.user_address = a.user_address 
    AND DATE(u.created_at) = CURRENT_DATE
WHERE a.timestamp > NOW() - INTERVAL '24 hours'
ORDER BY a.timestamp DESC
LIMIT 20;

-- ============================================================================
-- 查询2: 统计 - 跟单活动的 AI 分析覆盖率
-- ============================================================================
SELECT 
    COUNT(DISTINCT a.activity_id) as total_activities,
    COUNT(DISTINCT CASE WHEN m.market_id IS NOT NULL THEN a.activity_id END) as activities_with_market,
    COUNT(DISTINCT CASE WHEN ai.market_id IS NOT NULL THEN a.activity_id END) as activities_with_ai,
    ROUND(100.0 * COUNT(DISTINCT CASE WHEN m.market_id IS NOT NULL THEN a.activity_id END) / 
          NULLIF(COUNT(DISTINCT a.activity_id), 0), 2) as market_coverage_pct,
    ROUND(100.0 * COUNT(DISTINCT CASE WHEN ai.market_id IS NOT NULL THEN a.activity_id END) / 
          NULLIF(COUNT(DISTINCT a.activity_id), 0), 2) as ai_coverage_pct
FROM qd_polymarket_user_activities a
LEFT JOIN qd_polymarket_markets m ON m.condition_id = a.market_id
LEFT JOIN qd_polymarket_ai_analysis ai ON ai.market_id = m.market_id
WHERE a.timestamp > NOW() - INTERVAL '24 hours';

-- ============================================================================
-- 查询3: 顶级用户的交易 vs AI 推荐对比
-- ============================================================================
SELECT 
    u.user_address,
    u.rank,
    u.win_rate,
    m.question,
    a.side as user_action,
    a.outcome as user_outcome,
    ai.recommendation as ai_recommendation,
    ai.opportunity_score as ai_score,
    CASE 
        WHEN (a.outcome = 'YES' AND ai.recommendation = 'YES') OR 
             (a.outcome = 'NO' AND ai.recommendation = 'NO') THEN '✓ 一致'
        WHEN ai.recommendation IS NULL THEN '- 无AI分析'
        ELSE '✗ 不一致'
    END as alignment,
    a.timestamp as activity_time
FROM qd_polymarket_user_activities a
JOIN qd_polymarket_top_users u ON u.user_address = a.user_address 
    AND DATE(u.created_at) = CURRENT_DATE
LEFT JOIN qd_polymarket_markets m ON m.condition_id = a.market_id
LEFT JOIN qd_polymarket_ai_analysis ai ON ai.market_id = m.market_id
WHERE a.timestamp > NOW() - INTERVAL '24 hours'
    AND u.rank <= 10  -- 只看前10名用户
ORDER BY u.rank, a.timestamp DESC;

-- ============================================================================
-- 查询4: 检查 condition_id 填充情况
-- ============================================================================
SELECT 
    COUNT(*) as total_markets,
    COUNT(condition_id) as markets_with_condition_id,
    COUNT(*) - COUNT(condition_id) as markets_without_condition_id,
    ROUND(100.0 * COUNT(condition_id) / NULLIF(COUNT(*), 0), 2) as condition_id_coverage_pct
FROM qd_polymarket_markets;

-- ============================================================================
-- 查询5: 需要更新 condition_id 的市场
-- ============================================================================
SELECT 
    market_id,
    question,
    category,
    volume_24h,
    updated_at
FROM qd_polymarket_markets
WHERE condition_id IS NULL
    AND status = 'active'
ORDER BY volume_24h DESC
LIMIT 20;

-- ============================================================================
-- 查询6: 高分 AI 推荐 + 顶级用户也在交易的市场（高置信度机会）
-- ============================================================================
SELECT 
    m.market_id,
    m.question,
    ai.recommendation,
    ai.opportunity_score,
    ai.confidence_score,
    COUNT(DISTINCT a.user_address) as top_users_trading,
    STRING_AGG(DISTINCT u.rank::text, ', ' ORDER BY u.rank::text) as user_ranks,
    STRING_AGG(DISTINCT a.outcome, ', ') as user_outcomes,
    ai.reasoning
FROM qd_polymarket_ai_analysis ai
JOIN qd_polymarket_markets m ON m.market_id = ai.market_id
LEFT JOIN qd_polymarket_user_activities a ON a.market_id = m.condition_id
    AND a.timestamp > NOW() - INTERVAL '24 hours'
LEFT JOIN qd_polymarket_top_users u ON u.user_address = a.user_address
    AND DATE(u.created_at) = CURRENT_DATE
    AND u.rank <= 20
WHERE ai.recommendation IN ('YES', 'NO')
    AND ai.opportunity_score >= 70
    AND ai.created_at > NOW() - INTERVAL '24 hours'
GROUP BY m.market_id, m.question, ai.recommendation, ai.opportunity_score, 
         ai.confidence_score, ai.reasoning
HAVING COUNT(DISTINCT a.user_address) > 0  -- 至少有一个顶级用户在交易
ORDER BY ai.opportunity_score DESC, COUNT(DISTINCT a.user_address) DESC
LIMIT 10;
