"""
数据源模块
支持多种市场的K线数据获取

改进版本（参考 daily_stock_analysis 项目）:
- 熔断器保护 (circuit_breaker)
- 数据缓存 (cache_manager)
- 防封禁策略 (rate_limiter)
"""
from app.data_sources.factory import DataSourceFactory
from app.data_sources.circuit_breaker import (
    CircuitBreaker,
    get_realtime_circuit_breaker
)
from app.data_sources.cache_manager import (
    DataCache,
    get_realtime_cache,
    get_kline_cache,
    get_stock_info_cache
)
from app.data_sources.rate_limiter import (
    RateLimiter,
    get_random_user_agent,
    random_sleep,
    retry_with_backoff
)

__all__ = [
    # 工厂
    'DataSourceFactory',
    # 熔断器
    'CircuitBreaker',
    'get_realtime_circuit_breaker',
    # 缓存
    'DataCache',
    'get_realtime_cache',
    'get_kline_cache',
    'get_stock_info_cache',
    # 限流器
    'RateLimiter',
    'get_random_user_agent',
    'random_sleep',
    'retry_with_backoff',
]
