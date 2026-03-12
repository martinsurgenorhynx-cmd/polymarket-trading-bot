# 本地运行指南

## 快速启动（5 分钟）

### 前置条件

- Python 3.10+
- PostgreSQL 14+ （或使用 Docker）

---

## 方式 1：使用 Docker（推荐，最简单）

### 1. 创建 .env 文件

```bash
cd backend_api_python
cp env.example .env
```

### 2. 编辑 .env 文件

最小配置（只需要这几行）：

```bash
# 管理员账号
ADMIN_USER=admin
ADMIN_PASSWORD=123456

# LLM API Key（必需，用于 AI 分析）
OPENROUTER_API_KEY=your_api_key_here

# 数据库（Docker 会自动创建）
DATABASE_URL=postgresql://quantdinger:quantdinger123@postgres:5432/quantdinger
```

### 3. 启动服务

```bash
# 回到项目根目录
cd ..

# 启动所有服务（数据库 + 后端 + 前端）
docker-compose up -d
```

### 4. 访问系统

- 前端：http://localhost:8888
- 后端 API：http://localhost:5000
- 登录账号：admin / 123456

### 5. 测试 AI 分析

```bash
# 登录获取 token
curl -X POST http://localhost:5000/api/user/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"123456"}'

# 使用返回的 token 测试 AI 分析
curl -X POST http://localhost:5000/api/fast-analysis/analyze \
  -H "Authorization: Bearer <your_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "market": "Crypto",
    "symbol": "BTC/USDT",
    "language": "zh-CN"
  }'
```

---

## 方式 2：本地 Python 运行（开发模式）

### 1. 安装 PostgreSQL

#### macOS (Homebrew)
```bash
brew install postgresql@14
brew services start postgresql@14
```

#### Ubuntu/Debian
```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql
```

#### Windows
下载安装：https://www.postgresql.org/download/windows/

### 2. 创建数据库

```bash
# 进入 PostgreSQL
psql postgres

# 创建数据库和用户
CREATE DATABASE quantdinger;
CREATE USER quantdinger WITH ENCRYPTED PASSWORD 'quantdinger123';
GRANT ALL PRIVILEGES ON DATABASE quantdinger TO quantdinger;
\q
```

### 3. 初始化数据库表

```bash
cd backend_api_python

# 导入数据库结构
psql -U quantdinger -d quantdinger -f migrations/init.sql
```

如果提示密码，输入：`quantdinger123`

### 4. 安装 Python 依赖

```bash
# 创建虚拟环境（推荐）
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# 或
venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt
```

### 5. 创建 .env 文件

```bash
cp env.example .env
```

编辑 `.env`，修改以下配置：

```bash
# 数据库连接（本地）
DATABASE_URL=postgresql://quantdinger:quantdinger123@localhost:5432/quantdinger

# 管理员账号
ADMIN_USER=admin
ADMIN_PASSWORD=123456
SECRET_KEY=your-secret-key-change-me

# LLM API Key（必需）
OPENROUTER_API_KEY=your_api_key_here

# 开发模式
PYTHON_API_DEBUG=True
PYTHON_API_HOST=0.0.0.0
PYTHON_API_PORT=5000
```

### 6. 启动后端服务

```bash
python run.py
```

你应该看到：

```
 * Running on http://0.0.0.0:5000
 * Debug mode: on
```

### 7. 测试 API

打开浏览器访问：http://localhost:5000/api/health

应该返回：
```json
{
  "status": "ok",
  "timestamp": "2024-01-01T00:00:00"
}
```

---

## 获取 OpenRouter API Key

### 1. 注册 OpenRouter

访问：https://openrouter.ai/

### 2. 创建 API Key

1. 登录后点击右上角头像
2. 选择 "Keys"
3. 点击 "Create Key"
4. 复制生成的 key（格式：`sk-or-v1-xxx`）

### 3. 充值（可选）

- OpenRouter 支持按需付费
- 新用户通常有免费额度
- 价格：GPT-4o 约 $0.005/1K tokens

### 4. 配置到 .env

```bash
OPENROUTER_API_KEY=sk-or-v1-your-key-here
```

---

## 常见问题

### 1. 数据库连接失败

**错误**：`could not connect to server: Connection refused`

**解决**：
```bash
# 检查 PostgreSQL 是否运行
# macOS
brew services list

# Linux
sudo systemctl status postgresql

# 启动 PostgreSQL
brew services start postgresql@14  # macOS
sudo systemctl start postgresql    # Linux
```

### 2. 端口被占用

**错误**：`Address already in use`

