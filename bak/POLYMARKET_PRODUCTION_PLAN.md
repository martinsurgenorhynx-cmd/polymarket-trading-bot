# Polymarket 生产环境改进方案

## 当前问题分析

### 1. test_polymarket_worker.py 问题

**现有问题：**
- ❌ 只是测试脚本，不适合生产环境
- ❌ 没有错误处理和重试机制
- ❌ 没有监控和告警
- ❌ 没有性能优化
- ❌ 硬编码的测试参数

### 2. query_polymarket_results.py 问题

**现有问题：**
- ❌ 命令行脚本，不适合 Web 展示
- ❌ 没有分页功能
- ❌ 没有筛选和排序
- ❌ 性能问题（大量数据时）
- ❌ 没有缓存机制
- ❌ 多选项市场识别不完善

## 生产环境技术方案

### 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                     前端 (Frontend)                          │
│  - React/Vue Dashboard                                      │
│  - 实时数据展示                                              │
│  - 交互式图表                                                │
└─────────────────────────────────────────────────────────────┘
                            ↓ REST API
┌─────────────────────────────────────────────────────────────┐
│                   API 层 (Flask/FastAPI)                     │
│  - RESTful API                                              │
│  - WebSocket (实时推送)                                      │
│  - 认证授权                                                  │
│  - 限流保护                                                  │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                   服务层 (Services)                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Worker       │  │ Analyzer     │  │ Trader       │      │
│  │ Service      │  │ Service      │  │ Service      │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                   数据层 (Data Layer)                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ PostgreSQL   │  │ Redis        │  │ TimescaleDB  │      │
│  │ (主数据库)    │  │ (缓存/队列)   │  │ (时序数据)    │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                   外部服务 (External)                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Polymarket   │  │ LLM API      │  │ Monitoring   │      │
│  │ API          │  │ (OpenAI)     │  │ (Grafana)    │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
```


## 核心改进方案

### 1. Worker 服务改进

#### 1.1 生产级 Worker

```python
# app/services/polymarket_production_worker.py
import asyncio
import logging
from typing import List, Dict
from datetime import datetime, timedelta
import redis
from prometheus_client import Counter, Histogram, Gauge

class PolymarketProductionWorker:
    """生产环境 Polymarket Worker"""
    
    def __init__(self):
        self.redis_client = redis.Redis(
            host='localhost',
            port=6379,
            decode_responses=True
        )
        
        # Prometheus 指标
        self.markets_processed = Counter(
            'polymarket_markets_processed_total',
            'Total markets processed'
        )
        self.analysis_duration = Histogram(
            'polymarket_analysis_duration_seconds',
            'Time spent analyzing markets'
        )
        self.active_markets = Gauge(
            'polymarket_active_markets',
            'Number of active markets'
        )
        
        # 配置
        self.batch_size = 10  # 批量处理
        self.max_retries = 3
        self.retry_delay = 5
        
    async def run_forever(self):
        """持续运行 Worker"""
        while True:
            try:
                await self.process_batch()
                await asyncio.sleep(300)  # 5分钟
            except Exception as e:
                logging.error(f"Worker error: {e}")
                await asyncio.sleep(60)  # 错误后等待1分钟
    
    async def process_batch(self):
        """批量处理市场"""
        markets = await self.fetch_markets()
        
        # 并发处理
        tasks = [
            self.analyze_market(market)
            for market in markets[:self.batch_size]
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 统计
        success_count = sum(1 for r in results if not isinstance(r, Exception))
        self.markets_processed.inc(success_count)
        
        return results
    
    async def analyze_market(self, market: Dict):
        """分析单个市场（带重试）"""
        for attempt in range(self.max_retries):
            try:
                with self.analysis_duration.time():
                    result = await self._do_analysis(market)
                    await self._save_result(result)
                    return result
            except Exception as e:
                if attempt == self.max_retries - 1:
                    raise
                await asyncio.sleep(self.retry_delay * (attempt + 1))
```

#### 1.2 任务队列（Celery）

```python
# app/tasks/polymarket_tasks.py
from celery import Celery
from celery.schedules import crontab

app = Celery('polymarket', broker='redis://localhost:6379/0')

@app.task(bind=True, max_retries=3)
def analyze_market_task(self, market_id: str):
    """异步分析任务"""
    try:
        analyzer = PolymarketAnalyzer()
        result = analyzer.analyze_market(market_id)
        return result
    except Exception as exc:
        # 指数退避重试
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))

@app.task
def update_markets_task():
    """定时更新市场数据"""
    worker = PolymarketProductionWorker()
    return worker.update_all_markets()

# 定时任务配置
app.conf.beat_schedule = {
    'update-markets-every-5-minutes': {
        'task': 'app.tasks.polymarket_tasks.update_markets_task',
        'schedule': crontab(minute='*/5'),
    },
}
```

### 2. API 层改进

#### 2.1 RESTful API

```python
# app/routes/polymarket_v2.py
from flask import Blueprint, jsonify, request
from flask_limiter import Limiter
from flask_caching import Cache
import logging

polymarket_v2_bp = Blueprint('polymarket_v2', __name__)

# 限流器
limiter = Limiter(
    key_func=lambda: request.headers.get('X-User-ID', 'anonymous'),
    default_limits=["100 per hour"]
)

