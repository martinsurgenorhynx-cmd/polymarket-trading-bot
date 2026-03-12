# QuantDinger Changelog

This document records version updates, new features, bug fixes, and database migration instructions.

---

## V2.2.2 (2026-02-28)

### 🚀 New Features

#### Polymarket Prediction Markets Integration 🔮
- **Prediction Market Analysis**: Integrated Polymarket prediction markets as a new data source for AI analysis
- **AI-Driven Insights**: AI analyzes prediction market events and compares AI predictions with market consensus
- **Opportunity Discovery**: Identifies undervalued prediction opportunities with AI vs market divergence analysis
- **Asset Trading Recommendations**: Links prediction market events to related asset trading opportunities (e.g., BTC/USDT, ETH/USDT)
- **Data Analysis Only**: Focuses on data analysis and trading opportunity recommendations without live trading
- **Frontend Pages**: New `/polymarket` page with market listings, filtering, sorting, and search functionality
- **Market Detail View**: Comprehensive analysis view showing market info, AI analysis results, and related asset opportunities
- **AI Trading Radar Integration**: Prediction market opportunities appear in the AI Trading Radar alongside Crypto, US Stocks, and Forex

### 🐛 Bug Fixes
- Fixed duplicate `common.refresh` key in internationalization files (`zh-CN.js` and `en-US.js`)
- Fixed OKX position `entry_price` extraction (now correctly reads `avgPx`, `avgPxEp`, or `last` from position data)
- Improved symbol normalization across all exchanges to handle edge cases (e.g., PI, TRX without quote currency)
- Enhanced LLM provider fallback mechanism to handle 403/402/404/429 errors automatically

### 🎨 UI/UX Improvements
- Added Polymarket market cards with AI analysis summaries and opportunity scores
- Enhanced AI Trading Radar to display prediction market opportunities with distinct styling
- Improved symbol selector in Quick Trade panel with watchlist integration

### 📋 Database Migration

**Run the following SQL on your PostgreSQL database before deploying V2.2.2:**

```sql
-- ============================================================
-- QuantDinger V2.2.2 Database Migration
-- Polymarket Prediction Markets Integration
-- ============================================================

-- 预测市场表（缓存）
CREATE TABLE IF NOT EXISTS qd_polymarket_markets (
    id SERIAL PRIMARY KEY,
    market_id VARCHAR(255) UNIQUE NOT NULL,
    question TEXT,
    category VARCHAR(100),  -- crypto, politics, economics, sports
    current_probability DECIMAL(5,2),  -- YES概率（0-100）
    volume_24h DECIMAL(20,2),
    liquidity DECIMAL(20,2),
    end_date_iso TIMESTAMP,
    status VARCHAR(50),  -- active, closed, resolved
    outcome_tokens JSONB,  -- YES/NO价格和交易量
    slug VARCHAR(255),  -- Polymarket事件slug，用于构建URL
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 添加slug字段（如果表已存在但字段不存在）
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'qd_polymarket_markets' AND column_name = 'slug'
    ) THEN
        ALTER TABLE qd_polymarket_markets ADD COLUMN slug VARCHAR(255);
        RAISE NOTICE 'Added slug column to qd_polymarket_markets';
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_polymarket_category ON qd_polymarket_markets(category);
CREATE INDEX IF NOT EXISTS idx_polymarket_status ON qd_polymarket_markets(status);
CREATE INDEX IF NOT EXISTS idx_polymarket_updated ON qd_polymarket_markets(updated_at DESC);

-- AI分析记录表
CREATE TABLE IF NOT EXISTS qd_polymarket_ai_analysis (
    id SERIAL PRIMARY KEY,
    market_id VARCHAR(255) NOT NULL,
    user_id INTEGER,  -- 可选：用户特定的分析
    ai_predicted_probability DECIMAL(5,2),
    market_probability DECIMAL(5,2),
    divergence DECIMAL(5,2),  -- AI - 市场
    recommendation VARCHAR(20),  -- YES/NO/HOLD
    confidence_score DECIMAL(5,2),
    opportunity_score DECIMAL(5,2),
    reasoning TEXT,
    key_factors JSONB,
    related_assets TEXT[],  -- 相关资产列表
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_polymarket_analysis_market ON qd_polymarket_ai_analysis(market_id);
CREATE INDEX IF NOT EXISTS idx_polymarket_analysis_opportunity ON qd_polymarket_ai_analysis(opportunity_score DESC);
CREATE INDEX IF NOT EXISTS idx_polymarket_analysis_user ON qd_polymarket_ai_analysis(user_id);

-- 资产交易机会表（基于预测市场生成）
CREATE TABLE IF NOT EXISTS qd_polymarket_asset_opportunities (
    id SERIAL PRIMARY KEY,
    market_id VARCHAR(255) NOT NULL,
    asset_symbol VARCHAR(100),
    asset_market VARCHAR(50),
    signal VARCHAR(20),  -- BUY/SELL/HOLD
    confidence DECIMAL(5,2),
    reasoning TEXT,
    entry_suggestion JSONB,  -- 入场建议
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_polymarket_opp_market ON qd_polymarket_asset_opportunities(market_id);
CREATE INDEX IF NOT EXISTS idx_polymarket_opp_asset ON qd_polymarket_asset_opportunities(asset_symbol, asset_market);

-- Migration Complete
DO $$
BEGIN
    RAISE NOTICE '✅ QuantDinger V2.2.2 database migration completed!';
END $$;
```

