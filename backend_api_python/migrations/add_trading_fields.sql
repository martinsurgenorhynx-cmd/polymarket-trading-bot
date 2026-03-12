-- 为 qd_polymarket_markets 表添加交易所需的字段
-- 这些字段将在 worker 运行时收集，减少交易时的 CLI 查询次数

-- 添加 condition_id (交易必需)
ALTER TABLE qd_polymarket_markets 
ADD COLUMN IF NOT EXISTS condition_id VARCHAR(255);

-- 添加 yes_token_id (YES 方向的 token ID)
ALTER TABLE qd_polymarket_markets 
ADD COLUMN IF NOT EXISTS yes_token_id VARCHAR(255);

-- 添加 no_token_id (NO 方向的 token ID)
ALTER TABLE qd_polymarket_markets 
ADD COLUMN IF NOT EXISTS no_token_id VARCHAR(255);

-- 添加 accepting_orders (是否接受订单)
ALTER TABLE qd_polymarket_markets 
ADD COLUMN IF NOT EXISTS accepting_orders BOOLEAN DEFAULT true;

-- 添加 tokens_data (完整的 tokens 数组，JSON 格式)
ALTER TABLE qd_polymarket_markets 
ADD COLUMN IF NOT EXISTS tokens_data JSONB;

-- 添加索引以提升查询性能
CREATE INDEX IF NOT EXISTS idx_polymarket_condition_id ON qd_polymarket_markets(condition_id);
CREATE INDEX IF NOT EXISTS idx_polymarket_accepting_orders ON qd_polymarket_markets(accepting_orders) WHERE accepting_orders = true;

-- 添加注释
COMMENT ON COLUMN qd_polymarket_markets.condition_id IS 'Polymarket condition ID，用于交易';
COMMENT ON COLUMN qd_polymarket_markets.yes_token_id IS 'YES 方向的 token ID (十六进制)';
COMMENT ON COLUMN qd_polymarket_markets.no_token_id IS 'NO 方向的 token ID (十六进制)';
COMMENT ON COLUMN qd_polymarket_markets.accepting_orders IS '市场是否接受订单';
COMMENT ON COLUMN qd_polymarket_markets.tokens_data IS '完整的 tokens 数组数据，包含价格、token_id 等';