# 缓存
cache = Cache(config={'CACHE_TYPE': 'redis'})

@polymarket_v2_bp.route("/api/v2/polymarket/markets", methods=["GET"])
@limiter.limit("30 per minute")
@cache.cached(timeout=60, query_string=True)
def get_markets():
    """
    获取市场列表（分页、筛选、排序）
    
    Query Parameters:
        page: int - 页码（默认1）
        page_size: int - 每页数量（默认20，最大100）
        category: str - 分类筛选
        min_opportunity: float - 最小机会评分
        sort_by: str - 排序字段（opportunity_score, created_at等）
        order: str - 排序方向（asc, desc）
    """
    try:
        # 参数验证
        page = max(1, request.args.get('page', 1, type=int))
        page_size = min(100, max(1, request.args.get('page_size', 20, type=int)))
        category = request.args.get('category')
        min_opportunity = request.args.get('min_opportunity', 0, type=float)
        sort_by = request.args.get('sort_by', 'opportunity_score')
        order = request.args.get('order', 'desc')
        
        # 查询数据
        service = PolymarketQueryService()
        result = service.get_markets_paginated(
            page=page,
            page_size=page_size,
            category=category,
            min_opportunity=min_opportunity,
            sort_by=sort_by,
            order=order
        )
        
        return jsonify({
            "code": 1,
            "msg": "success",
            "data": result
        })
        
    except Exception as e:
        logging.error(f"Get markets failed: {e}", exc_info=True)
        return jsonify({
            "code": 0,
            "msg": str(e)
        }), 500

@polymarket_v2_bp.route("/api/v2/polymarket/markets/<market_id>", methods=["GET"])
@cache.cached(timeout=30)
def get_market_detail(market_id: str):
    """获取市场详情（包含历史分析）"""
    try:
        service = PolymarketQueryService()
        result = service.get_market_detail(market_id)
        
        if not result:
            return jsonify({
                "code": 0,
                "msg": "Market not found"
            }), 404
        
        return jsonify({
            "code": 1,
            "msg": "success",
            "data": result
        })
        
    except Exception as e:
        logging.error(f"Get market detail failed: {e}", exc_info=True)
        return jsonify({
            "code": 0,
            "msg": str(e)
        }), 500

@polymarket_v2_bp.route("/api/v2/polymarket/opportunities", methods=["GET"])
@limiter.limit("10 per minute")
@cache.cached(timeout=120)
def get_opportunities():
    """获取高分机会列表"""
    try:
        min_score = request.args.get('min_score', 75, type=float)
        limit = min(50, request.args.get('limit', 10, type=int))
        
        service = PolymarketQueryService()
        result = service.get_high_opportunities(
            min_score=min_score,
            limit=limit
        )
        
        return jsonify({
            "code": 1,
            "msg": "success",
            "data": result
        })
        
    except Exception as e:
        logging.error(f"Get opportunities failed: {e}", exc_info=True)
        return jsonify({
            "code": 0,
            "msg": str(e)
        }), 500
```


#### 2.2 WebSocket 实时推送

```python
# app/websocket/polymarket_ws.py
from flask_socketio import SocketIO, emit, join_room, leave_room
import redis

socketio = SocketIO(cors_allowed_origins="*")
redis_client = redis.Redis()
pubsub = redis_client.pubsub()

@socketio.on('subscribe_market')
def handle_subscribe(data):
    """订阅市场更新"""
    market_id = data.get('market_id')
    if market_id:
        join_room(f'market_{market_id}')
        emit('subscribed', {'market_id': market_id})

@socketio.on('unsubscribe_market')
def handle_unsubscribe(data):
    """取消订阅"""
    market_id = data.get('market_id')
    if market_id:
        leave_room(f'market_{market_id}')

def broadcast_market_update(market_id: str, data: dict):
    """广播市场更新"""
    socketio.emit(
        'market_update',
        data,
        room=f'market_{market_id}'
    )
```

### 3. 数据层改进

#### 3.1 数据库优化

```sql
-- 添加索引
CREATE INDEX CONCURRENTLY idx_polymarket_analysis_opportunity 
ON qd_polymarket_ai_analysis(opportunity_score DESC, created_at DESC);

CREATE INDEX CONCURRENTLY idx_polymarket_analysis_category 
ON qd_polymarket_ai_analysis(market_id) 
INCLUDE (recommendation, opportunity_score, created_at);

CREATE INDEX CONCURRENTLY idx_polymarket_markets_active 
ON qd_polymarket_markets(status, category) 
WHERE status = 'active';

-- 分区表（按时间分区）
CREATE TABLE qd_polymarket_ai_analysis_partitioned (
    LIKE qd_polymarket_ai_analysis INCLUDING ALL
) PARTITION BY RANGE (created_at);

CREATE TABLE qd_polymarket_ai_analysis_2025_q1 
PARTITION OF qd_polymarket_ai_analysis_partitioned
FOR VALUES FROM ('2025-01-01') TO ('2025-04-01');

