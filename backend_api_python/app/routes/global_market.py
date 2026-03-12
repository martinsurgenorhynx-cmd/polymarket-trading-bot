"""
Global Market Dashboard APIs.

Provides aggregated global market data including:
- Major indices (US, Europe, Japan, Korea, Australia, India)
- Forex pairs
- Crypto prices
- Market heatmap data (crypto, stocks, forex)
- Economic calendar with impact indicators
- Fear & Greed Index / VIX
- Financial news (Chinese & English)

Endpoints:
- GET /api/global-market/overview       - Global market overview
- GET /api/global-market/heatmap        - Market heatmap data
- GET /api/global-market/news           - Financial news (with lang param)
- GET /api/global-market/calendar       - Economic calendar
- GET /api/global-market/sentiment      - Fear & Greed / VIX
- GET /api/global-market/opportunities  - Trading opportunities scanner
"""

from __future__ import annotations

import time
import requests
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from flask import Blueprint, jsonify, request, g

from app.utils.logger import get_logger
from app.utils.auth import login_required
from app.utils.config_loader import load_addon_config

logger = get_logger(__name__)

global_market_bp = Blueprint("global_market", __name__)

# Cache for market data (simple in-memory cache)
# 多用户场景下，合理的缓存可以大幅减少 API 请求
_cache: Dict[str, Dict[str, Any]] = {}
_cache_ttl = 60  # Default 60 seconds cache

# 缓存时间配置（秒）
CACHE_TTL = {
    "crypto_heatmap": 300,      # 5分钟 - 加密货币变化快但热力图不需要实时
    "forex_pairs": 120,          # 2分钟 - 外汇日内波动较小
    "stock_indices": 120,        # 2分钟 - 指数变化较慢
    "market_overview": 120,      # 2分钟 - 概览数据
    "market_heatmap": 120,       # 2分钟 - 热力图
    "commodities": 120,          # 2分钟 - 大宗商品
    "market_news": 180,          # 3分钟 - 新闻
    "economic_calendar": 3600,   # 1小时 - 日历事件
    "market_sentiment": 21600,   # 6小时 - 宏观情绪变化缓慢
    "trading_opportunities": 3600, # 1小时 - 每小时更新一次
}


def _get_cached(key: str, ttl: int = None) -> Optional[Any]:
    """Get cached data if not expired."""
    if key in _cache:
        entry = _cache[key]
        # 优先使用传入的 ttl，然后是 CACHE_TTL 配置，最后是默认值
        cache_ttl = ttl or CACHE_TTL.get(key, entry.get("ttl", _cache_ttl))
        if time.time() - entry.get("ts", 0) < cache_ttl:
            return entry.get("data")
    return None


def _set_cached(key: str, data: Any, ttl: int = None):
    """Set cache entry."""
    _cache[key] = {
        "ts": time.time(),
        "data": data,
        "ttl": ttl or CACHE_TTL.get(key, _cache_ttl)
    }


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


# ============ Data Fetchers ============

def _fetch_crypto_prices_ccxt() -> List[Dict[str, Any]]:
    """Fetch crypto prices using CCXT (system's existing data source)."""
    try:
        from app.data_sources.crypto import CryptoDataSource
        
        crypto_source = CryptoDataSource()
        
        # Top crypto symbols to fetch
        symbols = [
            "BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT",
            "ADA/USDT", "DOGE/USDT", "AVAX/USDT", "DOT/USDT", "MATIC/USDT",
            "LINK/USDT", "LTC/USDT", "UNI/USDT", "ATOM/USDT", "XLM/USDT"
        ]
        
        result = []
        for symbol in symbols:
            try:
                ticker = crypto_source.get_ticker(symbol)
                if ticker:
                    base = symbol.split("/")[0]
                    result.append({
                        "symbol": base,
                        "name": base,
                        "price": _safe_float(ticker.get("last") or ticker.get("close")),
                        "change_24h": _safe_float(ticker.get("percentage", 0)),
                        "change_7d": 0,  # CCXT doesn't provide 7d change
                        "market_cap": 0,
                        "volume_24h": _safe_float(ticker.get("quoteVolume", 0)),
                        "image": "",
                        "category": "crypto"
                    })
            except Exception as e:
                logger.debug(f"Failed to fetch {symbol}: {e}")
                continue
        
        return result
    except Exception as e:
        logger.error(f"Failed to fetch crypto prices via CCXT: {e}")
        return []


def _fetch_crypto_prices_yfinance() -> List[Dict[str, Any]]:
    """Fetch crypto prices using yfinance as alternative."""
    try:
        import yfinance as yf
        
        symbols = [
            {"yf": "BTC-USD", "symbol": "BTC", "name": "Bitcoin"},
            {"yf": "ETH-USD", "symbol": "ETH", "name": "Ethereum"},
            {"yf": "BNB-USD", "symbol": "BNB", "name": "Binance Coin"},
            {"yf": "SOL-USD", "symbol": "SOL", "name": "Solana"},
            {"yf": "XRP-USD", "symbol": "XRP", "name": "Ripple"},
            {"yf": "ADA-USD", "symbol": "ADA", "name": "Cardano"},
            {"yf": "DOGE-USD", "symbol": "DOGE", "name": "Dogecoin"},
            {"yf": "AVAX-USD", "symbol": "AVAX", "name": "Avalanche"},
            {"yf": "DOT-USD", "symbol": "DOT", "name": "Polkadot"},
            {"yf": "MATIC-USD", "symbol": "MATIC", "name": "Polygon"},
            {"yf": "LINK-USD", "symbol": "LINK", "name": "Chainlink"},
            {"yf": "LTC-USD", "symbol": "LTC", "name": "Litecoin"},
        ]
        
        yf_symbols = [s["yf"] for s in symbols]
        tickers = yf.Tickers(" ".join(yf_symbols))
        
        result = []
        for crypto in symbols:
            try:
                ticker = tickers.tickers.get(crypto["yf"])
                if ticker:
                    hist = ticker.history(period="2d")
                    if len(hist) >= 2:
                        prev = hist["Close"].iloc[-2]
                        curr = hist["Close"].iloc[-1]
                        change = ((curr - prev) / prev) * 100
                        result.append({
                            "symbol": crypto["symbol"],
                            "name": crypto["name"],
                            "price": round(curr, 2),
                            "change_24h": round(change, 2),
                            "change_7d": 0,
                            "market_cap": 0,
                            "volume_24h": 0,
                            "image": "",
                            "category": "crypto"
                        })
                    elif len(hist) == 1:
                        result.append({
                            "symbol": crypto["symbol"],
                            "name": crypto["name"],
                            "price": round(hist["Close"].iloc[-1], 2),
                            "change_24h": 0,
                            "change_7d": 0,
                            "market_cap": 0,
                            "volume_24h": 0,
                            "image": "",
                            "category": "crypto"
                        })
            except Exception as e:
                logger.debug(f"Failed to fetch {crypto['yf']}: {e}")
        
        return result
    except Exception as e:
        logger.error(f"Failed to fetch crypto via yfinance: {e}")
        return []


def _fetch_crypto_prices() -> List[Dict[str, Any]]:
    """Fetch top crypto prices - try multiple sources."""
    # Try CCXT first (uses system's existing exchange connection)
    result = _fetch_crypto_prices_ccxt()
    if result and len(result) >= 5:
        logger.info(f"Fetched {len(result)} crypto prices via CCXT")
        return result
    
    # Try yfinance as second option
    result = _fetch_crypto_prices_yfinance()
    if result and len(result) >= 5:
        logger.info(f"Fetched {len(result)} crypto prices via yfinance")
        return result
    
    # Fallback to CoinGecko
    try:
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": 30,
            "page": 1,
            "sparkline": False,
            "price_change_percentage": "24h,7d"
        }
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        
        result = []
        for coin in data:
            result.append({
                "symbol": coin.get("symbol", "").upper(),
                "name": coin.get("name", ""),
                "price": _safe_float(coin.get("current_price")),
                "change_24h": _safe_float(coin.get("price_change_percentage_24h")),
                "change_7d": _safe_float(coin.get("price_change_percentage_7d_in_currency")),
                "market_cap": _safe_float(coin.get("market_cap")),
                "volume_24h": _safe_float(coin.get("total_volume")),
                "image": coin.get("image", ""),
                "category": "crypto"
            })
        logger.info(f"Fetched {len(result)} crypto prices via CoinGecko")
        return result
    except Exception as e:
        logger.error(f"Failed to fetch crypto prices from CoinGecko: {e}")
        
    # Last resort: return placeholder data for display
    logger.warning("All crypto data sources failed, returning placeholder data")
    return [
        {"symbol": "BTC", "name": "Bitcoin", "price": 0, "change_24h": 0, "change_7d": 0, "market_cap": 0, "volume_24h": 0, "image": "", "category": "crypto"},
        {"symbol": "ETH", "name": "Ethereum", "price": 0, "change_24h": 0, "change_7d": 0, "market_cap": 0, "volume_24h": 0, "image": "", "category": "crypto"},
        {"symbol": "BNB", "name": "BNB", "price": 0, "change_24h": 0, "change_7d": 0, "market_cap": 0, "volume_24h": 0, "image": "", "category": "crypto"},
        {"symbol": "SOL", "name": "Solana", "price": 0, "change_24h": 0, "change_7d": 0, "market_cap": 0, "volume_24h": 0, "image": "", "category": "crypto"},
        {"symbol": "XRP", "name": "XRP", "price": 0, "change_24h": 0, "change_7d": 0, "market_cap": 0, "volume_24h": 0, "image": "", "category": "crypto"},
    ]


