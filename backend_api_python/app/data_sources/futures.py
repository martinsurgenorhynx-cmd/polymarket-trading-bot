"""
期货数据源
支持：
1. 加密货币期货（Binance Futures via CCXT）
2. 传统期货（Yahoo Finance）
"""
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import ccxt
import yfinance as yf

from app.data_sources.base import BaseDataSource, TIMEFRAME_SECONDS
from app.utils.logger import get_logger
from app.config import CCXTConfig, APIKeys

logger = get_logger(__name__)


class FuturesDataSource(BaseDataSource):
    """期货数据源"""
    
    name = "Futures"
    
    # Yahoo Finance时间周期映射
    YF_TIMEFRAME_MAP = {
        '1m': '1m',
        '5m': '5m',
        '15m': '15m',
        '30m': '30m',
        '1H': '1h',
        '4H': '4h',
        '1D': '1d',
        '1W': '1wk'
    }
    
    # CCXT时间周期映射
    CCXT_TIMEFRAME_MAP = CCXTConfig.TIMEFRAME_MAP
    
    # 传统期货合约代码（Yahoo Finance）
    YF_SYMBOLS = {
        'GC': 'GC=F',   # 黄金期货
        'SI': 'SI=F',   # 白银期货
        'CL': 'CL=F',   # 原油期货
        'NG': 'NG=F',   # 天然气期货
        'ZC': 'ZC=F',   # 玉米期货
        'ZW': 'ZW=F',   # 小麦期货
    }
    
    def __init__(self):
        # 初始化CCXT（用于加密货币期货）
        config = {
            'timeout': CCXTConfig.TIMEOUT,
            'enableRateLimit': CCXTConfig.ENABLE_RATE_LIMIT,
            'options': {
                'defaultType': 'future'
            }
        }
        
        if CCXTConfig.PROXY:
            config['proxies'] = {
                'http': CCXTConfig.PROXY,
                'https': CCXTConfig.PROXY
            }
        
        self.exchange = ccxt.binance(config)

    def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        Get latest ticker for futures symbol.

        - For crypto futures, uses CCXT Binance futures client.
        - For traditional futures (Yahoo Finance symbols), returns a minimal ticker shape with `last`.
        """
        sym = (symbol or "").strip()
        if sym in self.YF_SYMBOLS or sym.endswith("=F"):
            try:
                yf_symbol = self.YF_SYMBOLS.get(sym, sym)
                if not yf_symbol.endswith("=F"):
                    yf_symbol = yf_symbol + "=F"
                t = yf.Ticker(yf_symbol)
                # Prefer fast_info if available, fall back to last close
                last = None
                try:
                    last = getattr(t, "fast_info", {}).get("last_price")
                except Exception:
                    last = None
                if last is None:
                    hist = t.history(period="2d", interval="1d")
                    if hist is not None and not hist.empty:
                        last = float(hist["Close"].iloc[-1])
                return {"symbol": yf_symbol, "last": float(last or 0.0)}
            except Exception:
                return {"symbol": sym, "last": 0.0}

        if ":" in sym:
            sym = sym.split(":", 1)[0]
        sym = sym.upper()
        if "/" not in sym:
            if sym.endswith("USDT") and len(sym) > 4:
                sym = f"{sym[:-4]}/USDT"
            elif sym.endswith("USD") and len(sym) > 3:
                sym = f"{sym[:-3]}/USD"
        return self.exchange.fetch_ticker(sym)
    
    def _get_timeframe_seconds(self, timeframe: str) -> int:
        """获取时间周期对应的秒数"""
        return TIMEFRAME_SECONDS.get(timeframe, 86400)
    
    def get_kline(
        self,
        symbol: str,
        timeframe: str,
        limit: int,
        before_time: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        获取期货K线数据
        
        Args:
            symbol: 期货合约代码
            timeframe: 时间周期
            limit: 数据条数
            before_time: 结束时间戳
        """
        # 判断是传统期货还是加密货币期货
        if symbol in self.YF_SYMBOLS or symbol.endswith('=F'):
            return self._get_traditional_futures(symbol, timeframe, limit, before_time)
        else:
            return self._get_crypto_futures(symbol, timeframe, limit, before_time)
    
    def _get_traditional_futures(
        self,
        symbol: str,
        timeframe: str,
        limit: int,
        before_time: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """使用yfinance获取传统期货数据"""
        try:
            # 转换symbol格式
            yf_symbol = self.YF_SYMBOLS.get(symbol, symbol)
            if not yf_symbol.endswith('=F'):
                yf_symbol = symbol + '=F'
            
            # 转换时间周期
            yf_interval = self.YF_TIMEFRAME_MAP.get(timeframe, '1d')
            
            # logger.info(f"获取传统期货K线: {yf_symbol}, 周期: {yf_interval}, 条数: {limit}")
            
            # 计算时间范围
            if before_time:
                end_time = datetime.fromtimestamp(before_time)
            else:
                end_time = datetime.now()
            
            tf_seconds = self._get_timeframe_seconds(timeframe)
            start_time = end_time - timedelta(seconds=tf_seconds * limit * 1.5)
            
            # yfinance 的 end 参数是不包含的（exclusive），需要加一天
            end_time_inclusive = end_time + timedelta(days=1)
            
            # 获取数据
            ticker = yf.Ticker(yf_symbol)
            df = ticker.history(
                start=start_time,
                end=end_time_inclusive,
                interval=yf_interval
            )
            
            if df.empty:
                logger.warning(f"No data: {yf_symbol}")
                return []
            
            # 转换格式
            klines = []
            for index, row in df.iterrows():
                klines.append({
                    'time': int(index.timestamp()),
                    'open': float(row['Open']),
                    'high': float(row['High']),
                    'low': float(row['Low']),
                    'close': float(row['Close']),
                    'volume': float(row['Volume'])
                })
            
            klines.sort(key=lambda x: x['time'])
            if len(klines) > limit:
                klines = klines[-limit:]
            
            # logger.info(f"获取到 {len(klines)} 条传统期货数据")
            return klines
            
        except Exception as e:
            logger.error(f"Failed to fetch traditional futures data: {e}")
            return []
    
    def _get_crypto_futures(
        self,
        symbol: str,
        timeframe: str,
        limit: int,
        before_time: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """使用CCXT获取加密货币期货数据"""
        try:
            # 确保symbol格式正确
            ccxt_symbol = symbol if '/' in symbol else f"{symbol}/USDT"
            ccxt_timeframe = self.CCXT_TIMEFRAME_MAP.get(timeframe, '1d')
            
            # logger.info(f"获取加密货币期货K线: {ccxt_symbol}, 周期: {ccxt_timeframe}, 条数: {limit}")
            
            # 获取数据
            if before_time:
                since_time = before_time - limit * self._get_timeframe_seconds(timeframe)
                ohlcv = self.exchange.fetch_ohlcv(
                    ccxt_symbol, 
                    ccxt_timeframe, 
                    since=since_time * 1000,
                    limit=limit
                )
            else:
                ohlcv = self.exchange.fetch_ohlcv(
                    ccxt_symbol, 
                    ccxt_timeframe, 
                    limit=limit
                )
            
            # 转换格式
            klines = []
            for candle in ohlcv:
                klines.append({
                    'time': int(candle[0] / 1000),
                    'open': float(candle[1]),
                    'high': float(candle[2]),
                    'low': float(candle[3]),
                    'close': float(candle[4]),
                    'volume': float(candle[5])
                })
            
            # logger.info(f"获取到 {len(klines)} 条加密货币期货数据")
            return klines
            
        except Exception as e:
            logger.error(f"Failed to fetch crypto futures data: {e}")
            return []

