# 快速启动（你的环境）

## 当前状态

你已经有了配置文件 `env`，但需要：
1. 重命名为 `.env`
2. 修改数据库配置（本地运行）
3. 配置 LLM API Key

---

## 步骤 1：重命名配置文件

```bash
cd backend_api_python
mv env .env
```

---

## 步骤 2：修改 .env 配置

打开 `.env` 文件，修改以下几行：

### 必须修改的配置

```bash
# 数据库连接（改为本地）
DATABASE_URL=postgresql://quantdinger:quantdinger123@localhost:5432/quantdinger

# LLM API Key（你已经配置了阿里云，但需要确认 API Key）
OPENAI_API_KEY=你的阿里云API_KEY
OPENAI_BASE_URL=https://coding.dashscope.aliyuncs.com/v1
OPENAI_MODEL=glm-5
LLM_PROVIDER=openai

# 开发模式
PYTHON_API_DEBUG=True
```

---

## 步骤 3：安装 PostgreSQL

### macOS (Homebrew)
```bash
brew install postgresql@14
brew services start postgresql@14
```

### 检查是否已安装
```bash
psql --version
```

---

## 步骤 4：创建数据库

```bash
# 进入 PostgreSQL
psql postgres

# 在 psql 中执行：
CREATE DATABASE quantdinger;
CREATE USER quantdinger WITH ENCRYPTED PASSWORD 'quantdinger123';
GRANT ALL PRIVILEGES ON DATABASE quantdinger TO quantdinger;
\q
```

---

## 步骤 5：初始化数据库表

```bash
cd backend_api_python
psql -U quantdinger -d quantdinger -f migrations/init.sql
```

如果提示输入密码，输入：`quantdinger123`

---

## 步骤 6：安装 Python 依赖

```bash
# 检查 Python 版本
python3 --version  # 需要 3.10+

# 安装依赖
pip3 install -r requirements.txt
```

---

## 步骤 7：启动后端

```bash
python3 run.py
```

你应该看到：
```
 * Running on http://0.0.0.0:5000
 * Debug mode: on
```

---

## 步骤 8：测试 API

### 1. 健康检查
```bash
curl http://localhost:5000/api/health
```

### 2. 登录
```bash
curl -X POST http://localhost:5000/api/user/login \
  -H "Content-Type: application/json" \
  -d '{"username":"quantdinger","password":"123456"}'
```

保存返回的 token。

### 3. 测试 AI 分析
```bash
TOKEN="你的token"

curl -X POST http://localhost:5000/api/fast-analysis/analyze \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "market": "Crypto",
    "symbol": "BTC/USDT",
    "language": "zh-CN"
  }'
```

---

## 常见问题

### 1. PostgreSQL 未安装

**错误**：`psql: command not found`

**解决**：
```bash
# macOS
brew install postgresql@14

# 或使用 Docker
docker run -d \
  --name postgres \
  -e POSTGRES_USER=quantdinger \
  -e POSTGRES_PASSWORD=quantdinger123 \
  -e POSTGRES_DB=quantdinger \
  -p 5432:5432 \
  postgres:14
```

### 2. 数据库连接失败

**错误**：`could not connect to server`

**解决**：
```bash
# 启动 PostgreSQL
brew services start postgresql@14

# 或检查 Docker 容器
docker ps | grep postgres
```

### 3. 端口被占用

**错误**：`Address already in use`

**解决**：
```bash
# 查看占用端口的进程
lsof -i :5000

# 杀死进程
kill -9 <PID>

# 或修改 .env 中的端口
PYTHON_API_PORT=5001
```

### 4. 依赖安装失败

**错误**：`error: command 'gcc' failed`

**解决**：
```bash
# macOS
xcode-select --install

# 或使用预编译包
pip3 install --only-binary :all: -r requirements.txt
```

---

## 一键启动脚本（推荐）

创建 `start.sh`：

```bash
#!/bin/bash

echo "🚀 启动 QuantDinger 后端..."

# 检查 .env 文件
if [ ! -f .env ]; then
    echo "❌ .env 文件不存在，正在创建..."
    mv env .env
    echo "✅ 已创建 .env 文件，请编辑配置后重新运行"
    exit 1
fi

# 检查 PostgreSQL
if ! command -v psql &> /dev/null; then
    echo "❌ PostgreSQL 未安装"
    echo "请运行: brew install postgresql@14"
    exit 1
fi

# 检查数据库是否存在
if ! psql -U quantdinger -d quantdinger -c "SELECT 1" &> /dev/null; then
    echo "❌ 数据库不存在或无法连接"
    echo "请运行以下命令创建数据库："
    echo "  psql postgres"
    echo "  CREATE DATABASE quantdinger;"
    echo "  CREATE USER quantdinger WITH PASSWORD 'quantdinger123';"
    echo "  GRANT ALL PRIVILEGES ON DATABASE quantdinger TO quantdinger;"
    exit 1
fi

# 检查表是否存在
TABLE_COUNT=$(psql -U quantdinger -d quantdinger -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';" 2>/dev/null | tr -d ' ')

if [ "$TABLE_COUNT" = "0" ]; then
    echo "📊 初始化数据库表..."
    psql -U quantdinger -d quantdinger -f migrations/init.sql
    echo "✅ 数据库表初始化完成"
fi

# 启动后端
echo "🎯 启动后端服务..."
python3 run.py
```

使用方法：
```bash
chmod +x start.sh
./start.sh
```

---

## 验证安装

运行以下命令验证所有组件：

```bash
# 1. 检查 PostgreSQL
psql -U quantdinger -d quantdinger -c "\dt"

# 2. 检查 Python 依赖
python3 -c "import flask, psycopg2, pandas; print('✅ 依赖正常')"

# 3. 检查后端
curl http://localhost:5000/api/health

# 4. 检查登录
curl -X POST http://localhost:5000/api/user/login \
  -H "Content-Type: application/json" \
  -d '{"username":"quantdinger","password":"123456"}'
```

---

## 下一步

1. ✅ 后端运行成功
2. 📱 启动前端（可选）
3. 🎨 访问 UI：http://localhost:8080
4. 🤖 测试 AI 分析功能

---

## 获取帮助

- 查看日志：`tail -f logs/app.log`
- 查看错误：`tail -f logs/app.log | grep ERROR`
- 重启服务：按 `Ctrl+C` 停止，然后重新运行 `python3 run.py`