def _fetch_stock_indices() -> List[Dict[str, Any]]:
    """Fetch major stock indices using yfinance."""
    indices = [
        # US Markets - 坐标错开避免重叠
        {"symbol": "^GSPC", "name_cn": "标普500", "name_en": "S&P 500", "region": "US", "flag": "🇺🇸", "lat": 40.7, "lng": -74.0},
        {"symbol": "^DJI", "name_cn": "道琼斯", "name_en": "Dow Jones", "region": "US", "flag": "🇺🇸", "lat": 38.5, "lng": -77.0},
        {"symbol": "^IXIC", "name_cn": "纳斯达克", "name_en": "NASDAQ", "region": "US", "flag": "🇺🇸", "lat": 37.5, "lng": -122.4},
        # Europe
        {"symbol": "^GDAXI", "name_cn": "德国DAX", "name_en": "DAX", "region": "EU", "flag": "🇩🇪", "lat": 50.1109, "lng": 8.6821},
        {"symbol": "^FTSE", "name_cn": "英国富时100", "name_en": "FTSE 100", "region": "EU", "flag": "🇬🇧", "lat": 51.5074, "lng": -0.1278},
        {"symbol": "^FCHI", "name_cn": "法国CAC40", "name_en": "CAC 40", "region": "EU", "flag": "🇫🇷", "lat": 48.8566, "lng": 2.3522},
        # Japan
        {"symbol": "^N225", "name_cn": "日经225", "name_en": "Nikkei 225", "region": "JP", "flag": "🇯🇵", "lat": 35.6762, "lng": 139.6503},
        # Korea
        {"symbol": "^KS11", "name_cn": "韩国KOSPI", "name_en": "KOSPI", "region": "KR", "flag": "🇰🇷", "lat": 37.5665, "lng": 126.9780},
        # Australia
        {"symbol": "^AXJO", "name_cn": "澳洲ASX200", "name_en": "ASX 200", "region": "AU", "flag": "🇦🇺", "lat": -33.8688, "lng": 151.2093},
        # India
        {"symbol": "^BSESN", "name_cn": "印度SENSEX", "name_en": "SENSEX", "region": "IN", "flag": "🇮🇳", "lat": 19.0760, "lng": 72.8777},
    ]
    
    try:
        import yfinance as yf
        
        symbols = [idx["symbol"] for idx in indices]
        tickers = yf.Tickers(" ".join(symbols))
        
        result = []
        for idx in indices:
            try:
                ticker = tickers.tickers.get(idx["symbol"])
                if ticker:
                    hist = ticker.history(period="2d")
                    
                    if len(hist) >= 2:
                        prev_close = hist["Close"].iloc[-2]
                        current = hist["Close"].iloc[-1]
                        change = ((current - prev_close) / prev_close) * 100
                    elif len(hist) == 1:
                        current = hist["Close"].iloc[-1]
                        change = 0
                    else:
                        current = 0
                        change = 0
                    
                    result.append({
                        "symbol": idx["symbol"],
                        "name_cn": idx["name_cn"],
                        "name_en": idx["name_en"],
                        "price": round(current, 2),
                        "change": round(change, 2),
                        "region": idx["region"],
                        "flag": idx["flag"],
                        "lat": idx["lat"],
                        "lng": idx["lng"],
                        "category": "index"
                    })
            except Exception as e:
                logger.debug(f"Failed to fetch {idx['symbol']}: {e}")
                result.append({
                    "symbol": idx["symbol"],
                    "name_cn": idx["name_cn"],
                    "name_en": idx["name_en"],
                    "price": 0,
                    "change": 0,
                    "region": idx["region"],
                    "flag": idx["flag"],
                    "lat": idx["lat"],
                    "lng": idx["lng"],
                    "category": "index"
                })
        
        return result
    except Exception as e:
        logger.error(f"Failed to fetch stock indices: {e}")
        return []


def _fetch_forex_pairs() -> List[Dict[str, Any]]:
    """Fetch major forex pairs."""
    pairs = [
        {"symbol": "EURUSD=X", "name": "EUR/USD", "name_cn": "欧元/美元", "name_en": "EUR/USD", "base": "EUR", "quote": "USD"},
        {"symbol": "GBPUSD=X", "name": "GBP/USD", "name_cn": "英镑/美元", "name_en": "GBP/USD", "base": "GBP", "quote": "USD"},
        {"symbol": "USDJPY=X", "name": "USD/JPY", "name_cn": "美元/日元", "name_en": "USD/JPY", "base": "USD", "quote": "JPY"},
        {"symbol": "USDCNH=X", "name": "USD/CNH", "name_cn": "美元/离岸人民币", "name_en": "USD/CNH", "base": "USD", "quote": "CNH"},
        {"symbol": "AUDUSD=X", "name": "AUD/USD", "name_cn": "澳元/美元", "name_en": "AUD/USD", "base": "AUD", "quote": "USD"},
        {"symbol": "USDCAD=X", "name": "USD/CAD", "name_cn": "美元/加元", "name_en": "USD/CAD", "base": "USD", "quote": "CAD"},
        {"symbol": "USDCHF=X", "name": "USD/CHF", "name_cn": "美元/瑞郎", "name_en": "USD/CHF", "base": "USD", "quote": "CHF"},
        {"symbol": "NZDUSD=X", "name": "NZD/USD", "name_cn": "纽元/美元", "name_en": "NZD/USD", "base": "NZD", "quote": "USD"},
    ]
    
    try:
        import yfinance as yf
        
        symbols = [p["symbol"] for p in pairs]
        tickers = yf.Tickers(" ".join(symbols))
        
        result = []
        for pair in pairs:
            try:
                ticker = tickers.tickers.get(pair["symbol"])
                if ticker:
                    hist = ticker.history(period="2d")
                    
                    if len(hist) >= 2:
                        prev_close = hist["Close"].iloc[-2]
                        current = hist["Close"].iloc[-1]
                        change = ((current - prev_close) / prev_close) * 100
                    elif len(hist) == 1:
                        current = hist["Close"].iloc[-1]
                        change = 0
                    else:
                        current = 0
                        change = 0
                    
                    result.append({
                        "symbol": pair["name"],
                        "name": pair["name"],
                        "name_cn": pair["name_cn"],
                        "name_en": pair["name_en"],
                        "price": round(current, 5),
                        "change": round(change, 2),
                        "base": pair["base"],
                        "quote": pair["quote"],
                        "category": "forex"
                    })
            except Exception as e:
                logger.debug(f"Failed to fetch {pair['symbol']}: {e}")
        
        return result
    except Exception as e:
        logger.error(f"Failed to fetch forex pairs: {e}")
        return []


def _fetch_commodities() -> List[Dict[str, Any]]:
    """Fetch commodity prices."""
    commodities = [
        {"symbol": "GC=F", "name_cn": "黄金", "name_en": "Gold", "unit": "USD/oz"},
        {"symbol": "SI=F", "name_cn": "白银", "name_en": "Silver", "unit": "USD/oz"},
        {"symbol": "CL=F", "name_cn": "原油 WTI", "name_en": "Crude Oil WTI", "unit": "USD/bbl"},
        {"symbol": "BZ=F", "name_cn": "原油 Brent", "name_en": "Brent Oil", "unit": "USD/bbl"},
        {"symbol": "HG=F", "name_cn": "铜", "name_en": "Copper", "unit": "USD/lb"},
        {"symbol": "NG=F", "name_cn": "天然气", "name_en": "Natural Gas", "unit": "USD/MMBtu"},
    ]
    
    result = []
    
    try:
        import yfinance as yf
        
        symbols = [c["symbol"] for c in commodities]
        tickers = yf.Tickers(" ".join(symbols))
        
        for commodity in commodities:
            try:
                ticker = tickers.tickers.get(commodity["symbol"])
                if ticker:
                    hist = ticker.history(period="2d")
                    
                    if len(hist) >= 2:
                        prev_close = hist["Close"].iloc[-2]
                        current = hist["Close"].iloc[-1]
                        change = ((current - prev_close) / prev_close) * 100
                        result.append({
                            "symbol": commodity["symbol"],
                            "name_cn": commodity["name_cn"],
                            "name_en": commodity["name_en"],
                            "price": round(current, 2),
                            "change": round(change, 2),
                            "unit": commodity["unit"],
                            "category": "commodity"
                        })
                    elif len(hist) == 1:
                        result.append({
                            "symbol": commodity["symbol"],
                            "name_cn": commodity["name_cn"],
                            "name_en": commodity["name_en"],
                            "price": round(hist["Close"].iloc[-1], 2),
                            "change": 0,
                            "unit": commodity["unit"],
                            "category": "commodity"
                        })
            except Exception as e:
                logger.debug(f"Failed to fetch {commodity['symbol']}: {e}")
        
        if result:
            logger.info(f"Fetched {len(result)} commodities via yfinance")
            return result
            
    except Exception as e:
        logger.error(f"Failed to fetch commodities: {e}")
    
    # Return placeholder data if all fetches failed
    if not result:
        logger.warning("Commodities fetch failed, returning placeholder data")
        for commodity in commodities:
            result.append({
                "symbol": commodity["symbol"],
                "name_cn": commodity["name_cn"],
                "name_en": commodity["name_en"],
                "price": 0,
                "change": 0,
                "unit": commodity["unit"],
                "category": "commodity"
            })
    
    return result


