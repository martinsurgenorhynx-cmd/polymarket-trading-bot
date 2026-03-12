-- 查询 Polymarket AI 分析结果
-- 按时间倒序，显示最近的分析

-- 基本查询：最近 20 条分析结果
SELECT 
    a.market_id,
    m.question,
    a.recommendation,
    a.opportunity_score,
    a.confidence_score,
    a.ai_predicted_probability,
    a.market_probability,
    a.divergence,
    a.reasoning,
    a.created_at
FROM qd_polymarket_ai_analysis a
LEFT JOIN qd_polymarket_markets m ON a.market_id = m.market_id
ORDER BY a.created_at DESC
LIMIT 20;

-- 查询推荐为 YES 的机会（按机会评分排序）
-- SELECT 
--     a.market_id,
--     m.question,
--     a.recommendation,
--     a.opportunity_score,
--     a.confidence_score,
--     a.ai_predicted_probability,
--     a.market_probability,
--     a.divergence,
--     a.reasoning,
--     a.created_at
-- FROM qd_polymarket_ai_analysis a
-- LEFT JOIN qd_polymarket_markets m ON a.market_id = m.market_id
-- WHERE a.recommendation = 'YES'
-- ORDER BY a.opportunity_score DESC, a.created_at DESC
-- LIMIT 20;

-- 查询推荐为 NO 的机会（按机会评分排序）
-- SELECT 
--     a.market_id,
--     m.question,
--     a.recommendation,
--     a.opportunity_score,
--     a.confidence_score,
--     a.ai_predicted_probability,
--     a.market_probability,
--     a.divergence,
--     a.reasoning,
--     a.created_at
-- FROM qd_polymarket_ai_analysis a
-- LEFT JOIN qd_polymarket_markets m ON a.market_id = m.market_id
-- WHERE a.recommendation = 'NO'
-- ORDER BY a.opportunity_score DESC, a.created_at DESC
-- LIMIT 20;

-- 查询今天的分析结果
-- SELECT 
--     a.market_id,
--     m.question,
--     a.recommendation,
--     a.opportunity_score,
--     a.confidence_score,
--     a.created_at
-- FROM qd_polymarket_ai_analysis a
-- LEFT JOIN qd_polymarket_markets m ON a.market_id = m.market_id
-- WHERE DATE(a.created_at) = CURRENT_DATE
-- ORDER BY a.opportunity_score DESC;

-- 统计分析结果
-- SELECT 
--     recommendation,
--     COUNT(*) as count,
--     AVG(opportunity_score) as avg_score,
--     AVG(confidence_score) as avg_confidence
-- FROM qd_polymarket_ai_analysis
-- WHERE DATE(created_at) = CURRENT_DATE
-- GROUP BY recommendation
-- ORDER BY count DESC;