-- 物化视图（高分机会）
CREATE MATERIALIZED VIEW mv_polymarket_high_opportunities AS
SELECT 
    a.market_id,
    a.recommendation,
    a.opportunity_score,
    a.confidence_score,
    a.ai_predicted_probability,
    a.market_probability,
    a.divergence,
    a.created_at,
    m.question,
    m.slug,
    m.category,
    m.volume_24h,
    m.liquidity
FROM qd_polymarket_ai_analysis a
INNER JOIN qd_polymarket_markets m ON a.market_id = m.market_id
WHERE a.opportunity_score > 75
  AND a.created_at > NOW() - INTERVAL '7 days'
ORDER BY a.opportunity_score DESC, a.created_at DESC;

-- 定时刷新
CREATE INDEX ON mv_polymarket_high_opportunities(opportunity_score DESC);
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_polymarket_high_opportunities;
```

#### 3.2 Redis 缓存策略

```python
# app/services/polymarket_cache.py
import redis
import json
from typing import Optional, Dict, List
from datetime import timedelta

class PolymarketCache:
    """Polymarket 缓存服务"""
    
    def __init__(self):
        self.redis = redis.Redis(
            host='localhost',
            port=6379,
            decode_responses=True
        )
        
        # 缓存时间配置
        self.TTL = {
            'market_list': 60,          # 市场列表 1分钟
            'market_detail': 30,        # 市场详情 30秒
            'analysis': 300,            # 分析结果 5分钟
            'opportunities': 120,       # 高分机会 2分钟
            'statistics': 600,          # 统计数据 10分钟
        }
    
    def get_market_list(self, cache_key: str) -> Optional[List[Dict]]:
        """获取市场列表缓存"""
        data = self.redis.get(f'market_list:{cache_key}')
        return json.loads(data) if data else None
    
    def set_market_list(self, cache_key: str, data: List[Dict]):
        """设置市场列表缓存"""
        self.redis.setex(
            f'market_list:{cache_key}',
            self.TTL['market_list'],
            json.dumps(data)
        )
    
    def get_analysis(self, market_id: str) -> Optional[Dict]:
        """获取分析结果缓存"""
        data = self.redis.get(f'analysis:{market_id}')
        return json.loads(data) if data else None
    
    def set_analysis(self, market_id: str, data: Dict):
        """设置分析结果缓存"""
        self.redis.setex(
            f'analysis:{market_id}',
            self.TTL['analysis'],
            json.dumps(data)
        )
    
    def invalidate_market(self, market_id: str):
        """使市场相关缓存失效"""
        pattern = f'*{market_id}*'
        for key in self.redis.scan_iter(match=pattern):
            self.redis.delete(key)
```

### 4. 查询服务改进

```python
# app/services/polymarket_query_service.py
from typing import List, Dict, Optional
from sqlalchemy import text
from app.utils.db import get_db_connection
from app.services.polymarket_cache import PolymarketCache

class PolymarketQueryService:
    """Polymarket 查询服务"""
    
    def __init__(self):
        self.cache = PolymarketCache()
    
    def get_markets_paginated(
        self,
        page: int = 1,
        page_size: int = 20,
        category: Optional[str] = None,
        min_opportunity: float = 0,
        sort_by: str = 'opportunity_score',
        order: str = 'desc'
    ) -> Dict:
        """分页获取市场列表"""
        
        # 生成缓存键
        cache_key = f"{page}_{page_size}_{category}_{min_opportunity}_{sort_by}_{order}"
        
        # 尝试从缓存获取
        cached = self.cache.get_market_list(cache_key)
        if cached:
            return cached
        
        # 构建查询
        offset = (page - 1) * page_size
        
        # 验证排序字段
        allowed_sort_fields = [
            'opportunity_score', 'confidence_score', 
            'created_at', 'volume_24h', 'divergence'
        ]
        if sort_by not in allowed_sort_fields:
            sort_by = 'opportunity_score'
        
        order_clause = 'DESC' if order.lower() == 'desc' else 'ASC'
        
        # 构建 WHERE 条件
        where_conditions = ['a.opportunity_score >= :min_opportunity']
        params = {'min_opportunity': min_opportunity}
        
        if category:
            where_conditions.append('m.category = :category')
            params['category'] = category
        
        where_clause = ' AND '.join(where_conditions)
        
        with get_db_connection() as conn:
            # 获取总数
            count_query = f"""
                SELECT COUNT(DISTINCT a.market_id) as total
                FROM qd_polymarket_ai_analysis a
                INNER JOIN qd_polymarket_markets m ON a.market_id = m.market_id
                WHERE {where_clause}
            """
            
            result = conn.execute(text(count_query), params).fetchone()
            total = result['total'] if result else 0
            
            # 获取数据
            data_query = f"""
                SELECT DISTINCT ON (a.market_id)
                    a.market_id,
                    a.recommendation,
                    a.opportunity_score,
                    a.confidence_score,
                    a.ai_predicted_probability,
                    a.market_probability,
                    a.divergence,
                    a.created_at,
                    m.question,
                    m.slug,
                    m.category,
                    m.volume_24h,
                    m.liquidity,
                    m.end_date_iso
                FROM qd_polymarket_ai_analysis a
                INNER JOIN qd_polymarket_markets m ON a.market_id = m.market_id
                WHERE {where_clause}
                ORDER BY a.market_id, a.created_at DESC
            """
            
            # 添加排序和分页
            data_query += f"""
                ORDER BY {sort_by} {order_clause}
                LIMIT :limit OFFSET :offset
            """
            
            params.update({'limit': page_size, 'offset': offset})
            
            rows = conn.execute(text(data_query), params).fetchall()
            
            # 格式化结果
            items = []
            for row in rows:
                item = dict(row._mapping)
                
                # 识别多选项市场
                item['is_multi_option'] = self._detect_multi_option(item['question'])
                item['option_info'] = self._extract_option_info(item['question'])
                
                items.append(item)
            
            result = {
                'items': items,
                'total': total,
                'page': page,
                'page_size': page_size,
                'total_pages': (total + page_size - 1) // page_size
            }
            
            # 缓存结果
            self.cache.set_market_list(cache_key, result)
            
            return result
    
    def _detect_multi_option(self, question: str) -> bool:
        """检测是否为多选项市场"""
        keywords = ['will ', 'win the', 'by ', 'before ', 'in 2025', 'in 2026']
        return any(kw in question.lower() for kw in keywords)
    
    def _extract_option_info(self, question: str) -> Optional[Dict]:
        """提取选项信息"""
        import re
        
        # 提取国家/队伍名称
        match = re.search(r'Will\s+([A-Za-z\s\-]+?)\s+(?:win|be|become)', question, re.IGNORECASE)
        if match:
            return {
                'type': 'competitor',
                'name': match.group(1).strip()
            }
        
        # 提取时间期限
        match = re.search(r'by\s+([A-Za-z]+\s+\d+,\s+\d{4})', question, re.IGNORECASE)
        if match:
            return {
                'type': 'deadline',
                'date': match.group(1).strip()
            }
        
        return None
