"""
外汇数据源
使用 Tiingo 获取外汇数据
"""
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import time
import requests
import threading

from app.data_sources.base import BaseDataSource, TIMEFRAME_SECONDS
from app.utils.logger import get_logger
from app.config import TiingoConfig, APIKeys

logger = get_logger(__name__)

# 全局缓存 - 减少 Tiingo API 调用
_forex_cache: Dict[str, Dict[str, Any]] = {}
_forex_cache_lock = threading.Lock()
_FOREX_CACHE_TTL = 60  # 外汇价格缓存 60 秒 (Tiingo 免费 API 限制严格)


class ForexDataSource(BaseDataSource):
    """外汇数据源 (Tiingo)"""
    
    name = "Forex/Tiingo"
    
    # Tiingo resampleFreq 映射
    # Tiingo 免费账户支持: 5min, 15min, 30min, 1hour, 4hour, 1day
    # 注意: 1min 需要付费订阅, 1week/1month 不被 Tiingo FX API 支持
    TIMEFRAME_MAP = {
        '1m': '1min',      # 需要付费订阅
        '5m': '5min',
        '15m': '15min',
        '30m': '30min',
        '1H': '1hour',
        '4H': '4hour',
        '1D': '1day',
        '1W': None,        # Tiingo 不支持，需要聚合
        '1M': None         # Tiingo 不支持，需要聚合
    }
    
    # 外汇对映射 (Tiingo 使用标准 ticker，如 eurusd, audusd)
    # 大写也可以，Tiingo 通常不区分大小写，但建议统一
    SYMBOL_MAP = {
        # 贵金属 (Tiingo 不一定支持所有 OANDA 格式的贵金属，通常是 XAUUSD)
        'XAUUSD': 'xauusd',
        'XAGUSD': 'xagusd',
        # 主要货币对
        'EURUSD': 'eurusd',
        'GBPUSD': 'gbpusd',
        'USDJPY': 'usdjpy',
        'AUDUSD': 'audusd',
        'USDCAD': 'usdcad',
        'USDCHF': 'usdchf',
        'NZDUSD': 'nzdusd',
    }
    
    def __init__(self):
        self.base_url = TiingoConfig.BASE_URL
        if not APIKeys.TIINGO_API_KEY:
             logger.warning("Tiingo API key is not configured; FX data will be unavailable")
    
    def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        获取外汇实时报价
        
        使用 Tiingo FX Top-of-Book API 获取实时报价
        带有 60 秒缓存以避免频繁触发 Tiingo 速率限制
        
        Returns:
            dict: {
                'last': 当前价格 (mid price),
                'bid': 买价,
                'ask': 卖价,
                'change': 涨跌额,
                'changePercent': 涨跌幅
            }
        """
        api_key = APIKeys.TIINGO_API_KEY
        if not api_key:
            logger.warning("Tiingo API key not configured")
            return {'last': 0, 'symbol': symbol}
        
        # 检查缓存
        cache_key = f"ticker_{symbol}"
        with _forex_cache_lock:
            cached = _forex_cache.get(cache_key)
            if cached:
                cache_time = cached.get('_cache_time', 0)
                if time.time() - cache_time < _FOREX_CACHE_TTL:
                    logger.debug(f"Using cached forex ticker for {symbol}")
                    return cached
        
        try:
            # 解析 symbol
            tiingo_symbol = self.SYMBOL_MAP.get(symbol)
            if not tiingo_symbol:
                tiingo_symbol = symbol.lower()
            
            # Tiingo FX Top-of-Book API
            # https://api.tiingo.com/tiingo/fx/top?tickers=eurusd&token=...
            url = f"{self.base_url}/fx/top"
            params = {
                'tickers': tiingo_symbol,
                'token': api_key
            }
            
            # 重试逻辑：处理 429 速率限制
            for attempt in range(3):
                response = requests.get(url, params=params, timeout=TiingoConfig.TIMEOUT)
                if response.status_code == 429:
                    wait_time = 2 * (attempt + 1)
                    logger.warning(f"Tiingo rate limit (429), waiting {wait_time}s before retry ({attempt+1}/3)")
                    time.sleep(wait_time)
                    continue
                break
            
            if response.status_code == 429:
                logger.warning("Tiingo rate limit exceeded for ticker request")
                logger.info("Note: Tiingo 1-minute forex data requires a paid subscription")
                # 返回缓存数据（如果有的话，即使已过期）
                with _forex_cache_lock:
                    if cache_key in _forex_cache:
                        logger.info(f"Returning stale cache for {symbol} due to rate limit")
                        return _forex_cache[cache_key]
                return {'last': 0, 'symbol': symbol}
            
            response.raise_for_status()
            data = response.json()
            
            if data and isinstance(data, list) and len(data) > 0:
                item = data[0]
                # Tiingo FX top returns: ticker, quoteTimestamp, bidPrice, bidSize, askPrice, askSize, midPrice
                bid = float(item.get('bidPrice', 0) or 0)
                ask = float(item.get('askPrice', 0) or 0)
                mid = float(item.get('midPrice', 0) or 0)
                
                # 如果没有 midPrice，计算中间价
                if not mid and bid and ask:
                    mid = (bid + ask) / 2
                
                last_price = mid or bid or ask
                
                # 获取前一天收盘价来计算涨跌（需要额外请求日线数据）
                prev_close = 0
                change = 0
                change_pct = 0
                
                try:
                    # 获取昨日收盘价
                    yesterday = (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d')
                    today = datetime.now().strftime('%Y-%m-%d')
                    price_url = f"{self.base_url}/fx/{tiingo_symbol}/prices"
                    price_params = {
                        'startDate': yesterday,
                        'endDate': today,
                        'resampleFreq': '1day',
                        'token': api_key
                    }
                    price_resp = requests.get(price_url, params=price_params, timeout=TiingoConfig.TIMEOUT)
                    if price_resp.status_code == 200:
                        price_data = price_resp.json()
                        if price_data and len(price_data) > 0:
                            prev_close = float(price_data[-1].get('close', 0) or 0)
                            if prev_close and last_price:
                                change = last_price - prev_close
                                change_pct = (change / prev_close) * 100
                except Exception:
                    pass  # 涨跌计算失败不影响主要功能
                
                result = {
                    'last': round(last_price, 5),
                    'bid': round(bid, 5),
                    'ask': round(ask, 5),
                    'change': round(change, 5),
                    'changePercent': round(change_pct, 2),
                    'previousClose': round(prev_close, 5) if prev_close else 0,
                    '_cache_time': time.time()
                }
                
                # 缓存结果
                with _forex_cache_lock:
                    _forex_cache[cache_key] = result
                
                return result
                
        except Exception as e:
            logger.error(f"Failed to get forex ticker for {symbol}: {e}")
        
        return {'last': 0, 'symbol': symbol}
    
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
        获取外汇K线数据
        
        Args:
            symbol: 外汇对代码（如 XAUUSD, EURUSD）
            timeframe: 时间周期
            limit: 数据条数
            before_time: 结束时间戳
        """
        # 动态获取 API Key
        api_key = APIKeys.TIINGO_API_KEY
        if not api_key:
            logger.error("Tiingo API key is not configured")
            return []
            
        try:
            # 1. 解析 Symbol
            tiingo_symbol = self.SYMBOL_MAP.get(symbol)
            if not tiingo_symbol:
                # 尝试智能转换: EURUSD -> eurusd
                tiingo_symbol = symbol.lower()

            # 2. 解析 Resolution (resampleFreq)
            resample_freq = self.TIMEFRAME_MAP.get(timeframe)
            
            # 特殊处理：1W/1M 需要用日线聚合
            aggregate_to_weekly = (timeframe == '1W')
            aggregate_to_monthly = (timeframe == '1M')
            original_limit = limit  # 保存原始请求数量
            
            if aggregate_to_weekly or aggregate_to_monthly:
                # 用日线数据聚合
                resample_freq = '1day'
                # 限制周线/月线的最大请求数量（Tiingo 免费 API 有数据量限制）
                # 周线最多请求 100 周 = 700 天 ≈ 2年
                # 月线最多请求 36 月 = 1080 天 ≈ 3年
                max_limit = 100 if aggregate_to_weekly else 36
                original_limit = min(original_limit, max_limit)
                # 需要更多日线数据来聚合（周线需要7天，月线需要30天）
                limit = original_limit * (7 if aggregate_to_weekly else 30)
            
            if not resample_freq:
                logger.warning(f"Tiingo does not support timeframe: {timeframe}")
                return []
            
            # 1分钟数据需要付费订阅提示
            if timeframe == '1m':
                logger.info(f"Note: Tiingo 1-minute forex data requires a paid subscription")
            
            # 3. 计算时间范围
            if before_time:
                end_dt = datetime.fromtimestamp(before_time)
            else:
                end_dt = datetime.now()
            
            # 根据周期和数量计算开始时间
            # 注意：聚合模式下使用日线秒数计算
            if aggregate_to_weekly or aggregate_to_monthly:
                tf_seconds = 86400  # 日线秒数
            else:
                tf_seconds = self._get_timeframe_seconds(timeframe)
            # 多取一些缓冲时间（1.5倍，外汇周末不交易）
            start_dt = end_dt - timedelta(seconds=limit * tf_seconds * 1.5)
            
            # Tiingo 免费 API 最多支持约 5 年数据，限制最大时间范围
            max_days = 365 * 3  # 最多 3 年
            if (end_dt - start_dt).days > max_days:
                start_dt = end_dt - timedelta(days=max_days)
                logger.info(f"Tiingo: Limited date range to {max_days} days")
            
            # 格式化日期为 YYYY-MM-DD (Tiingo 支持该格式)
            start_date_str = start_dt.strftime('%Y-%m-%d')
            end_date_str = end_dt.strftime('%Y-%m-%d')
            
            # 4. API 请求（带重试逻辑）
            # URL: https://api.tiingo.com/tiingo/fx/{ticker}/prices
            url = f"{self.base_url}/fx/{tiingo_symbol}/prices"
            
            params = {
                'startDate': start_date_str,
                'endDate': end_date_str,
                'resampleFreq': resample_freq,
                'token': api_key,
                'format': 'json'
            }
            
            # logger.info(f"Tiingo Request: {url} params={params}")
            
            # 重试逻辑：处理 429 速率限制
            max_retries = 3
            retry_delay = 2  # 秒
            response = None
            
            for attempt in range(max_retries):
                try:
                    response = requests.get(url, params=params, timeout=TiingoConfig.TIMEOUT)
                    
                    if response.status_code == 429:
                        # 速率限制，等待后重试
                        wait_time = retry_delay * (attempt + 1)
                        logger.warning(f"Tiingo rate limit (429), waiting {wait_time}s before retry ({attempt + 1}/{max_retries})")
                        time.sleep(wait_time)
                        continue
                    
                    break  # 成功或其他错误，退出重试循环
                    
                except requests.exceptions.Timeout:
                    if attempt < max_retries - 1:
                        logger.warning(f"Tiingo request timeout, retrying ({attempt + 1}/{max_retries})")
                        time.sleep(retry_delay)
                        continue
                    raise
            
            if response is None:
                logger.error("Tiingo API request failed after all retries")
                return []
            
            if response.status_code == 429:
                logger.error("Tiingo API rate limit exceeded. Please wait a moment before retrying.")
                return []
            
            if response.status_code == 403:
                logger.error("Tiingo API permission error (403): check whether your API key is valid and has access to this dataset.")
                return []
                 
            response.raise_for_status()
            data = response.json()
            
            # 5. 处理响应
            # Tiingo returns a list of dicts:
            # [
            #   {
            #     "date": "2023-01-01T00:00:00.000Z",
            #     "ticker": "eurusd",
            #     "open": 1.07,
            #     "high": 1.08,
            #     "low": 1.06,
            #     "close": 1.07
            #     "mid": ... (optional, depends on settings, usually OHLC are bid or mid)
            #   }, ...
            # ]
            # Note: Tiingo FX prices objects keys: date, open, high, low, close.
            
            if not isinstance(data, list):
                logger.warning(f"Tiingo response is not a list: {data}")
                return []
                
            klines = []
            for item in data:
                # 解析时间: "2023-01-01T00:00:00.000Z"
                dt_str = item.get('date')
                # Tiingo 返回的是 UTC 时间 ISO 格式，需要正确处理时区
                # 将 UTC 时间转换为本地时间戳
                if dt_str.endswith('Z'):
                    dt_str = dt_str[:-1] + '+00:00'  # 替换 Z 为 +00:00 表示 UTC
                
                dt = datetime.fromisoformat(dt_str)
                ts = int(dt.timestamp())  # 现在会正确处理 UTC 时区
                
                klines.append({
                    'time': ts,
                    'open': float(item.get('open')),
                    'high': float(item.get('high')),
                    'low': float(item.get('low')),
                    'close': float(item.get('close')),
                    'volume': 0.0 # Tiingo FX 通常没有 volume
                })
            
            # 按时间排序
            klines.sort(key=lambda x: x['time'])
            
            # 如果需要聚合到周线或月线
            if aggregate_to_weekly:
                klines = self._aggregate_to_weekly(klines)
                logger.debug(f"Aggregated {len(klines)} weekly candles from daily data")
            elif aggregate_to_monthly:
                klines = self._aggregate_to_monthly(klines)
                logger.debug(f"Aggregated {len(klines)} monthly candles from daily data")
            
            # 过滤到原始请求数量
            if len(klines) > original_limit:
                klines = klines[-original_limit:]
            
            # logger.info(f"获取到 {len(klines)} 条 Tiingo 外汇数据")
            return klines
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Tiingo API request failed: {e}")
            return []
        except Exception as e:
            logger.error(f"Failed to process Tiingo data: {e}")
            return []
    
    def _aggregate_to_weekly(self, daily_klines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """将日线数据聚合为周线"""
        if not daily_klines:
            return []
        
        weekly_klines = []
        current_week = None
        week_data = None
        
        for kline in daily_klines:
            dt = datetime.fromtimestamp(kline['time'])
            # 获取该日期所在周的周一
            week_start = dt - timedelta(days=dt.weekday())
            week_key = week_start.strftime('%Y-%W')
            
            if week_key != current_week:
                # 保存上一周的数据
                if week_data:
                    weekly_klines.append(week_data)
                # 开始新的一周
                current_week = week_key
                week_data = {
                    'time': int(week_start.timestamp()),
                    'open': kline['open'],
                    'high': kline['high'],
                    'low': kline['low'],
                    'close': kline['close'],
                    'volume': kline['volume']
                }
            else:
                # 更新本周数据
                week_data['high'] = max(week_data['high'], kline['high'])
                week_data['low'] = min(week_data['low'], kline['low'])
                week_data['close'] = kline['close']
                week_data['volume'] += kline['volume']
        
        # 添加最后一周
        if week_data:
            weekly_klines.append(week_data)
        
        return weekly_klines
    
    def _aggregate_to_monthly(self, daily_klines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """将日线数据聚合为月线"""
        if not daily_klines:
            return []
        
        monthly_klines = []
        current_month = None
        month_data = None
        
        for kline in daily_klines:
            dt = datetime.fromtimestamp(kline['time'])
            month_key = dt.strftime('%Y-%m')
            
            if month_key != current_month:
                # 保存上个月的数据
                if month_data:
                    monthly_klines.append(month_data)
                # 开始新的一月
                current_month = month_key
                month_start = dt.replace(day=1, hour=0, minute=0, second=0)
                month_data = {
                    'time': int(month_start.timestamp()),
                    'open': kline['open'],
                    'high': kline['high'],
                    'low': kline['low'],
                    'close': kline['close'],
                    'volume': kline['volume']
                }
            else:
                # 更新本月数据
                month_data['high'] = max(month_data['high'], kline['high'])
                month_data['low'] = min(month_data['low'], kline['low'])
                month_data['close'] = kline['close']
                month_data['volume'] += kline['volume']
        
        # 添加最后一月
        if month_data:
            monthly_klines.append(month_data)
        
        return monthly_klines
