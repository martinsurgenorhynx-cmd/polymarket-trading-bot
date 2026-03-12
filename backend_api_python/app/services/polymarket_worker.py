"""
Polymarket后台任务
每30分钟更新一次市场数据，并批量分析市场机会

可以通过以下方式运行：
1. 作为后台服务（在Flask应用中）
2. 本地独立运行：python -m app.services.polymarket_worker
"""
import os
import sys
import threading
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from app.utils.logger import get_logger
from app.utils.db import get_db_connection
from app.data_sources.polymarket import PolymarketDataSource
from app.services.polymarket_batch_analyzer import PolymarketBatchAnalyzer

logger = get_logger(__name__)


class PolymarketWorker:
    """Polymarket数据更新和分析后台任务"""
    
    def __init__(self, update_interval_minutes: int = 30, analysis_cache_minutes: int = 1440):  # 24小时缓存
        """
        初始化后台任务
        
        Args:
            update_interval_minutes: 市场数据更新间隔（分钟）
            analysis_cache_minutes: AI分析结果缓存时间（分钟）
        """
        self.update_interval_minutes = update_interval_minutes
        self.analysis_cache_minutes = analysis_cache_minutes
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self.polymarket_source = PolymarketDataSource()
        self.batch_analyzer = PolymarketBatchAnalyzer()
        self._last_update_ts = 0.0
        
    def start(self) -> bool:
        """启动后台任务"""
        with self._lock:
            if self._thread and self._thread.is_alive():
                return True
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run_loop, name="PolymarketWorker", daemon=True)
            self._thread.start()
            logger.info(f"PolymarketWorker started (update_interval={self.update_interval_minutes}min, cache={self.analysis_cache_minutes}min)")
            return True
    
    def stop(self, timeout_sec: float = 5.0) -> None:
        """停止后台任务"""
        with self._lock:
            if not self._thread or not self._thread.is_alive():
                return
            self._stop_event.set()
            self._thread.join(timeout=timeout_sec)
            if self._thread.is_alive():
                logger.warning("PolymarketWorker thread did not stop within timeout")
            else:
                logger.info("PolymarketWorker stopped")
    
    def _run_loop(self) -> None:
        """主循环"""
        logger.info("PolymarketWorker loop started")
        
        # 启动时立即执行一次
        self._update_markets_and_analyze()
        
        while not self._stop_event.is_set():
            try:
                # 等待指定时间间隔
                wait_seconds = self.update_interval_minutes * 60
                if self._stop_event.wait(wait_seconds):
                    break  # 如果收到停止信号，退出循环
                
                # 执行更新和分析
                self._update_markets_and_analyze()
                
            except Exception as e:
                logger.error(f"PolymarketWorker loop error: {e}", exc_info=True)
                # 出错后等待1分钟再重试
                self._stop_event.wait(60)
        
        logger.info("PolymarketWorker loop stopped")
    
    def _update_markets_and_analyze(
        self, 
        categories: List[str] = None, 
        limit: int = 50, 
        max_analyze: int = 30,
        return_stats: bool = False
    ) -> Optional[Dict]:
        """
        更新市场数据并分析（核心方法）
        
        Args:
            categories: 要分析的分类列表，None表示使用默认分类
            limit: 每个分类获取的市场数量
            max_analyze: 最多分析的市场数量
            return_stats: 是否返回统计信息
            
        Returns:
            如果return_stats=True，返回统计信息字典；否则返回None
        """
        try:
            logger.info(f"Starting Polymarket data update and analysis (categories={categories}, limit={limit}, max_analyze={max_analyze})...")
            start_time = time.time()
            
            # 默认分类
            if categories is None:
                categories = ["crypto","politics", "economics","sports", "tech", 
                             "finance", "geopolitics",  "entertainment",
                              "science"]
            
            # 统计信息
            stats = {
                "success": False,
                "total_markets": 0,
                "unique_markets": 0,
                "rule_filtered": 0,
                "analyzed": 0,
                "saved": 0,
                "elapsed_seconds": 0,
                "error": None
            }
            
            # 1. 更新市场数据
            all_markets = []
            for category in categories:
                try:
                    markets = self.polymarket_source.get_trending_markets(category, limit=limit)
                    all_markets.extend(markets)
                    logger.info(f"Fetched {len(markets)} markets from category: {category}")
                except Exception as e:
                    logger.warning(f"Failed to fetch markets for category {category}: {e}")
            
            stats["total_markets"] = len(all_markets)
            
            # 去重（按market_id）
            unique_markets = {}
            for market in all_markets:
                market_id = market.get('market_id')
                if market_id:
                    unique_markets[market_id] = market
            
            stats["unique_markets"] = len(unique_markets)
            logger.info(f"Total unique markets: {len(unique_markets)}")
            
            # 2. 批量分析市场
            markets_list = list(unique_markets.values())
            logger.info(f"Starting batch analysis for {len(markets_list)} markets...")
            
            # 规则筛选：先用规则筛选出最有价值的机会（不调用LLM）
            rule_based_opportunities = []
            for market in markets_list:
                prob = market.get('current_probability', 50.0)
                volume = market.get('volume_24h', 0)
                divergence = abs(prob - 50.0)
                
                # 规则筛选：高交易量 + 明显概率偏差 + 价格合理
                # 价格范围 10-90 对应 $0.10-$0.90，避免极端价格无法交易
                if volume > 5000 and divergence > 8 and 5 <= prob <= 95:
                    rule_based_opportunities.append(market)
            
            stats["rule_filtered"] = len(rule_based_opportunities)
            
            # 3. AI分析：只对规则筛选出的机会调用LLM
            if rule_based_opportunities:
                logger.info(f"Rule-based filtering: {len(rule_based_opportunities)} opportunities, analyzing top {max_analyze} with LLM")
                # 按交易量和概率偏差排序，取前N个
                rule_based_opportunities.sort(
                    key=lambda x: (x.get('volume_24h', 0) * abs(x.get('current_probability', 50) - 50)),
                    reverse=True
                )
                top_opportunities = rule_based_opportunities[:max_analyze]
                
                analyzed_markets = self.batch_analyzer.batch_analyze_markets(
                    top_opportunities,
                    max_opportunities=max_analyze
                )
                
                stats["analyzed"] = len(analyzed_markets)
            else:
                logger.info("No rule-based opportunities found, skipping LLM analysis")
                analyzed_markets = []
            
            # 4. 保存分析结果到数据库
            if analyzed_markets:
                self.batch_analyzer.save_batch_analysis(analyzed_markets)
                stats["saved"] = len(analyzed_markets)
                logger.info(f"Saved {len(analyzed_markets)} analysis results")
            
            stats["success"] = True
            stats["elapsed_seconds"] = time.time() - start_time
            
            logger.info(f"Polymarket update completed: {stats['unique_markets']} markets updated, {stats['analyzed']} opportunities identified in {stats['elapsed_seconds']:.1f}s")
            self._last_update_ts = time.time()
            
            return stats if return_stats else None
            
        except Exception as e:
            logger.error(f"Failed to update markets and analyze: {e}", exc_info=True)
            if return_stats:
                return {
                    "success": False,
                    "total_markets": 0,
                    "unique_markets": 0,
                    "rule_filtered": 0,
                    "analyzed": 0,
                    "saved": 0,
                    "elapsed_seconds": time.time() - start_time if 'start_time' in locals() else 0,
                    "error": str(e)
                }
            return None
    
    
    def _enrich_markets_with_trading_data(self, markets: List[Dict]) -> int:
        """
        增强市场数据，获取交易所需的信息
        使用 Gamma API 和 CLOB API 替代命令行查询
        
        Args:
            markets: 市场列表
            
        Returns:
            成功增强的市场数量
        """
        import requests
        
        enriched_count = 0
        
        # 初始化 session
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json'
        })
        
        gamma_api = "https://gamma-api.polymarket.com"
        clob_api = "https://clob.polymarket.com"
        
        for market in markets:
            try:
                market_id = market.get('market_id')
                question = market.get('question', '')
                
                if not market_id or not question:
                    continue
                
                # 方法1: 通过 Gamma API 搜索市场获取 condition_id
                try:
                    # 使用市场ID直接查询
                    search_url = f"{gamma_api}/markets"
                    params = {"id": market_id}
                    
                    response = session.get(search_url, params=params, timeout=10)
                    
                    if response.status_code != 200:
                        logger.debug(f"Failed to search market {market_id}: HTTP {response.status_code}")
                        continue
                    
                    search_results = response.json()
                    
                    # 找到匹配的市场
                    matched_market = None
                    if isinstance(search_results, list):
                        for m in search_results:
                            if m.get('id') == market_id:
                                matched_market = m
                                break
                    elif isinstance(search_results, dict):
                        if search_results.get('id') == market_id:
                            matched_market = search_results
                    
                    if not matched_market:
                        logger.debug(f"Market {market_id} not found in search results")
                        continue
                    
                    condition_id = matched_market.get('conditionId')
                    if not condition_id:
                        logger.debug(f"No condition_id for market {market_id}")
                        continue
                    
                except requests.RequestException as e:
                    logger.debug(f"Request error searching market {market_id}: {e}")
                    continue
                
                # 方法2: 通过 CLOB API 获取市场详情
                try:
                    market_url = f"{clob_api}/markets/{condition_id}"
                    
                    response = session.get(market_url, timeout=10)
                    
                    if response.status_code != 200:
                        logger.debug(f"Failed to get market details for {condition_id}: HTTP {response.status_code}")
                        continue
                    
                    market_info = response.json()
                    
                    # 提取交易数据
                    accepting_orders = market_info.get('accepting_orders', True)
                    tokens = market_info.get('tokens', [])
                    
                    if len(tokens) >= 2:
                        yes_token_id = tokens[0].get('token_id')
                        no_token_id = tokens[1].get('token_id')
                        
                        # 确保 token_id 是十六进制格式（0x开头）
                        # API 可能返回十进制或十六进制
                        if yes_token_id and not str(yes_token_id).startswith('0x'):
                            try:
                                # 如果是十进制数字，转换为十六进制
                                yes_token_id = hex(int(yes_token_id))
                            except (ValueError, TypeError):
                                pass
                        
                        if no_token_id and not str(no_token_id).startswith('0x'):
                            try:
                                # 如果是十进制数字，转换为十六进制
                                no_token_id = hex(int(no_token_id))
                            except (ValueError, TypeError):
                                pass
                        
                        # 更新市场数据
                        market['condition_id'] = condition_id
                        market['yes_token_id'] = yes_token_id
                        market['no_token_id'] = no_token_id
                        market['accepting_orders'] = accepting_orders
                        market['tokens_data'] = tokens
                        
                        enriched_count += 1
                        
                        logger.info(f"Enriched market {market_id}: condition_id={condition_id[:20]}..., yes_token={str(yes_token_id)[:20] if yes_token_id else 'None'}..., accepting_orders={accepting_orders}")
                    else:
                        logger.debug(f"Insufficient tokens for market {market_id}: {len(tokens)} tokens")
                    
                except requests.RequestException as e:
                    logger.debug(f"Request error getting market details for {condition_id}: {e}")
                    continue
                    
            except Exception as e:
                logger.debug(f"Failed to enrich market {market.get('market_id')}: {e}")
                continue
        
        return enriched_count
    
    def force_update(self) -> None:
        """强制立即更新（用于手动触发）"""
        logger.info("Force update triggered")
        self._update_markets_and_analyze()
    
    def run_once(self, categories: List[str] = None, limit: int = 50, max_analyze: int = 30) -> Dict:
        """
        单次执行更新和分析（不启动后台线程）
        
        Args:
            categories: 要分析的分类列表，None表示使用默认分类
            limit: 每个分类获取的市场数量
            max_analyze: 最多分析的市场数量
            
        Returns:
            执行结果字典，包含统计信息
        """
        logger.info(f"Running once: categories={categories}, limit={limit}, max_analyze={max_analyze}")
        
        # 调用核心方法并返回统计信息
        result = self._update_markets_and_analyze(
            categories=categories,
            limit=limit,
            max_analyze=max_analyze,
            return_stats=True
        )
        
        return result