```


### 5. 监控和告警

#### 5.1 Prometheus + Grafana

```python
# app/monitoring/metrics.py
from prometheus_client import Counter, Histogram, Gauge, Info
import time

# 业务指标
polymarket_requests = Counter(
    'polymarket_api_requests_total',
    'Total API requests',
    ['endpoint', 'method', 'status']
)

polymarket_analysis_duration = Histogram(
    'polymarket_analysis_duration_seconds',
    'Time spent on analysis',
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0]
)

polymarket_active_markets = Gauge(
    'polymarket_active_markets_count',
    'Number of active markets'
)

polymarket_high_opportunities = Gauge(
    'polymarket_high_opportunities_count',
    'Number of high opportunity markets',
    ['min_score']
)

polymarket_worker_status = Gauge(
    'polymarket_worker_status',
    'Worker status (1=running, 0=stopped)'
)

# 系统信息
polymarket_info = Info(
    'polymarket_version',
    'Polymarket service version'
)
polymarket_info.info({'version': '2.0.0', 'env': 'production'})

# 装饰器
def track_request(endpoint: str):
    """跟踪 API 请求"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            start_time = time.time()
            status = 'success'
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                status = 'error'
                raise
            finally:
                duration = time.time() - start_time
                polymarket_requests.labels(
                    endpoint=endpoint,
                    method='GET',
                    status=status
                ).inc()
                polymarket_analysis_duration.observe(duration)
        return wrapper
    return decorator
```

#### 5.2 日志系统

```python
# app/utils/logging_config.py
import logging
import logging.handlers
from pythonjsonlogger import jsonlogger

def setup_logging():
    """配置结构化日志"""
    
    # JSON 格式化器
    formatter = jsonlogger.JsonFormatter(
        '%(timestamp)s %(level)s %(name)s %(message)s %(pathname)s %(lineno)d'
    )
    
    # 文件处理器（按天轮转）
    file_handler = logging.handlers.TimedRotatingFileHandler(
        'logs/polymarket.log',
        when='midnight',
        interval=1,
        backupCount=30
    )
    file_handler.setFormatter(formatter)
    
    # 错误日志单独文件
    error_handler = logging.handlers.TimedRotatingFileHandler(
        'logs/polymarket_error.log',
        when='midnight',
        interval=1,
        backupCount=90
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    
    # 配置根日志器
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(error_handler)
    
    # 控制台输出（开发环境）
    if os.getenv('ENV') == 'development':
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
```

#### 5.3 告警规则

```yaml
# prometheus/alerts.yml
groups:
  - name: polymarket_alerts
    interval: 30s
    rules:
      # Worker 停止告警
      - alert: PolymarketWorkerDown
        expr: polymarket_worker_status == 0
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Polymarket Worker is down"
          description: "Worker has been down for more than 5 minutes"
      
      # API 错误率告警
      - alert: PolymarketHighErrorRate
        expr: |
          rate(polymarket_api_requests_total{status="error"}[5m]) 
          / 
          rate(polymarket_api_requests_total[5m]) 
          > 0.05
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High API error rate"
          description: "Error rate is above 5% for 5 minutes"
      
      # 分析延迟告警
      - alert: PolymarketSlowAnalysis
        expr: |
          histogram_quantile(0.95, 
            rate(polymarket_analysis_duration_seconds_bucket[5m])
          ) > 30
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Slow analysis performance"
          description: "95th percentile analysis time is above 30s"
      
      # 活跃市场数量异常
      - alert: PolymarketLowMarketCount
        expr: polymarket_active_markets_count < 10
        for: 15m
        labels:
          severity: warning
        annotations:
          summary: "Low active market count"
          description: "Active markets count is below 10"
```

### 6. 部署方案

#### 6.1 Docker Compose

```yaml
# docker-compose.prod.yml
version: '3.8'

services:
  # API 服务
  api:
    build: .
    image: polymarket-api:latest
    ports:
      - "5001:5001"
    environment:
      - ENV=production
      - DATABASE_URL=postgresql://user:pass@postgres:5432/polymarket
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - postgres
      - redis
    restart: always
    deploy:
      replicas: 3
      resources:
        limits:
          cpus: '1'
          memory: 1G
  
  # Worker 服务
  worker:
    build: .
    image: polymarket-worker:latest
    command: celery -A app.tasks.polymarket_tasks worker -l info
    environment:
      - ENV=production
      - DATABASE_URL=postgresql://user:pass@postgres:5432/polymarket
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - postgres
      - redis
    restart: always
    deploy:
      replicas: 2
  
  # Celery Beat (定时任务)
  beat:
    build: .
    image: polymarket-worker:latest
    command: celery -A app.tasks.polymarket_tasks beat -l info
    environment:
      - ENV=production
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - redis
    restart: always
  
  # PostgreSQL
  postgres:
    image: timescale/timescaledb:latest-pg14
    volumes:
      - postgres_data:/var/lib/postgresql/data
    environment:
      - POSTGRES_DB=polymarket
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=pass
    restart: always
  
  # Redis
  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data
    restart: always
  
  # Nginx (负载均衡)
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./ssl:/etc/nginx/ssl
    depends_on:
      - api
    restart: always
  
  # Prometheus
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    restart: always
  
  # Grafana
  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    volumes:
      - grafana_data:/var/lib/grafana
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    restart: always

volumes:
  postgres_data:
  redis_data:
  prometheus_data:
  grafana_data:
```

#### 6.2 Kubernetes 部署

```yaml
# k8s/deployment.yml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: polymarket-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: polymarket-api
  template:
    metadata:
      labels:
        app: polymarket-api
    spec:
      containers:
      - name: api
        image: polymarket-api:latest
        ports:
        - containerPort: 5001
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: polymarket-secrets
              key: database-url
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
        livenessProbe:
          httpGet:
            path: /health
            port: 5001
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: 5001
          initialDelaySeconds: 5
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: polymarket-api-service
spec:
  selector:
    app: polymarket-api
  ports:
  - protocol: TCP
    port: 80
    targetPort: 5001
  type: LoadBalancer
```


### 7. 前端改进

#### 7.1 React Dashboard

```typescript
// frontend/src/pages/PolymarketDashboard.tsx
import React, { useState, useEffect } from 'react';
import { useQuery } from 'react-query';
import { 
  Table, Pagination, Select, Input, 
  Card, Statistic, Row, Col, Tag 
} from 'antd';

interface Market {
  market_id: string;
  question: string;
  recommendation: 'YES' | 'NO' | 'HOLD';
  opportunity_score: number;
  confidence_score: number;
  ai_predicted_probability: number;
  market_probability: number;
  divergence: number;
  category: string;
  volume_24h: number;
  is_multi_option: boolean;
  option_info?: {
    type: string;
    name?: string;
    date?: string;
  };
}

export const PolymarketDashboard: React.FC = () => {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [category, setCategory] = useState<string>();
  const [minOpportunity, setMinOpportunity] = useState(0);
  const [sortBy, setSortBy] = useState('opportunity_score');
  
  // 获取市场列表
  const { data, isLoading, error } = useQuery(
    ['markets', page, pageSize, category, minOpportunity, sortBy],
    () => fetchMarkets({
      page,
      page_size: pageSize,
      category,
      min_opportunity: minOpportunity,
      sort_by: sortBy
    }),
    {
      refetchInterval: 60000, // 每分钟刷新
      keepPreviousData: true
    }
  );
  
  // 获取统计数据
  const { data: stats } = useQuery(
    'statistics',
    fetchStatistics,
    { refetchInterval: 300000 } // 每5分钟刷新
  );
  
  const columns = [
    {
      title: '问题',
      dataIndex: 'question',
      key: 'question',
      width: 300,
      render: (text: string, record: Market) => (
        <div>
          <a href={`/polymarket/${record.market_id}`}>{text}</a>
          {record.is_multi_option && (
            <Tag color="orange" style={{ marginLeft: 8 }}>
              多选项
            </Tag>
          )}
          {record.option_info && (
            <div style={{ fontSize: 12, color: '#666' }}>
              {record.option_info.type === 'competitor' && 
                `选项: ${record.option_info.name}`}
              {record.option_info.type === 'deadline' && 
                `期限: ${record.option_info.date}`}
            </div>
          )}
        </div>
      )
    },
    {
      title: '推荐',
      dataIndex: 'recommendation',
      key: 'recommendation',
      width: 80,
      render: (rec: string) => {
        const colors = {
          'YES': 'green',
          'NO': 'red',
          'HOLD': 'default'
        };
        return <Tag color={colors[rec]}>{rec}</Tag>;
      }
    },
    {
      title: '机会评分',
      dataIndex: 'opportunity_score',
      key: 'opportunity_score',
      width: 100,
      sorter: true,
      render: (score: number) => (
        <span style={{ 
          color: score > 85 ? '#52c41a' : score > 75 ? '#1890ff' : '#666'
        }}>
          {score.toFixed(0)}
        </span>
      )
    },
    {
      title: 'AI预测',
      dataIndex: 'ai_predicted_probability',
      key: 'ai_predicted_probability',
      width: 100,
      render: (prob: number) => `${prob.toFixed(1)}%`
    },
    {
      title: '市场概率',
      dataIndex: 'market_probability',
      key: 'market_probability',
      width: 100,
      render: (prob: number) => `${prob.toFixed(1)}%`
    },
    {
      title: '差异',
      dataIndex: 'divergence',
      key: 'divergence',
      width: 80,
      render: (div: number) => (
        <span style={{ color: div > 0 ? '#52c41a' : '#f5222d' }}>
          {div > 0 ? '+' : ''}{div.toFixed(1)}%
        </span>
      )
    },
    {
      title: '24h交易量',
      dataIndex: 'volume_24h',
      key: 'volume_24h',
      width: 120,
      render: (vol: number) => `$${vol.toLocaleString()}`
    }
  ];
  
  return (
    <div style={{ padding: 24 }}>
      <h1>Polymarket 预测市场分析</h1>
      
      {/* 统计卡片 */}
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card>
            <Statistic 
              title="活跃市场" 
              value={stats?.active_markets || 0} 
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic 
              title="高分机会" 
              value={stats?.high_opportunities || 0}
              valueStyle={{ color: '#3f8600' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic 
              title="今日分析" 
              value={stats?.today_analysis || 0} 
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic 
              title="平均机会评分" 
              value={stats?.avg_opportunity_score || 0}
              precision={1}
            />
          </Card>
        </Col>
      </Row>
      
      {/* 筛选器 */}
      <Card style={{ marginBottom: 16 }}>
        <Row gutter={16}>
          <Col span={6}>
            <Select
              placeholder="选择分类"
              style={{ width: '100%' }}
              onChange={setCategory}
              allowClear
            >
              <Select.Option value="crypto">Crypto</Select.Option>
              <Select.Option value="sports">Sports</Select.Option>
              <Select.Option value="politics">Politics</Select.Option>
              <Select.Option value="tech">Tech</Select.Option>
            </Select>
          </Col>
          <Col span={6}>
            <Input
              type="number"
              placeholder="最小机会评分"
              onChange={(e) => setMinOpportunity(Number(e.target.value))}
            />
          </Col>
          <Col span={6}>
            <Select
              placeholder="排序方式"
              style={{ width: '100%' }}
              value={sortBy}
              onChange={setSortBy}
            >
              <Select.Option value="opportunity_score">机会评分</Select.Option>
              <Select.Option value="created_at">最新分析</Select.Option>
              <Select.Option value="volume_24h">交易量</Select.Option>
              <Select.Option value="divergence">概率差异</Select.Option>
            </Select>
          </Col>
        </Row>
      </Card>
      
      {/* 数据表格 */}
      <Card>
        <Table
          columns={columns}
          dataSource={data?.items || []}
          loading={isLoading}
          rowKey="market_id"
          pagination={false}
        />
        
        <Pagination
          current={page}
          pageSize={pageSize}
          total={data?.total || 0}
          onChange={(p, ps) => {
            setPage(p);
            setPageSize(ps);
          }}
          showSizeChanger
          showTotal={(total) => `共 ${total} 条`}
          style={{ marginTop: 16, textAlign: 'right' }}
        />
      </Card>
    </div>
  );
};
```

### 8. 性能优化

#### 8.1 数据库连接池

```python
# app/utils/db_pool.py
from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool
import os

engine = create_engine(
    os.getenv('DATABASE_URL'),
    poolclass=QueuePool,
    pool_size=20,          # 连接池大小
    max_overflow=10,       # 最大溢出连接数
    pool_timeout=30,       # 获取连接超时
    pool_recycle=3600,     # 连接回收时间
    pool_pre_ping=True,    # 连接前检查
    echo=False
)
```

#### 8.2 批量操作

```python
# app/services/polymarket_batch_service.py
from typing import List, Dict
import asyncio

class PolymarketBatchService:
    """批量操作服务"""
    
    async def batch_analyze(self, market_ids: List[str]) -> List[Dict]:
        """批量分析市场"""
        # 分批处理，每批10个
        batch_size = 10
        results = []
        
        for i in range(0, len(market_ids), batch_size):
            batch = market_ids[i:i + batch_size]
            
            # 并发分析
            tasks = [self.analyze_market(mid) for mid in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            results.extend(batch_results)
            
            # 避免过载
            await asyncio.sleep(1)
        
        return results
    
    def batch_insert(self, records: List[Dict]):
        """批量插入数据库"""
        from sqlalchemy import insert
        from app.models import PolymarketAnalysis
        
        with engine.begin() as conn:
            conn.execute(
                insert(PolymarketAnalysis),
                records
            )
```

### 9. 安全措施

#### 9.1 API 认证

```python
# app/middleware/auth.py
from functools import wraps
from flask import request, jsonify
import jwt
import os

def require_auth(f):
    """API 认证装饰器"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        
        if not token:
            return jsonify({'error': 'No token provided'}), 401
        
        try:
            # 移除 'Bearer ' 前缀
            token = token.replace('Bearer ', '')
            
            # 验证 JWT
            payload = jwt.decode(
                token,
                os.getenv('JWT_SECRET'),
                algorithms=['HS256']
            )
            
            # 将用户信息添加到请求上下文
            request.user_id = payload['user_id']
            
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401
        
        return f(*args, **kwargs)
    
    return decorated