**Migration Notes:**
- All statements use `IF NOT EXISTS` — safe to run multiple times
- No existing data is modified or deleted
- New tables are created for Polymarket data caching and AI analysis
- Polymarket integration is read-only (data analysis only, no live trading)

### 📝 Configuration Notes
- No new environment variables required for basic Polymarket integration
- Polymarket data source uses placeholder/dummy data by default (can be extended with actual API integration)
- AI analysis leverages existing LLM configuration from System Settings

---

## V2.2.1 (2026-02-27)

### 🚀 New Features

#### Membership & Billing System
- **Subscription Plans**: Monthly / Yearly / Lifetime tiers with configurable pricing and credit bundles
- **Credit System**: Each plan includes credits; lifetime members receive recurring monthly credit bonuses
- **Plan Management**: All plan prices, credits, and bonus amounts configurable via System Settings → Billing Configuration
- **Membership Orders**: Order tracking with status management (paid / pending / failed / refunded)

#### USDT On-Chain Payment (TRC20)
- **HD Wallet Integration**: Per-order unique receiving address derived from xpub (BIP-32/44) — no private key on server
- **Automatic Reconciliation**: Background polling via TronGrid API detects incoming payments and confirms orders
- **Depth-Flexible xpub**: Supports both account-level (depth=3) and change-level (depth=4) xpub keys
- **Configurable Expiry**: Order expiration time and confirmation delay configurable in System Settings
- **Scan-to-Pay Modal**: Professional checkout UI with QR code, step indicator, real-time status, copy-to-clipboard, dark theme support

#### VIP Free Indicators
- **VIP Free Tag**: Admins can mark community indicators as "VIP Free" when publishing
- **Zero-Credit Access**: VIP members can use VIP-free indicators without spending credits
- **Visual Badge**: VIP Free indicators display a distinct badge in the Indicator Market

#### AI Trading Opportunities Radar
- **Multi-Market Scanning**: Auto-scans Crypto, US Stocks, and Forex markets every hour
- **Rolling Carousel**: Opportunities displayed in a rotating carousel with market-specific styling
- **Signal Classification**: BUY / SELL signals with percentage change and reason text
- **Multi-Language**: All radar card content fully internationalized

#### Simplified Strategy Creation
- **Simple / Advanced Mode Toggle**: New users start with simplified mode, power users can switch to advanced
- **Smart Defaults**: 15-minute K-line period, 5x leverage, market order, sensible TP/SL percentages
- **Live Trading Disclaimer**: Mandatory risk acknowledgment checkbox before enabling live trading

#### System Settings Simplification
- **Streamlined Configuration**: Removed redundant config groups (server, strategy); consolidated into essential categories
- **Market Order Default**: Changed default order mode to market order for reliable execution
- **Billing Config i18n**: All billing configuration items fully multi-language supported

