#!/bin/bash
# 循环运行 Polymarket Worker 100次

echo "========================================"
echo "循环运行 Polymarket Worker"
echo "========================================"
echo ""
echo "配置:"
echo "  循环次数: 100"
echo "  每次分析: 20个市场"
echo "  增强交易数据: 是"
echo ""

for i in {1..100}; do
    echo "----------------------------------------"
    echo "[第 $i/100 次] $(date '+%Y-%m-%d %H:%M:%S')"
    echo "----------------------------------------"
    
    # 运行 worker
    python run_once_polymarket_worker.py \
        --limit 50 \
        --max-analyze 20 \
        --enrich-trading-data
    
    EXIT_CODE=$?
    
    if [ $EXIT_CODE -ne 0 ]; then
        echo ""
        echo "⚠️  Worker 执行失败 (退出码: $EXIT_CODE)"
        echo "   继续下一次..."
    fi
    
    echo ""
    echo "等待 5 秒后继续..."
    sleep 5
    echo ""
done

echo "========================================"
echo "完成！共执行 100 次"
echo "========================================"
