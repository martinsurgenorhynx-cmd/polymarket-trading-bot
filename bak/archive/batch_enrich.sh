#!/bin/bash
# 批量增强市场数据脚本

echo "================================"
echo "批量增强 Polymarket 市场数据"
echo "================================"
echo ""

# 配置
MAX_RUNS=100
BATCH_SIZE=20

for i in $(seq 1 $MAX_RUNS); do
    echo "[批次 $i/$MAX_RUNS] 增强 $BATCH_SIZE 个市场..."
    
    # 运行增强脚本
    python enrich_analyzed_markets.py --limit $BATCH_SIZE 2>&1 | grep -E "(找到|成功增强|现在有|完成)"
    
    # 检查是否还有需要增强的市场
    REMAINING=$(python -c "
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath('.'))))
from dotenv import load_dotenv
load_dotenv('.env')
from app.utils.db import get_db_connection

with get_db_connection() as conn:
    cursor = conn.cursor()
    cursor.execute('''
        SELECT COUNT(*) as count
        FROM qd_polymarket_ai_analysis a
        INNER JOIN qd_polymarket_markets m ON a.market_id = m.market_id
        WHERE a.opportunity_score > 60
          AND m.condition_id IS NULL
          AND m.status = 'active'
          AND m.volume_24h > 1000
    ''')
    print(cursor.fetchone()['count'])
" 2>/dev/null)
    
    echo "  剩余需要增强: $REMAINING"
    echo ""
    
    # 如果没有剩余，退出
    if [ "$REMAINING" = "0" ]; then
        echo "✓ 所有市场都已增强！"
        break
    fi
    
    # 延迟2秒
    sleep 2
done

echo ""
echo "================================"
echo "批量增强完成"
echo "================================"