#### Quick Trade Panel (闪电交易) 🆕
- **Side-Sliding Drawer**: Professional trading panel slides in from the right, allowing instant order placement without leaving the analysis page
- **Multi-Exchange Support**: Select from saved exchange credentials (Binance, OKX, Bitget, Bybit, etc.) with real-time balance display
- **Long/Short Toggle**: Color-coded direction buttons with one-click switching
- **Market / Limit Orders**: Toggle between market and limit order types; limit orders accept a specific price
- **Leverage Slider**: Interactive 1x–125x leverage control for futures trading
- **TP/SL Price Setting**: Optional take-profit and stop-loss by **absolute price** (not percentage)
- **Current Position Display**: Shows open position with side, size, entry price, unrealized PnL, and one-click close button
- **Recent Trade History**: Displays last 5 quick trades with status tags
- **AI Radar Integration**: "Trade Now" button on each AI Trading Opportunities card pre-fills symbol, direction, and price
- **Indicator Analysis Integration**: Quick Trade button in chart header and floating ⚡ button pre-fills current symbol and price
- **Auto-Polling**: Balance and position data refresh every 10 seconds
- **Full Dark Theme**: Complete dark mode support for all panel elements
- **Multi-Language**: All labels and messages fully internationalized (zh-CN / en-US)

#### Indicator Market Performance Tracking
- **Live Performance Data**: Fixed aggregation to correctly parse backtest `result_json` and include live trade data
- **Combined Metrics**: Backtest return, live PnL, and win rate now properly displayed on indicator cards

### 🐛 Bug Fixes
- Fixed `quick_trade.py` importing from non-existent `auth_utils` module (corrected to `auth`)
- Fixed "Live Performance" data showing all zeros in Indicator Market (incorrect SQL query referencing non-existent columns)
- Fixed incorrect entry price display in Position Records (was falling back to current price)
- Fixed inaccurate System Overview statistics for running strategies, total capital, and total PnL
- Fixed multiple duplicate i18n key issues in `zh-CN.js` and `en-US.js` causing ESLint build failures
- Fixed exposed i18n keys (`common.loading`, `common.noData`, `systemOverview.*`) not configured
- Fixed HTML nesting issues in trading assistant strategy creation form
- Fixed `ed25519-blake2b` build failure in Docker by adding temporary build dependencies
- Fixed "Current depth (3) is not suitable for deriving address" error for xpub — now compatible with both depth 3 and depth 4

### 🎨 UI/UX Improvements
- Removed "Total Analyses" / "Accuracy Rate" row from homepage AI Analysis section
- Removed "Search" and "Portfolio Checkup" features from AI Asset Analysis page
- Professional USDT checkout modal with custom header, step indicator, dual-column layout
- Dark theme and mobile responsive support for payment modal
- Trading Opportunities Radar carousel with smooth scrolling animation

### 📋 Database Migration

**Run the following SQL on your PostgreSQL database before deploying V2.2.1:**