```

#### 9.2 输入验证

```python
# app/validators/polymarket_validators.py
from marshmallow import Schema, fields, validate, ValidationError

class MarketQuerySchema(Schema):
    """市场查询参数验证"""
    page = fields.Int(
        missing=1,
        validate=validate.Range(min=1, max=10000)
    )
    page_size = fields.Int(
        missing=20,
        validate=validate.Range(min=1, max=100)
    )
    category = fields.Str(
        validate=validate.OneOf(['crypto', 'sports', 'politics', 'tech'])
    )
    min_opportunity = fields.Float(
        missing=0,
        validate=validate.Range(min=0, max=100)
    )
    sort_by = fields.Str(
        missing='opportunity_score',
        validate=validate.OneOf([
            'opportunity_score', 'created_at', 
            'volume_24h', 'divergence'
        ])
    )
    order = fields.Str(
        missing='desc',
        validate=validate.OneOf(['asc', 'desc'])
    )

def validate_query_params(schema_class):
    """验证查询参数装饰器"""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            schema = schema_class()
            try:
                validated = schema.load(request.args)
                request.validated_args = validated
            except ValidationError as err:
                return jsonify({
                    'code': 0,
                    'msg': 'Invalid parameters',
                    'errors': err.messages
                }), 400
            
            return f(*args, **kwargs)
        return wrapper
    return decorator
