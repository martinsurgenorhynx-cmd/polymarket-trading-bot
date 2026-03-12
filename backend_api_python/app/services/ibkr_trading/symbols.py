"""
Symbol Mapping and Conversion

Converts QuantDinger system symbols to IB contract format.
"""

from typing import Tuple, Optional


def normalize_symbol(symbol: str, market_type: str) -> Tuple[str, str, str]:
    """
    Convert system symbol to IB contract parameters.
    
    Args:
        symbol: Symbol code in the system
        market_type: Market type (USStock)
        
    Returns:
        (ib_symbol, exchange, currency)
    """
    symbol = (symbol or "").strip().upper()
    market_type = (market_type or "").strip()
    
    if market_type == "USStock":
        # US stocks: AAPL, TSLA, GOOGL
        # Use SMART routing for best execution
        return symbol, "SMART", "USD"
    
    else:
        # Default to US stock
        return symbol, "SMART", "USD"


def parse_symbol(symbol: str) -> Tuple[str, Optional[str]]:
    """
    Parse symbol and auto-detect market type.
    
    Args:
        symbol: Symbol code
        
    Returns:
        (clean_symbol, market_type)
    """
    symbol = (symbol or "").strip().upper()
    
    # Default to US stock
    return symbol, "USStock"


def format_display_symbol(ib_symbol: str, exchange: str) -> str:
    """
    Convert IB contract format back to display format.
    
    Args:
        ib_symbol: IB symbol
        exchange: Exchange code
        
    Returns:
        Display symbol
    """
    return ib_symbol