```sql
-- ============================================================
-- QuantDinger V2.2.1 Database Migration
-- Membership, USDT Payment, VIP Free Indicators
-- ============================================================

-- 1. User Table: Add membership columns
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'qd_users' AND column_name = 'vip_plan'
    ) THEN
        ALTER TABLE qd_users ADD COLUMN vip_plan VARCHAR(20) DEFAULT '';
        RAISE NOTICE 'Added vip_plan column to qd_users';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'qd_users' AND column_name = 'vip_is_lifetime'
    ) THEN
        ALTER TABLE qd_users ADD COLUMN vip_is_lifetime BOOLEAN DEFAULT FALSE;
        RAISE NOTICE 'Added vip_is_lifetime column to qd_users';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'qd_users' AND column_name = 'vip_monthly_credits_last_grant'
    ) THEN
        ALTER TABLE qd_users ADD COLUMN vip_monthly_credits_last_grant TIMESTAMP;
        RAISE NOTICE 'Added vip_monthly_credits_last_grant column to qd_users';
    END IF;
END $$;

-- 2. Indicator Codes: Add VIP Free flag
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'qd_indicator_codes' AND column_name = 'vip_free'
    ) THEN
        ALTER TABLE qd_indicator_codes ADD COLUMN vip_free BOOLEAN DEFAULT FALSE;
        RAISE NOTICE 'Added vip_free column to qd_indicator_codes';
    END IF;
END $$;

-- 3. Membership Orders table
CREATE TABLE IF NOT EXISTS qd_membership_orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES qd_users(id) ON DELETE CASCADE,
    plan VARCHAR(20) NOT NULL,
    price_usd DECIMAL(10,2) DEFAULT 0,
    status VARCHAR(20) DEFAULT 'paid',
    created_at TIMESTAMP DEFAULT NOW(),
    paid_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_membership_orders_user_id ON qd_membership_orders(user_id);

-- 4. USDT Orders table (on-chain payment tracking)
CREATE TABLE IF NOT EXISTS qd_usdt_orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES qd_users(id) ON DELETE CASCADE,
    plan VARCHAR(20) NOT NULL,
    chain VARCHAR(20) NOT NULL DEFAULT 'TRC20',
    amount_usdt DECIMAL(20,6) NOT NULL DEFAULT 0,
    address_index INTEGER NOT NULL DEFAULT 0,
    address VARCHAR(80) NOT NULL DEFAULT '',
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    tx_hash VARCHAR(120) DEFAULT '',
    paid_at TIMESTAMP,
    confirmed_at TIMESTAMP,
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_usdt_orders_address_unique ON qd_usdt_orders(chain, address);
CREATE INDEX IF NOT EXISTS idx_usdt_orders_user_id ON qd_usdt_orders(user_id);
CREATE INDEX IF NOT EXISTS idx_usdt_orders_status ON qd_usdt_orders(status);

-- 5. Quick Trades table (manual / discretionary orders from Quick Trade Panel)
CREATE TABLE IF NOT EXISTS qd_quick_trades (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES qd_users(id) ON DELETE CASCADE,
    credential_id   INTEGER DEFAULT 0,
    exchange_id     VARCHAR(40) NOT NULL DEFAULT '',
    symbol          VARCHAR(60) NOT NULL DEFAULT '',
    side            VARCHAR(10) NOT NULL DEFAULT '',       -- buy / sell
    order_type      VARCHAR(20) NOT NULL DEFAULT 'market', -- market / limit
    amount          DECIMAL(24, 8) DEFAULT 0,
    price           DECIMAL(24, 8) DEFAULT 0,
    leverage        INTEGER DEFAULT 1,
    market_type     VARCHAR(20) DEFAULT 'swap',            -- swap / spot
    tp_price        DECIMAL(24, 8) DEFAULT 0,
    sl_price        DECIMAL(24, 8) DEFAULT 0,
    status          VARCHAR(20) DEFAULT 'submitted',       -- submitted / filled / failed / cancelled
    exchange_order_id VARCHAR(120) DEFAULT '',
    filled_amount   DECIMAL(24, 8) DEFAULT 0,
    avg_fill_price  DECIMAL(24, 8) DEFAULT 0,
    error_msg       TEXT DEFAULT '',
    source          VARCHAR(40) DEFAULT 'manual',          -- ai_radar / ai_analysis / indicator / manual
    raw_result      JSONB,
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_quick_trades_user    ON qd_quick_trades(user_id);
CREATE INDEX IF NOT EXISTS idx_quick_trades_created ON qd_quick_trades(created_at DESC);

-- Migration Complete
DO $$
BEGIN
    RAISE NOTICE '✅ QuantDinger V2.2.1 database migration completed!';
END $$;
```

**Migration Notes:**
- All statements use `IF NOT EXISTS` — safe to run multiple times
- No existing data is modified or deleted
- New `.env` variables required for USDT payment: `USDT_PAY_ENABLED`, `USDT_TRC20_XPUB`, `TRONGRID_API_KEY`
- New `.env` variables for membership pricing: `MEMBERSHIP_MONTHLY_PRICE_USD`, `MEMBERSHIP_MONTHLY_CREDITS`, etc.
- See `backend_api_python/env.example` for all new configuration options

### 📝 Configuration Notes

New environment variables (all optional, with defaults):

| Variable | Default | Description |
|----------|---------|-------------|
| `MEMBERSHIP_MONTHLY_PRICE_USD` | `19.9` | Monthly plan price |
| `MEMBERSHIP_MONTHLY_CREDITS` | `500` | Credits included in monthly plan |
| `MEMBERSHIP_YEARLY_PRICE_USD` | `169` | Yearly plan price |
| `MEMBERSHIP_YEARLY_CREDITS` | `8000` | Credits included in yearly plan |
| `MEMBERSHIP_LIFETIME_PRICE_USD` | `499` | Lifetime plan price |
| `MEMBERSHIP_LIFETIME_CREDITS` | `30000` | Initial credits for lifetime plan |
| `MEMBERSHIP_LIFETIME_MONTHLY_BONUS` | `500` | Monthly bonus credits for lifetime members |
| `USDT_PAY_ENABLED` | `false` | Enable USDT TRC20 payment |
| `USDT_TRC20_XPUB` | _(empty)_ | TRC20 HD wallet xpub for address derivation |
| `TRONGRID_API_KEY` | _(empty)_ | TronGrid API key for on-chain monitoring |
| `USDT_ORDER_EXPIRE_MINUTES` | `30` | USDT order expiration time |