def _fetch_fear_greed_index() -> Dict[str, Any]:
    """Fetch Fear & Greed Index from alternative.me (crypto)."""
    try:
        url = "https://api.alternative.me/fng/?limit=1"
        logger.debug(f"Fetching Fear & Greed Index from {url}")
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        
        if data.get("data"):
            item = data["data"][0]
            value = int(item.get("value", 50))
            classification = item.get("value_classification", "Neutral")
            logger.info(f"Fear & Greed Index fetched: {value} ({classification})")
            return {
                "value": value,
                "classification": classification,
                "timestamp": int(item.get("timestamp", 0)),
                "source": "alternative.me"
            }
        else:
            logger.warning("Fear & Greed API returned empty data")
    except requests.exceptions.Timeout:
        logger.error("Fear & Greed Index request timeout")
    except requests.exceptions.RequestException as e:
        logger.error(f"Fear & Greed Index request failed: {e}")
    except Exception as e:
        logger.error(f"Failed to fetch Fear & Greed Index: {e}")
    
    logger.warning("Returning default Fear & Greed value (50)")
    return {"value": 50, "classification": "Neutral", "timestamp": 0, "source": "N/A"}


def _fetch_vix() -> Dict[str, Any]:
    """Fetch VIX (CBOE Volatility Index) with multiple fallbacks."""
    # 默认值 - 合理的市场中性水平
    DEFAULT_VIX = {"value": 18, "change": 0, "level": "low", 
                   "interpretation": "低波动 - 市场稳定", 
                   "interpretation_en": "Low - Market Stable"}
    
    # 1) 尝试 yfinance
    try:
        import yfinance as yf
        logger.debug("Fetching VIX from yfinance")
        ticker = yf.Ticker("^VIX")
        
        try:
            hist = ticker.history(period="5d")
        except Exception as hist_err:
            logger.warning(f"yfinance VIX failed: {hist_err}")
            hist = None
        
        if hist is not None and not hist.empty and len(hist) >= 1:
            current = float(hist["Close"].iloc[-1])
            if current > 0:
                prev_close = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else current
                change = ((current - prev_close) / prev_close) * 100 if prev_close else 0
                logger.info(f"VIX from yfinance: {current:.2f}")
            else:
                raise ValueError("VIX value is 0")
        else:
            raise ValueError("VIX history empty")
            
    except Exception as e:
        logger.warning(f"yfinance VIX failed, trying akshare: {e}")
        
        # 2) 尝试 Akshare (对中国服务器友好)
        try:
            import akshare as ak
            vix_df = ak.index_vix()  # VIX指数
            if vix_df is not None and len(vix_df) > 0:
                current = float(vix_df.iloc[-1]['close'])
                prev_close = float(vix_df.iloc[-2]['close']) if len(vix_df) >= 2 else current
                change = ((current - prev_close) / prev_close) * 100 if prev_close else 0
                logger.info(f"VIX from akshare: {current:.2f}")
            else:
                raise ValueError("Akshare VIX empty")
        except Exception as ak_err:
            logger.warning(f"Akshare VIX also failed: {ak_err}")
            return DEFAULT_VIX
    
    if current <= 0:
        return DEFAULT_VIX
    
    # VIX levels interpretation
    if current < 12:
        level = "very_low"
        interpretation_cn = "极低波动 - 市场极度乐观"
        interpretation_en = "Very Low - Extreme Optimism"
    elif current < 20:
        level = "low"
        interpretation_cn = "低波动 - 市场稳定"
        interpretation_en = "Low - Market Stable"
    elif current < 25:
        level = "moderate"
        interpretation_cn = "中等波动 - 正常水平"
        interpretation_en = "Moderate - Normal Level"
    elif current < 30:
        level = "high"
        interpretation_cn = "高波动 - 市场担忧"
        interpretation_en = "High - Market Concern"
    else:
        level = "very_high"
        interpretation_cn = "极高波动 - 市场恐慌"
        interpretation_en = "Very High - Market Panic"
    
    return {
        "value": round(current, 2),
        "change": round(change, 2),
        "level": level,
        "interpretation": interpretation_cn,
        "interpretation_en": interpretation_en
    }


def _fetch_dollar_index() -> Dict[str, Any]:
    """Fetch US Dollar Index (DXY) with multiple fallbacks."""
    # 默认值 - 合理的中性水平
    DEFAULT_DXY = {"value": 104, "change": 0, "level": "moderate_strong",
                   "interpretation": "美元偏强 - 关注资金流向", 
                   "interpretation_en": "Moderately Strong - Watch capital flows"}
    
    current = 0
    change = 0
    
    # 1) 尝试 yfinance
    try:
        import yfinance as yf
        logger.debug("Fetching DXY from yfinance")
        ticker = yf.Ticker("DX-Y.NYB")
        
        try:
            hist = ticker.history(period="5d")
        except Exception as hist_err:
            logger.warning(f"yfinance DXY failed: {hist_err}")
            hist = None
        
        if hist is not None and not hist.empty and len(hist) >= 1:
            current = float(hist["Close"].iloc[-1])
            if current > 0:
                prev_close = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else current
                change = ((current - prev_close) / prev_close) * 100 if prev_close else 0
                logger.info(f"DXY from yfinance: {current:.2f}")
            else:
                raise ValueError("DXY value is 0")
        else:
            raise ValueError("DXY history empty")
            
    except Exception as e:
        logger.warning(f"yfinance DXY failed, trying akshare: {e}")
        
        # 2) 尝试 Akshare 获取美元指数
        try:
            import akshare as ak
            # Akshare 外汇数据
            fx_df = ak.currency_boc_sina(symbol="美元")
            if fx_df is not None and len(fx_df) > 0:
                # 使用中行汇率估算 DXY (近似值)
                usd_cny = float(fx_df.iloc[-1]['中行汇买价']) / 100
                current = usd_cny * 14.5  # 大致换算
                change = 0
                logger.info(f"DXY estimated from akshare: {current:.2f}")
            else:
                raise ValueError("Akshare DXY empty")
        except Exception as ak_err:
            logger.warning(f"Akshare DXY also failed: {ak_err}")
            return DEFAULT_DXY
    
    if current <= 0:
        return DEFAULT_DXY
    
    # DXY interpretation
    if current > 105:
        level = "strong"
        interpretation_cn = "美元强势 - 利空大宗商品/新兴市场"
        interpretation_en = "Strong USD - Bearish commodities/EM"
    elif current > 100:
        level = "moderate_strong"
        interpretation_cn = "美元偏强 - 关注资金流向"
        interpretation_en = "Moderately Strong - Watch capital flows"
    elif current > 95:
        level = "neutral"
        interpretation_cn = "美元中性 - 市场均衡"
        interpretation_en = "Neutral - Market balanced"
    elif current > 90:
        level = "moderate_weak"
        interpretation_cn = "美元偏弱 - 利多风险资产"
        interpretation_en = "Moderately Weak - Bullish risk assets"
    else:
        level = "weak"
        interpretation_cn = "美元疲软 - 利多黄金/大宗商品"
        interpretation_en = "Weak USD - Bullish gold/commodities"
    
    logger.info(f"DXY fetched: {current:.2f} ({level})")
    return {
        "value": round(current, 2),
        "change": round(change, 2),
        "level": level,
        "interpretation": interpretation_cn,
        "interpretation_en": interpretation_en
    }


