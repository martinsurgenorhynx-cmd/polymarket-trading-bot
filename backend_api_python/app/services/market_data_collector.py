"""
市场数据采集服务 - AI分析专用

设计理念：
1. 数据为王 - 先把数据获取做好、做稳定
2. 统一数据源 - 完全复用 DataSourceFactory 和 kline_service
3. 复用全球金融板块 - 宏观数据、情绪数据复用 global_market.py 的缓存
4. 快速稳定 - 不依赖慢速外部服务（如Jina Reader）

数据源映射：
- 价格/K线: DataSourceFactory (已验证，与K线模块、自选列表一致)
- 宏观数据: 复用 global_market.py (VIX, DXY, TNX, Fear&Greed等，带缓存)
- 新闻: Finnhub API (结构化数据，无需深度阅读)
- 基本面: Finnhub (美股) / 固定描述 (加密)
"""

import time
import os
import sys
import json
import argparse
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError

import yfinance as yf
import pandas as pd

# 本地直跑时，优先加载 .env，确保 API keys 可用
try:
    from dotenv import load_dotenv
    _this_file_dir = os.path.dirname(os.path.abspath(__file__))
    _backend_root_dir = os.path.dirname(os.path.dirname(_this_file_dir))
    _repo_root_dir = os.path.dirname(_backend_root_dir)
    load_dotenv(os.path.join(_backend_root_dir, ".env"), override=False)
    load_dotenv(os.path.join(_repo_root_dir, ".env"), override=False)
except Exception:
    # python-dotenv 可选，不影响系统环境变量注入
    pass

# 支持直接执行该文件：自动补齐 backend_api_python 到 sys.path
if __package__ in (None, ""):
    _this_file_dir = os.path.dirname(os.path.abspath(__file__))
    _backend_root_dir = os.path.dirname(os.path.dirname(_this_file_dir))
    if _backend_root_dir not in sys.path:
        sys.path.insert(0, _backend_root_dir)

from app.data_sources import DataSourceFactory
from app.services.kline import KlineService
from app.utils.logger import get_logger
from app.config import APIKeys

logger = get_logger(__name__)