---

## V2.1.3 (2026-02-XX)

### 🚀 New Features

#### Cross-Sectional Strategy Support
- **Multi-Symbol Portfolio Management** - Added support for cross-sectional strategies that manage a portfolio of multiple symbols simultaneously
  - Strategy type selection: Single Symbol vs Cross-Sectional
  - Symbol list configuration: Select multiple symbols for portfolio management
  - Portfolio size: Configure the number of symbols to hold simultaneously
  - Long/Short ratio: Set the proportion of long vs short positions (0-1)
  - Rebalance frequency: Daily, Weekly, or Monthly portfolio rebalancing
  - Indicator execution: Indicators receive a `data` dictionary (symbol -> DataFrame) for cross-symbol analysis
  - Signal generation: Automatic buy/sell/close signals based on indicator rankings
  - Parallel execution: Multiple orders executed concurrently for efficiency
- **Backend Implementation**
  - Cross-sectional configurations stored in `trading_config` JSON field
  - New `_run_cross_sectional_strategy_loop` method in TradingExecutor
  - Automatic rebalancing based on configured frequency
  - Support for both long and short positions in the same portfolio
- **Frontend UI**
  - Strategy type selector in strategy creation/editing form
  - Conditional display of single-symbol vs cross-sectional configuration fields
  - Multi-select symbol picker for cross-sectional strategies
  - Full i18n support (Chinese and English)

See `docs/CROSS_SECTIONAL_STRATEGY_GUIDE_CN.md` or `docs/CROSS_SECTIONAL_STRATEGY_GUIDE_EN.md` for detailed usage instructions.

### 🐛 Bug Fixes
- Fixed decimal precision issues in exchange order quantities (Binance Spot LOT_SIZE filter errors)
- Improved `_dec_str` method across all exchange clients for accurate quantity formatting
- Enhanced quantity normalization to respect exchange precision requirements
- Fixed validation logic for cross-sectional strategies (now validates correct symbol list field)
- Fixed success message to show correct strategy count for cross-sectional strategies

### 📋 Database Migration

**Run the following SQL on your PostgreSQL database before deploying V2.1.3:**

```sql
-- ============================================================
-- QuantDinger V2.1.3 Database Migration
-- Cross-Sectional Strategy Support
-- ============================================================

-- Add last_rebalance_at column to track rebalancing time for cross-sectional strategies
-- Note: Cross-sectional strategy configurations (symbol_list, portfolio_size, long_ratio, rebalance_frequency)
-- are stored in the trading_config JSON field, not as separate database columns.
-- This migration only adds the last_rebalance_at timestamp field which is needed for rebalancing logic.

DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'qd_strategies_trading' 
        AND column_name = 'last_rebalance_at'
    ) THEN
        ALTER TABLE qd_strategies_trading 
        ADD COLUMN last_rebalance_at TIMESTAMP;
        RAISE NOTICE 'Added last_rebalance_at column to qd_strategies_trading';
    ELSE
        RAISE NOTICE 'Column last_rebalance_at already exists';
    END IF;
END $$;
```

**Migration Notes:**
- This migration is safe to run multiple times (uses IF NOT EXISTS check)
- Cross-sectional strategy configurations are stored in the `trading_config` JSON field, so no additional columns are needed
- The `last_rebalance_at` field is used to track when the last rebalancing occurred for cross-sectional strategies
- If you don't run this migration, cross-sectional strategies will still work, but rebalancing frequency checks may not function correctly

---

## V2.1.2 (2026-02-01)

### 🚀 New Features

#### Indicator Parameter Support
- **External Parameter Passing** - Indicators can now declare parameters using `# @param` syntax that can be configured per-strategy
  - Supported types: `int`, `float`, `bool`, `str`
  - Parameters are displayed in the strategy creation form after selecting an indicator
  - Different strategies using the same indicator can have different parameter values
