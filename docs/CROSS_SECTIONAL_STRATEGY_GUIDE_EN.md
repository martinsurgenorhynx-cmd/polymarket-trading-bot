# Cross-Sectional Strategy Guide

## Overview

Cross-Sectional Strategy is a strategy type that trades multiple symbols simultaneously. It scores and ranks all symbols based on certain factors, then goes long on top-ranked symbols and short on bottom-ranked symbols.

## Features

1. **Multi-Symbol Support**: Can trade multiple symbols (stocks, cryptocurrencies, etc.) simultaneously
2. **Automatic Ranking**: Automatically ranks symbols based on indicator-calculated scores
3. **Portfolio Management**: Automatically manages portfolio positions, maintaining long/short ratios
4. **Periodic Rebalancing**: Supports daily/weekly/monthly rebalancing frequencies
5. **Batch Execution**: Executes trades for multiple symbols in parallel for improved efficiency

## Configuration

### Strategy Configuration Parameters

When creating or editing a strategy, add the following parameters to `trading_config`:

```json
{
  "cs_strategy_type": "cross_sectional",  // Strategy type: 'single' or 'cross_sectional'
  "symbol_list": [                        // Symbol list
    "Crypto:BTC/USDT",
    "Crypto:ETH/USDT",
    "Crypto:BNB/USDT"
  ],
  "portfolio_size": 10,                   // Portfolio size (total of long + short positions)
  "long_ratio": 0.5,                     // Long ratio (0-1, 0.5 means 50% long, 50% short)
  "rebalance_frequency": "daily"          // Rebalancing frequency: 'daily' | 'weekly' | 'monthly'
}
```

### Parameter Description

- **cs_strategy_type**: 
  - `'single'`: Single-symbol strategy (default, original functionality)
  - `'cross_sectional'`: Cross-sectional strategy

- **symbol_list**: 
  - List of symbols, format: `["Market:SYMBOL", ...]`
  - Example: `["Crypto:BTC/USDT", "Crypto:ETH/USDT"]`

- **portfolio_size**: 
  - Portfolio size, i.e., the number of symbols to hold simultaneously
  - Example: 10 means holding 10 symbols at the same time

- **long_ratio**: 
  - Long ratio, a float between 0 and 1
  - Example: 0.5 means 50% long, 50% short
  - Example: 1.0 means 100% long (no short positions)

- **rebalance_frequency**: 
  - Rebalancing frequency
  - `'daily'`: Daily rebalancing
  - `'weekly'`: Weekly rebalancing
  - `'monthly'`: Monthly rebalancing

## Indicator Code Writing

Cross-sectional strategy indicator code needs to return scores and rankings for all symbols.

### Indicator Code Template

```python
# Cross-sectional strategy indicator template
# Input: data = {symbol1: df1, symbol2: df2, ...}
# Output: scores = {symbol1: score1, symbol2: score2, ...}
#         rankings = [symbol1, symbol2, ...]  # Optional, auto-sorted by scores if not provided

scores = {}
for symbol, df in data.items():
    # Calculate factor values for each symbol
    # Example: Momentum factor
    momentum = (df['close'].iloc[-1] / df['close'].iloc[-20] - 1) * 100
    
    # Example: RSI indicator
    def calculate_rsi(prices, period=14):
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi.iloc[-1]
    
    rsi = calculate_rsi(df['close'], 14)
    
    # Composite score (adjust weights as needed)
    score = momentum * 0.6 + (100 - rsi) * 0.4
    scores[symbol] = score

# Optional: Manually specify ranking (if not provided, system will auto-sort by scores)
# rankings = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
```

### Indicator Code Environment Variables

The following variables are available when indicator code executes:

