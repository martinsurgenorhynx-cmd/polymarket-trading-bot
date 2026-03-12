"""
数据源基类
定义统一的数据源接口
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta

from app.utils.logger import get_logger

logger = get_logger(__name__)


# K线周期映射（秒数）
TIMEFRAME_SECONDS = {
    '1m': 60,
    '5m': 300,
    '15m': 900,
    '30m': 1800,
    '1H': 3600,
    '4H': 14400,
    '1D': 86400,
    '1W': 604800
}


class BaseDataSource(ABC):
    """数据源基类"""
    
    name: str = "base"
    
    @abstractmethod
    def get_kline(
        self,
        symbol: str,
        timeframe: str,
        limit: int,
        before_time: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        获取K线数据
        
        Args:
            symbol: 交易对/股票代码
            timeframe: 时间周期 (1m, 5m, 15m, 30m, 1H, 4H, 1D, 1W)
            limit: 数据条数
            before_time: 获取此时间之前的数据（Unix时间戳，秒）
            
        Returns:
            K线数据列表，格式:
            [{"time": int, "open": float, "high": float, "low": float, "close": float, "volume": float}, ...]
        """
        pass

    def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        Get latest ticker for a symbol (best-effort).

        This is an optional interface used by the strategy executor for fetching current price.
        Implementations may return a dict compatible with CCXT `fetch_ticker` shape (e.g. {'last': ...}).
        """
        raise NotImplementedError("get_ticker is not implemented for this data source")
    
    def format_kline(
        self,
        timestamp: int,
        open_price: float,
        high: float,
        low: float,
        close: float,
        volume: float
    ) -> Dict[str, Any]:
        """格式化单条K线数据"""
        return {
            'time': timestamp,
            'open': round(float(open_price), 4),
            'high': round(float(high), 4),
            'low': round(float(low), 4),
            'close': round(float(close), 4),
            'volume': round(float(volume), 2)
        }
    
    def calculate_time_range(
        self,
        timeframe: str,
        limit: int,
        buffer_ratio: float = 1.2
    ) -> int:
        """
        计算获取指定数量K线所需的时间范围（秒）
        
        Args:
            timeframe: 时间周期
            limit: K线数量
            buffer_ratio: 缓冲系数
            
        Returns:
            时间范围（秒）
        """
        seconds_per_candle = TIMEFRAME_SECONDS.get(timeframe, 86400)
        return int(seconds_per_candle * limit * buffer_ratio)
    
    def filter_and_limit(
        self,
        klines: List[Dict[str, Any]],
        limit: int,
        before_time: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        过滤和限制K线数据
        
        Args:
            klines: K线数据列表
            limit: 最大数量
            before_time: 过滤此时间之后的数据
            
        Returns:
            处理后的K线数据
        """
        # 按时间排序
        klines.sort(key=lambda x: x['time'])
        
        # 过滤时间
        if before_time:
            klines = [k for k in klines if k['time'] < before_time]
        
        # 限制数量（取最新的）
        if len(klines) > limit:
            klines = klines[-limit:]
        
        return klines
    
    def log_result(
        self,
        symbol: str,
        klines: List[Dict[str, Any]],
        timeframe: str
    ):
        """记录获取结果日志"""
        if klines:
            latest_time = datetime.fromtimestamp(klines[-1]['time'])
            time_diff = (datetime.now() - latest_time).total_seconds()
            # logger.info(
            #     f"{self.name}: {symbol} 获取 {len(klines)} 条数据, "
            #     f"最新时间: {latest_time}, 延迟: {time_diff:.0f}秒"
            # )
            
            # 检查数据是否过旧
            max_diff = TIMEFRAME_SECONDS.get(timeframe, 3600) * 2
            if time_diff > max_diff:
                logger.warning(f"Warning: {symbol} data is delayed ({time_diff:.0f}s)")
        else:
            logger.warning(f"{self.name}: no data for {symbol}")