- **Cross-Indicator Calling** - Indicators can now call other indicators using `call_indicator(id_or_name, df)` function
  - Supports calling by indicator ID (number) or name (string)
  - Maximum call depth of 5 to prevent circular dependencies
  - Only allows calling own indicators or published community indicators

#### Parameter Declaration Syntax
```
# @param <name> <type> <default> <description>
```

| Field | Description | Example |
|-------|-------------|---------|
| name | Parameter name (variable name) | `ma_fast` |
| type | Data type: `int`, `float`, `bool`, `str` | `int` |
| default | Default value | `5` |
| description | Description (shown in UI tooltip) | `Short-term MA period` |

#### Example: Dual Moving Average with Parameters
```python
# @param sma_short int 14 Short-term MA period
# @param sma_long int 28 Long-term MA period

# Get parameters
sma_short_period = params.get('sma_short', 14)
sma_long_period = params.get('sma_long', 28)

my_indicator_name = "Dual MA Strategy"
my_indicator_description = f"SMA{sma_short_period}/{sma_long_period} crossover"

df = df.copy()
sma_short = df["close"].rolling(sma_short_period).mean()
sma_long = df["close"].rolling(sma_long_period).mean()

# Golden cross / Death cross
buy = (sma_short > sma_long) & (sma_short.shift(1) <= sma_long.shift(1))
sell = (sma_short < sma_long) & (sma_short.shift(1) >= sma_long.shift(1))

df["buy"] = buy.fillna(False).astype(bool)
df["sell"] = sell.fillna(False).astype(bool)

# Chart markers
buy_marks = [df["low"].iloc[i] * 0.995 if df["buy"].iloc[i] else None for i in range(len(df))]
sell_marks = [df["high"].iloc[i] * 1.005 if df["sell"].iloc[i] else None for i in range(len(df))]

output = {
    "name": my_indicator_name,
    "plots": [
        {"name": f"SMA{sma_short_period}", "data": sma_short.tolist(), "color": "#FF9800", "overlay": True},
        {"name": f"SMA{sma_long_period}", "data": sma_long.tolist(), "color": "#3F51B5", "overlay": True}
    ],
    "signals": [
        {"type": "buy", "text": "B", "data": buy_marks, "color": "#00E676"},
        {"type": "sell", "text": "S", "data": sell_marks, "color": "#FF5252"}
    ]
}
```

#### Example: Using call_indicator()
```python
# Call another indicator by name or ID
# rsi_df = call_indicator('RSI', df)           # By name
# rsi_df = call_indicator(5, df)               # By ID
# rsi_df = call_indicator('RSI', df, {'period': 14})  # With params

# Note: The called indicator must be created first
# and accessible (own indicator or published community indicator)
```

### 🐛 Bug Fixes

#### Dashboard Fixes
- **Fixed current positions showing records from other users** - Position synchronization now correctly associates positions with the strategy owner's user_id
- **Fixed strategy distribution pie chart always showing "No Data"** - Chart now uses `strategy_stats` data which includes all strategies with trading activity
- **Removed AI strategy count from running strategies card** - Dashboard now only shows indicator strategy count since AI strategies category has been removed

---

## V2.1.1 (2026-01-31)

### 🚀 New Features

#### AI Analysis System Overhaul
- **Fast Analysis Mode**: Replaced the complex multi-agent system with a streamlined single LLM call architecture for faster and more accurate analysis
- **Progressive Loading**: Market data now loads independently - each section (sentiment, indices, heatmap, calendar) displays as soon as it's ready
- **Professional Loading Animation**: New progress bar with step indicators during AI analysis
- **Analysis Memory**: Store analysis results for history review and user feedback
- **Stop Loss/Take Profit Calculation**: Now based on ATR (Average True Range) and Support/Resistance levels with clear methodology hints

#### Global Market Integration
- Integrated Global Market data directly into AI Analysis page
- Real-time scrolling display of major global indices with flags, prices, and percentage changes
- Interactive heatmaps for Crypto, Commodities, Sectors, and Forex
- Economic calendar with bullish/bearish/neutral impact indicators
- Commodities heatmap added (Gold, Silver, Crude Oil, etc.)

#### Indicator Community Enhancements
- **Admin Review System**: Administrators can now review, approve, reject, unpublish, and delete community indicators
- **Purchase & Rating System**: Users can buy indicators, leave ratings and comments
- **Statistics Tracking**: Purchase count, average rating, rating count, view count for each indicator

