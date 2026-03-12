"""
Symbol normalization helpers.

Input symbols may come from UI/strategy config in ccxt-like shape:
- "SOL/USDT:USDT"
- "SOL/USDT"

We convert them into exchange-specific identifiers.
"""

from __future__ import annotations

from typing import Dict, Tuple


def _split_base_quote(symbol: str) -> Tuple[str, str]:
    """
    分割符号为基础货币和报价货币。
    
    处理各种格式：
    - BTC/USDT -> (BTC, USDT)
    - BTCUSDT -> (BTCUSDT, "") - 需要进一步处理
    - PI, TRX -> (PI, "") - 需要进一步处理
    """
    s = (symbol or "").strip()
    if ":" in s:
        s = s.split(":", 1)[0]
    if "/" not in s:
        # 尝试识别报价货币（常见格式：BASEQUOTE）
        s_upper = s.upper()
        common_quotes = ['USDT', 'USD', 'BTC', 'ETH', 'BUSD', 'USDC', 'BNB']
        for quote in common_quotes:
            if s_upper.endswith(quote) and len(s_upper) > len(quote):
                base = s_upper[:-len(quote)]
                if base:
                    return base, quote
        # 无法识别，返回原符号和空报价
        return s_upper, ""
    base, quote = s.split("/", 1)
    return base.strip().upper(), quote.strip().upper()


def to_binance_futures_symbol(symbol: str) -> str:
    base, quote = _split_base_quote(symbol)
    if not quote:
        return (symbol or "").replace("/", "").replace(":", "").upper()
    return f"{base}{quote}"


def to_okx_swap_inst_id(symbol: str) -> str:
    base, quote = _split_base_quote(symbol)
    if not base or not quote:
        return symbol
    # OKX perpetual swap instrument id: BASE-QUOTE-SWAP
    return f"{base}-{quote}-SWAP"


def to_okx_spot_inst_id(symbol: str) -> str:
    base, quote = _split_base_quote(symbol)
    if not base or not quote:
        return symbol
    return f"{base}-{quote}"


def to_bitget_um_symbol(symbol: str) -> str:
    base, quote = _split_base_quote(symbol)
    if not quote:
        return (symbol or "").replace("/", "").replace(":", "").upper()
    return f"{base}{quote}"


_KRAKEN_BASE_MAP: Dict[str, str] = {
    # Common spot naming differences
    "BTC": "XBT",
}

_BITFINEX_QUOTE_MAP: Dict[str, str] = {
    # Bitfinex uses "UST" for Tether USDt
    "USDT": "UST",
}

_KUCOIN_FUTURES_BASE_MAP: Dict[str, str] = {
    # KuCoin futures uses XBT for BTC on many contracts
    "BTC": "XBT",
}


def to_bybit_symbol(symbol: str) -> str:
    """
    Bybit symbol format (v5): typically concatenated, e.g. BTCUSDT.
    """
    return to_binance_futures_symbol(symbol)


def to_coinbase_product_id(symbol: str) -> str:
    """
    Coinbase Exchange product id format: BASE-QUOTE, e.g. BTC-USDT.
    """
    base, quote = _split_base_quote(symbol)
    if not base or not quote:
        return symbol
    return f"{base}-{quote}"


def to_kraken_pair(symbol: str) -> str:
    """
    Kraken spot pair format is exchange-specific (e.g. XBTUSDT).
    We use a best-effort mapping for common assets; callers can override by passing
    already-normalized Kraken pair strings.
    """
    base, quote = _split_base_quote(symbol)
    if not base or not quote:
        return symbol
    b = _KRAKEN_BASE_MAP.get(base, base)
    return f"{b}{quote}"


def to_kucoin_symbol(symbol: str) -> str:
    """
    KuCoin spot symbol format: BASE-QUOTE, e.g. BTC-USDT.
    """
    base, quote = _split_base_quote(symbol)
    if not base or not quote:
        return symbol
    return f"{base}-{quote}"