- `symbols`: Symbol list `['Crypto:BTC/USDT', 'Crypto:ETH/USDT', ...]`
- `data`: K-line data for all symbols `{symbol: df, ...}`
- `scores`: Dictionary for storing scores (needs to be populated in code)
- `rankings`: List for storing rankings (optional, auto-sorted by scores if not provided)
- `np`: numpy
- `pd`: pandas
- `trading_config`: Trading configuration
- `config`: Trading configuration (alias)

### Output Requirements

Indicator code needs to populate the `scores` dictionary:

```python
scores[symbol] = score_value  # score_value can be any numeric value
```

Optional: Populate the `rankings` list (if not provided, system will auto-sort by scores):

```python
rankings = [symbol1, symbol2, ...]  # Sorted by score from high to low
```

## Signal Generation Logic

The system automatically generates trading signals based on the following logic:

1. **Rank Symbols**: Rank all symbols based on indicator-calculated scores
2. **Select Positions**:
   - Top `portfolio_size * long_ratio` symbols → Long
   - Bottom `portfolio_size * (1 - long_ratio)` symbols → Short
3. **Generate Signals**:
   - New symbols: If a symbol is not in current positions, generate open signal
   - Remove symbols: If a symbol is not in target positions, generate close signal
   - Direction change: If a symbol needs to change from long to short or vice versa, first generate close signal, then open signal

## Usage Examples

### 1. Create Cross-Sectional Strategy

When creating a strategy via API, include in the request body:

```json
{
  "strategy_name": "Momentum Cross-Sectional Strategy",
  "trading_config": {
    "cs_strategy_type": "cross_sectional",
    "symbol_list": [
      "Crypto:BTC/USDT",
      "Crypto:ETH/USDT",
      "Crypto:BNB/USDT",
      "Crypto:ADA/USDT",
      "Crypto:SOL/USDT"
    ],
    "portfolio_size": 5,
    "long_ratio": 0.6,
    "rebalance_frequency": "daily",
    "timeframe": "1H",
    "initial_capital": 10000,
    "leverage": 1,
    "market_type": "swap"
  },
  "indicator_config": {
    "indicator_id": 123,
    "indicator_code": "..."
  }
}
```

### 2. Indicator Code Example

```python
# Momentum + RSI Composite Score
scores = {}
for symbol, df in data.items():
    # 20-period momentum
    momentum = (df['close'].iloc[-1] / df['close'].iloc[-20] - 1) * 100
    
    # RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    rsi_value = rsi.iloc[-1]
    
    # Composite score
    score = momentum * 0.7 + (100 - rsi_value) * 0.3
    scores[symbol] = score
```

## Notes

1. **Data Retrieval**: The system retrieves K-line data for each symbol. If data retrieval fails for a symbol, that symbol will be skipped.
2. **Rebalancing Frequency**: The system checks if rebalancing is needed based on `rebalance_frequency` settings. No trades will be executed if it's not time to rebalance.
3. **Batch Execution**: All trading signals are executed in parallel, with a maximum of 10 concurrent trades.
4. **Position Management**: The system automatically manages positions to ensure the portfolio meets configuration requirements.
5. **Compatibility**: Cross-sectional strategy functionality does not affect existing single-symbol strategies. Both can coexist.

## Database Migration

If you need to store cross-sectional strategy configuration in database fields (optional), you can run the migration script:

```sql
-- Run migrations/add_cross_sectional_strategy.sql
```

If you don't run the migration script, cross-sectional strategy configuration will be stored in the `trading_config` JSON field, and functionality will work normally.

## Troubleshooting

1. **Strategy Not Executing**:
   - Check if `cs_strategy_type` is `'cross_sectional'`
   - Check if `symbol_list` is not empty
   - Check if rebalancing frequency time has been reached

2. **Indicator Execution Failed**:
   - Check if indicator code correctly populates the `scores` dictionary
   - Check if data for all symbols can be retrieved normally

3. **Signals Not Generated**:
   - Check if `portfolio_size` is less than or equal to the length of `symbol_list`
   - Check if scores are valid