```

#### 9.3 SQL 注入防护

```python
# 始终使用参数化查询
# ✅ 正确
conn.execute(text("SELECT * FROM markets WHERE id = :id"), {"id": market_id})

# ❌ 错误
conn.execute(f"SELECT * FROM markets WHERE id = '{market_id}'")
```

### 10. 部署检查清单

#### 10.1 上线前检查

- [ ] 环境变量配置完整
  - [ ] DATABASE_URL
  - [ ] REDIS_URL
  - [ ] POLYMARKET_API_KEY
  - [ ] POLYMARKET_PRIVATE_KEY
  - [ ] JWT_SECRET
  - [ ] OPENAI_API_KEY

- [ ] 数据库准备
  - [ ] 创建所有表
  - [ ] 创建索引
  - [ ] 创建物化视图
  - [ ] 配置分区表
  - [ ] 设置定时任务（刷新物化视图）

- [ ] Redis 配置
  - [ ] 持久化配置（AOF + RDB）
  - [ ] 内存限制
  - [ ] 淘汰策略

- [ ] 监控配置
  - [ ] Prometheus 指标暴露
  - [ ] Grafana 仪表板导入
  - [ ] 告警规则配置
  - [ ] 日志收集配置

- [ ] 安全配置
  - [ ] HTTPS 证书
  - [ ] 防火墙规则
  - [ ] API 限流
  - [ ] JWT 密钥轮换

- [ ] 性能测试
  - [ ] 压力测试
  - [ ] 并发测试
  - [ ] 数据库查询优化
  - [ ] 缓存命中率测试

#### 10.2 启动顺序

```bash
# 1. 启动基础设施
docker-compose up -d postgres redis

