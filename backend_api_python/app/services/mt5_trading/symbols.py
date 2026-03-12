"""
Symbol Mapping and Conversion for MT5

Handles forex symbol normalization and parsing.
"""

from typing import Tuple, Optional


# Common forex pairs with their typical MT5 symbol format
FOREX_PAIRS = {
    # Major pairs
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD",
    # Cross pairs
    "EURGBP", "EURJPY", "EURCHF", "EURAUD", "EURCAD", "EURNZD",
    "GBPJPY", "GBPCHF", "GBPAUD", "GBPCAD", "GBPNZD",
    "AUDJPY", "AUDCHF", "AUDCAD", "AUDNZD",
    "NZDJPY", "NZDCHF", "NZDCAD",
    "CADJPY", "CADCHF",
    "CHFJPY",
    # Exotic pairs
    "USDMXN", "USDZAR", "USDTRY", "USDHKD", "USDSGD", "USDNOK", "USDSEK", "USDDKK",
    "EURTRY", "EURMXN", "EURNOK", "EURSEK", "EURDKK", "EURPLN", "EURHUF", "EURCZK",
    # Metals
    "XAUUSD", "XAGUSD", "XAUEUR",
    # Indices (CFD)
    "US30", "US500", "USTEC", "UK100", "DE40", "JP225", "AU200",
    # Crypto (if broker supports)
    "BTCUSD", "ETHUSD", "LTCUSD", "XRPUSD",
}


def normalize_symbol(symbol: str, broker_suffix: str = "") -> str:
    """
    Normalize symbol to MT5 format.
    
    Different brokers may use different suffixes:
    - No suffix: "EURUSD"
    - With suffix: "EURUSDm", "EURUSD.raw", "EURUSD-ECN"
    
    Args:
        symbol: Symbol code (e.g., "EUR/USD", "EURUSD", "eurusd")
        broker_suffix: Broker-specific suffix (e.g., "m", ".raw", "-ECN")
        
    Returns:
        Normalized MT5 symbol
    """
    # Remove common separators and convert to uppercase
    normalized = (symbol or "").strip().upper()
    normalized = normalized.replace("/", "").replace("-", "").replace("_", "").replace(" ", "")
    
    # Add broker suffix if provided
    if broker_suffix:
        # Check if symbol already has the suffix
        if not normalized.endswith(broker_suffix.upper()):
            normalized = normalized + broker_suffix
    
    return normalized


def parse_symbol(symbol: str) -> Tuple[str, Optional[str]]:
    """
    Parse symbol and extract base/quote currencies.
    
    Args:
        symbol: MT5 symbol (e.g., "EURUSD", "EURUSDm")
        
    Returns:
        (clean_symbol, market_type)
    """
    clean = (symbol or "").strip().upper()
    
    # Remove common broker suffixes
    for suffix in ["M", ".RAW", "-ECN", ".STD", ".PRO", ".", "#"]:
        if clean.endswith(suffix):
            clean = clean[:-len(suffix)]
    
    # Determine market type based on symbol pattern
    if clean in FOREX_PAIRS or (len(clean) == 6 and clean.isalpha()):
        return clean, "forex"
    
    if clean.startswith("XAU") or clean.startswith("XAG"):
        return clean, "metal"
    
    if clean.startswith("BTC") or clean.startswith("ETH") or clean.startswith("LTC"):
        return clean, "crypto"
    
    if any(idx in clean for idx in ["US30", "US500", "USTEC", "UK100", "DE40", "JP225"]):
        return clean, "index"
    
    # Default to forex
    return clean, "forex"


def get_lot_size_info(symbol: str) -> dict:
    """
    Get lot size information for a symbol.
    
    Standard forex lot sizes:
    - Standard lot: 100,000 units
    - Mini lot: 10,000 units
    - Micro lot: 1,000 units
    - Nano lot: 100 units
    
    Args:
        symbol: MT5 symbol
        
    Returns:
        Dict with lot size information
    """
    clean, market_type = parse_symbol(symbol)
    
    if market_type == "forex":
        return {
            "standard_lot": 100000,
            "min_lot": 0.01,
            "lot_step": 0.01,
            "max_lot": 100.0,
        }
    
    if market_type == "metal":
        # Gold/Silver typically uses oz
        return {
            "standard_lot": 100,  # 100 oz
            "min_lot": 0.01,
            "lot_step": 0.01,
            "max_lot": 50.0,
        }
    
    if market_type == "index":
        return {
            "standard_lot": 1,
            "min_lot": 0.1,
            "lot_step": 0.1,
            "max_lot": 100.0,
        }
    
    # Default
    return {
        "standard_lot": 1,
        "min_lot": 0.01,
        "lot_step": 0.01,
        "max_lot": 100.0,
    }