#### Trading Assistant Improvements
- Improved IBKR/MT5 connection test feedback
- Added local deployment warning for external trading platforms
- Virtual profit/loss calculation for signal-only strategies

### 🐛 Bug Fixes
- Fixed progress bar and timer not animating during AI analysis
- Fixed missing i18n translations for various components
- Fixed Tiingo API rate limit issues with caching
- Fixed data fetching with multiple fallback sources
- Fixed watchlist price batch fetch timeout handling
- Fixed heatmap multi-language support for commodities and forex
- **Fixed AI analysis history not filtered by user** - All users were seeing the same history records; now each user only sees their own analysis history
- **Fixed "Missing Turnstile token" error when changing password** - Logged-in users no longer need Turnstile verification to request password change verification code

### 🎨 UI/UX Improvements
- Reorganized left menu: Indicator Market moved below Indicator Analysis, Settings moved to bottom
- Skeleton loading animations for progressive data display
- Dark theme support for all new components
- Compact market overview bar design

### 📋 Database Migration

**Run the following SQL on your PostgreSQL database before deploying V2.1.1:**

```sql
-- ============================================================
-- QuantDinger V2.1.1 Database Migration
-- ============================================================

-- 1. AI Analysis Memory Table
CREATE TABLE IF NOT EXISTS qd_analysis_memory (
    id SERIAL PRIMARY KEY,
    market VARCHAR(50) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    decision VARCHAR(10) NOT NULL,
    confidence INT DEFAULT 50,
    price_at_analysis DECIMAL(24, 8),
    entry_price DECIMAL(24, 8),
    stop_loss DECIMAL(24, 8),
    take_profit DECIMAL(24, 8),
    summary TEXT,
    reasons JSONB,
    risks JSONB,
    scores JSONB,
    indicators_snapshot JSONB,
    raw_result JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    validated_at TIMESTAMP,
    actual_outcome VARCHAR(20),
    actual_return_pct DECIMAL(10, 4),
    was_correct BOOLEAN,
    user_feedback VARCHAR(20),
    feedback_at TIMESTAMP
);

-- Add raw_result column if table exists but column doesn't
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'qd_analysis_memory' AND column_name = 'raw_result'
    ) THEN
        ALTER TABLE qd_analysis_memory ADD COLUMN raw_result JSONB;
    END IF;
END $$;

-- Add user_id column for user-specific history filtering
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'qd_analysis_memory' AND column_name = 'user_id'
    ) THEN
        ALTER TABLE qd_analysis_memory ADD COLUMN user_id INT;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_analysis_memory_symbol ON qd_analysis_memory(market, symbol);
CREATE INDEX IF NOT EXISTS idx_analysis_memory_created ON qd_analysis_memory(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_analysis_memory_validated ON qd_analysis_memory(validated_at) WHERE validated_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_analysis_memory_user ON qd_analysis_memory(user_id);

-- 2. Indicator Purchase Records
CREATE TABLE IF NOT EXISTS qd_indicator_purchases (
    id SERIAL PRIMARY KEY,
    indicator_id INTEGER NOT NULL REFERENCES qd_indicator_codes(id) ON DELETE CASCADE,
    buyer_id INTEGER NOT NULL REFERENCES qd_users(id) ON DELETE CASCADE,
    seller_id INTEGER NOT NULL REFERENCES qd_users(id),
    price DECIMAL(10,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(indicator_id, buyer_id)
);

CREATE INDEX IF NOT EXISTS idx_purchases_indicator ON qd_indicator_purchases(indicator_id);
CREATE INDEX IF NOT EXISTS idx_purchases_buyer ON qd_indicator_purchases(buyer_id);
CREATE INDEX IF NOT EXISTS idx_purchases_seller ON qd_indicator_purchases(seller_id);

-- 3. Indicator Comments
CREATE TABLE IF NOT EXISTS qd_indicator_comments (
    id SERIAL PRIMARY KEY,
    indicator_id INTEGER NOT NULL REFERENCES qd_indicator_codes(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES qd_users(id) ON DELETE CASCADE,
    rating INTEGER DEFAULT 5 CHECK (rating >= 1 AND rating <= 5),
    content TEXT DEFAULT '',
    parent_id INTEGER REFERENCES qd_indicator_comments(id) ON DELETE CASCADE,
    is_deleted INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_comments_indicator ON qd_indicator_comments(indicator_id);
CREATE INDEX IF NOT EXISTS idx_comments_user ON qd_indicator_comments(user_id);

-- 4. Indicator Codes Extensions
DO $$
BEGIN
    -- Purchase count
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'qd_indicator_codes' AND column_name = 'purchase_count'
    ) THEN
        ALTER TABLE qd_indicator_codes ADD COLUMN purchase_count INTEGER DEFAULT 0;
    END IF;
    
    -- Average rating
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'qd_indicator_codes' AND column_name = 'avg_rating'
    ) THEN
        ALTER TABLE qd_indicator_codes ADD COLUMN avg_rating DECIMAL(3,2) DEFAULT 0;
    END IF;
    
    -- Rating count
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'qd_indicator_codes' AND column_name = 'rating_count'
    ) THEN
        ALTER TABLE qd_indicator_codes ADD COLUMN rating_count INTEGER DEFAULT 0;
    END IF;
    
    -- View count
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'qd_indicator_codes' AND column_name = 'view_count'
    ) THEN
        ALTER TABLE qd_indicator_codes ADD COLUMN view_count INTEGER DEFAULT 0;
    END IF;
    
    -- Review status
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'qd_indicator_codes' AND column_name = 'review_status'
    ) THEN
        ALTER TABLE qd_indicator_codes ADD COLUMN review_status VARCHAR(20) DEFAULT 'approved';
        UPDATE qd_indicator_codes SET review_status = 'approved' WHERE publish_to_community = 1;
    END IF;
    
    -- Review note
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'qd_indicator_codes' AND column_name = 'review_note'
    ) THEN
        ALTER TABLE qd_indicator_codes ADD COLUMN review_note TEXT DEFAULT '';
    END IF;
    
    -- Reviewed at
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'qd_indicator_codes' AND column_name = 'reviewed_at'
    ) THEN
        ALTER TABLE qd_indicator_codes ADD COLUMN reviewed_at TIMESTAMP;
    END IF;
    
    -- Reviewed by
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'qd_indicator_codes' AND column_name = 'reviewed_by'
    ) THEN
        ALTER TABLE qd_indicator_codes ADD COLUMN reviewed_by INTEGER;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_indicator_review_status ON qd_indicator_codes(review_status);

-- 5. User Table Extensions
DO $$
BEGIN
    -- Token version (for single-client login)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'qd_users' AND column_name = 'token_version'
    ) THEN
        ALTER TABLE qd_users ADD COLUMN token_version INTEGER DEFAULT 1;
    END IF;
    
    -- Notification settings
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'qd_users' AND column_name = 'notification_settings'
    ) THEN
        ALTER TABLE qd_users ADD COLUMN notification_settings TEXT DEFAULT '{}';
    END IF;
END $$;

-- Migration Complete
DO $$
BEGIN
    RAISE NOTICE '✅ QuantDinger V2.1.1 database migration completed!';
END $$;
```

### 🗑️ Removed
- Old multi-agent AI analysis system (`backend_api_python/app/services/agents/` directory)
- Old analysis routes and services
- Standalone Global Market page (merged into AI Analysis)
- Reflection worker background process

### ⚠️ Breaking Changes
- AI Analysis API endpoints changed from `/api/analysis/*` to `/api/fast-analysis/*`
- Old analysis history data is not compatible with new format

### 📝 Configuration Notes
- No new environment variables required
- Existing LLM configuration in System Settings will be used for AI Analysis

---

## Version History

| Version | Date | Highlights |
|---------|------|------------|
| V2.2.2 | 2026-02-28 | Polymarket prediction markets integration, AI-driven prediction analysis, asset trading recommendations |
| V2.2.1 | 2026-02-27 | Membership & Billing, USDT TRC20 payment, VIP free indicators, AI Trading Radar, simplified strategy creation |
| V2.1.3 | 2026-02-XX | Cross-sectional strategy support |
| V2.1.2 | 2026-02-01 | Indicator parameters, cross-indicator calling |
| V2.1.1 | 2026-01-31 | AI Analysis overhaul, Global Market integration, Indicator Community enhancements |

---

*For questions or issues, please open a GitHub issue or contact the maintainers.*