def _fetch_yield_curve() -> Dict[str, Any]:
    """Fetch Treasury Yield Curve (10Y - 2Y spread)."""
    try:
        import yfinance as yf
        
        logger.debug("Fetching Treasury Yield Curve")
        
        # 10-year Treasury yield
        tnx = yf.Ticker("^TNX")
        
        # 使用 try-except 包裹 history 调用
        try:
            tnx_hist = tnx.history(period="5d")
        except Exception as hist_err:
            logger.warning(f"TNX history fetch failed: {hist_err}")
            tnx_hist = None
        
        # 安全检查
        if tnx_hist is None or tnx_hist.empty:
            logger.warning("TNX history is None or empty, returning default")
            return {
                "yield_10y": 4.2, "yield_2y": 4.0, "spread": 0.2, "change": 0,
                "level": "normal", "interpretation": "数据暂不可用", 
                "interpretation_en": "Data temporarily unavailable", "signal": "neutral"
            }
        
        if len(tnx_hist) >= 1:
            yield_10y = tnx_hist["Close"].iloc[-1]
            
            # Get 2-year yield (using different ticker)
            try:
                # Use ^TYX (30-year) and calculate approximate 2Y
                tyx = yf.Ticker("^TYX")
                tyx_hist = tyx.history(period="5d")
                yield_30y = tyx_hist["Close"].iloc[-1] if len(tyx_hist) >= 1 else 0
                
                # Approximate 2Y as lower bound (rough estimate)
                # In reality, we'd need proper 2Y data
                yield_2y = yield_10y * 0.85  # Rough approximation
                
                spread = yield_10y - yield_2y
                
                if len(tnx_hist) >= 2:
                    prev_10y = tnx_hist["Close"].iloc[-2]
                    prev_2y = prev_10y * 0.85
                    prev_spread = prev_10y - prev_2y
                    change = spread - prev_spread
                else:
                    change = 0
                
            except:
                yield_2y = yield_10y * 0.85
                spread = yield_10y - yield_2y
                change = 0
        else:
            yield_10y = 0
            yield_2y = 0
            spread = 0
            change = 0
        
        # Yield curve interpretation
        if spread < -0.5:
            level = "deeply_inverted"
            interpretation_cn = "深度倒挂 - 强烈衰退信号"
            interpretation_en = "Deeply Inverted - Strong recession signal"
            signal = "bearish"
        elif spread < 0:
            level = "inverted"
            interpretation_cn = "收益率倒挂 - 衰退预警"
            interpretation_en = "Inverted - Recession warning"
            signal = "bearish"
        elif spread < 0.5:
            level = "flat"
            interpretation_cn = "曲线平坦 - 经济放缓信号"
            interpretation_en = "Flat - Economic slowdown signal"
            signal = "neutral"
        elif spread < 1.5:
            level = "normal"
            interpretation_cn = "正常曲线 - 经济健康"
            interpretation_en = "Normal - Healthy economy"
            signal = "bullish"
        else:
            level = "steep"
            interpretation_cn = "陡峭曲线 - 经济扩张预期"
            interpretation_en = "Steep - Economic expansion expected"
            signal = "bullish"
        
        logger.info(f"Yield Curve: 10Y={yield_10y:.2f}%, spread={spread:.2f}% ({level})")
        return {
            "yield_10y": round(yield_10y, 2),
            "yield_2y": round(yield_2y, 2),
            "spread": round(spread, 2),
            "change": round(change, 3),
            "level": level,
            "signal": signal,
            "interpretation": interpretation_cn,
            "interpretation_en": interpretation_en
        }
    except Exception as e:
        logger.error(f"Failed to fetch Yield Curve: {e}", exc_info=True)
        return {
            "yield_10y": 0, "yield_2y": 0, "spread": 0, "change": 0,
            "level": "unknown", "signal": "neutral",
            "interpretation": "数据获取失败", "interpretation_en": "Data fetch failed"
        }


def _fetch_vxn() -> Dict[str, Any]:
    """Fetch NASDAQ Volatility Index (VXN) - Tech sector fear gauge."""
    try:
        import yfinance as yf
        
        logger.debug("Fetching VXN from yfinance")
        ticker = yf.Ticker("^VXN")
        hist = ticker.history(period="5d")
        
        if len(hist) >= 2:
            prev_close = hist["Close"].iloc[-2]
            current = hist["Close"].iloc[-1]
            change = ((current - prev_close) / prev_close) * 100
        elif len(hist) == 1:
            current = hist["Close"].iloc[-1]
            change = 0
        else:
            current = 0
            change = 0
        
        # VXN levels (typically higher than VIX)
        if current < 15:
            level = "very_low"
            interpretation_cn = "科技股极低波动 - 市场乐观"
            interpretation_en = "Very Low Tech Volatility - Optimistic"
        elif current < 22:
            level = "low"
            interpretation_cn = "科技股低波动 - 稳定"
            interpretation_en = "Low Tech Volatility - Stable"
        elif current < 28:
            level = "moderate"
            interpretation_cn = "科技股中等波动 - 正常"
            interpretation_en = "Moderate Tech Volatility - Normal"
        elif current < 35:
            level = "high"
            interpretation_cn = "科技股高波动 - 谨慎"
            interpretation_en = "High Tech Volatility - Caution"
        else:
            level = "very_high"
            interpretation_cn = "科技股极高波动 - 恐慌"
            interpretation_en = "Very High Tech Volatility - Panic"
        
        logger.info(f"VXN fetched: {current:.2f} ({level})")
        return {
            "value": round(current, 2),
            "change": round(change, 2),
            "level": level,
            "interpretation": interpretation_cn,
            "interpretation_en": interpretation_en
        }
    except Exception as e:
        logger.error(f"Failed to fetch VXN: {e}", exc_info=True)
        return {"value": 0, "change": 0, "level": "unknown", "interpretation": "数据获取失败", "interpretation_en": "Data fetch failed"}


def _fetch_gvz() -> Dict[str, Any]:
    """Fetch Gold Volatility Index (GVZ) - Safe haven sentiment."""
    try:
        import yfinance as yf
        
        logger.debug("Fetching GVZ from yfinance")
        ticker = yf.Ticker("^GVZ")
        hist = ticker.history(period="5d")
        
        if len(hist) >= 2:
            prev_close = hist["Close"].iloc[-2]
            current = hist["Close"].iloc[-1]
            change = ((current - prev_close) / prev_close) * 100
        elif len(hist) == 1:
            current = hist["Close"].iloc[-1]
            change = 0
        else:
            current = 0
            change = 0
        
        # GVZ levels
        if current < 12:
            level = "very_low"
            interpretation_cn = "黄金低波动 - 避险需求低"
            interpretation_en = "Low Gold Vol - Low safe haven demand"
        elif current < 16:
            level = "low"
            interpretation_cn = "黄金稳定 - 市场平静"
            interpretation_en = "Gold Stable - Market calm"
        elif current < 20:
            level = "moderate"
            interpretation_cn = "黄金中等波动 - 关注避险情绪"
            interpretation_en = "Moderate Gold Vol - Watch safe haven"
        elif current < 25:
            level = "high"
            interpretation_cn = "黄金高波动 - 避险需求上升"
            interpretation_en = "High Gold Vol - Rising safe haven demand"
        else:
            level = "very_high"
            interpretation_cn = "黄金极高波动 - 市场避险"
            interpretation_en = "Very High Gold Vol - Flight to safety"
        
        logger.info(f"GVZ fetched: {current:.2f} ({level})")
        return {
            "value": round(current, 2),
            "change": round(change, 2),
            "level": level,
            "interpretation": interpretation_cn,
            "interpretation_en": interpretation_en
        }
    except Exception as e:
        logger.error(f"Failed to fetch GVZ: {e}", exc_info=True)
        return {"value": 0, "change": 0, "level": "unknown", "interpretation": "数据获取失败", "interpretation_en": "Data fetch failed"}


def _fetch_put_call_ratio() -> Dict[str, Any]:
    """
    Calculate Put/Call Ratio proxy using VIX term structure.
    Higher ratio = more bearish sentiment.
    """
    try:
        import yfinance as yf
        
        logger.debug("Calculating Put/Call Ratio proxy")
        
        # Use VIX and VIX3M as proxy for put/call sentiment
        vix = yf.Ticker("^VIX")
        vix3m = yf.Ticker("^VIX3M")
        
        vix_hist = vix.history(period="5d")
        vix3m_hist = vix3m.history(period="5d")
        
        if len(vix_hist) >= 1 and len(vix3m_hist) >= 1:
            vix_val = vix_hist["Close"].iloc[-1]
            vix3m_val = vix3m_hist["Close"].iloc[-1]
            
            # VIX/VIX3M ratio as sentiment proxy
            # > 1 = backwardation (fear), < 1 = contango (complacency)
            ratio = vix_val / vix3m_val if vix3m_val > 0 else 1.0
            
            if len(vix_hist) >= 2 and len(vix3m_hist) >= 2:
                prev_ratio = vix_hist["Close"].iloc[-2] / vix3m_hist["Close"].iloc[-2] if vix3m_hist["Close"].iloc[-2] > 0 else 1.0
                change = ((ratio - prev_ratio) / prev_ratio) * 100
            else:
                change = 0
        else:
            ratio = 1.0
            change = 0
        
        # Interpretation
        if ratio > 1.15:
            level = "high_fear"
            interpretation_cn = "VIX倒挂 - 短期恐慌情绪高涨"
            interpretation_en = "VIX Backwardation - High short-term fear"
            signal = "bearish"
        elif ratio > 1.0:
            level = "elevated"
            interpretation_cn = "轻度倒挂 - 市场谨慎"
            interpretation_en = "Slight Backwardation - Market cautious"
            signal = "neutral"
        elif ratio > 0.9:
            level = "normal"
            interpretation_cn = "正常结构 - 市场稳定"
            interpretation_en = "Normal Structure - Market stable"
            signal = "neutral"
        elif ratio > 0.8:
            level = "complacent"
            interpretation_cn = "深度正价差 - 市场自满"
            interpretation_en = "Deep Contango - Market complacent"
            signal = "bullish"
        else:
            level = "extreme_complacency"
            interpretation_cn = "极度自满 - 警惕反转"
            interpretation_en = "Extreme Complacency - Watch for reversal"
            signal = "neutral"
        
        logger.info(f"VIX Term Structure: ratio={ratio:.3f} ({level})")
        return {
            "value": round(ratio, 3),
            "vix": round(vix_val, 2) if 'vix_val' in dir() else 0,
            "vix3m": round(vix3m_val, 2) if 'vix3m_val' in dir() else 0,
            "change": round(change, 2),
            "level": level,
            "signal": signal,
            "interpretation": interpretation_cn,
            "interpretation_en": interpretation_en
        }
    except Exception as e:
        logger.error(f"Failed to calculate Put/Call proxy: {e}", exc_info=True)
        return {
            "value": 1.0, "vix": 0, "vix3m": 0, "change": 0,
            "level": "unknown", "signal": "neutral",
            "interpretation": "数据获取失败", "interpretation_en": "Data fetch failed"
        }