**解决**：
```bash
# 查看占用端口的进程
lsof -i :5000  # macOS/Linux
netstat -ano | findstr :5000  # Windows

# 杀死进程或修改 .env 中的端口
PYTHON_API_PORT=5001
```

### 3. 依赖安装失败

**错误**：`error: Microsoft Visual C++ 14.0 or greater is required`

**解决**（Windows）：
- 安装 Visual Studio Build Tools
- 或使用预编译的 wheel：`pip install --only-binary :all: psycopg2-binary`

### 4. AI 分析失败

**错误**：`LLM API key not configured`

**解决**：
1. 确认 `.env` 中配置了 `OPENROUTER_API_KEY`
2. 检查 key 是否有效
3. 检查网络连接（可能需要代理）

### 5. 需要代理

如果你的网络无法访问 OpenRouter，配置代理：

```bash
# .env 文件
PROXY_PORT=7890
PROXY_HOST=127.0.0.1
PROXY_SCHEME=socks5h
```

---

## 验证安装

### 1. 检查数据库

```bash
psql -U quantdinger -d quantdinger -c "\dt"
```

应该看到所有表：
```
 qd_strategies_trading
 qd_strategy_positions
 qd_strategy_trades
 pending_orders
 qd_users
 ...
```

### 2. 检查后端 API

```bash
curl http://localhost:5000/api/health
```

### 3. 登录测试

```bash
curl -X POST http://localhost:5000/api/user/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"123456"}'
```

应该返回 token：
```json
{
  "code": 1,
  "msg": "success",
  "data": {
    "token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
    "user": {
      "id": 1,
      "username": "admin",
      "role": "admin"
    }
  }
}
```

### 4. 测试 AI 分析

```bash
# 使用上一步获取的 token
TOKEN="your_token_here"

curl -X POST http://localhost:5000/api/fast-analysis/analyze \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "market": "Crypto",
    "symbol": "BTC/USDT",
    "language": "zh-CN",
    "timeframe": "1D"
  }'
```

应该返回 AI 分析结果（需要等待 5-10 秒）：
```json
{
  "code": 1,
  "msg": "success",
  "data": {
    "recommendation": "BUY",
    "confidence": 75,
    "entry_price": 50000,
    "stop_loss": 48000,
    "take_profit": 55000,
    "analysis": {
      "technical": "...",
      "fundamental": "...",
      "sentiment": "..."
    }
  }
}
```

---

## 启动前端（可选）

如果你想要完整的 UI：

### 1. 安装 Node.js

访问：https://nodejs.org/

### 2. 安装前端依赖

```bash
cd quantdinger_vue
npm install
```

### 3. 启动前端开发服务器

```bash
npm run serve
```

### 4. 访问前端

打开浏览器：http://localhost:8080

---

## 开发工具推荐

### 1. 数据库管理

- **DBeaver**（免费）：https://dbeaver.io/
- **pgAdmin**（官方）：https://www.pgadmin.org/
- **TablePlus**（macOS）：https://tableplus.com/

### 2. API 测试

- **Postman**：https://www.postman.com/
- **Insomnia**：https://insomnia.rest/
- **curl**（命令行）

### 3. 日志查看

```bash
# 实时查看日志
tail -f logs/app.log

# 只看错误
tail -f logs/app.log | grep ERROR

# 只看 AI 分析
tail -f logs/app.log | grep FastAnalysis
```

---

## 下一步

### 1. 创建策略

访问前端 → 策略管理 → 创建新策略

### 2. 运行回测

选择策略 → 回测 → 查看结果

### 3. 使用 AI 分析

市场页面 → 选择交易对 → 点击"AI 分析"

### 4. 查看 Dashboard

Dashboard → 查看策略表现、持仓、交易记录

---

## 停止服务

### Docker 方式

```bash
docker-compose down
```

### 本地 Python 方式

按 `Ctrl+C` 停止后端服务

---

## 完全卸载

### Docker 方式

```bash
# 停止并删除容器
docker-compose down -v

# 删除镜像
docker rmi quantdinger_backend quantdinger_frontend
```

### 本地方式

```bash
# 删除数据库
psql postgres -c "DROP DATABASE quantdinger;"
psql postgres -c "DROP USER quantdinger;"

# 删除虚拟环境
rm -rf venv

# 删除日志
rm -rf logs
```

---

## 获取帮助

- GitHub Issues：https://github.com/your-repo/issues
- 文档：查看项目根目录的 README.md
- 日志：`logs/app.log`

---

## 总结

最简单的启动方式：

```bash
# 1. 创建配置
cp env.example .env
# 编辑 .env，设置 OPENROUTER_API_KEY

# 2. 启动（Docker）
docker-compose up -d

# 3. 访问
open http://localhost:8888
```

就这么简单！
