-- Polymarket 跟单系统数据库迁移
-- 创建日期: 2024-01-01
-- 说明: 添加排行榜用户和交易活动表

-- ============================================================================
-- 表1: qd_polymarket_top_users (排行榜用户)
-- ============================================================================
CREATE TABLE IF NOT EXISTS qd_polymarket_top_users (
    id SERIAL PRIMARY KEY,
    user_address VARCHAR(42) NOT NULL,
    period VARCHAR(20) NOT NULL,  -- 'day', 'week', 'month', 'all'
    rank INT NOT NULL,
    volume DECIMAL(20, 2),
    profit DECIMAL(20, 2),
    trades INT,
    win_rate DECIMAL(5, 4),
    created_at TIMESTAMP DEFAULT NOW()
);

-- 创建唯一索引（每个用户每天每个周期只有一条记录）
CREATE UNIQUE INDEX IF NOT EXISTS idx_top_users_unique 
ON qd_polymarket_top_users(user_address, period, DATE(created_at));

-- 索引
CREATE INDEX IF NOT EXISTS idx_top_users_address ON qd_polymarket_top_users(user_address);
CREATE INDEX IF NOT EXISTS idx_top_users_period ON qd_polymarket_top_users(period);
CREATE INDEX IF NOT EXISTS idx_top_users_created ON qd_polymarket_top_users(created_at DESC);

-- 注释
COMMENT ON TABLE qd_polymarket_top_users IS 'Polymarket排行榜用户数据';
COMMENT ON COLUMN qd_polymarket_top_users.user_address IS '用户钱包地址';
COMMENT ON COLUMN qd_polymarket_top_users.period IS '排行榜周期: day/week/month/all';
COMMENT ON COLUMN qd_polymarket_top_users.rank IS '排名';
COMMENT ON COLUMN qd_polymarket_top_users.volume IS '交易量';
COMMENT ON COLUMN qd_polymarket_top_users.profit IS '利润';
COMMENT ON COLUMN qd_polymarket_top_users.trades IS '交易次数';
COMMENT ON COLUMN qd_polymarket_top_users.win_rate IS '胜率';

-- ============================================================================
-- 表2: qd_polymarket_user_activities (用户交易活动)
-- ============================================================================
CREATE TABLE IF NOT EXISTS qd_polymarket_user_activities (
    id SERIAL PRIMARY KEY,
    activity_id VARCHAR(100) UNIQUE NOT NULL,  -- 防止重复
    user_address VARCHAR(42) NOT NULL,
    market_id VARCHAR(100),
    asset_id VARCHAR(100),
    side VARCHAR(10) NOT NULL,  -- 'BUY' 或 'SELL'
    outcome VARCHAR(10),  -- 'YES' 或 'NO'
    size DECIMAL(20, 8),
    price DECIMAL(10, 6),
    fee_rate_bps INT,
    timestamp TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_activities_user ON qd_polymarket_user_activities(user_address);
CREATE INDEX IF NOT EXISTS idx_activities_market ON qd_polymarket_user_activities(market_id);
CREATE INDEX IF NOT EXISTS idx_activities_timestamp ON qd_polymarket_user_activities(timestamp DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_activities_unique ON qd_polymarket_user_activities(activity_id);

-- 注释
COMMENT ON TABLE qd_polymarket_user_activities IS 'Polymarket用户交易活动记录';
COMMENT ON COLUMN qd_polymarket_user_activities.activity_id IS '活动唯一ID（用于去重）';
COMMENT ON COLUMN qd_polymarket_user_activities.user_address IS '用户钱包地址';
COMMENT ON COLUMN qd_polymarket_user_activities.market_id IS '市场ID';
COMMENT ON COLUMN qd_polymarket_user_activities.asset_id IS '资产ID（token）';
COMMENT ON COLUMN qd_polymarket_user_activities.side IS '交易方向: BUY/SELL';
COMMENT ON COLUMN qd_polymarket_user_activities.outcome IS '结果: YES/NO';
COMMENT ON COLUMN qd_polymarket_user_activities.size IS '交易数量';
COMMENT ON COLUMN qd_polymarket_user_activities.price IS '交易价格';
COMMENT ON COLUMN qd_polymarket_user_activities.fee_rate_bps IS '手续费率（基点）';
COMMENT ON COLUMN qd_polymarket_user_activities.timestamp IS '交易时间';

-- ============================================================================
-- 查询视图: 用户活动汇总
-- ============================================================================
CREATE OR REPLACE VIEW v_polymarket_user_activity_summary AS
SELECT 
    u.user_address,
    u.period,
    u.rank,
    u.volume,
    u.profit,
    u.win_rate,
    COUNT(a.id) as activity_count,
    MAX(a.timestamp) as last_activity_at,
    SUM(CASE WHEN a.side = 'BUY' THEN 1 ELSE 0 END) as buy_count,
    SUM(CASE WHEN a.side = 'SELL' THEN 1 ELSE 0 END) as sell_count
FROM qd_polymarket_top_users u
LEFT JOIN qd_polymarket_user_activities a ON u.user_address = a.user_address
WHERE DATE(u.created_at) = CURRENT_DATE
GROUP BY u.user_address, u.period, u.rank, u.volume, u.profit, u.win_rate
ORDER BY u.rank;

COMMENT ON VIEW v_polymarket_user_activity_summary IS '用户活动汇总视图（当日数据）';

-- ============================================================================
-- 查询视图: 最近活动
-- ============================================================================
CREATE OR REPLACE VIEW v_polymarket_recent_activities AS
SELECT 
    a.activity_id,
    a.user_address,
    u.rank as user_rank,
    u.period as user_period,
    u.win_rate as user_win_rate,
    a.market_id,
    a.side,
    a.outcome,
    a.size,
    a.price,
    a.timestamp,
    a.created_at
FROM qd_polymarket_user_activities a
LEFT JOIN qd_polymarket_top_users u ON a.user_address = u.user_address
WHERE DATE(u.created_at) = CURRENT_DATE
ORDER BY a.timestamp DESC
LIMIT 100;

COMMENT ON VIEW v_polymarket_recent_activities IS '最近100条交易活动（关联用户排名信息）';

-- ============================================================================
-- 完成提示
-- ============================================================================
DO $$
BEGIN
    RAISE NOTICE '✅ Polymarket跟单系统数据库迁移完成！';
    RAISE NOTICE '   - 表1: qd_polymarket_top_users (排行榜用户)';
    RAISE NOTICE '   - 表2: qd_polymarket_user_activities (交易活动)';
    RAISE NOTICE '   - 视图1: v_polymarket_user_activity_summary (用户汇总)';
    RAISE NOTICE '   - 视图2: v_polymarket_recent_activities (最近活动)';
END $$;