def _fetch_financial_news(lang: str = "all") -> Dict[str, List[Dict[str, Any]]]:
    """Fetch financial news using search service - separated by language."""
    result = {"cn": [], "en": []}
    
    try:
        from app.services.search import SearchService
        search = SearchService()
        
        # Chinese news queries
        cn_queries = [
            "加密货币新闻",
            "美联储利率",
            "美股市场最新消息",
            "外汇市场分析",
            "全球经济数据",
            "期货市场动态",
        ]
        
        # English news queries
        en_queries = [
            "stock market news today",
            "cryptocurrency bitcoin news",
            "forex market analysis",
            "federal reserve interest rate",
            "global economic outlook",
            "S&P 500 market update",
        ]
        
        # Fetch Chinese news
        if lang in ("all", "cn"):
            for query in cn_queries:
                try:
                    results = search.search(query, num_results=5, date_restrict="d1")
                    for r in results:
                        result["cn"].append({
                            "title": r.get("title", ""),
                            "link": r.get("link", ""),
                            "snippet": r.get("snippet", ""),
                            "source": r.get("source", ""),
                            "published": r.get("published", ""),
                            "category": query,
                            "lang": "cn"
                        })
                except Exception:
                    pass
        
        # Fetch English news
        if lang in ("all", "en"):
            for query in en_queries:
                try:
                    results = search.search(query, num_results=5, date_restrict="d1")
                    for r in results:
                        result["en"].append({
                            "title": r.get("title", ""),
                            "link": r.get("link", ""),
                            "snippet": r.get("snippet", ""),
                            "source": r.get("source", ""),
                            "published": r.get("published", ""),
                            "category": query,
                            "lang": "en"
                        })
                except Exception:
                    pass
        
        # Remove duplicates
        for lang_key in ["cn", "en"]:
            seen = set()
            unique = []
            for news in result[lang_key]:
                link = news.get("link", "")
                if link and link not in seen:
                    seen.add(link)
                    unique.append(news)
            result[lang_key] = unique[:15]  # Limit to 15 per language
        
    except Exception as e:
        logger.error(f"Failed to fetch financial news: {e}")
    
    return result


def _get_economic_calendar() -> List[Dict[str, Any]]:
    """
    Get economic calendar events with impact indicators.
    Impact: bullish (利多), bearish (利空), neutral (中性)
    """
    today = datetime.now()
    events = []
    
    # Comprehensive economic events with impact analysis
    sample_events = [
        {
            "name": "美国非农就业数据",
            "name_en": "US Non-Farm Payrolls",
            "country": "US",
            "importance": "high",
            "forecast": "180K",
            "previous": "175K",
            "impact_if_above": "bullish",  # 高于预期利多美元
            "impact_if_below": "bearish",
            "impact_desc": "高于预期利多美元/美股，低于预期利空",
            "impact_desc_en": "Above forecast: bullish USD/stocks; Below: bearish"
        },
        {
            "name": "美联储利率决议",
            "name_en": "Fed Interest Rate Decision",
            "country": "US",
            "importance": "high",
            "forecast": "5.25%",
            "previous": "5.25%",
            "impact_if_above": "bearish",  # 加息利空股市
            "impact_if_below": "bullish",
            "impact_desc": "加息利空股市/加密货币，降息利多",
            "impact_desc_en": "Rate hike: bearish stocks/crypto; Cut: bullish"
        },
        {
            "name": "美国CPI月率",
            "name_en": "US CPI m/m",
            "country": "US",
            "importance": "high",
            "forecast": "0.3%",
            "previous": "0.4%",
            "impact_if_above": "bearish",  # CPI高利空
            "impact_if_below": "bullish",
            "impact_desc": "CPI高于预期增加加息预期，利空股市",
            "impact_desc_en": "Higher CPI increases rate hike expectations, bearish stocks"
        },
        {
            "name": "欧洲央行利率决议",
            "name_en": "ECB Interest Rate Decision",
            "country": "EU",
            "importance": "high",
            "forecast": "4.50%",
            "previous": "4.50%",
            "impact_if_above": "bearish",
            "impact_if_below": "bullish",
            "impact_desc": "加息利空欧股，利多欧元",
            "impact_desc_en": "Rate hike: bearish EU stocks, bullish EUR"
        },
        {
            "name": "日本央行利率决议",
            "name_en": "BoJ Interest Rate Decision",
            "country": "JP",
            "importance": "high",
            "forecast": "0.10%",
            "previous": "0.10%",
            "impact_if_above": "bullish",  # 日本加息利多日元
            "impact_if_below": "bearish",
            "impact_desc": "加息预期利多日元，利空日股",
            "impact_desc_en": "Rate hike expectation: bullish JPY, bearish Nikkei"
        },
        {
            "name": "美国初请失业金人数",
            "name_en": "US Initial Jobless Claims",
            "country": "US",
            "importance": "medium",
            "forecast": "215K",
            "previous": "212K",
            "impact_if_above": "bearish",
            "impact_if_below": "bullish",
            "impact_desc": "失业人数上升利空美元，利多黄金",
            "impact_desc_en": "Rising claims: bearish USD, bullish gold"
        },
        {
            "name": "英国央行利率决议",
            "name_en": "BoE Interest Rate Decision",
            "country": "UK",
            "importance": "high",
            "forecast": "5.25%",
            "previous": "5.25%",
            "impact_if_above": "bullish",
            "impact_if_below": "bearish",
            "impact_desc": "加息利多英镑，利空英股",
            "impact_desc_en": "Rate hike: bullish GBP, bearish UK stocks"
        },
        {
            "name": "美国零售销售月率",
            "name_en": "US Retail Sales m/m",
            "country": "US",
            "importance": "medium",
            "forecast": "0.4%",
            "previous": "0.6%",
            "impact_if_above": "bullish",
            "impact_if_below": "bearish",
            "impact_desc": "零售数据强劲利多美元和美股",
            "impact_desc_en": "Strong retail: bullish USD and stocks"
        },
        {
            "name": "OPEC月度报告",
            "name_en": "OPEC Monthly Report",
            "country": "INTL",
            "importance": "medium",
            "forecast": "-",
            "previous": "-",
            "impact_if_above": "bullish",
            "impact_if_below": "bearish",
            "impact_desc": "减产预期利多原油，增产预期利空",
            "impact_desc_en": "Production cut: bullish oil; Increase: bearish"
        },
    ]
    
    import random
    
    for i, evt in enumerate(sample_events):
        # Some events in the past (released), some in the future (upcoming)
        days_offset = i % 14 - 5  # Range from -5 to +8 days
        event_date = today + timedelta(days=days_offset)
        hour = (8 + (i * 3)) % 24
        
        # Determine if event has been released (past events)
        is_released = event_date.date() < today.date() or (
            event_date.date() == today.date() and hour < today.hour
        )
        
        # Generate actual value and impact for released events
        actual_value = None
        actual_impact = None
        expected_impact = evt["impact_if_above"]  # Default expected impact
        
        if is_released:
            # Simulate actual values
            forecast_num = ''.join(filter(lambda x: x.isdigit() or x == '.', evt["forecast"]))
            if forecast_num:
                try:
                    base = float(forecast_num)
                    # Random variation around forecast
                    variation = random.uniform(-0.15, 0.15)
                    actual_num = base * (1 + variation)
                    
                    # Format like the forecast
                    if 'K' in evt["forecast"]:
                        actual_value = f"{actual_num:.0f}K"
                    elif '%' in evt["forecast"]:
                        actual_value = f"{actual_num:.2f}%"
                    else:
                        actual_value = f"{actual_num:.2f}"
                    
                    # Determine actual impact based on actual vs forecast
                    if actual_num > base:
                        actual_impact = evt["impact_if_above"]
                    elif actual_num < base:
                        actual_impact = evt["impact_if_below"]
                    else:
                        actual_impact = "neutral"
                except:
                    actual_value = evt["forecast"]
                    actual_impact = "neutral"
            else:
                actual_value = evt["forecast"]
                actual_impact = "neutral"
        
        events.append({
            "id": i + 1,
            "name": evt["name"],
            "name_en": evt["name_en"],
            "country": evt["country"],
            "date": event_date.strftime("%Y-%m-%d"),
            "time": f"{hour:02d}:30",
            "importance": evt["importance"],
            "actual": actual_value,
            "forecast": evt["forecast"],
            "previous": evt["previous"],
            "impact_if_above": evt["impact_if_above"],
            "impact_if_below": evt["impact_if_below"],
            "impact_desc": evt["impact_desc"],
            "impact_desc_en": evt["impact_desc_en"],
            "expected_impact": expected_impact,
            "actual_impact": actual_impact,
            "is_released": is_released
        })
    
    # Sort by date
    events.sort(key=lambda x: (x["date"], x["time"]))
    
    return events