# 2. 运行数据库迁移
python manage.py db upgrade

# 3. 创建索引和物化视图
psql -f scripts/create_indexes.sql

# 4. 启动 API 服务
docker-compose up -d api

# 5. 启动 Worker
docker-compose up -d worker beat

# 6. 启动监控
docker-compose up -d prometheus grafana

# 7. 启动 Nginx
docker-compose up -d nginx

# 8. 验证服务
curl http://localhost/api/v2/health
```

### 11. 成本估算

#### 11.1 云服务成本（AWS 示例）

| 服务 | 规格 | 月成本（USD） |
|------|------|--------------|
| EC2 (API) | t3.medium x 3 | $120 |
| EC2 (Worker) | t3.small x 2 | $60 |
| RDS PostgreSQL | db.t3.medium | $80 |
| ElastiCache Redis | cache.t3.small | $40 |
| ALB | 负载均衡器 | $25 |
| CloudWatch | 日志和监控 | $30 |
| S3 | 备份存储 | $10 |
| **总计** | | **$365/月** |

#### 11.2 第三方服务成本

| 服务 | 用途 | 月成本（USD） |
|------|------|--------------|
| OpenAI API | AI 分析 | $100-500 |
| Polymarket API | 市场数据 | 免费 |
| Grafana Cloud | 监控（可选） | $0-50 |
| **总计** | | **$100-550/月** |

**总成本估算：$465-915/月**

### 12. 扩展策略

#### 12.1 水平扩展

```yaml
# 根据负载自动扩展
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: polymarket-api-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: polymarket-api
  minReplicas: 3
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

#### 12.2 数据库扩展

