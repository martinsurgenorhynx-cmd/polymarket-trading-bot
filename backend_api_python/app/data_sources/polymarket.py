"""
Polymarket预测市场数据源
从Polymarket获取预测市场数据
"""
import time
import requests
import json
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta

from app.utils.logger import get_logger
from app.utils.db import get_db_connection

logger = get_logger(__name__)


class PolymarketDataSource:
    """Polymarket预测市场数据源"""
    
    def __init__(self):
        # Polymarket官方API端点（根据官方文档）
        # Gamma API: 市场、事件、标签、搜索等（完全公开，无需认证）
        self.gamma_api = "https://gamma-api.polymarket.com"
        # Data API: 用户持仓、交易、活动等（完全公开，无需认证）
        self.data_api = "https://data-api.polymarket.com"
        # CLOB API: 订单簿、价格、交易操作（公开端点无需认证）
        self.clob_api = "https://clob.polymarket.com"
        self.cache_ttl = 300  # 5分钟缓存
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json'
        })
        
    def get_trending_markets(self, category: str = None, limit: int = 50) -> List[Dict]:
        """
        获取热门预测市场
        
        Args:
            category: 类别筛选 (crypto, politics, economics, sports, all)
            limit: 返回数量限制
            
        Returns:
            预测市场列表
        """
        try:
            # 先从数据库缓存读取
            cached = self._get_cached_markets(category, limit)
            if cached:
                return cached
            
            # 从真实API获取 - 获取多个分类的数据以确保多样性
            all_markets = []
            
            if category and category != "all":
                # 如果指定了类别，只获取该类别的数据
                markets = self._fetch_markets_from_api(category, limit * 2)
                all_markets.extend(markets)
            else:
                # 如果没有指定类别或指定了"all"，获取多个分类的数据
                categories_to_fetch = ["crypto", "politics", "economics", "sports"]
                for cat in categories_to_fetch:
                    markets = self._fetch_markets_from_api(cat, limit // len(categories_to_fetch) + 10)
                    all_markets.extend(markets)
            
            # 去重（按market_id）
            seen = set()
            unique_markets = []
            for market in all_markets:
                market_id = market.get("market_id")
                if market_id and market_id not in seen:
                    seen.add(market_id)
                    unique_markets.append(market)
            
            # 按交易量排序
            unique_markets.sort(key=lambda x: x.get('volume_24h', 0), reverse=True)
            
            # 保存到数据库缓存
            if unique_markets:
                self._save_markets_to_db(unique_markets)
                return unique_markets[:limit]
            
            # 如果API失败，返回空列表（不再使用示例数据）
            logger.warning("Polymarket API unavailable, returning empty list")
            return []
            
        except Exception as e:
            logger.error(f"Failed to get trending markets: {e}", exc_info=True)
            return []
    
    def get_market_details(self, market_id: str) -> Optional[Dict]:
        """获取单个市场详情"""
        try:
            # 确保market_id是字符串
            market_id = str(market_id).strip()
            if not market_id:
                logger.warning("Empty market_id provided")
                return None
            
            # 先从数据库读取
            try:
                with get_db_connection() as db:
                    cur = db.cursor()
                    cur.execute("""
                        SELECT market_id, question, category, current_probability, 
                               volume_24h, liquidity, end_date_iso, status, outcome_tokens
                        FROM qd_polymarket_markets
                        WHERE market_id = %s
                    """, (market_id,))
                    row = cur.fetchone()
                    cur.close()
                    
                    if row:
                        # RealDictCursor返回字典，使用键访问
                        db_market_id = str(row.get('market_id') or market_id)
                        # 解析outcome_tokens（可能是JSON字符串）
                        outcome_tokens = {}
                        outcome_tokens_raw = row.get('outcome_tokens')
                        if outcome_tokens_raw:
                            try:
                                if isinstance(outcome_tokens_raw, str):
                                    outcome_tokens = json.loads(outcome_tokens_raw)
                                else:
                                    outcome_tokens = outcome_tokens_raw if isinstance(outcome_tokens_raw, dict) else {}
                            except:
                                outcome_tokens = {}
                        
                        return {
                            "market_id": db_market_id,
                            "question": row.get('question') or '',
                            "category": row.get('category') or 'other',
                            "current_probability": float(row.get('current_probability') or 0),
                            "volume_24h": float(row.get('volume_24h') or 0),
                            "liquidity": float(row.get('liquidity') or 0),
                            "end_date_iso": row.get('end_date_iso'),
                            "status": row.get('status') or 'active',
                            "outcome_tokens": outcome_tokens,
                            "polymarket_url": self._build_polymarket_url(row.get('slug'), db_market_id),
                            "slug": row.get('slug') if row.get('slug') and not str(row.get('slug', '')).isdigit() else None
                        }
            except Exception as db_error:
                logger.warning(f"Database query failed for market {market_id}: {db_error}")
                # 继续尝试从API获取
            
            # 如果数据库没有，从API获取
            logger.info(f"Market {market_id} not in database, fetching from API")
            market = self._fetch_market_from_api(market_id)
            if market:
                try:
                    self._save_markets_to_db([market])
                except Exception as save_error:
                    logger.warning(f"Failed to save market to DB: {save_error}")
                return market
            
            logger.warning(f"Market {market_id} not found in API")
            return None
            
        except Exception as e:
            logger.error(f"Failed to get market details for {market_id}: {e}", exc_info=True)
            return None
    
    def get_market_history(self, market_id: str, days: int = 30) -> List[Dict]:
        """获取市场历史价格数据"""
        # 这里需要实现历史数据获取逻辑
        # 暂时返回空列表
        return []
    
    def search_markets(self, keyword: str, limit: int = 20, use_cache: bool = True) -> List[Dict]:
        """
        搜索相关预测市场
        优先从API获取实时数据，数据库仅作为可选缓存
        
        Args:
            keyword: 搜索关键词
            limit: 返回结果数量限制
            use_cache: 是否使用数据库缓存（AI分析时应设为False以获取最新数据）
        """
        try:
            logger.info(f"Searching Polymarket markets for keyword: '{keyword}' (limit={limit}, use_cache={use_cache})")
            
            # 如果允许使用缓存，先尝试从数据库搜索
            if use_cache:
                with get_db_connection() as db:
                    cur = db.cursor()
                    # 改进搜索：同时搜索question和slug字段，也支持market_id精确匹配
                    keyword_lower = keyword.lower()
                    is_numeric = keyword_lower.isdigit()
                    has_hyphens = '-' in keyword_lower
                    
                    if is_numeric:
                        # 如果是纯数字，可能是market_id，精确匹配
                        cur.execute("""
                            SELECT market_id, question, category, current_probability, 
                                   volume_24h, liquidity, end_date_iso, status, slug
                            FROM qd_polymarket_markets
                            WHERE market_id = %s AND status = 'active'
                            ORDER BY volume_24h DESC
                            LIMIT %s
                        """, (keyword, limit))
                    elif has_hyphens:
                        # 如果包含连字符，可能是slug，优先匹配slug
                        cur.execute("""
                            SELECT market_id, question, category, current_probability, 
                                   volume_24h, liquidity, end_date_iso, status, slug
                            FROM qd_polymarket_markets
                            WHERE (slug ILIKE %s OR question ILIKE %s) AND status = 'active'
                            ORDER BY 
                                CASE WHEN slug ILIKE %s THEN 1 ELSE 2 END,
                                volume_24h DESC
                            LIMIT %s
                        """, (f"%{keyword}%", f"%{keyword}%", f"%{keyword}%", limit))
                    else:
                        # 普通文本搜索
                        cur.execute("""
                            SELECT market_id, question, category, current_probability, 
                                   volume_24h, liquidity, end_date_iso, status, slug
                            FROM qd_polymarket_markets
                            WHERE (question ILIKE %s OR slug ILIKE %s) AND status = 'active'
                            ORDER BY volume_24h DESC
                            LIMIT %s
                        """, (f"%{keyword}%", f"%{keyword}%", limit))
                    
                    rows = cur.fetchall()
                    cur.close()
                    
                    if rows:
                        logger.info(f"Found {len(rows)} markets in database for keyword '{keyword}'")
                        return [{
                            "market_id": str(row.get('market_id') or ''),
                            "question": row.get('question') or '',
                            "category": row.get('category') or 'other',
                            "current_probability": float(row.get('current_probability') or 0),
                            "volume_24h": float(row.get('volume_24h') or 0),
                            "liquidity": float(row.get('liquidity') or 0),
                            "end_date_iso": row.get('end_date_iso'),
                            "status": row.get('status') or 'active',
                            "polymarket_url": self._build_polymarket_url(row.get('slug'), row.get('market_id') or ''),
                            "slug": row.get('slug') if row.get('slug') and not str(row.get('slug', '')).isdigit() else None
                        } for row in rows]
            
            # 直接从Gamma API获取并过滤（AI分析时使用）
            logger.info(f"Fetching from API for keyword '{keyword}' (use_cache={use_cache})...")
            
            # 优化：如果关键词看起来像slug，先尝试直接查询（避免全量获取）
            import re
            keyword_lower = keyword.lower().strip()
            is_slug_like = '-' in keyword_lower and not keyword_lower.isdigit()
            
            if is_slug_like:
                # 尝试直接通过slug查询（最高效，根据Polymarket API文档）
                direct_market = self._fetch_market_by_slug(keyword_lower)
                if direct_market:
                    logger.info(f"Found market directly by slug (no need to fetch all markets): {keyword_lower}")
                    return [direct_market]
            
            # 如果直接查询失败，获取更多数据以便有足够的选择空间
            # 进行多次请求以获取更多市场（每次最多100个事件，但每个事件可能包含多个市场）
            all_markets = []
            max_requests = 3  # 最多请求3次，获取300个事件（约4500个市场）
            for page in range(max_requests):
                page_markets = self._fetch_from_gamma_api(category=None, limit=100)
                if not page_markets:
                    break
                all_markets.extend(page_markets)
                # 如果已经获取了足够多的市场，可以提前停止
                if len(all_markets) >= 3000:  # 最多获取3000个市场
                    break
                logger.info(f"Fetched page {page + 1}/{max_requests}, total markets: {len(all_markets)}")
                # 短暂延迟，避免API限流
                if page < max_requests - 1:
                    time.sleep(0.5)
            logger.info(f"Fetched {len(all_markets)} markets from API, filtering for keyword '{keyword}'...")
            
            # 按关键词过滤（支持多个关键词匹配）
            # 如果关键词看起来像slug（包含连字符），也尝试匹配slug
            keyword_is_slug = '-' in keyword_lower
            # 提取关键词（去除常见停用词和标点）
            # 提取关键词：去除标点，保留字母数字和连字符
            keyword_words = re.findall(r'\b\w+\b', keyword_lower)
            # 过滤掉太短的词（少于3个字符）和常见停用词
            stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'will', 'would', 'should', 'could', 'may', 'might', 'can', 'must'}
            keyword_words = [w for w in keyword_words if len(w) >= 3 and w not in stop_words]
            
            # 如果没有提取到关键词，使用原始关键词
            if not keyword_words:
                keyword_words = [keyword_lower]
            
            logger.info(f"Extracted keywords: {keyword_words} from '{keyword}'")
            
            filtered = []
            scored_markets = []  # 用于存储带评分的结果
            top_candidates = []  # 用于存储接近匹配的候选（用于调试）
            
            for market in all_markets:
                question = market.get("question", "").lower()
                slug = (market.get("slug") or "").lower()
                market_id = str(market.get("market_id") or "")
                
                score = 0
                match_reason = ""
                
                # 1. 完全匹配（最高优先级，分数100）
                if keyword_lower in question:
                    score = 100
                    match_reason = "exact_match_question"
                elif keyword_lower == slug:
                    score = 100
                    match_reason = "exact_match_slug"
                
                # 2. 如果关键词看起来像slug，检查slug字段
                if score < 100 and keyword_is_slug:
                    if keyword_lower == slug:
                        score = 100
                        match_reason = "exact_slug_match"
                    elif keyword_lower in slug or slug in keyword_lower:
                        score = 90
                        match_reason = "partial_slug_match"
                
                # 3. 如果关键词是纯数字，检查market_id
                if score < 90 and keyword_lower.isdigit():
                    if keyword_lower == market_id:
                        score = 100
                        match_reason = "market_id_match"
                
                # 4. 关键词匹配：检查所有关键词是否都在问题中
                if score < 90 and keyword_words:
                    # 计算匹配的关键词数量
                    matched_words = sum(1 for word in keyword_words if word in question or word in slug)
                    if matched_words > 0:
                        # 匹配率
                        match_ratio = matched_words / len(keyword_words)
                        # 降低阈值：从60%降到40%，提高匹配率
                        if match_ratio >= 0.4:
                            score = int(60 + match_ratio * 30)  # 60-90分
                            match_reason = f"keyword_match_{matched_words}/{len(keyword_words)}"
                        else:
                            # 记录接近匹配的候选（用于调试）
                            if matched_words >= 1 and len(top_candidates) < 5:
                                top_candidates.append((match_ratio, market.get('question', '')[:80], matched_words, len(keyword_words)))
                
                # 5. 部分匹配：检查关键词的主要部分是否在问题中
                if score < 60 and keyword_words:
                    # 如果关键词包含多个词，尝试匹配主要部分
                    if len(keyword_words) > 1:
                        # 取前3个最重要的词（通常是名词）
                        important_words = keyword_words[:3]
                        matched_important = sum(1 for word in important_words if word in question or word in slug)
                        # 降低要求：至少匹配1个重要词即可
                        if matched_important >= 1:
                            score = 50
                            match_reason = f"important_words_match_{matched_important}/{len(important_words)}"
                
                if score >= 50:  # 降低最低分数要求从60到50
                    scored_markets.append((score, market, match_reason))
                    logger.debug(f"Matched (score={score}, reason={match_reason}): {market.get('question', '')[:60]}")
            
            # 按分数排序，取前limit个
            scored_markets.sort(key=lambda x: x[0], reverse=True)
            filtered = [market for score, market, reason in scored_markets[:limit]]
            
            # 输出调试信息
            if len(scored_markets) == 0 and top_candidates:
                logger.warning(f"No exact matches found. Top candidates (partial matches):")
                for ratio, question, matched, total in top_candidates:
                    logger.warning(f"  - {question} (matched {matched}/{total} keywords, ratio={ratio:.2f})")
            
            logger.info(f"Filtered {len(filtered)} markets matching keyword '{keyword}' from API (from {len(all_markets)} total markets, {len(scored_markets)} scored matches)")
            if len(scored_markets) > 0:
                logger.info(f"Top match: {filtered[0].get('question', '')[:80]} (score={scored_markets[0][0]})")
            return filtered
            
        except Exception as e:
            logger.error(f"Failed to search markets: {e}", exc_info=True)
            return []
    
    def _get_cached_markets(self, category: str = None, limit: int = 50) -> Optional[List[Dict]]:
        """从数据库缓存读取市场数据"""
        try:
            with get_db_connection() as db:
                cur = db.cursor()
                
                # 检查缓存是否新鲜（5分钟内）
                cutoff_time = datetime.now() - timedelta(seconds=self.cache_ttl)
                
                query = """
                    SELECT market_id, question, category, current_probability, 
                           volume_24h, liquidity, end_date_iso, status, outcome_tokens
                    FROM qd_polymarket_markets
                    WHERE status = 'active' AND updated_at > %s
                """
                params = [cutoff_time]
                
                if category:
                    query += " AND category = %s"
                    params.append(category)
                
                query += " ORDER BY volume_24h DESC LIMIT %s"
                params.append(limit)
                
                cur.execute(query, params)
                rows = cur.fetchall()
                cur.close()
                
                if rows:
                    result = []
                    for row in rows:
                        market_id = str(row.get('market_id') or '')
                        slug = row.get('slug')
                        # 确保使用正确的URL构建方法
                        polymarket_url = self._build_polymarket_url(slug, market_id)
                        result.append({
                            "market_id": market_id,
                            "question": row.get('question') or '',
                            "category": row.get('category') or 'other',
                            "current_probability": float(row.get('current_probability') or 0),
                            "volume_24h": float(row.get('volume_24h') or 0),
                            "liquidity": float(row.get('liquidity') or 0),
                            "end_date_iso": row.get('end_date_iso'),
                            "status": row.get('status') or 'active',
                            "outcome_tokens": row.get('outcome_tokens') if row.get('outcome_tokens') else {},
                            "polymarket_url": polymarket_url,
                            "slug": slug if slug and not str(slug).isdigit() else None
                        })
                    return result
            
            return None
        except Exception as e:
            logger.debug(f"Failed to get cached markets: {e}")
            return None
    
    def _fetch_markets_from_api(self, category: str = None, limit: int = 50) -> List[Dict]:
        """
        从Polymarket Gamma API获取市场数据
        使用官方推荐的 /events 端点
        """
        try:
            # 使用Gamma API的/events端点（官方推荐方式）
            markets = self._fetch_from_gamma_api(category, limit)
            if markets:
                # 按volume_24h降序排序（因为API不支持order参数，需要本地排序）
                markets.sort(key=lambda x: x.get('volume_24h', 0), reverse=True)
                return markets[:limit]  # 返回排序后的前limit个
            
            # 如果API返回空列表，记录警告（可能是API暂时不可用、网络问题或限流）
            logger.warning(f"Gamma API failed to fetch markets for category '{category}' (可能原因: API暂时不可用、网络问题、限流或返回空数据)")
            return []
            
        except Exception as e:
            logger.error(f"Failed to fetch markets from API: {e}", exc_info=True)
            return []
    
    def _fetch_from_gamma_api(self, category: str = None, limit: int = 50) -> List[Dict]:
        """
        使用Gamma API的/events端点获取市场数据（官方推荐方式）
        参考: https://docs.polymarket.com/market-data/fetching-markets
        """
        try:
            # 使用/events端点获取活跃市场（推荐方式）
            # 根据官方文档：https://docs.polymarket.com/market-data/fetching-markets
            # order参数支持的值：volume_24hr, volume, liquidity, competitive, start_date, end_date
            # 但某些端点可能不支持，先尝试不带order参数
            url = f"{self.gamma_api}/events"
            params = {
                "active": "true",
                "closed": "false",
                "limit": min(limit * 2, 500)  # 获取更多数据以便排序和筛选
            }
            
            # 尝试添加排序参数（如果API支持）
            # 根据文档，可能的排序字段：volume_24hr, volume, liquidity等
            # 如果API不支持，会在422错误后移除
            
            # 如果指定了类别，需要通过tag_id筛选
            # 注意：需要先获取tag_id，这里先用关键词推断
            if category:
                # 可以尝试通过搜索或标签来筛选
                # 暂时先获取所有，然后在解析时过滤
                pass
            
            logger.info(f"Fetching from Gamma API: {url} with params: {params}")
            response = self.session.get(url, params=params, timeout=15)
            
            logger.info(f"Gamma API response status: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    logger.debug(f"Gamma API returned data type: {type(data)}, keys: {list(data.keys()) if isinstance(data, dict) else 'list'}")
                    
                    # Gamma API返回的可能是列表或包含data字段的对象
                    if isinstance(data, list):
                        logger.info(f"Gamma API returned list with {len(data)} items")
                        markets = self._parse_gamma_events(data, category)
                        logger.info(f"Parsed {len(markets)} markets from Gamma API")
                        return markets
                    elif isinstance(data, dict):
                        # 可能是 {"data": [...]} 格式
                        if "data" in data:
                            events_list = data["data"]
                            logger.info(f"Gamma API returned dict with 'data' field containing {len(events_list) if isinstance(events_list, list) else 'non-list'} items")
                            markets = self._parse_gamma_events(events_list, category)
                            logger.info(f"Parsed {len(markets)} markets from Gamma API")
                            return markets
                        # 或者直接是事件对象
                        elif "id" in data or "slug" in data:
                            logger.info("Gamma API returned single event object")
                            markets = self._parse_gamma_events([data], category)
                            logger.info(f"Parsed {len(markets)} markets from Gamma API")
                            return markets
                        else:
                            logger.warning(f"Gamma API returned dict with unexpected keys: {list(data.keys())}")
                            logger.debug(f"Full response: {str(data)[:500]}")
                    
                    logger.warning(f"Gamma API returned unexpected format: {type(data)}")
                    return []
                except json.JSONDecodeError as je:
                    logger.error(f"Gamma API returned invalid JSON: {je}")
                    logger.error(f"Response text (first 500 chars): {response.text[:500]}")
                    return []
            
            # 非200状态码
            status_code = response.status_code
            if status_code == 429:
                logger.warning(f"Gamma API rate limited (429). 建议: 稍后重试或减少请求频率")
            elif status_code == 503:
                logger.warning(f"Gamma API service unavailable (503). Polymarket API可能正在维护")
            elif status_code >= 500:
                logger.warning(f"Gamma API server error ({status_code}). Polymarket服务器可能暂时不可用")
            else:
                logger.warning(f"Gamma API returned status {status_code}")
            logger.debug(f"Response headers: {dict(response.headers)}")
            logger.debug(f"Response text (first 500 chars): {response.text[:500]}")
            return []
            
        except requests.exceptions.Timeout:
            logger.warning("Gamma API request timeout after 15 seconds (可能原因: 网络延迟或API响应慢)")
            return []
        except requests.exceptions.ConnectionError as ce:
            logger.warning(f"Gamma API connection error: {ce} (可能原因: 网络连接问题或Polymarket API不可达)")
            return []
        except Exception as e:
            logger.warning(f"Gamma API failed: {e} (可能原因: API格式变更、网络问题或服务异常)")
            return []
    
    def _parse_gamma_events(self, events_data: List[Dict], category_filter: str = None) -> List[Dict]:
        """
        解析Gamma API返回的事件数据
        Gamma API的/events端点返回事件对象，每个事件包含关联的市场数据
        
        根据官方文档，事件对象结构：
        - event对象包含markets数组
        - 每个market包含clobTokenIds、outcomePrices等字段
        """
        parsed = []
        if not events_data:
            logger.warning("_parse_gamma_events received empty events_data")
            return parsed
            
        logger.info(f"Parsing {len(events_data)} events from Gamma API")
        
        # 记录第一个事件的键，用于调试
        if events_data:
            first_event_keys = list(events_data[0].keys())[:10]
            logger.info(f"First event keys: {first_event_keys}")
            logger.debug(f"First event sample: {str(events_data[0])[:500]}")
        
        for idx, event in enumerate(events_data):
            try:
                # Gamma API的事件对象结构
                # 事件可能有多个市场（markets字段），或者直接包含市场信息
                markets = event.get("markets", [])
                
                # 如果事件没有markets字段，可能事件本身就是市场数据
                if not markets:
                    # 检查是否直接是市场对象（有question或title字段）
                    if "question" in event or "title" in event or "slug" in event:
                        markets = [event]
                    else:
                        if idx < 3:  # 只记录前3个的详细信息
                            logger.debug(f"Event {idx} has no markets and doesn't look like a market. Keys: {list(event.keys())[:10]}")
                        continue
                
                if idx < 3:  # 只记录前3个的详细信息
                    logger.debug(f"Processing event {idx} with {len(markets)} markets")
                
                for market_idx, market in enumerate(markets):
                    # 提取市场基本信息
                    market_id = market.get("id") or market.get("slug") or event.get("id") or event.get("slug", "")
                    question = market.get("question") or event.get("question") or market.get("title") or event.get("title", "")
                    
                    if idx < 3 and market_idx < 2:  # 记录前几个市场的详细信息
                        logger.info(f"Event {idx}, Market {market_idx}: id={market_id}, question={question[:50] if question else 'None'}, event_slug={event.get('slug')}, market_slug={market.get('slug')}, keys={list(market.keys())[:10]}")
                    
                    if not question:
                        if idx < 3:
                            logger.warning(f"Event {idx}, Market {market_idx}: No question found, skipping. Market keys: {list(market.keys())[:10]}")
                        continue
                    
                    # 推断类别
                    inferred_category = self._infer_category(question)
                    
                    # 如果指定了类别筛选，进行过滤
                    if category_filter and inferred_category != category_filter:
                        continue
                    
                    # 提取 condition_id（用于跟单系统关联和价格获取）
                    condition_id = market.get("conditionId") or event.get("conditionId")
                    
                    # 获取概率和outcome数据
                    current_probability = 50.0
                    outcome_tokens = {}
                    
                    # 方法1: 从CLOB API获取实时价格（最准确）
                    try:
                        if condition_id:
                            prices = self._get_market_prices_from_clob(condition_id)
                            if prices:
                                yes_price = prices.get("YES", 0)
                                no_price = prices.get("NO", 0)
                                if yes_price > 0:
                                    current_probability = yes_price * 100 if yes_price <= 1 else yes_price
                                    outcome_tokens["YES"] = {"price": yes_price if yes_price <= 1 else yes_price / 100, "volume": 0}
                                if no_price > 0:
                                    outcome_tokens["NO"] = {"price": no_price if no_price <= 1 else no_price / 100, "volume": 0}
                    except Exception as e:
                        logger.debug(f"Failed to get prices from CLOB API: {e}")
                    
                    # 方法2: 处理outcomePrices字段（可能是JSON字符串）
                    if current_probability == 50.0:
                        outcome_prices_str = market.get("outcomePrices") or event.get("outcomePrices")
                        if outcome_prices_str:
                            try:
                                if isinstance(outcome_prices_str, str):
                                    outcome_prices = json.loads(outcome_prices_str)
                                else:
                                    outcome_prices = outcome_prices_str
                                
                                # outcomePrices通常是["0.65", "0.35"]格式，对应YES和NO
                                if isinstance(outcome_prices, list) and len(outcome_prices) >= 2:
                                    yes_price = float(outcome_prices[0]) if outcome_prices[0] else 0
                                    no_price = float(outcome_prices[1]) if outcome_prices[1] else 0
                                    current_probability = yes_price * 100 if yes_price <= 1 else yes_price
                                    outcome_tokens["YES"] = {"price": yes_price if yes_price <= 1 else yes_price / 100, "volume": 0}
                                    outcome_tokens["NO"] = {"price": no_price if no_price <= 1 else no_price / 100, "volume": 0}
                            except Exception as e:
                                logger.debug(f"Failed to parse outcomePrices: {e}")
                    
                    # 从market或event中获取outcomes
                    # outcomes可能是对象数组、字符串数组，或者需要从其他字段解析
                    outcomes = market.get("outcomes") or market.get("tokens") or event.get("outcomes") or []
                    
                    # 处理outcomes数组（可能是对象或字符串）
                    for outcome in outcomes:
                        try:
                            # 如果outcome是字符串，跳过或尝试解析
                            if isinstance(outcome, str):
                                # 可能是简单的字符串标识，如"YES"或"NO"
                                outcome_upper = outcome.upper()
                                if "YES" in outcome_upper:
                                    if "YES" not in outcome_tokens:
                                        outcome_tokens["YES"] = {"price": 0.5, "volume": 0}
                                elif "NO" in outcome_upper:
                                    if "NO" not in outcome_tokens:
                                        outcome_tokens["NO"] = {"price": 0.5, "volume": 0}
                                continue
                            
                            # outcome是对象
                            if not isinstance(outcome, dict):
                                continue
                                
                            title = str(outcome.get("title") or outcome.get("name", "")).upper()
                            # 获取价格（可能是price、probability或currentPrice）
                            price = float(outcome.get("price") or outcome.get("probability") or outcome.get("currentPrice") or 0)
                            
                            if "YES" in title or title == "YES" or outcome.get("outcome") == "Yes":
                                current_probability = price * 100 if price <= 1 else price
                                outcome_tokens["YES"] = {
                                    "price": price if price <= 1 else price / 100,
                                    "volume": float(outcome.get("volume", outcome.get("volume24hr", 0)) or 0)
                                }
                            elif "NO" in title or title == "NO" or outcome.get("outcome") == "No":
                                outcome_tokens["NO"] = {
                                    "price": price if price <= 1 else price / 100,
                                    "volume": float(outcome.get("volume", outcome.get("volume24hr", 0)) or 0)
                                }
                        except Exception as e:
                            logger.debug(f"Failed to parse outcome: {e}")
                            continue
                    
                    # 如果没有找到outcomes，尝试从其他字段获取概率
                    if current_probability == 50.0:
                        # 尝试从market的probability字段获取
                        prob = market.get("probability") or market.get("yesProbability") or event.get("probability")
                        if prob:
                            current_probability = float(prob) * 100 if float(prob) <= 1 else float(prob)
                    
                    # 获取交易量和流动性
                    volume_24h = float(
                        market.get("volume_24hr") or 
                        market.get("volume24hr") or 
                        market.get("volume_24h") or 
                        event.get("volume_24hr") or 
                        event.get("volume24hr") or 
                        0
                    )
                    
                    liquidity = float(
                        market.get("liquidity") or 
                        market.get("totalLiquidity") or 
                        event.get("liquidity") or 
                        0
                    )
                    
                    # 解析结束日期
                    end_date_iso = None
                    end_date = market.get("endDate") or market.get("end_date") or event.get("endDate") or event.get("end_date")
                    if end_date:
                        try:
                            if isinstance(end_date, (int, float)):
                                end_date_iso = datetime.fromtimestamp(end_date).isoformat() + "Z"
                            elif isinstance(end_date, str):
                                # 尝试解析ISO格式字符串
                                end_date_iso = end_date
                        except:
                            pass
                    
                    # 获取slug用于构建URL
                    # 根据Polymarket API文档：slug应该直接从API返回的数据中获取
                    # URL格式: https://polymarket.com/event/{slug}
                    # slug是字符串标识符，不是数字ID
                    slug = None
                    
                    # 优先从event获取slug（因为event包含markets）
                    if event.get("slug"):
                        slug_str = str(event.get("slug", "")).strip()
                        # 如果slug不是纯数字，且包含字母或连字符，则是有效slug
                        if slug_str and not slug_str.isdigit() and ('-' in slug_str or any(c.isalpha() for c in slug_str)):
                            slug = slug_str
                    
                    # 如果event没有有效slug，尝试从market获取
                    if not slug and market.get("slug"):
                        slug_str = str(market.get("slug", "")).strip()
                        if slug_str and not slug_str.isdigit() and ('-' in slug_str or any(c.isalpha() for c in slug_str)):
                            slug = slug_str
                    
                    # 如果仍然没有有效slug，尝试通过API查询获取
                    if not slug and market_id:
                        try:
                            # 使用markets端点通过ID查询，获取完整的slug信息
                            detail_market = self._fetch_market_detail_by_id(market_id)
                            if detail_market and detail_market.get("slug"):
                                slug_str = str(detail_market.get("slug", "")).strip()
                                if slug_str and not slug_str.isdigit() and ('-' in slug_str or any(c.isalpha() for c in slug_str)):
                                    slug = slug_str
                        except Exception as e:
                            logger.debug(f"Failed to fetch slug for market {market_id}: {e}")
                    
                    # 构建URL（使用统一的辅助方法）
                    polymarket_url = self._build_polymarket_url(slug, market_id)
                    if not slug:
                        logger.warning(f"Market {market_id} has no valid slug, using markets endpoint as fallback")
                    
                    market_data = {
                        "market_id": market_id,
                        "question": question,
                        "category": inferred_category,
                        "current_probability": round(current_probability, 2),
                        "volume_24h": volume_24h,
                        "liquidity": liquidity,
                        "end_date_iso": end_date_iso,
                        "status": "active" if market.get("active", event.get("active", True)) else "closed",
                        "outcome_tokens": outcome_tokens,
                        "polymarket_url": polymarket_url,
                        "slug": slug if slug else None,  # 保存slug（如果不是数字）
                        "condition_id": condition_id  # 保存 condition_id（用于跟单系统）
                    }
                    
                    parsed.append(market_data)
                    
                    if idx < 3 and market_idx < 2:  # 记录成功解析的市场
                        logger.info(f"Successfully parsed market: {question[:50]}, prob={current_probability:.1f}%, volume={volume_24h}")
                    
            except Exception as e:
                logger.warning(f"Failed to parse event {idx} (id={event.get('id', event.get('slug', 'unknown'))}): {e}", exc_info=True)
                continue
        
        logger.info(f"Successfully parsed {len(parsed)} markets from {len(events_data)} events")
        return parsed
    
    def _parse_rest_markets(self, markets_data: List[Dict]) -> List[Dict]:
        """解析REST API返回的市场数据"""
        parsed = []
        for market in markets_data:
            try:
                # 提取基本信息
                market_id = market.get("id") or market.get("slug") or market.get("market_id", "")
                question = market.get("question") or market.get("title", "")
                
                # 计算概率
                current_probability = 50.0
                outcome_tokens = {}
                
                if "outcomes" in market:
                    for outcome in market["outcomes"]:
                        title = str(outcome.get("title", "")).upper()
                        price = float(outcome.get("price", outcome.get("probability", 0)) or 0)
                        if "YES" in title or title == "YES":
                            current_probability = price * 100
                            outcome_tokens["YES"] = {
                                "price": price,
                                "volume": float(outcome.get("volume", 0) or 0)
                            }
                        elif "NO" in title or title == "NO":
                            outcome_tokens["NO"] = {
                                "price": price,
                                "volume": float(outcome.get("volume", 0) or 0)
                            }
                
                volume_24h = float(market.get("volume_24h", market.get("volume", 0)) or 0)
                liquidity = float(market.get("liquidity", 0) or 0)
                
                # 推断类别
                category = self._infer_category(question)
                
                # 解析结束日期
                end_date_iso = market.get("end_date") or market.get("endDate")
                if isinstance(end_date_iso, (int, float)):
                    try:
                        end_date_iso = datetime.fromtimestamp(end_date_iso).isoformat() + "Z"
                    except:
                        end_date_iso = None
                
                # 获取slug用于构建URL
                slug = None
                slug_str = str(market.get('slug', '')).strip() if market.get('slug') else ''
                
                # 检查slug是否有效（不是数字，且包含字母或连字符）
                if slug_str and not slug_str.isdigit() and ('-' in slug_str or any(c.isalpha() for c in slug_str)):
                    slug = slug_str
                else:
                    # 如果slug无效，尝试通过API查询获取
                    try:
                        detail_market = self._fetch_market_detail_by_id(market_id)
                        if detail_market and detail_market.get("slug"):
                            slug_str = str(detail_market.get("slug", "")).strip()
                            if slug_str and not slug_str.isdigit() and ('-' in slug_str or any(c.isalpha() for c in slug_str)):
                                slug = slug_str
                    except Exception as e:
                        logger.debug(f"Failed to fetch slug for market {market_id}: {e}")
                
                # 构建URL（使用统一的辅助方法）
                polymarket_url = self._build_polymarket_url(slug, market_id)
                if not slug:
                    logger.warning(f"Market {market_id} has no valid slug, using markets endpoint as fallback")
                
                parsed.append({
                    "market_id": market_id,
                    "question": question,
                    "category": category,
                    "current_probability": round(current_probability, 2),
                    "volume_24h": volume_24h,
                    "liquidity": liquidity,
                    "end_date_iso": end_date_iso,
                    "status": "active" if market.get("active", True) else "closed",
                    "outcome_tokens": outcome_tokens,
                    "polymarket_url": polymarket_url,
                    "slug": slug if slug else None
                })
            except Exception as e:
                logger.debug(f"Failed to parse market {market.get('id')}: {e}")
                continue
        
        return parsed
    
    def _infer_category(self, question: str) -> str:
        """从问题中推断类别"""
        question_lower = question.lower()
        
        # 加密货币关键词
        crypto_keywords = ['btc', 'bitcoin', 'eth', 'ethereum', 'sol', 'solana', 'crypto', 'token', 'coin', 'defi', 'nft']
        if any(kw in question_lower for kw in crypto_keywords):
            return "crypto"
        
        # 政治关键词
        politics_keywords = ['election', 'president', 'trump', 'biden', 'senate', 'congress', 'vote', 'political', 'democrat', 'republican']
        if any(kw in question_lower for kw in politics_keywords):
            return "politics"
        
        # 经济关键词
        economics_keywords = ['gdp', 'inflation', 'unemployment', 'fed', 'federal reserve', 'interest rate', 'economic', 'economy', 'recession', 'gdp growth', 'cpi', 'ppi']
        if any(kw in question_lower for kw in economics_keywords):
            return "economics"
        
        # 体育关键词
        sports_keywords = ['nfl', 'nba', 'mlb', 'soccer', 'football', 'basketball', 'baseball', 'championship', 'world cup', 'olympics', 'super bowl', 'stanley cup', 'world series']
        if any(kw in question_lower for kw in sports_keywords):
            return "sports"
        
        # 科技关键词
        tech_keywords = ['ai', 'artificial intelligence', 'chatgpt', 'openai', 'tech', 'technology', 'apple', 'google', 'microsoft', 'meta', 'tesla', 'ipo', 'startup']
        if any(kw in question_lower for kw in tech_keywords):
            return "tech"
        
        # 金融关键词
        finance_keywords = ['stock', 's&p', 'dow', 'nasdaq', 'market cap', 'earnings', 'revenue', 'profit', 'bank', 'banking', 'financial', 'trading']
        if any(kw in question_lower for kw in finance_keywords):
            return "finance"
        
        # 地缘政治关键词
        geopolitics_keywords = ['war', 'conflict', 'russia', 'ukraine', 'china', 'taiwan', 'north korea', 'iran', 'israel', 'palestine', 'middle east', 'nato', 'sanctions']
        if any(kw in question_lower for kw in geopolitics_keywords):
            return "geopolitics"
        
        # 文化关键词
        culture_keywords = ['movie', 'film', 'oscar', 'grammy', 'award', 'celebrity', 'music', 'album', 'tv show', 'series', 'netflix', 'disney']
        if any(kw in question_lower for kw in culture_keywords):
            return "culture"
        
        # 气候关键词
        climate_keywords = ['climate', 'global warming', 'temperature', 'carbon', 'emission', 'renewable', 'solar', 'wind energy', 'paris agreement', 'cop']
        if any(kw in question_lower for kw in climate_keywords):
            return "climate"
        
        # 娱乐关键词
        entertainment_keywords = ['game', 'gaming', 'esports', 'tournament', 'streaming', 'youtube', 'twitch', 'podcast', 'comic', 'anime', 'manga']
        if any(kw in question_lower for kw in entertainment_keywords):
            return "entertainment"
        
        return "other"
    
    def _build_polymarket_url(self, slug: Optional[str], market_id: str) -> str:
        """
        根据slug构建Polymarket URL
        参考: https://docs.polymarket.com/market-data/fetching-markets
        
        Args:
            slug: 从API或数据库获取的slug（可能是None或数字字符串）
            market_id: 市场ID（作为备选）
        
        Returns:
            Polymarket URL字符串
        """
        if slug:
            slug_str = str(slug).strip()
            # 检查slug是否有效（不是数字，且包含字母或连字符）
            if slug_str and not slug_str.isdigit() and ('-' in slug_str or any(c.isalpha() for c in slug_str)):
                import re
                slug_clean = re.sub(r'[^a-zA-Z0-9\-]', '-', slug_str)
                slug_clean = slug_clean.strip('-')
                if slug_clean:
                    return f"https://polymarket.com/event/{slug_clean}"
        
        # 如果没有有效slug，尝试通过API获取slug
        if market_id:
            try:
                detail_market = self._fetch_market_detail_by_id(market_id)
                if detail_market:
                    # 尝试从detail中获取slug
                    event_slug = detail_market.get('slug')
                    if event_slug:
                        slug_str = str(event_slug).strip()
                        if slug_str and not slug_str.isdigit() and ('-' in slug_str or any(c.isalpha() for c in slug_str)):
                            import re
                            slug_clean = re.sub(r'[^a-zA-Z0-9\-]', '-', slug_str)
                            slug_clean = slug_clean.strip('-')
                            if slug_clean:
                                return f"https://polymarket.com/event/{slug_clean}"
                    
                    # 如果event没有slug，尝试从markets中获取
                    markets = detail_market.get('markets', [])
                    if markets:
                        for m in markets:
                            market_slug = m.get('slug')
                            if market_slug:
                                slug_str = str(market_slug).strip()
                                if slug_str and not slug_str.isdigit() and ('-' in slug_str or any(c.isalpha() for c in slug_str)):
                                    import re
                                    slug_clean = re.sub(r'[^a-zA-Z0-9\-]', '-', slug_str)
                                    slug_clean = slug_clean.strip('-')
                                    if slug_clean:
                                        return f"https://polymarket.com/event/{slug_clean}"
            except Exception as e:
                logger.debug(f"Failed to fetch slug for market {market_id}: {e}")
        
        # 如果所有方法都失败，返回搜索页面（更可靠）
        # 注意：Polymarket的URL格式可能已经改变，使用搜索作为fallback
        return f"https://polymarket.com/search?q={market_id}"
    
    def _fetch_market_detail_by_id(self, market_id: str) -> Optional[Dict]:
        """
        通过market ID从API获取市场详情（用于获取slug）
        参考: https://docs.polymarket.com/market-data/fetching-markets
        """
        try:
            # 方法1: 尝试通过events端点查询（推荐，因为events包含markets）
            url = f"{self.gamma_api}/events"
            params = {"active": "true", "closed": "false", "limit": 100}
            response = self.session.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                events = response.json()
                if isinstance(events, list):
                    for event in events:
                        markets = event.get("markets", [])
                        if not markets and ("question" in event or "slug" in event):
                            markets = [event]
                        
                        for market in markets:
                            m_id = market.get("id") or market.get("slug") or ""
                            e_id = event.get("id") or event.get("slug") or ""
                            # 匹配market_id或event_id
                            if str(m_id) == str(market_id) or str(e_id) == str(market_id):
                                # 返回event（因为event包含slug）
                                return event
                elif isinstance(events, dict):
                    if "data" in events:
                        events_list = events["data"]
                        for event in events_list:
                            markets = event.get("markets", [])
                            if not markets and ("question" in event or "slug" in event):
                                markets = [event]
                            
                            for market in markets:
                                m_id = market.get("id") or market.get("slug") or ""
                                e_id = event.get("id") or event.get("slug") or ""
                                if str(m_id) == str(market_id) or str(e_id) == str(market_id):
                                    return event
            
            # 方法2: 尝试通过markets端点查询
            url = f"{self.gamma_api}/markets"
            params = {"id": market_id, "limit": 1}
            response = self.session.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list) and len(data) > 0:
                    return data[0]
                elif isinstance(data, dict) and "id" in data:
                    return data
            
            return None
        except Exception as e:
            logger.debug(f"Failed to fetch market detail by ID {market_id}: {e}")
            return None
    
    def _fetch_market_by_slug(self, slug: str) -> Optional[Dict]:
        """
        直接通过slug查询市场（最高效的方式）
        根据Polymarket API文档：https://docs.polymarket.com/market-data/fetching-markets
        可以使用 /markets?slug=xxx 直接查询
        """
        try:
            # 方法1: 尝试通过markets端点直接查询slug
            url = f"{self.gamma_api}/markets"
            params = {"slug": slug, "limit": 10}
            logger.info(f"Fetching market by slug from Gamma API: {url} with params: {params}")
            response = self.session.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list) and len(data) > 0:
                    # 解析返回的市场数据
                    markets = self._parse_gamma_events(data)
                    # 精确匹配slug
                    for market in markets:
                        market_slug = market.get("slug", "").lower()
                        if market_slug == slug.lower() or slug.lower() in market_slug:
                            logger.info(f"Found market by slug: {slug}")
                            return market
                    # 如果没有精确匹配，返回第一个
                    if markets:
                        logger.info(f"Found market by slug (fuzzy match): {slug}")
                        return markets[0]
                elif isinstance(data, dict):
                    # 单个市场对象
                    markets = self._parse_gamma_events([data])
                    if markets:
                        logger.info(f"Found market by slug: {slug}")
                        return markets[0]
            
            # 方法2: 尝试通过events端点查询（events可能包含slug信息）
            url = f"{self.gamma_api}/events"
            params = {"active": "true", "closed": "false", "limit": 100}
            response = self.session.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                events = data if isinstance(data, list) else (data.get("data", []) if isinstance(data, dict) else [])
                
                # 在返回的事件中查找匹配的slug
                for event in events:
                    event_slug = (event.get("slug") or "").lower()
                    if event_slug == slug.lower() or slug.lower() in event_slug:
                        parsed = self._parse_gamma_events([event])
                        if parsed:
                            logger.info(f"Found market by slug via events: {slug}")
                            return parsed[0]
            
            logger.warning(f"Market with slug '{slug}' not found via direct query")
            return None
            
        except Exception as e:
            logger.error(f"Failed to fetch market by slug {slug}: {e}", exc_info=True)
            return None
    
    def _fetch_market_from_api(self, market_id: str) -> Optional[Dict]:
        """
        从Gamma API获取单个市场数据
        支持通过slug或id查询
        """
        try:
            # 判断是slug还是market_id
            is_slug = not market_id.isdigit() and ('-' in market_id or any(c.isalpha() for c in market_id))
            
            # 如果是slug，优先使用直接查询方法
            if is_slug:
                market = self._fetch_market_by_slug(market_id)
                if market:
                    return market
            
            # 方法1: 通过markets端点查询（支持id和slug）
            url = f"{self.gamma_api}/markets"
            params = {"id": market_id, "limit": 10} if not is_slug else {"slug": market_id, "limit": 10}
            response = self.session.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list) and len(data) > 0:
                    markets = self._parse_gamma_events(data)
                    if markets:
                        return markets[0]
                elif isinstance(data, dict):
                    markets = self._parse_gamma_events([data])
                    if markets:
                        return markets[0]
            
            # 方法2: 通过events端点搜索（作为备选）
            url = f"{self.gamma_api}/events"
            params = {
                "active": "true",
                "closed": "false",
                "limit": 100
            }
            response = self.session.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                events = data if isinstance(data, list) else (data.get("data", []) if isinstance(data, dict) else [])
                
                # 在返回的事件中查找匹配的市场
                for event in events:
                    markets = event.get("markets", [])
                    if not markets:
                        markets = [event]
                    
                    for market in markets:
                        m_id = market.get("id") or market.get("slug") or event.get("id") or event.get("slug", "")
                        if str(m_id) == str(market_id) or market.get("slug") == market_id:
                            parsed = self._parse_gamma_events([event])
                            if parsed:
                                return parsed[0]
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to fetch market {market_id}: {e}", exc_info=True)
            return None
    
    def _save_markets_to_db(self, markets: List[Dict]):
        """保存市场数据到数据库"""
        try:
            with get_db_connection() as db:
                cur = db.cursor()
                for market in markets:
                    # 获取slug，但如果是数字则不要使用（数字不是有效的slug）
                    slug = market.get('slug') or None
                    # 如果slug是数字，说明不是有效的slug，设置为None
                    if slug and str(slug).isdigit():
                        slug = None
                    # 清理slug，只保留字母数字和连字符
                    import re
                    if slug:
                        slug = re.sub(r'[^a-zA-Z0-9\-]', '-', str(slug))
                        slug = slug.strip('-')
                        # 如果清理后为空或仍然是数字，设置为None
                        if not slug or slug.isdigit():
                            slug = None
                    
                    # 提取新增的交易字段
                    condition_id = market.get('condition_id')
                    yes_token_id = market.get('yes_token_id')
                    no_token_id = market.get('no_token_id')
                    accepting_orders = market.get('accepting_orders', True)
                    tokens_data = market.get('tokens_data')
                    
                    cur.execute("""
                        INSERT INTO qd_polymarket_markets
                        (market_id, question, category, current_probability, volume_24h,
                         liquidity, end_date_iso, status, outcome_tokens, slug, 
                         condition_id, yes_token_id, no_token_id, accepting_orders, tokens_data, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                        ON CONFLICT (market_id) DO UPDATE SET
                            question = EXCLUDED.question,
                            category = EXCLUDED.category,
                            current_probability = EXCLUDED.current_probability,
                            volume_24h = EXCLUDED.volume_24h,
                            liquidity = EXCLUDED.liquidity,
                            end_date_iso = EXCLUDED.end_date_iso,
                            status = EXCLUDED.status,
                            outcome_tokens = EXCLUDED.outcome_tokens,
                            slug = EXCLUDED.slug,
                            condition_id = EXCLUDED.condition_id,
                            yes_token_id = EXCLUDED.yes_token_id,
                            no_token_id = EXCLUDED.no_token_id,
                            accepting_orders = EXCLUDED.accepting_orders,
                            tokens_data = EXCLUDED.tokens_data,
                            updated_at = NOW()
                    """, (
                        market.get('market_id'),
                        market.get('question'),
                        market.get('category', 'other'),
                        market.get('current_probability', 50.0),
                        market.get('volume_24h', 0),
                        market.get('liquidity', 0),
                        market.get('end_date_iso'),
                        market.get('status', 'active'),
                        json.dumps(market.get('outcome_tokens', {})),
                        slug,
                        condition_id,
                        yes_token_id,
                        no_token_id,
                        accepting_orders,
                        json.dumps(tokens_data) if tokens_data else None
                    ))
                db.commit()
                cur.close()
        except Exception as e:
            logger.error(f"Failed to save markets to DB: {type(e).__name__}: {e}", exc_info=True)
    
    def _get_sample_markets(self, category: str = None, limit: int = 50) -> List[Dict]:
        """
        获取示例市场数据（已弃用）
        现在应该使用真实的API数据
        """
        # 不再返回示例数据，返回空列表
        logger.warning("Sample data method called, but real API should be used instead")
        return []

    def get_leaderboard(self, period: str = 'month', limit: int = 5) -> List[Dict]:
        """
        获取Polymarket排行榜（交易者排行榜）

        Args:
            period: 排行榜周期 ('day', 'week', 'month', 'all')
            limit: 返回数量（默认5，最大100）

        Returns:
            排行榜用户列表，包含字段：
            - rank: 排名
            - proxyWallet (user): 用户钱包地址
            - userName: 用户名
            - vol (volume): 交易量
            - pnl (profit): 利润
            - profileImage: 头像
        """
        try:
            # 使用 Data API v1 的 leaderboard 端点
            url = f"{self.data_api}/v1/leaderboard"
            
            # 映射period参数（API使用大写格式）
            period_map = {
                'day': 'DAY',
                'week': 'WEEK',
                'month': 'MONTH',
                'all': 'ALL'
            }
            api_period = period_map.get(period, 'MONTH')
            
            params = {
                'category': 'OVERALL',
                'timePeriod': api_period,
                'orderBy': 'PNL',  # 按利润排序
                'limit': min(limit, 100)  # API最大支持100
            }

            logger.info(f"Fetching leaderboard: period={api_period}, limit={limit}")
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()

            users = response.json()
            
            # 标准化数据格式，将 proxyWallet 映射为 user（保持兼容性）
            for user in users:
                user['user'] = user.get('proxyWallet')
                user['volume'] = user.get('vol')
                user['profit'] = user.get('pnl')
                # rank 已经在返回数据中
            
            logger.info(f"Got {len(users)} users from {period} leaderboard")

            return users

        except Exception as e:
            logger.error(f"Failed to get leaderboard: {e}", exc_info=True)
            return []

    def get_user_activities(self, user_address: str, limit: int = 5) -> List[Dict]:
        """
        获取用户交易活动

        Args:
            user_address: 用户地址
            limit: 返回数量（默认5）

        Returns:
            用户交易活动列表
        """
        try:
            url = f"{self.data_api}/activity"
            params = {
                'user': user_address,
                'limit': limit
            }

            logger.info(f"Fetching activities for user: {user_address[:10]}..., limit={limit}")
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()

            activities = response.json()

            # 返回数据是数组
            logger.info(f"Got {len(activities)} activities for user {user_address[:10]}...")

            return activities

        except Exception as e:
            logger.error(f"Failed to get user activities: {e}", exc_info=True)
            return []
    
    def get_market_by_condition_id(self, condition_id: str) -> Optional[Dict]:
        """
        通过 condition_id 获取市场详情
        
        Args:
            condition_id: 市场的 condition ID
            
        Returns:
            市场详情字典，如果未找到则返回 None
        """
        try:
            # 先尝试从数据库查询
            try:
                with get_db_connection() as db:
                    cur = db.cursor()
                    cur.execute("""
                        SELECT market_id, question, category, current_probability, 
                               volume_24h, liquidity, end_date_iso, status, outcome_tokens, slug
                        FROM qd_polymarket_markets
                        WHERE condition_id = %s
                    """, (condition_id,))
                    row = cur.fetchone()
                    cur.close()
                    
                    if row:
                        return {
                            "market_id": str(row.get('market_id') or ''),
                            "question": row.get('question') or '',
                            "category": row.get('category') or 'other',
                            "current_probability": float(row.get('current_probability') or 0),
                            "volume_24h": float(row.get('volume_24h') or 0),
                            "liquidity": float(row.get('liquidity') or 0),
                            "end_date_iso": row.get('end_date_iso'),
                            "status": row.get('status') or 'active',
                            "outcome_tokens": row.get('outcome_tokens') if row.get('outcome_tokens') else {},
                            "polymarket_url": self._build_polymarket_url(row.get('slug'), row.get('market_id') or ''),
                            "slug": row.get('slug') if row.get('slug') and not str(row.get('slug', '')).isdigit() else None
                        }
            except Exception as db_error:
                logger.debug(f"Database query failed for condition_id {condition_id}: {db_error}")
            
            # 如果数据库没有，从 API 获取
            # 使用 Gamma API 的 events 端点搜索
            logger.info(f"Condition ID {condition_id} not in database, fetching from API")
            
            url = f"{self.gamma_api}/events"
            params = {
                "active": "true",
                "closed": "false",
                "limit": 100
            }
            
            response = self.session.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                events = data if isinstance(data, list) else (data.get("data", []) if isinstance(data, dict) else [])
                
                # 在返回的事件中查找匹配的 condition_id
                for event in events:
                    event_condition_id = event.get("conditionId")
                    if event_condition_id == condition_id:
                        parsed = self._parse_gamma_events([event])
                        if parsed:
                            market = parsed[0]
                            # 保存到数据库
                            try:
                                self._save_markets_to_db([market])
                            except Exception as save_error:
                                logger.warning(f"Failed to save market to DB: {save_error}")
                            return market
                    
                    # 也检查 markets 中的 condition_id
                    markets = event.get("markets", [])
                    for market in markets:
                        market_condition_id = market.get("conditionId")
                        if market_condition_id == condition_id:
                            parsed = self._parse_gamma_events([event])
                            if parsed:
                                market_data = parsed[0]
                                # 保存到数据库
                                try:
                                    self._save_markets_to_db([market_data])
                                except Exception as save_error:
                                    logger.warning(f"Failed to save market to DB: {save_error}")
                                return market_data
            
            logger.debug(f"Market with condition_id {condition_id} not found in API (may be closed/settled)")
            return None
            
        except Exception as e:
            logger.error(f"Failed to get market by condition_id {condition_id}: {e}", exc_info=True)
            return None