def _generate_heatmap_data() -> Dict[str, Any]:
    """Generate heatmap data for crypto, stock sectors, and forex."""
    
    # Get crypto data (prefer market-cap ranked data for heatmap)
    # NOTE: CCXT/yfinance often lack market_cap -> heatmap should use CoinGecko when possible.
    crypto_data = _get_cached("crypto_heatmap")
    if not crypto_data:
        try:
            url = "https://api.coingecko.com/api/v3/coins/markets"
            params = {
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": 30,
                "page": 1,
                "sparkline": False,
                "price_change_percentage": "24h"
            }
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json() or []
            crypto_data = []
            for coin in data:
                crypto_data.append({
                    "symbol": (coin.get("symbol") or "").upper(),
                    "name": coin.get("name", ""),
                    "price": _safe_float(coin.get("current_price")),
                    "change_24h": _safe_float(coin.get("price_change_percentage_24h")),
                    "market_cap": _safe_float(coin.get("market_cap")),
                    "volume_24h": _safe_float(coin.get("total_volume")),
                    "image": coin.get("image", ""),
                    "category": "crypto"
                })
            logger.info(f"Fetched crypto heatmap data via CoinGecko: {len(crypto_data)} items")
            # Heatmap data doesn't need ultra-frequent refresh
            _set_cached("crypto_heatmap", crypto_data, 300)
        except Exception as e:
            logger.error(f"Failed to fetch crypto heatmap via CoinGecko: {e}")
            # Fallback to existing multi-source crypto fetcher
            crypto_data = _get_cached("crypto_prices") or _fetch_crypto_prices()
            _set_cached("crypto_prices", crypto_data, 30)
            _set_cached("crypto_heatmap", crypto_data, 30)
    
    # Get forex data
    forex_data = _get_cached("forex_pairs")
    if not forex_data:
        forex_data = _fetch_forex_pairs()
        _set_cached("forex_pairs", forex_data, 30)
    
    heatmap = {
        "crypto": [],
        "sectors": [],
        "forex": [],
        "commodities": [],  # 新增大宗商品热力图
        "indices": []
    }
    
    # Commodities heatmap (黄金、白银、原油等)
    commodities_data = _get_cached("commodities")
    if not commodities_data:
        commodities_data = _fetch_commodities()
        _set_cached("commodities", commodities_data)
    
    for comm in (commodities_data or []):
        heatmap["commodities"].append({
            "name": comm.get("name_cn", comm.get("name_en", "")),
            "name_cn": comm.get("name_cn", ""),
            "name_en": comm.get("name_en", ""),
            "value": comm.get("change", 0),
            "price": comm.get("price", 0),
            "unit": comm.get("unit", "")
        })
    
    # Crypto heatmap
    # Ensure mainstream coins by market cap appear first; also avoid blank symbols
    crypto_sorted = sorted(
        (crypto_data or []),
        key=lambda x: _safe_float(x.get("market_cap", 0)),
        reverse=True
    )
    for coin in [c for c in crypto_sorted if c.get("symbol")][:25]:
        heatmap["crypto"].append({
            "name": coin.get("symbol", ""),
            "fullName": coin.get("name", ""),
            "value": coin.get("change_24h", 0),
            "marketCap": coin.get("market_cap", 0),
            "volume": coin.get("volume_24h", 0),
            "price": coin.get("price", 0)
        })
    
    # Forex heatmap
    for pair in forex_data:
        heatmap["forex"].append({
            "name": pair.get("name", ""),
            "name_cn": pair.get("name_cn", pair.get("name", "")),
            "name_en": pair.get("name_en", pair.get("name", "")),
            "value": pair.get("change", 0),
            "price": pair.get("price", 0)
        })
    
    # Stock sectors (using ETFs as proxy for real-time data)
    sectors = [
        {"name": "科技", "name_en": "Technology", "etf": "XLK", "value": 0, "stocks": ["AAPL", "MSFT", "GOOGL", "NVDA", "META"]},
        {"name": "金融", "name_en": "Financials", "etf": "XLF", "value": 0, "stocks": ["JPM", "BAC", "WFC", "GS", "MS"]},
        {"name": "医疗", "name_en": "Healthcare", "etf": "XLV", "value": 0, "stocks": ["JNJ", "PFE", "UNH", "MRK", "ABBV"]},
        {"name": "消费", "name_en": "Consumer", "etf": "XLY", "value": 0, "stocks": ["AMZN", "TSLA", "HD", "NKE", "MCD"]},
        {"name": "能源", "name_en": "Energy", "etf": "XLE", "value": 0, "stocks": ["XOM", "CVX", "COP", "SLB", "EOG"]},
        {"name": "工业", "name_en": "Industrials", "etf": "XLI", "value": 0, "stocks": ["CAT", "BA", "GE", "HON", "UPS"]},
        {"name": "材料", "name_en": "Materials", "etf": "XLB", "value": 0, "stocks": ["LIN", "APD", "DD", "NEM", "FCX"]},
        {"name": "公用事业", "name_en": "Utilities", "etf": "XLU", "value": 0, "stocks": ["NEE", "DUK", "SO", "D", "AEP"]},
        {"name": "房地产", "name_en": "Real Estate", "etf": "XLRE", "value": 0, "stocks": ["AMT", "PLD", "CCI", "EQIX", "SPG"]},
        {"name": "通信", "name_en": "Communication", "etf": "XLC", "value": 0, "stocks": ["GOOGL", "META", "DIS", "NFLX", "VZ"]},
    ]
    
    # Try to fetch real sector ETF data
    try:
        import yfinance as yf
        etf_symbols = [s["etf"] for s in sectors]
        tickers = yf.Tickers(" ".join(etf_symbols))
        
        for sector in sectors:
            try:
                ticker = tickers.tickers.get(sector["etf"])
                if ticker:
                    hist = ticker.history(period="2d")
                    if len(hist) >= 2:
                        prev = hist["Close"].iloc[-2]
                        curr = hist["Close"].iloc[-1]
                        sector["value"] = round(((curr - prev) / prev) * 100, 2)
                    elif len(hist) == 1:
                        sector["value"] = 0
            except Exception:
                pass
    except Exception as e:
        logger.debug(f"Failed to fetch sector ETFs: {e}")
    
    heatmap["sectors"] = sectors
    
    # Index heatmap by region
    indices_data = _get_cached("stock_indices")
    if indices_data:
        for idx in indices_data:
            heatmap["indices"].append({
                "symbol": idx.get("symbol", ""),
                "name": idx.get("name_cn", idx.get("name", "")),
                "name_cn": idx.get("name_cn", ""),
                "name_en": idx.get("name_en", ""),
                "region": idx.get("region", ""),
                "value": idx.get("change", 0),
                "price": idx.get("price", 0),
                "flag": idx.get("flag", "")
            })
    
    return heatmap


# ============ API Endpoints ============

@global_market_bp.route("/overview", methods=["GET"])
@login_required
def market_overview():
    """
    Get global market overview including indices, forex, crypto, and commodities.
    Includes geo coordinates for world map display.
    """
    try:
        # Check cache first
        cached = _get_cached("market_overview", 30)
        if cached:
            logger.debug(f"Returning cached overview: indices={len(cached.get('indices', []))}, "
                        f"forex={len(cached.get('forex', []))}, crypto={len(cached.get('crypto', []))}, "
                        f"commodities={len(cached.get('commodities', []))}")
            return jsonify({"code": 1, "msg": "success", "data": cached})
        
        logger.info("Fetching fresh market overview data...")
        
        # Fetch data in parallel
        result = {
            "indices": [],
            "forex": [],
            "crypto": [],
            "commodities": [],
            "timestamp": int(time.time())
        }
        
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                executor.submit(_fetch_stock_indices): "indices",
                executor.submit(_fetch_forex_pairs): "forex",
                executor.submit(_fetch_crypto_prices): "crypto",
                executor.submit(_fetch_commodities): "commodities"
            }
            
            for future in as_completed(futures):
                key = futures[future]
                try:
                    data = future.result()
                    result[key] = data if data else []
                    logger.info(f"Fetched {key}: {len(result[key])} items")
                    # Cache individual results
                    _set_cached(f"{key}_data", result[key], 30)
                except Exception as e:
                    logger.error(f"Failed to fetch {key}: {e}", exc_info=True)
                    result[key] = []
        
        # Log summary
        logger.info(f"Market overview complete: indices={len(result['indices'])}, "
                   f"forex={len(result['forex'])}, crypto={len(result['crypto'])}, "
                   f"commodities={len(result['commodities'])}")
        
        # Also cache indices for heatmap
        _set_cached("stock_indices", result["indices"], 30)
        _set_cached("forex_pairs", result["forex"], 30)
        _set_cached("crypto_prices", result["crypto"], 30)
        
        # Cache the full result
        _set_cached("market_overview", result, 30)
        
        return jsonify({"code": 1, "msg": "success", "data": result})
        
    except Exception as e:
        logger.error(f"market_overview failed: {e}", exc_info=True)
        return jsonify({"code": 0, "msg": str(e), "data": None}), 500


