#!/bin/bash

# QuantDinger 本地启动脚本
# 自动检查并启动所有必要的服务

set -e  # 遇到错误立即退出

echo "🚀 QuantDinger 本地启动脚本"
echo "================================"
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 进入后端目录
cd backend_api_python

# 1. 检查并创建 .env 文件
echo "📝 检查配置文件..."
if [ ! -f .env ]; then
    if [ -f env ]; then
        echo "${YELLOW}⚠️  发现 env 文件，正在重命名为 .env${NC}"
        mv env .env
        echo "${GREEN}✅ 已创建 .env 文件${NC}"
        echo ""
        echo "${YELLOW}⚠️  请编辑 .env 文件，确保以下配置正确：${NC}"
        echo "   1. DATABASE_URL=postgresql://quantdinger:quantdinger123@localhost:5432/quantdinger"
        echo "   2. OPENAI_API_KEY=你的API密钥"
        echo ""
        echo "按回车键继续..."
        read
    else
        echo "${RED}❌ 未找到配置文件${NC}"
        echo "请从 env.example 复制并创建 .env 文件"
        exit 1
    fi
else
    echo "${GREEN}✅ .env 文件存在${NC}"
fi

# 2. 检查 PostgreSQL
echo ""
echo "🗄️  检查 PostgreSQL..."
if ! command -v psql &> /dev/null; then
    echo "${RED}❌ PostgreSQL 未安装${NC}"
    echo "请运行: brew install postgresql@14"
    exit 1
fi
echo "${GREEN}✅ PostgreSQL 已安装 ($(psql --version))${NC}"

# 3. 检查 PostgreSQL 是否运行
echo ""
echo "🔍 检查 PostgreSQL 服务..."
if ! pg_isready -h localhost -p 5432 &> /dev/null; then
    echo "${YELLOW}⚠️  PostgreSQL 未运行，正在启动...${NC}"
    brew services start postgresql@14
    sleep 3
    if ! pg_isready -h localhost -p 5432 &> /dev/null; then
        echo "${RED}❌ PostgreSQL 启动失败${NC}"
        exit 1
    fi
fi
echo "${GREEN}✅ PostgreSQL 服务运行中${NC}"

# 4. 检查数据库是否存在
echo ""
echo "📊 检查数据库..."
if ! psql -U quantdinger -d quantdinger -c "SELECT 1" &> /dev/null; then
    echo "${YELLOW}⚠️  数据库不存在，正在创建...${NC}"
    
    # 创建数据库和用户
    psql postgres <<EOF
CREATE DATABASE quantdinger;
CREATE USER quantdinger WITH ENCRYPTED PASSWORD 'quantdinger123';
GRANT ALL PRIVILEGES ON DATABASE quantdinger TO quantdinger;
EOF
    
    if [ $? -eq 0 ]; then
        echo "${GREEN}✅ 数据库创建成功${NC}"
    else
        echo "${RED}❌ 数据库创建失败${NC}"
        echo "请手动执行："
        echo "  psql postgres"
        echo "  CREATE DATABASE quantdinger;"
        echo "  CREATE USER quantdinger WITH PASSWORD 'quantdinger123';"
        echo "  GRANT ALL PRIVILEGES ON DATABASE quantdinger TO quantdinger;"
        exit 1
    fi
else
    echo "${GREEN}✅ 数据库已存在${NC}"
fi

# 5. 检查数据库表
echo ""
echo "📋 检查数据库表..."
TABLE_COUNT=$(psql -U quantdinger -d quantdinger -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';" 2>/dev/null | tr -d ' ')

if [ "$TABLE_COUNT" = "0" ] || [ -z "$TABLE_COUNT" ]; then
    echo "${YELLOW}⚠️  数据库表不存在，正在初始化...${NC}"
    PGPASSWORD=quantdinger123 psql -U quantdinger -d quantdinger -f migrations/init.sql
    if [ $? -eq 0 ]; then
        echo "${GREEN}✅ 数据库表初始化成功${NC}"
    else
        echo "${RED}❌ 数据库表初始化失败${NC}"
        exit 1
    fi
else
    echo "${GREEN}✅ 数据库表已存在 ($TABLE_COUNT 个表)${NC}"
fi

# 6. 检查 Python 依赖
echo ""
echo "🐍 检查 Python 依赖..."
if ! python3 -c "import flask" &> /dev/null; then
    echo "${YELLOW}⚠️  依赖未安装，正在安装...${NC}"
    pip3 install -r requirements.txt
    if [ $? -eq 0 ]; then
        echo "${GREEN}✅ 依赖安装成功${NC}"
    else
        echo "${RED}❌ 依赖安装失败${NC}"
        exit 1
    fi
else
    echo "${GREEN}✅ Python 依赖已安装${NC}"
fi

# 7. 启动后端服务
echo ""
echo "================================"
echo "${GREEN}🎯 启动后端服务...${NC}"
echo "================================"
echo ""
echo "访问地址："
echo "  - API: http://localhost:5000"
echo "  - 健康检查: http://localhost:5000/api/health"
echo ""
echo "登录信息："
echo "  - 用户名: quantdinger"
echo "  - 密码: 123456"
echo ""
echo "按 Ctrl+C 停止服务"
echo ""

python3 run.py