class MarketDataCollector:
    """
    市场数据采集器
    
    职责：为AI分析提供完整、准确、及时的市场数据
    
    数据层次：
    1. 核心数据 (必须成功): 价格、K线
    2. 分析数据 (增强): 技术指标、基本面
    3. 宏观数据 (可选): 复用 global_market.py (VIX, DXY, TNX, Fear&Greed等)
    4. 情绪数据 (可选): 新闻、市场情绪
    """
    
    def __init__(self):
        self.kline_service = KlineService()
        self._finnhub_client = None
        self._ak = None
        self._init_clients()
    
    def _init_clients(self):
        """初始化外部API客户端"""
        # Finnhub
        finnhub_key = APIKeys.FINNHUB_API_KEY
        if finnhub_key:
            try:
                import finnhub
                self._finnhub_client = finnhub.Client(api_key=finnhub_key)
            except Exception as e:
                logger.warning(f"Finnhub client init failed: {e}")
        
        # akshare (optional, for supplementary data)
        try:
            import akshare as ak
            self._ak = ak
        except ImportError:
            logger.info("akshare not installed")
    
    def collect_all(
        self,
        market: str,
        symbol: str,
        timeframe: str = "1D",
        include_macro: bool = True,
        include_news: bool = True,
        include_polymarket: bool = True,  # 新增：是否包含预测市场数据
        timeout: int = 30
    ) -> Dict[str, Any]:
        """
        采集所有市场数据
        
        Args:
            market: 市场类型 (USStock, Crypto, Forex, Futures)
            symbol: 标的代码
            timeframe: K线周期
            include_macro: 是否包含宏观数据
            include_news: 是否包含新闻
            include_polymarket: 是否包含预测市场数据
            timeout: 总超时时间(秒)
            
        Returns:
            完整的市场数据字典
        """
        start_time = time.time()
        
        data = {
            "market": market,
            "symbol": symbol,
            "timeframe": timeframe,
            "collected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            # 核心数据
            "price": None,
            "kline": None,
            "indicators": {},
            # 基本面
            "fundamental": {},
            "company": {},
            # 宏观
            "macro": {},
            # 情绪
            "news": [],
            "sentiment": {},
            # 预测市场
            "polymarket": [],
            # 元数据
            "_meta": {
                "success_items": [],
                "failed_items": [],
                "duration_ms": 0
            }
        }
        
        # === 阶段1: 核心数据 (并行获取) ===
        with ThreadPoolExecutor(max_workers=4) as executor:
            core_futures = {
                executor.submit(self._get_price, market, symbol): "price",
                executor.submit(self._get_kline, market, symbol, timeframe, 60): "kline",
            }
            
            # 如果需要基本面，也并行获取
            if market == 'USStock':
                core_futures[executor.submit(self._get_fundamental, market, symbol)] = "fundamental"
                core_futures[executor.submit(self._get_company, market, symbol)] = "company"
            elif market == 'Crypto':
                # 加密货币的"基本面"是固定描述
                core_futures[executor.submit(self._get_crypto_info, symbol)] = "fundamental"
            
            try:
                for future in as_completed(core_futures, timeout=15):
                    key = core_futures[future]
                    try:
                        result = future.result(timeout=3)
                        if result:
                            data[key] = result
                            data["_meta"]["success_items"].append(key)
                        else:
                            data["_meta"]["failed_items"].append(key)
                    except Exception as e:
                        logger.warning(f"Core data fetch failed ({key}): {e}")
                        data["_meta"]["failed_items"].append(key)
            except TimeoutError:
                logger.warning(f"Core data fetch timed out for {market}:{symbol}")
        
        # 计算技术指标 (本地计算，不需要外部API)
        if data.get("kline"):
            data["indicators"] = self._calculate_indicators(data["kline"])
            data["_meta"]["success_items"].append("indicators")
        
        # === 阶段2: 宏观数据 (如果需要) ===
        if include_macro:
            try:
                data["macro"] = self._get_macro_data(market, timeout=10)
                if data["macro"]:
                    data["_meta"]["success_items"].append("macro")
            except Exception as e:
                logger.warning(f"Macro data fetch failed: {e}")
                data["_meta"]["failed_items"].append("macro")
        
        # === 阶段3: 新闻/情绪 (如果需要) ===
        if include_news:
            try:
                # 获取公司名称以改善搜索
                company_name = None
                if data.get("company"):
                    company_name = data["company"].get("name")
                
                news_result = self._get_news(market, symbol, company_name, timeout=8)
                data["news"] = news_result.get("news", [])
                data["sentiment"] = news_result.get("sentiment", {})
                
                if data["news"]:
                    data["_meta"]["success_items"].append("news")
            except Exception as e:
                logger.warning(f"News fetch failed: {e}")
                data["_meta"]["failed_items"].append("news")
        
        # === 阶段4: 预测市场数据 (如果需要) ===
        if include_polymarket:
            try:
                polymarket_events = self._get_polymarket_events(symbol, market)
                data["polymarket"] = polymarket_events
                if polymarket_events:
                    data["_meta"]["success_items"].append("polymarket")
            except Exception as e:
                logger.debug(f"Polymarket data fetch failed: {e}")
                data["_meta"]["failed_items"].append("polymarket")
        
        # 记录总耗时
        data["_meta"]["duration_ms"] = int((time.time() - start_time) * 1000)
        logger.info(f"Market data collection completed for {market}:{symbol} in {data['_meta']['duration_ms']}ms")
        logger.info(f"  Success: {data['_meta']['success_items']}")
        logger.info(f"  Failed: {data['_meta']['failed_items']}")
        
        return data
    
    # ==================== 核心数据获取 ====================
    
    def _get_price(self, market: str, symbol: str) -> Optional[Dict[str, Any]]:
        """
        获取实时价格 - 使用 kline_service (与自选列表一致)
        """
        try:
            price_data = self.kline_service.get_realtime_price(market, symbol, force_refresh=True)
            if price_data and price_data.get('price', 0) > 0:
                # 安全转换为 float，处理 None 值
                def safe_float(val, default=0.0):
                    if val is None:
                        return default
                    try:
                        return float(val)
                    except (ValueError, TypeError):
                        return default
                
                price = safe_float(price_data.get('price'))
                return {
                    "price": price,
                    "change": safe_float(price_data.get('change')),
                    "changePercent": safe_float(price_data.get('changePercent')),
                    "high": safe_float(price_data.get('high'), price),
                    "low": safe_float(price_data.get('low'), price),
                    "open": safe_float(price_data.get('open'), price),
                    "previousClose": safe_float(price_data.get('previousClose'), price),
                    "source": price_data.get('source', 'unknown')
                }
        except Exception as e:
            logger.warning(f"Price fetch failed for {market}:{symbol}: {e}")
        
        # 如果 kline_service 失败，尝试从 K 线最后一根获取价格
        try:
            klines = DataSourceFactory.get_kline(market, symbol, "1D", 2)
            if klines and len(klines) > 0:
                latest = klines[-1]
                price = float(latest.get('close', 0))
                if price > 0:
                    prev_close = float(klines[-2].get('close', price)) if len(klines) > 1 else price
                    change = price - prev_close
                    change_pct = (change / prev_close * 100) if prev_close > 0 else 0
                    
                    logger.info(f"Price fetched from K-line fallback for {market}:{symbol}: ${price}")
                    return {
                        "price": price,
                        "change": round(change, 6),
                        "changePercent": round(change_pct, 2),
                        "high": float(latest.get('high', price)),
                        "low": float(latest.get('low', price)),
                        "open": float(latest.get('open', price)),
                        "previousClose": prev_close,
                        "source": "kline_fallback"
                    }
        except Exception as e:
            logger.warning(f"K-line fallback price fetch also failed for {market}:{symbol}: {e}")
        
        return None
    
    def _get_kline(
        self, market: str, symbol: str, timeframe: str, limit: int = 60
    ) -> Optional[List[Dict[str, Any]]]:
        """
        获取K线数据 - 使用 DataSourceFactory (与K线模块一致)
        """
        try:
            klines = DataSourceFactory.get_kline(market, symbol, timeframe, limit)
            if klines and len(klines) > 0:
                return klines
        except Exception as e:
            logger.warning(f"Kline fetch failed for {market}:{symbol}: {e}")
        return None
    
    def _calculate_indicators(self, klines: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        计算技术指标 (本地计算，无外部依赖)
        
        返回格式符合前端 FastAnalysisReport.vue 的期望：
        {
            rsi: { value, signal },
            macd: { signal, trend },
            moving_averages: { ma5, ma10, ma20, trend },
            levels: { support, resistance },
            volatility: { level, pct }
        }
        """
        if not klines or len(klines) < 5:
            return {}
        
        try:
            closes = [float(k.get('close', 0)) for k in klines]
            highs = [float(k.get('high', 0)) for k in klines]
            lows = [float(k.get('low', 0)) for k in klines]
            volumes = [float(k.get('volume', 0)) for k in klines]
            
            if not closes:
                return {}
            
            current_price = closes[-1]
            indicators = {}
            
            # ========== RSI ==========
            if len(closes) >= 15:
                rsi_value = self._calc_rsi(closes, 14)
                if rsi_value < 30:
                    rsi_signal = "oversold"
                elif rsi_value > 70:
                    rsi_signal = "overbought"
                else:
                    rsi_signal = "neutral"
                indicators['rsi'] = {
                    'value': round(rsi_value, 2),
                    'signal': rsi_signal,
                }
            
            # ========== MACD ==========
            if len(closes) >= 26:
                macd_raw = self._calc_macd(closes)
                macd_val = macd_raw.get('MACD', 0)
                macd_sig = macd_raw.get('MACD_signal', 0)
                macd_hist = macd_raw.get('MACD_histogram', 0)
                
                if macd_val > macd_sig and macd_hist > 0:
                    macd_signal = "bullish"
                    macd_trend = "golden_cross" if macd_hist > 0 else "bullish"
                elif macd_val < macd_sig and macd_hist < 0:
                    macd_signal = "bearish"
                    macd_trend = "death_cross" if macd_hist < 0 else "bearish"
                else:
                    macd_signal = "neutral"
                    macd_trend = "consolidating"
                
                indicators['macd'] = {
                    'value': round(macd_val, 6),
                    'signal_line': round(macd_sig, 6),
                    'histogram': round(macd_hist, 6),
                    'signal': macd_signal,
                    'trend': macd_trend,
                }
            
            # ========== 移动平均线 ==========
            ma5 = sum(closes[-5:]) / 5 if len(closes) >= 5 else current_price
            ma10 = sum(closes[-10:]) / 10 if len(closes) >= 10 else current_price
            ma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else current_price
            
            if current_price > ma5 > ma10 > ma20:
                ma_trend = "strong_uptrend"
            elif current_price > ma20:
                ma_trend = "uptrend"
            elif current_price < ma5 < ma10 < ma20:
                ma_trend = "strong_downtrend"
            elif current_price < ma20:
                ma_trend = "downtrend"
            else:
                ma_trend = "sideways"
            
            indicators['moving_averages'] = {
                'ma5': round(ma5, 6),
                'ma10': round(ma10, 6),
                'ma20': round(ma20, 6),
                'trend': ma_trend,
            }
            
            # ========== 支撑/阻力位 (多种方法综合) ==========
            # 方法1: 枢轴点 (Pivot Points) - 使用前一日数据
            if len(klines) >= 2:
                prev_high = float(klines[-2].get('high', highs[-2]) if len(highs) >= 2 else current_price * 1.02)
                prev_low = float(klines[-2].get('low', lows[-2]) if len(lows) >= 2 else current_price * 0.98)
                prev_close = float(klines[-2].get('close', closes[-2]) if len(closes) >= 2 else current_price)
                
                pivot = (prev_high + prev_low + prev_close) / 3
                r1 = 2 * pivot - prev_low  # 阻力位1
                s1 = 2 * pivot - prev_high  # 支撑位1
                r2 = pivot + (prev_high - prev_low)  # 阻力位2
                s2 = pivot - (prev_high - prev_low)  # 支撑位2
            else:
                pivot = current_price
                r1 = r2 = current_price * 1.02
                s1 = s2 = current_price * 0.98
            
            # 方法2: 近期高低点
            recent_highs = highs[-20:] if len(highs) >= 20 else highs
            recent_lows = lows[-20:] if len(lows) >= 20 else lows
            swing_high = max(recent_highs) if recent_highs else current_price * 1.05
            swing_low = min(recent_lows) if recent_lows else current_price * 0.95
            
            # 方法3: 布林带中轨上下 (如果有)
            bb_upper = indicators.get('bollinger', {}).get('upper', swing_high)
            bb_lower = indicators.get('bollinger', {}).get('lower', swing_low)
            
            # 综合取值: 取多种方法的平均/加权
            resistance = round((r1 + swing_high + bb_upper) / 3, 6) if bb_upper else round((r1 + swing_high) / 2, 6)
            support = round((s1 + swing_low + bb_lower) / 3, 6) if bb_lower else round((s1 + swing_low) / 2, 6)
            
            indicators['levels'] = {
                'support': support,
                'resistance': resistance,
                'pivot': round(pivot, 6),
                's1': round(s1, 6),
                'r1': round(r1, 6),
                's2': round(s2, 6),
                'r2': round(r2, 6),
                'swing_high': round(swing_high, 6),
                'swing_low': round(swing_low, 6),
                'method': 'pivot_swing_bb_avg'  # 标注计算方法
            }
            
            # ========== ATR 和波动率 ==========
            atr = 0
            if len(klines) >= 14:
                # 真实波动幅度 ATR (True Range)
                true_ranges = []
                for i in range(-14, 0):
                    h = float(klines[i].get('high', 0))
                    l = float(klines[i].get('low', 0))
                    prev_c = float(klines[i-1].get('close', 0)) if i > -14 else h
                    if h > 0 and l > 0:
                        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
                        true_ranges.append(tr)
                
                atr = sum(true_ranges) / len(true_ranges) if true_ranges else 0
                volatility_pct = (atr / current_price * 100) if current_price > 0 else 0
                
                if volatility_pct > 5:
                    volatility_level = "high"
                elif volatility_pct > 2:
                    volatility_level = "medium"
                else:
                    volatility_level = "low"
            else:
                volatility_level = "unknown"
                volatility_pct = 0
            
            indicators['volatility'] = {
                'level': volatility_level,
                'pct': round(volatility_pct, 2),
                'atr': round(atr, 6),  # 添加 ATR 绝对值
            }
            
            # ========== 止盈止损建议 (基于 ATR 和支撑/阻力) ==========
            # 止损: 基于 2x ATR 或支撑位，取更保守的
            atr_stop_loss = current_price - (2 * atr) if atr > 0 else current_price * 0.95
            support_stop = indicators['levels']['support']
            suggested_stop_loss = max(atr_stop_loss, support_stop * 0.99)  # 略低于支撑位
            
            # 止盈: 基于 3x ATR 或阻力位，考虑风险回报比
            atr_take_profit = current_price + (3 * atr) if atr > 0 else current_price * 1.05
            resistance_tp = indicators['levels']['resistance']
            suggested_take_profit = min(atr_take_profit, resistance_tp * 1.01)  # 略高于阻力位
            
            # 风险回报比
            risk = current_price - suggested_stop_loss
            reward = suggested_take_profit - current_price
            risk_reward_ratio = round(reward / risk, 2) if risk > 0 else 0
            
            indicators['trading_levels'] = {
                'suggested_stop_loss': round(suggested_stop_loss, 6),
                'suggested_take_profit': round(suggested_take_profit, 6),
                'risk_reward_ratio': risk_reward_ratio,
                'atr_multiplier_sl': 2.0,  # 止损使用 2x ATR
                'atr_multiplier_tp': 3.0,  # 止盈使用 3x ATR
                'method': 'atr_support_resistance'
            }
            
            # ========== 布林带 (附加) ==========
            if len(closes) >= 20:
                bb_data = self._calc_bollinger(closes, 20, 2)
                indicators['bollinger'] = bb_data
            
            # ========== 成交量 (附加) ==========
            if len(volumes) >= 20:
                avg_vol = sum(volumes[-20:]) / 20
                indicators['volume_ratio'] = round(volumes[-1] / avg_vol, 2) if avg_vol > 0 else 1.0
            
            # ========== 价格位置 (附加) ==========
            if len(closes) >= 20:
                high_20 = max(highs[-20:])
                low_20 = min(lows[-20:])
                if high_20 > low_20:
                    indicators['price_position'] = round((current_price - low_20) / (high_20 - low_20) * 100, 1)
                else:
                    indicators['price_position'] = 50.0
            
            # ========== 整体趋势 (附加) ==========
            indicators['trend'] = ma_trend
            indicators['current_price'] = round(current_price, 6)
            
            return indicators
            
        except Exception as e:
            logger.warning(f"Indicator calculation failed: {e}")
            return {}
    
    def _calc_rsi(self, closes: List[float], period: int = 14) -> float:
        """计算RSI"""
        if len(closes) < period + 1:
            return 50.0
        
        deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]
        
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return round(rsi, 2)
    
    def _calc_macd(self, closes: List[float]) -> Dict[str, float]:
        """计算MACD"""
        def ema(data, period):
            multiplier = 2 / (period + 1)
            ema_values = [data[0]]
            for i in range(1, len(data)):
                ema_values.append((data[i] - ema_values[-1]) * multiplier + ema_values[-1])
            return ema_values
        
        ema12 = ema(closes, 12)
        ema26 = ema(closes, 26)
        
        macd_line = [ema12[i] - ema26[i] for i in range(len(closes))]
        signal_line = ema(macd_line, 9)
        histogram = [macd_line[i] - signal_line[i] for i in range(len(closes))]
        
        return {
            'MACD': round(macd_line[-1], 4),
            'MACD_signal': round(signal_line[-1], 4),
            'MACD_histogram': round(histogram[-1], 4)
        }
    
    def _calc_bollinger(self, closes: List[float], period: int = 20, std_dev: int = 2) -> Dict[str, float]:
        """计算布林带"""
        if len(closes) < period:
            return {}
        
        recent = closes[-period:]
        middle = sum(recent) / period
        
        variance = sum((x - middle) ** 2 for x in recent) / period
        std = variance ** 0.5
        
        return {
            'BB_upper': round(middle + std_dev * std, 4),
            'BB_middle': round(middle, 4),
            'BB_lower': round(middle - std_dev * std, 4),
            'BB_width': round((std_dev * std * 2) / middle * 100, 2) if middle > 0 else 0
        }
    
    # ==================== 基本面数据 ====================
    
    def _get_fundamental(self, market: str, symbol: str) -> Optional[Dict[str, Any]]:
        """获取基本面数据"""
        try:
            if market == 'USStock':
                return self._get_us_fundamental(symbol)
        except Exception as e:
            logger.warning(f"Fundamental data fetch failed for {market}:{symbol}: {e}")
        return None
    
    def _get_us_fundamental(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        美股基本面 - Finnhub + yfinance
        包括：基础财务指标 + 财报数据（资产负债表、利润表、现金流量表）
        """
        result = {}
        
        # === 1. 基础财务指标 (Finnhub) ===
        if self._finnhub_client:
            try:
                metrics = self._finnhub_client.company_basic_financials(symbol, 'all')
                if metrics and metrics.get('metric'):
                    m = metrics['metric']
                    result.update({
                        'pe_ratio': m.get('peBasicExclExtraTTM'),
                        'pb_ratio': m.get('pbQuarterly'),
                        'ps_ratio': m.get('psTTM'),
                        'market_cap': m.get('marketCapitalization'),
                        'dividend_yield': m.get('dividendYieldIndicatedAnnual'),
                        'beta': m.get('beta'),
                        '52w_high': m.get('52WeekHigh'),
                        '52w_low': m.get('52WeekLow'),
                        'roe': m.get('roeTTM'),
                        'eps': m.get('epsBasicExclExtraItemsTTM'),
                        'revenue_growth': m.get('revenueGrowthTTMYoy'),
                        'profit_margin': m.get('netProfitMarginTTM'),
                        'debt_to_equity': m.get('totalDebtToEquityQuarterly'),
                        'current_ratio': m.get('currentRatioQuarterly'),
                        'quick_ratio': m.get('quickRatioQuarterly'),
                    })
            except Exception as e:
                logger.debug(f"Finnhub fundamental failed for {symbol}: {e}")
        
        # === 2. yfinance 补充基础指标 ===
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info or {}
            
            # 补充缺失的基础指标
            if not result.get('pe_ratio'):
                result['pe_ratio'] = info.get('trailingPE') or info.get('forwardPE')
            if not result.get('pb_ratio'):
                result['pb_ratio'] = info.get('priceToBook')
            if not result.get('market_cap'):
                result['market_cap'] = info.get('marketCap')
            if not result.get('dividend_yield'):
                result['dividend_yield'] = info.get('dividendYield')
            if not result.get('beta'):
                result['beta'] = info.get('beta')
            if not result.get('52w_high'):
                result['52w_high'] = info.get('fiftyTwoWeekHigh')
            if not result.get('52w_low'):
                result['52w_low'] = info.get('fiftyTwoWeekLow')
            if not result.get('roe'):
                result['roe'] = info.get('returnOnEquity')
            if not result.get('eps'):
                result['eps'] = info.get('trailingEps')
            
            # 补充更多财务指标
            result.update({
                'revenue': info.get('totalRevenue'),
                'gross_profit': info.get('grossProfits'),
                'operating_margin': info.get('operatingMargins'),
                'profit_margin': result.get('profit_margin') or info.get('profitMargins'),
                'ebitda': info.get('ebitda'),
                'debt': info.get('totalDebt'),
                'cash': info.get('totalCash'),
                'free_cash_flow': info.get('freeCashflow'),
                'operating_cash_flow': info.get('operatingCashflow'),
                'book_value': info.get('bookValue'),
                'enterprise_value': info.get('enterpriseValue'),
            })
        except Exception as e:
            logger.debug(f"yfinance fundamental failed for {symbol}: {e}")
        
        # === 3. 获取财报数据（资产负债表、利润表、现金流量表）===
        financial_statements = self._get_financial_statements(symbol)
        if financial_statements:
            result['financial_statements'] = financial_statements
        
        # === 4. 获取盈利报告（Earnings）===
        earnings_data = self._get_earnings_data(symbol)
        if earnings_data:
            result['earnings'] = earnings_data
        
        return result if result else None
    
    def _get_financial_statements(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        获取财务报表数据（资产负债表、利润表、现金流量表）
        
        使用 yfinance 获取，包含最近几个季度的数据
        """
        try:
            ticker = yf.Ticker(symbol)
            statements = {}
            
            # 资产负债表 (Balance Sheet)
            try:
                balance_sheet = ticker.balance_sheet
                if balance_sheet is not None and not balance_sheet.empty:
                    # 获取最近4个季度
                    latest_quarters = balance_sheet.columns[:4] if len(balance_sheet.columns) >= 4 else balance_sheet.columns
                    statements['balance_sheet'] = {
                        'latest_date': str(latest_quarters[0]) if len(latest_quarters) > 0 else None,
                        'total_assets': float(balance_sheet.loc['Total Assets', latest_quarters[0]]) if 'Total Assets' in balance_sheet.index and len(latest_quarters) > 0 else None,
                        'total_liabilities': float(balance_sheet.loc['Total Liab', latest_quarters[0]]) if 'Total Liab' in balance_sheet.index and len(latest_quarters) > 0 else None,
                        'total_equity': float(balance_sheet.loc['Stockholders Equity', latest_quarters[0]]) if 'Stockholders Equity' in balance_sheet.index and len(latest_quarters) > 0 else None,
                        'cash': float(balance_sheet.loc['Cash', latest_quarters[0]]) if 'Cash' in balance_sheet.index and len(latest_quarters) > 0 else None,
                        'debt': float(balance_sheet.loc['Total Debt', latest_quarters[0]]) if 'Total Debt' in balance_sheet.index and len(latest_quarters) > 0 else None,
                        'current_assets': float(balance_sheet.loc['Current Assets', latest_quarters[0]]) if 'Current Assets' in balance_sheet.index and len(latest_quarters) > 0 else None,
                        'current_liabilities': float(balance_sheet.loc['Current Liabilities', latest_quarters[0]]) if 'Current Liabilities' in balance_sheet.index and len(latest_quarters) > 0 else None,
                    }
            except Exception as e:
                logger.debug(f"Balance sheet fetch failed for {symbol}: {e}")
            
            # 利润表 (Income Statement)
            try:
                income_stmt = ticker.financials
                if income_stmt is not None and not income_stmt.empty:
                    latest_quarters = income_stmt.columns[:4] if len(income_stmt.columns) >= 4 else income_stmt.columns
                    statements['income_statement'] = {
                        'latest_date': str(latest_quarters[0]) if len(latest_quarters) > 0 else None,
                        'total_revenue': float(income_stmt.loc['Total Revenue', latest_quarters[0]]) if 'Total Revenue' in income_stmt.index and len(latest_quarters) > 0 else None,
                        'gross_profit': float(income_stmt.loc['Gross Profit', latest_quarters[0]]) if 'Gross Profit' in income_stmt.index and len(latest_quarters) > 0 else None,
                        'operating_income': float(income_stmt.loc['Operating Income', latest_quarters[0]]) if 'Operating Income' in income_stmt.index and len(latest_quarters) > 0 else None,
                        'net_income': float(income_stmt.loc['Net Income', latest_quarters[0]]) if 'Net Income' in income_stmt.index and len(latest_quarters) > 0 else None,
                        'eps': float(income_stmt.loc['Basic EPS', latest_quarters[0]]) if 'Basic EPS' in income_stmt.index and len(latest_quarters) > 0 else None,
                    }
            except Exception as e:
                logger.debug(f"Income statement fetch failed for {symbol}: {e}")
            
            # 现金流量表 (Cash Flow Statement)
            try:
                cashflow = ticker.cashflow
                if cashflow is not None and not cashflow.empty:
                    latest_quarters = cashflow.columns[:4] if len(cashflow.columns) >= 4 else cashflow.columns
                    statements['cash_flow'] = {
                        'latest_date': str(latest_quarters[0]) if len(latest_quarters) > 0 else None,
                        'operating_cash_flow': float(cashflow.loc['Operating Cash Flow', latest_quarters[0]]) if 'Operating Cash Flow' in cashflow.index and len(latest_quarters) > 0 else None,
                        'investing_cash_flow': float(cashflow.loc['Capital Expenditure', latest_quarters[0]]) if 'Capital Expenditure' in cashflow.index and len(latest_quarters) > 0 else None,
                        'financing_cash_flow': float(cashflow.loc['Financing Cash Flow', latest_quarters[0]]) if 'Financing Cash Flow' in cashflow.index and len(latest_quarters) > 0 else None,
                        'free_cash_flow': float(cashflow.loc['Free Cash Flow', latest_quarters[0]]) if 'Free Cash Flow' in cashflow.index and len(latest_quarters) > 0 else None,
                    }
            except Exception as e:
                logger.debug(f"Cash flow statement fetch failed for {symbol}: {e}")
            
            return statements if statements else None
            
        except Exception as e:
            logger.debug(f"Financial statements fetch failed for {symbol}: {e}")
            return None
    
    def _get_earnings_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        获取盈利报告数据（Earnings）
        
        包括：历史盈利、盈利预测、盈利日期等
        """
        try:
            ticker = yf.Ticker(symbol)
            earnings_data = {}
            
            # 历史盈利数据
            try:
                earnings_history = ticker.earnings_history
                if earnings_history is not None and not earnings_history.empty:
                    # 获取最近4个季度
                    recent_earnings = earnings_history.head(4)
                    earnings_data['history'] = []
                    for _, row in recent_earnings.iterrows():
                        earnings_data['history'].append({
                            'date': str(row.get('Date', '')),
                            'eps_actual': float(row.get('EPS Actual', 0)) if row.get('EPS Actual') is not None else None,
                            'eps_estimate': float(row.get('EPS Estimate', 0)) if row.get('EPS Estimate') is not None else None,
                            'surprise': float(row.get('Surprise(%)', 0)) if row.get('Surprise(%)') is not None else None,
                        })
            except Exception as e:
                logger.debug(f"Earnings history fetch failed for {symbol}: {e}")
            
            # 盈利日历（未来盈利日期）
            try:
                earnings_calendar = ticker.calendar
                if earnings_calendar is not None and not earnings_calendar.empty:
                    earnings_data['upcoming'] = {
                        'next_earnings_date': str(earnings_calendar.index[0]) if len(earnings_calendar.index) > 0 else None,
                        'eps_estimate': float(earnings_calendar.loc[earnings_calendar.index[0], 'Earnings Estimate']) if len(earnings_calendar.index) > 0 and 'Earnings Estimate' in earnings_calendar.columns else None,
                        'revenue_estimate': float(earnings_calendar.loc[earnings_calendar.index[0], 'Revenue Estimate']) if len(earnings_calendar.index) > 0 and 'Revenue Estimate' in earnings_calendar.columns else None,
                    }
            except Exception as e:
                logger.debug(f"Earnings calendar fetch failed for {symbol}: {e}")
            
            # 季度盈利数据
            try:
                quarterly_earnings = ticker.quarterly_earnings
                if quarterly_earnings is not None and not quarterly_earnings.empty:
                    latest_q = quarterly_earnings.index[0] if len(quarterly_earnings.index) > 0 else None
                    if latest_q:
                        earnings_data['quarterly'] = {
                            'latest_quarter': str(latest_q),
                            'revenue': float(quarterly_earnings.loc[latest_q, 'Revenue']) if 'Revenue' in quarterly_earnings.columns else None,
                            'earnings': float(quarterly_earnings.loc[latest_q, 'Earnings']) if 'Earnings' in quarterly_earnings.columns else None,
                        }
            except Exception as e:
                logger.debug(f"Quarterly earnings fetch failed for {symbol}: {e}")
            
            return earnings_data if earnings_data else None
            
        except Exception as e:
            logger.debug(f"Earnings data fetch failed for {symbol}: {e}")
            return None
    
    def _get_crypto_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """加密货币信息 (固定描述为主)"""
        # 常见加密货币的描述
        crypto_info = {
            'BTC': {
                'name': 'Bitcoin',
                'description': '比特币，数字黄金，市值第一的加密货币，作为价值存储和避险资产',
                'category': 'Store of Value',
            },
            'ETH': {
                'name': 'Ethereum',
                'description': '以太坊，智能合约平台，DeFi和NFT生态的基础设施',
                'category': 'Smart Contract Platform',
            },
            'BNB': {
                'name': 'Binance Coin',
                'description': '币安币，全球最大交易所的平台代币',
                'category': 'Exchange Token',
            },
            'SOL': {
                'name': 'Solana',
                'description': '高性能公链，主打高TPS和低Gas费',
                'category': 'Smart Contract Platform',
            },
            'XRP': {
                'name': 'Ripple',
                'description': '瑞波币，专注跨境支付解决方案',
                'category': 'Payment',
            },
            'DOGE': {
                'name': 'Dogecoin',
                'description': '狗狗币，Meme币代表，社区驱动',
                'category': 'Meme',
            },
        }
        
        # 提取基础代币名
        base = symbol.split('/')[0] if '/' in symbol else symbol
        base = base.upper()
        
        if base in crypto_info:
            return crypto_info[base]
        
        return {
            'name': base,
            'description': f'{base} 是一种加密货币',
            'category': 'Unknown',
        }
    
    def _get_company(self, market: str, symbol: str) -> Optional[Dict[str, Any]]:
        """获取公司信息"""
        try:
            if market == 'USStock' and self._finnhub_client:
                profile = self._finnhub_client.company_profile2(symbol=symbol)
                if profile:
                    return {
                        'name': profile.get('name'),
                        'industry': profile.get('finnhubIndustry'),
                        'country': profile.get('country'),
                        'exchange': profile.get('exchange'),
                        'ipo_date': profile.get('ipo'),
                        'market_cap': profile.get('marketCapitalization'),
                        'website': profile.get('weburl'),
                    }
            
        except Exception as e:
            logger.debug(f"Company info fetch failed for {market}:{symbol}: {e}")
        
        return None
    
    # ==================== 宏观数据 (复用全球金融板块) ====================
    
    def _get_macro_data(self, market: str, timeout: int = 10) -> Dict[str, Any]:
        """
        获取宏观经济数据 - 复用 global_market.py 的函数和缓存
        
        优势：
        1. 数据与全球金融页面一致
        2. 复用30秒/5分钟缓存，降低API调用
        3. 已有完整的数据解读和级别判断
        """
        try:
            # 复用 global_market.py 的市场情绪数据 (有5分钟缓存)
            from app.routes.global_market import (
                _fetch_vix, _fetch_dollar_index, _fetch_yield_curve,
                _fetch_fear_greed_index,
                _get_cached, _set_cached
            )
            
            result = {}
            
            # 1) 尝试从缓存获取 (global_market 的缓存, 6小时有效)
            MACRO_CACHE_TTL = 21600  # 6 hours
            cached_sentiment = _get_cached("market_sentiment", MACRO_CACHE_TTL)
            if cached_sentiment:
                logger.info("Using cached sentiment data from global_market (6h cache)")
                # 转换格式
                if cached_sentiment.get('vix'):
                    vix = cached_sentiment['vix']
                    result['VIX'] = {
                        'name': 'VIX恐慌指数',
                        'description': vix.get('interpretation', ''),
                        'price': vix.get('value', 0),
                        'change': vix.get('change', 0),
                        'changePercent': vix.get('change', 0),
                        'level': vix.get('level', 'unknown'),
                    }
                
                if cached_sentiment.get('dxy'):
                    dxy = cached_sentiment['dxy']
                    result['DXY'] = {
                        'name': '美元指数',
                        'description': dxy.get('interpretation', ''),
                        'price': dxy.get('value', 0),
                        'change': dxy.get('change', 0),
                        'changePercent': dxy.get('change', 0),
                        'level': dxy.get('level', 'unknown'),
                    }
                
                if cached_sentiment.get('yield_curve'):
                    yc = cached_sentiment['yield_curve']
                    result['TNX'] = {
                        'name': '美债10年收益率',
                        'description': yc.get('interpretation', ''),
                        'price': yc.get('yield_10y', 0),
                        'change': yc.get('change', 0),
                        'changePercent': 0,
                        'spread': yc.get('spread', 0),
                        'level': yc.get('level', 'unknown'),
                    }
                
                if cached_sentiment.get('fear_greed'):
                    fg = cached_sentiment['fear_greed']
                    result['FEAR_GREED'] = {
                        'name': '恐惧贪婪指数',
                        'description': fg.get('classification', 'Neutral'),
                        'price': fg.get('value', 50),
                        'change': 0,
                        'changePercent': 0,
                    }
                
                if result:
                    return result
            
            # 2) 如果没有缓存，快速并行获取关键指标
            logger.info("Fetching macro data from global_market functions")
            
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {
                    executor.submit(_fetch_vix): "VIX",
                    executor.submit(_fetch_dollar_index): "DXY",
                    executor.submit(_fetch_yield_curve): "TNX",
                    executor.submit(_fetch_fear_greed_index): "FEAR_GREED",
                }
                
                try:
                    for future in as_completed(futures, timeout=timeout):
                        key = futures[future]
                        try:
                            data = future.result(timeout=5)
                            if data:
                                # 转换为统一格式
                                if key == 'VIX':
                                    result[key] = {
                                        'name': 'VIX恐慌指数',
                                        'description': data.get('interpretation', ''),
                                        'price': data.get('value', 0),
                                        'change': data.get('change', 0),
                                        'changePercent': data.get('change', 0),
                                        'level': data.get('level', 'unknown'),
                                    }
                                elif key == 'DXY':
                                    result[key] = {
                                        'name': '美元指数',
                                        'description': data.get('interpretation', ''),
                                        'price': data.get('value', 0),
                                        'change': data.get('change', 0),
                                        'changePercent': data.get('change', 0),
                                        'level': data.get('level', 'unknown'),
                                    }
                                elif key == 'TNX':
                                    result[key] = {
                                        'name': '美债10年收益率',
                                        'description': data.get('interpretation', ''),
                                        'price': data.get('yield_10y', 0),
                                        'change': data.get('change', 0),
                                        'changePercent': 0,
                                        'spread': data.get('spread', 0),
                                        'level': data.get('level', 'unknown'),
                                    }
                                elif key == 'FEAR_GREED':
                                    result[key] = {
                                        'name': '恐惧贪婪指数',
                                        'description': data.get('classification', 'Neutral'),
                                        'price': data.get('value', 50),
                                        'change': 0,
                                        'changePercent': 0,
                                    }
                        except Exception as e:
                            logger.debug(f"Macro indicator {key} fetch failed: {e}")
                except TimeoutError:
                    logger.warning("Macro data fetch timed out")
            
            # 注：黄金等大宗商品数据不再作为宏观指标获取
            # 原因：1) 如果分析的是黄金，价格已在 _get_price 中获取
            #       2) 减少 API 调用，提高稳定性
            pass
            
            return result
            
        except ImportError as e:
            logger.warning(f"Could not import from global_market: {e}")
            return {}
        except Exception as e:
            logger.error(f"_get_macro_data failed: {e}")
            return {}
    
    # ==================== 新闻/情绪数据 ====================
    
    def _get_news(
        self, market: str, symbol: str, company_name: str = None, timeout: int = 8
    ) -> Dict[str, Any]:
        """
        获取新闻和情绪数据
        
        策略（按优先级）：
        1. 结构化API (Finnhub) - 美股首选
        2. 搜索引擎 (Bocha/Tavily) - 补充搜索
        3. 情绪分析 - Finnhub 社交媒体情绪
        """
        news_list = []
        sentiment = {}
        
        # === 1) Finnhub 新闻 (美股首选) ===
        if self._finnhub_client:
            try:
                end_date = datetime.now().strftime('%Y-%m-%d')
                start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
                
                raw_news = []
                
                if market == 'USStock':
                    raw_news = self._finnhub_client.company_news(symbol, _from=start_date, to=end_date)
                elif market == 'Crypto':
                    # 加密货币通用新闻
                    raw_news = self._finnhub_client.general_news('crypto', min_id=0)
                else:
                    # 其他市场通用新闻
                    raw_news = self._finnhub_client.general_news('general', min_id=0)
                
                if raw_news:
                    for item in raw_news[:10]:
                        if not item.get('headline'):
                            continue
                        news_list.append({
                            "datetime": datetime.fromtimestamp(item.get('datetime', 0)).strftime('%Y-%m-%d %H:%M'),
                            "headline": item.get('headline', ''),
                            "summary": item.get('summary', '')[:300] if item.get('summary') else '',
                            "source": item.get('source', 'Finnhub'),
                            "url": item.get('url', ''),
                            "sentiment": item.get('sentiment', 'neutral'),
                        })
                    logger.info(f"Finnhub 新闻获取成功: {len(news_list)} 条")
            except Exception as e:
                logger.debug(f"Finnhub news fetch failed: {e}")
        
        # === 2) Finnhub 情绪分数 (美股社交媒体情绪) ===
        if self._finnhub_client and market == 'USStock':
            try:
                social = self._finnhub_client.stock_social_sentiment(symbol)
                if social:
                    sentiment['reddit'] = social.get('reddit', {})
                    sentiment['twitter'] = social.get('twitter', {})
            except Exception as e:
                logger.debug(f"Finnhub sentiment fetch failed: {e}")
        
        # === 3) 搜索引擎补充 (如果新闻太少) ===
        if len(news_list) < 5:
            search_news = self._get_news_from_search(market, symbol, company_name)
            news_list.extend(search_news)
        
        # === 4) 获取全球重大事件新闻（地缘政治、战争等） ===
        # 这些事件会影响所有市场，特别是加密货币
        global_events = self._get_global_major_events()
        if global_events:
            news_list.extend(global_events)
            logger.info(f"Added {len(global_events)} global major events to news list")
        
        # 去重（按标题）
        seen_titles = set()
        unique_news = []
        for item in news_list:
            title = item.get('headline', '')
            if title and title not in seen_titles:
                seen_titles.add(title)
                unique_news.append(item)
        
        # 按时间排序
        unique_news.sort(key=lambda x: x.get('datetime', ''), reverse=True)
        
        return {
            "news": unique_news[:15],  # 最多15条
            "sentiment": sentiment,
        }
    
    def _get_news_from_search(
        self, market: str, symbol: str, company_name: str = None
    ) -> List[Dict[str, Any]]:
        """
        从搜索引擎获取新闻
        
        使用增强的搜索服务 (Bocha/Tavily/SerpAPI)
        """
        news_list = []
        
        try:
            from app.services.search import get_search_service
            search_service = get_search_service()
            
            if not search_service.is_available:
                return news_list
            
            # 构建搜索名称
            search_name = company_name or symbol
            
            # 搜索股票新闻
            response = search_service.search_stock_news(
                stock_code=symbol,
                stock_name=search_name,
                market=market,
                max_results=5
            )
            
            if response.success and response.results:
                for result in response.results:
                    news_list.append({
                        "datetime": result.published_date or datetime.now().strftime('%Y-%m-%d'),
                        "headline": result.title,
                        "summary": result.snippet[:200] if result.snippet else '',
                        "source": f"搜索:{result.source}",
                        "url": result.url,
                        "sentiment": result.sentiment,
                    })
                logger.info(f"搜索引擎新闻补充: {len(news_list)} 条 (来源: {response.provider})")
        except Exception as e:
            logger.debug(f"搜索引擎新闻获取失败: {e}")
        
        return news_list
    
    def _get_global_major_events(self) -> List[Dict]:
        """
        获取全球重大事件新闻（地缘政治、战争、重大政策等）
        这些事件会影响所有市场，特别是加密货币
        
        Returns:
            全球重大事件新闻列表
        """
        news_list = []
        
        try:
            from app.services.search import get_search_service
            search_service = get_search_service()
            
            if not search_service.is_available:
                return news_list
            
            # 搜索全球重大事件（最近24小时）
            # 优化：减少搜索次数，只搜索最重要的查询
            global_event_queries = [
                "war conflict breaking news today"  # 只搜索最重要的查询，减少API调用
            ]
            
            for query in global_event_queries:
                try:
                    response = search_service.search_with_fallback(
                        query=query,
                        max_results=2,
                        days=1  # 只搜索最近1天的新闻
                    )
                    
                    if response.success and response.results:
                        for result in response.results:
                            # 检查是否是重大事件（包含关键词）
                            title_lower = result.title.lower()
                            snippet_lower = (result.snippet or "").lower()
                            text = f"{title_lower} {snippet_lower}"
                            
                            # 重大事件关键词
                            major_event_keywords = [
                                "war", "conflict", "military", "attack", "strike", "sanctions",
                                "geopolitical", "crisis", "tension", "iran", "israel", "russia",
                                "ukraine", "middle east", "nato", "united states",
                                "战争", "冲突", "军事", "袭击", "制裁", "地缘政治", "危机"
                            ]
                            
                            if any(keyword in text for keyword in major_event_keywords):
                                news_list.append({
                                    "datetime": result.published_date or datetime.now().strftime('%Y-%m-%d %H:%M'),
                                    "headline": result.title,
                                    "summary": result.snippet[:300] if result.snippet else '',
                                    "source": f"全球事件:{result.source}",
                                    "url": result.url,
                                    "sentiment": "negative" if any(kw in text for kw in ["war", "conflict", "attack", "战争", "冲突", "袭击"]) else "neutral",
                                    "is_global_event": True  # 标记为全球事件
                                })
                                logger.info(f"Found global major event: {result.title[:60]}")
                except Exception as e:
                    logger.debug(f"Failed to search global events with query '{query}': {e}")
                    continue
            
            # 去重
            seen_titles = set()
            unique_events = []
            for item in news_list:
                title = item.get('headline', '')
                if title and title not in seen_titles:
                    seen_titles.add(title)
                    unique_events.append(item)
            
            return unique_events[:5]  # 最多返回5条全球重大事件
            
        except Exception as e:
            logger.debug(f"Failed to get global major events: {e}")
            return []
    
    def _get_polymarket_events(self, symbol: str, market: str) -> List[Dict]:
        """
        获取与资产相关的预测市场事件
        直接调用Polymarket API获取实时数据，不依赖本地数据库
        
        Args:
            symbol: 资产符号
            market: 市场类型
            
        Returns:
            相关预测市场事件列表
        """
        try:
            from app.data_sources.polymarket import PolymarketDataSource
            
            polymarket_source = PolymarketDataSource()
            
            # 提取关键词
            keywords = self._extract_polymarket_keywords(symbol, market)
            logger.info(f"Extracted Polymarket keywords for {symbol}: {keywords}")
            
            # 优化：使用缓存加速，减少API调用时间
            # 对于AI分析，使用短期缓存（5分钟）即可，既保证时效性又提升性能
            # 进一步优化：限制关键词数量，只搜索最重要的关键词（最多2个）
            related_markets = []
            max_keywords = 2  # 最多只搜索2个关键词，减少API调用
            for keyword in keywords[:max_keywords]:
                try:
                    # 使用use_cache=True启用缓存，减少API调用时间
                    markets = polymarket_source.search_markets(keyword, limit=5, use_cache=True)
                    logger.info(f"Found {len(markets)} markets for keyword '{keyword}' (cached)")
                    related_markets.extend(markets)
                except Exception as e:
                    logger.warning(f"Failed to search Polymarket for keyword '{keyword}': {e}")
                    continue
            
            # 去重
            seen = set()
            result = []
            for market_data in related_markets:
                market_id = market_data.get('market_id')
                if market_id and market_id not in seen:
                    seen.add(market_id)
                    # 构建正确的 Polymarket URL
                    # 优先使用已有的 polymarket_url，如果没有则根据 slug 或 market_id 构建
                    polymarket_url = market_data.get('polymarket_url')
                    if not polymarket_url:
                        slug = market_data.get('slug')
                        if slug and not str(slug).isdigit() and ('-' in str(slug) or any(c.isalpha() for c in str(slug))):
                            # 使用有效的 slug
                            polymarket_url = f"https://polymarket.com/event/{slug}"
                        else:
                            # 使用 markets 端点（更可靠）
                            polymarket_url = f"https://polymarket.com/markets/{market_id}"
                    
                    result.append({
                        "market_id": market_id,
                        "question": market_data.get('question', ''),
                        "current_probability": market_data.get('current_probability', 50.0),
                        "volume_24h": market_data.get('volume_24h', 0),
                        "liquidity": market_data.get('liquidity', 0),
                        "category": market_data.get('category', 'other'),
                        "polymarket_url": polymarket_url
                    })
            
            logger.info(f"Total {len(result)} unique Polymarket events found for {symbol}")
            return result
        except Exception as e:
            logger.debug(f"Failed to get polymarket events for {symbol}: {e}")
            return []
    
    def _extract_polymarket_keywords(self, symbol: str, market: str) -> List[str]:
        """
        提取用于搜索预测市场的关键词
        优化：只保留最重要的关键词，减少API调用次数
        """
        keywords = []
        
        # 基础符号（最重要）
        if '/' in symbol:
            base = symbol.split('/')[0]
            keywords.append(base)
        else:
            keywords.append(symbol)
        
        # 加密货币全名映射（只保留一个最重要的全名，避免重复）
        crypto_names = {
            'BTC': 'Bitcoin',
            'ETH': 'Ethereum',
            'SOL': 'Solana',
            'BNB': 'Binance',
            'XRP': 'Ripple',
            'ADA': 'Cardano',
            'DOGE': 'Dogecoin',
            'AVAX': 'Avalanche',
            'DOT': 'Polkadot',
            'MATIC': 'Polygon'
        }
        
        base_symbol = symbol.split('/')[0] if '/' in symbol else symbol
        if base_symbol in crypto_names:
            # 只添加一个全名，避免大小写重复
            keywords.append(crypto_names[base_symbol])
        
        # 优化：移除通用关键词（如 '$100k', 'ETF', 'approval'），这些会匹配到很多不相关的市场
        # 只保留与资产直接相关的关键词，最多2-3个
        
        # 去重并限制数量（最多3个关键词）
        unique_keywords = []
        seen = set()
        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower not in seen:
                seen.add(kw_lower)
                unique_keywords.append(kw)
                if len(unique_keywords) >= 3:  # 最多3个关键词
                    break
        
        logger.info(f"Extracted {len(unique_keywords)} Polymarket keywords (optimized from {len(keywords)}): {unique_keywords}")
        return unique_keywords


# 全局实例
_collector: Optional[MarketDataCollector] = None

def get_market_data_collector() -> MarketDataCollector:
    """获取市场数据采集器单例"""
    global _collector
    if _collector is None:
        _collector = MarketDataCollector()
    return _collector



def main() -> None:
    """本地调试入口：采集单个标的市场数据并输出 JSON。"""
    parser = argparse.ArgumentParser(description="Collect market data for local debugging")
    parser.add_argument("market", nargs="?", default="USStock", help="Market type, default: USStock")
    parser.add_argument("symbol", nargs="?", default="AAPL", help="Symbol, default: AAPL")
    parser.add_argument("--timeframe", default="1D", help="K-line timeframe, default: 1D")
    parser.add_argument("--timeout", type=int, default=30, help="Total timeout seconds")
    parser.add_argument("--no-macro", action="store_true", help="Disable macro data collection")
    parser.add_argument("--no-news", action="store_true", help="Disable news collection")
    parser.add_argument("--no-polymarket", action="store_true", help="Disable polymarket collection")
    args = parser.parse_args()

    logger.info(f"Local debug run: market={args.market}, symbol={args.symbol}, timeframe={args.timeframe}")

    collector = MarketDataCollector()
    result = collector.collect_all(
        market=args.market,
        symbol=args.symbol,
        timeframe=args.timeframe,
        include_macro=not args.no_macro,
        include_news=not args.no_news,
        include_polymarket=not args.no_polymarket,
        timeout=args.timeout,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()