@global_market_bp.route("/heatmap", methods=["GET"])
@login_required
def market_heatmap():
    """
    Get market heatmap data for crypto, stock sectors, forex, and indices.
    """
    try:
        cached = _get_cached("market_heatmap", 30)
        if cached:
            return jsonify({"code": 1, "msg": "success", "data": cached})
        
        data = _generate_heatmap_data()
        _set_cached("market_heatmap", data, 30)
        
        return jsonify({"code": 1, "msg": "success", "data": data})
        
    except Exception as e:
        logger.error(f"market_heatmap failed: {e}", exc_info=True)
        return jsonify({"code": 0, "msg": str(e), "data": None}), 500


@global_market_bp.route("/news", methods=["GET"])
@login_required
def market_news():
    """
    Get financial news from various sources.
    Query params:
        - lang: 'cn', 'en', or 'all' (default: 'all')
    """
    try:
        lang = request.args.get("lang", "all")
        cache_key = f"market_news_{lang}"
        
        cached = _get_cached(cache_key, 180)  # 3 minutes cache for news
        if cached:
            return jsonify({"code": 1, "msg": "success", "data": cached})
        
        news = _fetch_financial_news(lang)
        _set_cached(cache_key, news, 180)
        
        return jsonify({"code": 1, "msg": "success", "data": news})
        
    except Exception as e:
        logger.error(f"market_news failed: {e}", exc_info=True)
        return jsonify({"code": 0, "msg": str(e), "data": None}), 500


@global_market_bp.route("/calendar", methods=["GET"])
@login_required
def economic_calendar():
    """
    Get economic calendar events with impact indicators.
    """
    try:
        cached = _get_cached("economic_calendar", 3600)  # 1 hour cache
        if cached:
            return jsonify({"code": 1, "msg": "success", "data": cached})
        
        events = _get_economic_calendar()
        _set_cached("economic_calendar", events, 3600)
        
        return jsonify({"code": 1, "msg": "success", "data": events})
        
    except Exception as e:
        logger.error(f"economic_calendar failed: {e}", exc_info=True)
        return jsonify({"code": 0, "msg": str(e), "data": None}), 500


@global_market_bp.route("/sentiment", methods=["GET"])
@login_required
def market_sentiment():
    """
    Get comprehensive market sentiment indicators.
    Includes: Fear & Greed, VIX, DXY, Yield Curve, VXN, GVZ, VIX Term Structure.
    """
    try:
        # 缓存6小时 (21600秒)，宏观数据变化缓慢，减少 API 调用
        MACRO_CACHE_TTL = 21600  # 6 hours
        cached = _get_cached("market_sentiment", MACRO_CACHE_TTL)
        if cached:
            logger.debug("Returning cached sentiment data (6h cache)")
            return jsonify({"code": 1, "msg": "success", "data": cached})
        
        logger.info("Fetching fresh sentiment data (comprehensive)")
        
        # Fetch all indicators in parallel
        with ThreadPoolExecutor(max_workers=7) as executor:
            futures = {
                executor.submit(_fetch_fear_greed_index): "fear_greed",
                executor.submit(_fetch_vix): "vix",
                executor.submit(_fetch_dollar_index): "dxy",
                executor.submit(_fetch_yield_curve): "yield_curve",
                executor.submit(_fetch_vxn): "vxn",
                executor.submit(_fetch_gvz): "gvz",
                executor.submit(_fetch_put_call_ratio): "vix_term",
            }
            
            results = {}
            for future in as_completed(futures):
                key = futures[future]
                try:
                    results[key] = future.result()
                except Exception as e:
                    logger.error(f"Failed to fetch {key}: {e}")
                    results[key] = None
        
        # Log summary
        logger.info(f"Sentiment data fetched: Fear&Greed={results.get('fear_greed', {}).get('value')}, "
                   f"VIX={results.get('vix', {}).get('value')}, DXY={results.get('dxy', {}).get('value')}")
        
        data = {
            "fear_greed": results.get("fear_greed") or {"value": 50, "classification": "Neutral"},
            "vix": results.get("vix") or {"value": 0, "level": "unknown"},
            "dxy": results.get("dxy") or {"value": 0, "level": "unknown"},
            "yield_curve": results.get("yield_curve") or {"spread": 0, "level": "unknown"},
            "vxn": results.get("vxn") or {"value": 0, "level": "unknown"},
            "gvz": results.get("gvz") or {"value": 0, "level": "unknown"},
            "vix_term": results.get("vix_term") or {"value": 1.0, "level": "unknown"},
            "timestamp": int(time.time())
        }
        
        _set_cached("market_sentiment", data, 21600)  # 6 hours cache
        
        return jsonify({"code": 1, "msg": "success", "data": data})
        
    except Exception as e:
        logger.error(f"market_sentiment failed: {e}", exc_info=True)
        return jsonify({"code": 0, "msg": str(e), "data": None}), 500


def _fetch_stock_opportunity_prices() -> List[Dict[str, Any]]:
    """Fetch popular US stock prices for opportunity scanning."""
    stocks = [
        {"symbol": "AAPL", "name": "Apple"},
        {"symbol": "MSFT", "name": "Microsoft"},
        {"symbol": "GOOGL", "name": "Alphabet"},
        {"symbol": "AMZN", "name": "Amazon"},
        {"symbol": "TSLA", "name": "Tesla"},
        {"symbol": "NVDA", "name": "NVIDIA"},
        {"symbol": "META", "name": "Meta"},
        {"symbol": "NFLX", "name": "Netflix"},
        {"symbol": "AMD", "name": "AMD"},
        {"symbol": "CRM", "name": "Salesforce"},
        {"symbol": "COIN", "name": "Coinbase"},
        {"symbol": "BABA", "name": "Alibaba"},
        {"symbol": "NIO", "name": "NIO"},
        {"symbol": "PLTR", "name": "Palantir"},
        {"symbol": "INTC", "name": "Intel"},
    ]

    try:
        import yfinance as yf

        symbols = [s["symbol"] for s in stocks]
        tickers = yf.Tickers(" ".join(symbols))

        result = []
        for stock in stocks:
            try:
                ticker = tickers.tickers.get(stock["symbol"])
                if ticker:
                    hist = ticker.history(period="2d")
                    if len(hist) >= 2:
                        prev_close = float(hist["Close"].iloc[-2])
                        current = float(hist["Close"].iloc[-1])
                        change = ((current - prev_close) / prev_close) * 100
                    elif len(hist) == 1:
                        current = float(hist["Close"].iloc[-1])
                        change = 0
                    else:
                        continue

                    result.append({
                        "symbol": stock["symbol"],
                        "name": stock["name"],
                        "price": round(current, 2),
                        "change": round(change, 2)
                    })
            except Exception as e:
                logger.debug(f"Failed to fetch stock {stock['symbol']}: {e}")

        return result
    except Exception as e:
        logger.error(f"Failed to fetch stock opportunity prices: {e}")
        return []


def _analyze_opportunities_crypto(opportunities: list):
    """Scan crypto market for trading opportunities."""
    crypto_data = _get_cached("crypto_prices")
    if not crypto_data:
        crypto_data = _fetch_crypto_prices()
        if crypto_data:
            _set_cached("crypto_prices", crypto_data)
    
    if not crypto_data:
        logger.warning("_analyze_opportunities_crypto: No crypto data available")
        return

    logger.debug(f"_analyze_opportunities_crypto: Analyzing {len(crypto_data)} crypto coins")

    for coin in (crypto_data or [])[:20]:
        change = _safe_float(coin.get("change_24h", 0))
        change_7d = _safe_float(coin.get("change_7d", 0))
        symbol = coin.get("symbol", "")
        name = coin.get("name", "")
        price = _safe_float(coin.get("price", 0))

        signal = None
        strength = "medium"
        reason = ""
        impact = "neutral"

        # Lower thresholds to show more opportunities
        if change > 15:
            signal = "overbought"
            strength = "strong"
            reason = f"24h涨幅{change:.1f}%，7日涨幅{change_7d:.1f}%，短期超买风险"
            impact = "bearish"
        elif change > 5:  # Lowered from 8 to 5
            signal = "bullish_momentum"
            strength = "medium"
            reason = f"24h涨幅{change:.1f}%，上涨动能强劲"
            impact = "bullish"
        elif change < -15:
            signal = "oversold"
            strength = "strong"
            reason = f"24h跌幅{abs(change):.1f}%，可能超卖反弹"
            impact = "bullish"
        elif change < -5:  # Lowered from -8 to -5
            signal = "bearish_momentum"
            strength = "medium"
            reason = f"24h跌幅{abs(change):.1f}%，下跌趋势明显"
            impact = "bearish"

        if signal:
            opportunities.append({
                "symbol": symbol,
                "name": name,
                "price": price,
                "change_24h": change,
                "change_7d": change_7d,
                "signal": signal,
                "strength": strength,
                "reason": reason,
                "impact": impact,
                "market": "Crypto",
                "timestamp": int(time.time())
            })