# 全局单例
_polymarket_worker: Optional[PolymarketWorker] = None
_worker_lock = threading.Lock()


def get_polymarket_worker() -> PolymarketWorker:
    """获取PolymarketWorker单例"""
    global _polymarket_worker
    with _worker_lock:
        if _polymarket_worker is None:
            update_interval = int(os.getenv("POLYMARKET_UPDATE_INTERVAL_MIN", "30"))
            cache_minutes = int(os.getenv("POLYMARKET_ANALYSIS_CACHE_MIN", "30"))
            _polymarket_worker = PolymarketWorker(
                update_interval_minutes=update_interval,
                analysis_cache_minutes=cache_minutes
            )
        return _polymarket_worker


def main():
    """
    本地运行主函数
    
    使用方法：
    1. 单次运行（立即执行一次更新和分析）：
       python -m app.services.polymarket_worker
    
    2. 持续运行（每30分钟自动更新）：
       python -m app.services.polymarket_worker --daemon
    
    3. 自定义更新间隔（每10分钟）：
       python -m app.services.polymarket_worker --daemon --interval 10
    
    4. 仅更新市场数据（不分析）：
       python -m app.services.polymarket_worker --update-only
    
    5. 仅分析已有市场：
       python -m app.services.polymarket_worker --analyze-only
    """
    import argparse
    
    # 加载环境变量
    from dotenv import load_dotenv
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')
    load_dotenv(env_path)
    
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='Polymarket Worker - 市场数据更新和AI分析')
    parser.add_argument('--daemon', action='store_true', help='持续运行模式（后台服务）')
    parser.add_argument('--interval', type=int, default=30, help='更新间隔（分钟），默认30分钟')
    parser.add_argument('--update-only', action='store_true', help='仅更新市场数据，不进行AI分析')
    parser.add_argument('--analyze-only', action='store_true', help='仅分析已有市场，不更新数据')
    parser.add_argument('--categories', type=str, help='指定分析的分类，用逗号分隔（如：crypto,politics）')
    parser.add_argument('--limit', type=int, default=50, help='每个分类获取的市场数量，默认50')
    parser.add_argument('--max-analyze', type=int, default=30, help='最多分析的市场数量，默认30')
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("Polymarket Worker - 市场数据更新和AI分析")
    print("=" * 80)
    print(f"运行模式: {'持续运行' if args.daemon else '单次运行'}")
    print(f"更新间隔: {args.interval} 分钟")
    print(f"操作模式: ", end="")
    if args.update_only:
        print("仅更新数据")
    elif args.analyze_only:
        print("仅分析市场")
    else:
        print("更新+分析")
    print("=" * 80)
    
    try:
        if args.daemon:
            # 持续运行模式
            print(f"\n启动后台服务（每 {args.interval} 分钟更新一次）...")
            print("按 Ctrl+C 停止服务\n")
            
            worker = PolymarketWorker(
                update_interval_minutes=args.interval,
                analysis_cache_minutes=1440
            )
            worker.start()
            
            # 保持运行
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\n\n收到停止信号，正在关闭...")
                worker.stop()
                print("服务已停止")
        else:
            # 单次运行模式
            print("\n开始执行...")
            
            # 确定要分析的分类
            if args.categories:
                categories = [c.strip() for c in args.categories.split(',')]
            else:
                categories = None  # 使用默认分类
            
            if args.analyze_only:
                print("⚠️ 暂不支持从数据库加载，请使用完整模式")
                return
            
            # 创建worker实例并执行
            worker = PolymarketWorker(
                update_interval_minutes=args.interval,
                analysis_cache_minutes=1440
            )
            
            # 调用核心方法
            result = worker._update_markets_and_analyze(
                categories=categories,
                limit=args.limit,
                max_analyze=args.max_analyze,
                return_stats=True
            )
            
            # 显示结果
            print("\n" + "=" * 80)
            print("执行结果")
            print("=" * 80)
            
            if result['success']:
                print(f"✓ 执行成功")
                print(f"  总市场数: {result['total_markets']}")
                print(f"  唯一市场: {result['unique_markets']}")
                print(f"  规则筛选: {result['rule_filtered']} 个高价值机会")
                print(f"  AI分析: {result['analyzed']} 个市场")
                print(f"  已保存: {result['saved']} 个分析结果")
                print(f"  耗时: {result['elapsed_seconds']:.1f} 秒")
            else:
                print(f"✗ 执行失败: {result.get('error', 'Unknown error')}")
            
            print("=" * 80)
            
    except KeyboardInterrupt:
        print("\n\n用户中断")
    except Exception as e:
        print(f"\n✗ 执行失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