```python
# 读写分离
from sqlalchemy import create_engine

# 主库（写）
master_engine = create_engine(os.getenv('DATABASE_MASTER_URL'))

# 从库（读）
slave_engines = [
    create_engine(os.getenv('DATABASE_SLAVE1_URL')),
    create_engine(os.getenv('DATABASE_SLAVE2_URL'))
]

def get_read_engine():
    """随机选择一个从库"""
    import random
    return random.choice(slave_engines)
```

#### 12.3 缓存分层

```
┌─────────────────────────────────────┐
│  L1: 应用内存缓存 (LRU, 5分钟)       │
└─────────────────────────────────────┘
              ↓ miss
┌─────────────────────────────────────┐
│  L2: Redis 缓存 (10分钟)            │
└─────────────────────────────────────┘
              ↓ miss
┌─────────────────────────────────────┐
│  L3: 数据库物化视图 (实时)           │
└─────────────────────────────────────┘
              ↓ miss
┌─────────────────────────────────────┐
│  L4: 数据库查询                      │
└─────────────────────────────────────┘
```

### 13. 实施路线图

#### Phase 1: 基础设施（1-2周）
- [ ] 搭建 Docker 环境
- [ ] 配置数据库和 Redis
- [ ] 实现基础 API v2
- [ ] 添加数据库索引
- [ ] 基础监控和日志

#### Phase 2: 核心功能（2-3周）
- [ ] 重构 Worker 服务
- [ ] 实现 Celery 任务队列
- [ ] 添加缓存层
- [ ] 实现分页和筛选
- [ ] 多选项市场识别优化

#### Phase 3: 高级功能（2-3周）
- [ ] WebSocket 实时推送
- [ ] 前端 Dashboard
- [ ] 高级监控和告警
- [ ] 性能优化
- [ ] 安全加固

#### Phase 4: 测试和上线（1-2周）
- [ ] 压力测试
- [ ] 安全测试
- [ ] 灰度发布
- [ ] 生产环境部署
- [ ] 文档完善

**总时间：6-10周**

### 14. 维护计划

#### 14.1 日常维护

- **每日**
  - 检查监控告警
  - 查看错误日志
  - 验证数据更新

- **每周**
  - 数据库性能分析
  - 缓存命中率分析
  - 成本分析

- **每月**
  - 数据库备份验证
  - 安全补丁更新
  - 性能优化评估

#### 14.2 备份策略

```bash
# 数据库备份脚本
#!/bin/bash
# backup.sh

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backups/postgres"

# 全量备份
pg_dump -h localhost -U quantdinger quantdinger > \
  $BACKUP_DIR/polymarket_$DATE.sql

# 压缩
gzip $BACKUP_DIR/polymarket_$DATE.sql

# 上传到 S3
aws s3 cp $BACKUP_DIR/polymarket_$DATE.sql.gz \
  s3://my-backups/polymarket/

# 删除7天前的本地备份
find $BACKUP_DIR -name "*.sql.gz" -mtime +7 -delete
```

### 15. 故障恢复

#### 15.1 常见问题处理

**问题：Worker 停止工作**
```bash
# 检查 Worker 状态
docker-compose ps worker

# 查看日志
docker-compose logs worker --tail=100

# 重启 Worker
docker-compose restart worker
```

**问题：数据库连接耗尽**
```sql
-- 查看当前连接
SELECT count(*) FROM pg_stat_activity;

-- 终止空闲连接
SELECT pg_terminate_backend(pid) 
FROM pg_stat_activity 
WHERE state = 'idle' 
  AND state_change < NOW() - INTERVAL '10 minutes';
```

**问题：Redis 内存不足**
```bash
# 查看内存使用
redis-cli INFO memory

# 清理过期键
redis-cli --scan --pattern "market_list:*" | xargs redis-cli DEL

# 调整淘汰策略
redis-cli CONFIG SET maxmemory-policy allkeys-lru
```

#### 15.2 灾难恢复

```bash
# 1. 从备份恢复数据库
gunzip polymarket_20260308.sql.gz
psql -h localhost -U quantdinger quantdinger < polymarket_20260308.sql

# 2. 重建索引
psql -f scripts/create_indexes.sql

# 3. 刷新物化视图
psql -c "REFRESH MATERIALIZED VIEW CONCURRENTLY mv_polymarket_high_opportunities;"

# 4. 重启所有服务
docker-compose restart
```

## 总结

这个生产环境方案提供了：

1. **可靠性**：错误处理、重试机制、健康检查
2. **可扩展性**：水平扩展、负载均衡、数据库分区
3. **可观测性**：监控、日志、告警
4. **高性能**：缓存、批量操作、数据库优化
5. **安全性**：认证、限流、输入验证
6. **可维护性**：结构化代码、文档、自动化部署

**关键改进点：**
- ✅ 从测试脚本升级到生产级服务
- ✅ 添加完整的监控和告警
- ✅ 实现缓存和性能优化
- ✅ 提供 RESTful API 和 WebSocket
- ✅ 支持水平扩展和高可用
- ✅ 完善的部署和维护方案
- ✅ 多选项市场识别和展示优化

**下一步行动：**
1. 根据实际需求选择合适的 Phase 开始实施
2. 准备云服务账号和资源
3. 配置 CI/CD 流程
4. 开始 Phase 1 基础设施搭建