def to_kucoin_futures_symbol(symbol: str) -> str:
    """
    KuCoin Futures (USDT perpetual) symbol is exchange-specific, common examples:
    - XBTUSDTM, ETHUSDTM

    We provide a best-effort mapping: BASEQUOTE + "M".
    If caller already provides an exchange-native symbol (no '/'), we return as-is.
    """
    s = (symbol or "").strip()
    if "/" not in s:
        return s
    base, quote = _split_base_quote(symbol)
    if not base or not quote:
        return s
    b = _KUCOIN_FUTURES_BASE_MAP.get(base, base)
    return f"{b}{quote}M"


def to_kraken_futures_symbol(symbol: str) -> str:
    """
    Kraken Futures instruments are exchange-specific (e.g. PF_XBTUSD, PI_XBTUSD).
    This helper is best-effort:
    - If caller already passes an exchange-native instrument (contains '_' or starts with PF_/PI_), return as-is.
    - Otherwise, map BTC->XBT and assume USD quote for futures (most Kraken Futures perps are USD margined).
    """
    s = (symbol or "").strip()
    if not s:
        return s
    up = s.upper()
    if "_" in up or up.startswith("PF_") or up.startswith("PI_"):
        return s
    base, quote = _split_base_quote(symbol)
    if not base:
        return s
    b = _KRAKEN_BASE_MAP.get(base, base)
    q = "USD"
    # Keep USDT as USD best-effort (platform-dependent)
    if quote and quote.upper() == "USD":
        q = "USD"
    return f"PF_{b}{q}"


def to_gate_currency_pair(symbol: str) -> str:
    """
    Gate spot/futures currency_pair/contract format: BASE_QUOTE, e.g. BTC_USDT.
    """
    base, quote = _split_base_quote(symbol)
    if not base or not quote:
        return symbol
    return f"{base}_{quote}"


def to_bitfinex_spot_symbol(symbol: str) -> str:
    """
    Bitfinex spot trading symbol format: tBASEQUOTE, e.g. tBTCUST.
    """
    base, quote = _split_base_quote(symbol)
    if not base or not quote:
        s = str(symbol or "").strip()
        return s if s.startswith("t") else f"t{s}"
    q = _BITFINEX_QUOTE_MAP.get(quote, quote)
    return f"t{base}{q}"


def to_bitfinex_perp_symbol(symbol: str) -> str:
    """
    Bitfinex derivatives perpetual naming (best-effort): tBASEF0:QUOTEF0, e.g. tBTCF0:USTF0.
    """
    base, quote = _split_base_quote(symbol)
    if not base or not quote:
        s = str(symbol or "").strip()
        return s if s.startswith("t") else f"t{s}"
    q = _BITFINEX_QUOTE_MAP.get(quote, quote)
    return f"t{base}F0:{q}F0"


def to_deepcoin_symbol(symbol: str) -> str:
    """
    Deepcoin symbol format: typically BASE-QUOTE for spot, BASE-QUOTE-SWAP for perpetual.
    Examples:
    - Spot: BTC-USDT
    - Perpetual: BTC-USDT-SWAP
    
    If symbol already contains '-', return as-is (already in Deepcoin format).
    """
    s = (symbol or "").strip()
    if not s:
        return s
    
    # Already in Deepcoin format
    if "-" in s:
        return s.upper()
    
    base, quote = _split_base_quote(symbol)
    if not base or not quote:
        # Best effort: remove slashes and colons
        return s.replace("/", "-").replace(":", "-").upper()
    
    # Return BASE-QUOTE format (caller adds -SWAP if needed for futures)
    return f"{base}-{quote}"


def to_deepcoin_swap_symbol(symbol: str) -> str:
    """
    Deepcoin perpetual swap symbol format: BASE-QUOTE-SWAP, e.g. BTC-USDT-SWAP.
    """
    base_symbol = to_deepcoin_symbol(symbol)
    if base_symbol.endswith("-SWAP"):
        return base_symbol
    return f"{base_symbol}-SWAP"

