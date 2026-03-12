
# Generated Strategy: MA交叉策略
import pandas as pd
import numpy as np

# Helper function for checking signals safely
def get_val(arr, i, default=0):
    if i < 0 or i >= len(arr): return default
    return arr[i]

# ===========================
# 1. Parameters
# ===========================
initial_position_pct = 0.1
leverage = 1
max_pyramiding = 0

# Pyramiding
add_position_pct = 0
add_threshold_pct = 0.0 

# Risk Management
stop_loss_pct = 0.0
take_profit_activation = 0.0
trailing_callback = 0.0

# ===========================
# 2. Indicators Calculation
# ===========================

# ===========================
# 3. Entry Signal Logic
# ===========================
# Default False
df['raw_buy'] = False
df['raw_sell'] = False

# ===========================
# 4. Core Loop (Backtest)
# ===========================
open_long_signals = [False] * len(df)
add_long_signals = [False] * len(df)
close_long_signals = [False] * len(df)

open_long_text = [None] * len(df)
add_long_text = [None] * len(df)

open_long_price = [0.0] * len(df)
add_long_price = [0.0] * len(df)
close_long_price = [0.0] * len(df)
close_long_text = [None] * len(df)

open_short_signals = [False] * len(df)
add_short_signals = [False] * len(df)
close_short_signals = [False] * len(df)

open_short_price = [0.0] * len(df)
add_short_price = [0.0] * len(df)
close_short_price = [0.0] * len(df)
close_short_text = [None] * len(df)

position = 0 # 0, 1 (Long), -1 (Short)
position_count = 0
avg_entry_price = 0.0
last_add_price = 0.0
highest_price = 0.0 # For Long: Highest High; For Short: Lowest Low

close_arr = df['close'].values
high_arr = df['high'].values
low_arr = df['low'].values
raw_buy_arr = df['raw_buy'].values
raw_sell_arr = df['raw_sell'].values

