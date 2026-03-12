#!/bin/bash

# QuantDinger Python API 启动脚本

# 激活虚拟环境（如果使用虚拟环境）
# source venv/bin/activate

# 检查依赖是否安装
if ! python -c "import flask" 2>/dev/null; then
    echo "正在安装依赖..."
    pip install -r requirements.txt
fi

# 启动服务
echo "启动 QuantDinger Python API 服务..."
echo "服务地址: http://0.0.0.0:5000"

# 创建日志目录
mkdir -p logs

# 开发环境（使用新的入口文件）
python run.py

# 生产环境（使用 gunicorn）
# gunicorn -w 4 -b 0.0.0.0:5000 --timeout 120 --access-logfile logs/access.log --error-logfile logs/error.log "run:create_app()"