def _analyze_opportunities_stocks(opportunities: list):
    """Scan US stocks for trading opportunities."""
    stock_data = _get_cached("stock_opportunity_prices")
    if not stock_data:
        stock_data = _fetch_stock_opportunity_prices()
        if stock_data:
            _set_cached("stock_opportunity_prices", stock_data, 3600)
    
    if not stock_data:
        logger.warning("_analyze_opportunities_stocks: No stock data available")
        return

    logger.debug(f"_analyze_opportunities_stocks: Analyzing {len(stock_data)} stocks")

    for stock in (stock_data or []):
        change = _safe_float(stock.get("change", 0))
        symbol = stock.get("symbol", "")
        name = stock.get("name", "")
        price = _safe_float(stock.get("price", 0))

        signal = None
        strength = "medium"
        reason = ""
        impact = "neutral"

        # US stocks: smaller thresholds than crypto
        if change > 5:
            signal = "overbought"
            strength = "strong"
            reason = f"日涨幅{change:.1f}%，短期涨幅较大，注意回调风险"
            impact = "bearish"
        elif change > 2:  # Lowered from 3 to 2
            signal = "bullish_momentum"
            strength = "medium"
            reason = f"日涨幅{change:.1f}%，上涨动能强劲"
            impact = "bullish"
        elif change < -5:
            signal = "oversold"
            strength = "strong"
            reason = f"日跌幅{abs(change):.1f}%，可能超卖反弹"
            impact = "bullish"
        elif change < -2:  # Lowered from -3 to -2
            signal = "bearish_momentum"
            strength = "medium"
            reason = f"日跌幅{abs(change):.1f}%，下跌趋势明显"
            impact = "bearish"

        if signal:
            opportunities.append({
                "symbol": symbol,
                "name": name,
                "price": price,
                "change_24h": change,
                "signal": signal,
                "strength": strength,
                "reason": reason,
                "impact": impact,
                "market": "USStock",
                "timestamp": int(time.time())
            })


def _analyze_opportunities_forex(opportunities: list):
    """Scan forex pairs for trading opportunities."""
    forex_data = _get_cached("forex_pairs")
    if not forex_data:
        forex_data = _fetch_forex_pairs()
        if forex_data:
            _set_cached("forex_pairs", forex_data, 3600)
    
    if not forex_data:
        logger.warning("_analyze_opportunities_forex: No forex data available")
        return

    logger.debug(f"_analyze_opportunities_forex: Analyzing {len(forex_data)} forex pairs")

    for pair in (forex_data or []):
        change = _safe_float(pair.get("change", 0))
        symbol = pair.get("symbol", pair.get("name", ""))
        name = pair.get("name_cn", pair.get("name", ""))
        price = _safe_float(pair.get("price", 0))

        signal = None
        strength = "medium"
        reason = ""
        impact = "neutral"

        # Forex: even smaller thresholds
        if change > 1.5:
            signal = "overbought"
            strength = "strong"
            reason = f"日涨幅{change:.2f}%，汇率波动剧烈，注意回调"
            impact = "bearish"
        elif change > 0.5:  # Lowered from 0.8 to 0.5
            signal = "bullish_momentum"
            strength = "medium"
            reason = f"日涨幅{change:.2f}%，上涨动能较强"
            impact = "bullish"
        elif change < -1.5:
            signal = "oversold"
            strength = "strong"
            reason = f"日跌幅{abs(change):.2f}%，汇率波动剧烈，可能反弹"
            impact = "bullish"
        elif change < -0.5:  # Lowered from -0.8 to -0.5
            signal = "bearish_momentum"
            strength = "medium"
            reason = f"日跌幅{abs(change):.2f}%，下跌趋势明显"
            impact = "bearish"

        if signal:
            opportunities.append({
                "symbol": symbol,
                "name": name,
                "price": price,
                "change_24h": change,
                "signal": signal,
                "strength": strength,
                "reason": reason,
                "impact": impact,
                "market": "Forex",
                "timestamp": int(time.time())
            })


def _analyze_opportunities_polymarket(opportunities: list):
    """扫描预测市场机会"""
    try:
        from app.data_sources.polymarket import PolymarketDataSource
        from app.services.polymarket_analyzer import PolymarketAnalyzer
        
        polymarket_source = PolymarketDataSource()
        analyzer = PolymarketAnalyzer()
        
        # 获取热门市场
        markets = polymarket_source.get_trending_markets(limit=20)
        
        for market in markets:
            try:
                # AI分析
                analysis = analyzer.analyze_market(market['market_id'])
                
                if analysis.get('error'):
                    continue
                
                # 只添加高分机会
                if analysis.get('opportunity_score', 0) > 75:
                    opportunities.append({
                        "symbol": market['question'][:50],  # 简化显示
                        "name": market['question'],
                        "price": market['current_probability'],
                        "change_24h": 0,  # 预测市场没有24h涨跌幅概念
                        "signal": "prediction_opportunity",
                        "strength": "strong" if analysis.get('opportunity_score', 0) > 85 else "medium",
                        "reason": f"AI预测概率{analysis.get('ai_predicted_probability', 0):.1f}%，市场概率{market['current_probability']:.1f}%，差异{analysis.get('divergence', 0):.1f}%",
                        "impact": "bullish" if analysis.get('recommendation') == "YES" else "bearish",
                        "market": "PredictionMarket",
                        "market_id": market['market_id'],
                        "ai_analysis": {
                            "predicted_probability": analysis.get('ai_predicted_probability', 0),
                            "recommendation": analysis.get('recommendation', 'HOLD'),
                            "confidence_score": analysis.get('confidence_score', 0),
                            "opportunity_score": analysis.get('opportunity_score', 0)
                        },
                        "timestamp": int(time.time())
                    })
            except Exception as e:
                logger.debug(f"Failed to analyze polymarket {market.get('market_id')}: {e}")
                continue
                
    except Exception as e:
        logger.error(f"_analyze_opportunities_polymarket failed: {e}")


@global_market_bp.route("/opportunities", methods=["GET"])
@login_required
def trading_opportunities():
    """
    Scan for trading opportunities across Crypto, US Stocks, and Forex.
    Note: Prediction Markets are excluded as they have their own dedicated page.
    Cached for 1 hour. Pass ?force=true to skip cache.
    """
    try:
        force = request.args.get("force", "").lower() in ("true", "1")

        if not force:
            cached = _get_cached("trading_opportunities")
            if cached:
                return jsonify({"code": 1, "msg": "success", "data": cached})

        opportunities = []

        # 1) Crypto
        try:
            _analyze_opportunities_crypto(opportunities)
            crypto_count = len([o for o in opportunities if o.get("market") == "Crypto"])
            logger.info(f"Trading opportunities: found {crypto_count} crypto opportunities")
        except Exception as e:
            logger.error(f"Failed to analyze crypto opportunities: {e}", exc_info=True)

        # 2) US Stocks
        try:
            _analyze_opportunities_stocks(opportunities)
            stock_count = len([o for o in opportunities if o.get("market") == "USStock"])
            logger.info(f"Trading opportunities: found {stock_count} US stock opportunities")
        except Exception as e:
            logger.error(f"Failed to analyze stock opportunities: {e}", exc_info=True)

        # 3) Forex
        try:
            _analyze_opportunities_forex(opportunities)
            forex_count = len([o for o in opportunities if o.get("market") == "Forex"])
            logger.info(f"Trading opportunities: found {forex_count} forex opportunities")
        except Exception as e:
            logger.error(f"Failed to analyze forex opportunities: {e}", exc_info=True)

        # Note: Prediction Markets are excluded from trading opportunities radar
        # as they have their own dedicated page at /polymarket

        # Sort by absolute change descending
        opportunities.sort(key=lambda x: abs(x.get("change_24h", 0)), reverse=True)

        logger.info(f"Trading opportunities: total {len(opportunities)} opportunities found (Crypto: {len([o for o in opportunities if o.get('market') == 'Crypto'])}, USStock: {len([o for o in opportunities if o.get('market') == 'USStock'])}, Forex: {len([o for o in opportunities if o.get('market') == 'Forex'])})")

        _set_cached("trading_opportunities", opportunities, 3600)

        return jsonify({"code": 1, "msg": "success", "data": opportunities})

    except Exception as e:
        logger.error(f"trading_opportunities failed: {e}", exc_info=True)
        return jsonify({"code": 0, "msg": str(e), "data": None}), 500


@global_market_bp.route("/refresh", methods=["POST"])
@login_required
def refresh_data():
    """
    Force refresh all market data (clears cache).
    """
    try:
        global _cache
        _cache = {}
        return jsonify({"code": 1, "msg": "Cache cleared successfully", "data": None})
    except Exception as e:
        logger.error(f"refresh_data failed: {e}", exc_info=True)
        return jsonify({"code": 0, "msg": str(e), "data": None}), 500