for i in range(len(df)):
    current_close = close_arr[i]
    current_high = high_arr[i]
    current_low = low_arr[i]
    
    if position == 1:
        # Long Position
        if current_high > highest_price:
            highest_price = current_high
            
        profit_pct = (highest_price - avg_entry_price) / avg_entry_price
        current_profit_pct = (current_close - avg_entry_price) / avg_entry_price
        
        # 1. Trailing Stop
        if take_profit_activation > 0 and profit_pct >= take_profit_activation:
            drawdown = (highest_price - current_close) / avg_entry_price
            if drawdown >= trailing_callback:
                close_long_signals[i] = True
                close_long_price[i] = current_close
                close_long_text[i] = "Trailing Stop"
                position = 0
                position_count = 0
                continue
                
        # 2. Stop Loss
        if stop_loss_pct > 0:
            loss_pct = (avg_entry_price - current_low) / avg_entry_price
            if loss_pct >= stop_loss_pct:
                close_long_signals[i] = True
                close_long_price[i] = avg_entry_price * (1 - stop_loss_pct)
                close_long_text[i] = "Stop Loss"
                position = 0
                position_count = 0
                continue
                
        # 3. Signal Exit (if enabled)
        # Note: Code2 uses raw_sell_arr for exit
        if raw_sell_arr[i]:
             close_long_signals[i] = True
             close_long_price[i] = current_close
             close_long_text[i] = "Signal Exit"
             position = 0
             position_count = 0
             
             # Reverse to Short if trade_direction allows (simplified here)
             # For now we just close.
             continue
             
        # 4. Pyramiding (Add Long)
        if max_pyramiding > 0 and position_count < max_pyramiding + 1 and current_profit_pct > 0:
             # Condition: Price rise by threshold
             if add_threshold_pct > 0:
                 target_price = last_add_price * (1 + add_threshold_pct)
                 if current_high >= target_price:
                     add_long_signals[i] = True
                     add_long_price[i] = target_price
                     add_long_text[i] = "Add Long"
                     position_count += 1
                     last_add_price = target_price
             
    elif position == -1:
        # Short Position
        # For Short, highest_price tracks the LOWEST price (best profit scenario)
        if highest_price == 0: highest_price = avg_entry_price
        if current_low < highest_price:
            highest_price = current_low
            
        # Profit: (Entry - Lowest) / Entry
        profit_pct = (avg_entry_price - highest_price) / avg_entry_price
        current_profit_pct = (avg_entry_price - current_close) / avg_entry_price
        
        # 1. Trailing Stop
        if take_profit_activation > 0 and profit_pct >= take_profit_activation:
            # Drawdown: (Current - Lowest) / Entry
            drawdown = (current_close - highest_price) / avg_entry_price
            if drawdown >= trailing_callback:
                close_short_signals[i] = True
                close_short_price[i] = current_close
                close_short_text[i] = "Trailing Stop"
                position = 0
                position_count = 0
                continue

        # 2. Stop Loss
        if stop_loss_pct > 0:
            # Loss: Price went up. (High - Entry) / Entry
            loss_pct = (current_high - avg_entry_price) / avg_entry_price
            if loss_pct >= stop_loss_pct:
                close_short_signals[i] = True
                close_short_price[i] = avg_entry_price * (1 + stop_loss_pct)
                close_short_text[i] = "Stop Loss"
                position = 0
                position_count = 0
                continue

        # 3. Signal Exit
        if raw_buy_arr[i]:
             close_short_signals[i] = True
             close_short_price[i] = current_close
             close_short_text[i] = "Signal Exit"
             position = 0
             position_count = 0
             continue

        # 4. Pyramiding (Add Short)
        if max_pyramiding > 0 and position_count < max_pyramiding + 1 and current_profit_pct > 0:
             # Condition: Price drop by threshold
             if add_threshold_pct > 0:
                 target_price = last_add_price * (1 - add_threshold_pct)
                 if current_low <= target_price:
                     add_short_signals[i] = True
                     add_short_price[i] = target_price
                     add_short_text[i] = "Add Short"
                     position_count += 1
                     last_add_price = target_price

    else:
        # No Position
        if raw_buy_arr[i]:
            open_long_signals[i] = True
            open_long_price[i] = current_close
            open_long_text[i] = "Open Long"
            position = 1
            position_count = 1
            avg_entry_price = current_close
            last_add_price = current_close
            highest_price = current_close
            
        elif raw_sell_arr[i]:
            open_short_signals[i] = True
            open_short_price[i] = current_close
            open_short_text[i] = "Open Short"
            position = -1
            position_count = 1
            avg_entry_price = current_close
            last_add_price = current_close
            highest_price = current_close # Init with Entry

# Append columns
df['open_long'] = open_long_signals
df['add_long'] = add_long_signals
df['close_long'] = close_long_signals
df['open_long_price'] = [p if s else None for p, s in zip(open_long_price, open_long_signals)]
df['add_long_price'] = [p if s else None for p, s in zip(add_long_price, add_long_signals)]
df['close_long_price'] = [p if s else None for p, s in zip(close_long_price, close_long_signals)]
df['open_long_text'] = open_long_text
df['add_long_text'] = add_long_text
df['close_long_text'] = close_long_text

# ===========================
# 5. Output
# ===========================
output = {
    "name": "MA交叉策略",
    "plots": [
],
    "signals": [
        {
            "name": "Open Long",
            "type": "buy",
            "data": df['open_long_price'].tolist(),
            "color": "#00FF00",
            "text": "Open Long"
        },
        {
            "name": "Add Long",
            "type": "buy",
            "data": df['add_long_price'].tolist(),
            "color": "#00DD00",
            "text": "Add Long"
        },
        {
            "name": "Close Long",
            "type": "sell",
            "data": df['close_long_price'].tolist(),
            "color": "#FF6600",
            "text": "Close Long"
        },
        {
            "name": "Open Short",
            "type": "sell",
            "data": df['open_short_price'].tolist(),
            "color": "#FF0000",
            "text": "Open Short"
        },
        {
            "name": "Add Short",
            "type": "sell",
            "data": df['add_short_price'].tolist(),
            "color": "#DD0000",
            "text": "Add Short"
        },
        {
            "name": "Close Short",
            "type": "buy",
            "data": df['close_short_price'].tolist(),
            "color": "#00CCFF",
            "text": "Close Short"
        }
    ]
}
