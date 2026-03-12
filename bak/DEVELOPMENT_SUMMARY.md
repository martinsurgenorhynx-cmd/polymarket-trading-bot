# QuantDinger 开发环境总结

## 当前状态

### ✅ 已完成

1. **后端服务** - 运行在 `http://localhost:5001`
   - Flask API 服务正常运行
   - 数据库连接正常（PostgreSQL）
   - 用户认证系统工作正常
   - 所有API端点已注册

2. **前端服务** - 运行在 `http://localhost:8080`
   - 静态文件服务器已启动
   - 前端已构建（dist目录）

3. **数据库**
   - PostgreSQL 14.19 运行正常
   - 数据库名: `quantdinger`
   - 用户: `quantdinger` / 密码: `quantdinger123`
   - 已有 32 个表，包含基础数据

4. **本地调试工具**
   - 创建了多个调试脚本，无需启动服务器即可测试
   - 详见 `backend_api_python/DEBUG_GUIDE.md`

## 访问信息

### 后端 API
- **地址**: `http://localhost:5001`
- **健康检查**: `http://localhost:5001/api/health`
- **登录端点**: `http://localhost:5001/api/auth/login`

### 前端
- **地址**: `http://localhost:8080`
- **注意**: 前端和后端在不同端口，需要配置代理或CORS

### 数据库
- **主机**: localhost
- **端口**: 5432
- **数据库**: quantdinger
- **用户**: quantdinger
- **密码**: quantdinger123

### 默认账号
- **用户名**: `quantdinger`
- **密码**: `123456`
- **角色**: admin

## API 使用示例

### 1. 登录获取Token

```bash
curl -X POST http://localhost:5001/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"quantdinger","password":"123456"}'
```

响应：
```json
{
  "code": 1,
  "msg": "Login successful",
  "data": {
    "token": "eyJhbGci...",
    "userinfo": {
      "id": 1,
      "username": "quantdinger",
      "role": {
        "id": "admin",
        "permissions": [...]
      }
    }
  }
}
```

### 2. 使用Token访问API

```bash
curl -X POST http://localhost:5001/api/fast-analysis/analyze \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -d '{
    "market": "Crypto",
    "symbol": "BTC/USDT",
    "timeframe": "1D",
    "language": "zh-CN"
  }'
```

## 本地调试（无需启动服务）

### 快速测试所有服务

```bash
cd backend_api_python
python simple_test.py
```

### 交互式调试

```bash
python -i simple_test.py
```

然后可以直接使用：

```python
# 查询数据库
from app.utils.db import get_db_connection
with get_db_connection() as db:
    cur = db.cursor()
    cur.execute("SELECT * FROM qd_users")
    print(cur.fetchall())
    cur.close()

# 使用服务
from app.services.user_service import get_user_service
service = get_user_service()
user = service.get_user_by_username('quantdinger')
print(user)
```

### 完整调试示例

```bash
python debug_examples.py
```

详细文档: `backend_api_python/DEBUG_GUIDE.md`

## API 权限说明

### 关于Swagger文档
- ❌ 项目中没有内置 Swagger/OpenAPI 文档
- 可以通过查看 `backend_api_python/app/routes/` 目录了解所有端点

### 关于权限控制
- ✅ 大部分API需要登录（使用 `@login_required` 装饰器）
- ✅ 约 125 个端点需要权限，总共约 256 个端点
- ❌ 没有内置的"禁用权限"选项
- 💡 如需禁用权限，可以：
  1. 修改 `app/utils/auth.py` 中的 `login_required` 装饰器
  2. 或在 `.env` 中添加自定义配置

### 无需权限的端点
- `/api/health` - 健康检查
- `/api/auth/login` - 登录
- `/api/auth/register` - 注册
- `/api/auth/send-code` - 发送验证码
- `/api/auth/security-config` - 安全配置

## 项目结构

```
QuantDinger/
├── backend_api_python/          # 后端代码
│   ├── app/
│   │   ├── routes/             # API路由（256个端点）
│   │   ├── services/           # 业务逻辑服务
│   │   ├── data_sources/       # 数据源（Crypto, Stock, Forex等）
│   │   ├── utils/              # 工具函数
│   │   └── config/             # 配置
│   ├── examples/               # 调试示例
│   ├── scripts/                # 脚本工具
│   ├── simple_test.py          # 简单测试
│   ├── debug_examples.py       # 调试工具
│   ├── DEBUG_GUIDE.md          # 调试指南
│   ├── run.py                  # 服务入口
│   └── .env                    # 环境配置
├── frontend/                    # 前端代码
│   └── dist/                   # 构建产物
└── docs/                       # 文档

已创建的文档：
├── backend_api_python/LOCAL_SETUP_GUIDE.md      # 本地设置指南
├── backend_api_python/QUICK_START.md            # 快速开始
├── backend_api_python/DEBUG_GUIDE.md            # 调试指南
├── backend_api_python/WORKERS_GUIDE.md          # Worker说明
├── backend_api_python/DASHBOARD_DATA_FLOW.md    # 数据流说明
├── backend_api_python/DATABASE_DATA_FLOW.md     # 数据库说明
├── backend_api_python/FAST_ANALYSIS_FLOW.md     # AI分析说明
└── backend_api_python/app/services/README.md    # 服务说明
```

## 核心服务说明

### 1. 回测服务 (BacktestService)
- 位置: `app/services/backtest.py`
- 功能: 策略回测、性能评估
- 安全: 使用沙箱执行用户策略代码

### 2. 快速分析服务 (FastAnalysisService)
- 位置: `app/services/fast_analysis.py`
- 功能: AI市场分析、信号生成
- 依赖: LLM API（OpenAI/Alibaba Cloud）

### 3. 用户服务 (UserService)
- 位置: `app/services/user_service.py`
- 功能: 用户管理、认证、权限

### 4. K线服务 (KlineService)
- 位置: `app/services/kline.py`
- 功能: 获取市场K线数据
- 支持: Crypto, Stock, Forex, Futures

### 5. 策略编译器 (StrategyCompiler)
- 位置: `app/services/strategy_compiler.py`
- 功能: 将配置编译为Python策略代码

### 6. 实盘交易服务
- 位置: `app/services/live_trading/`
- 支持: Binance, Bybit, OKX, Bitget等多个交易所

## 下一步建议

### 如果要完整运行前后端

1. **使用 nginx 代理**（推荐）
   ```bash
   # 安装 nginx
   brew install nginx
   
   # 使用项目提供的配置
   nginx -c /path/to/QuantDinger/nginx-local.conf
   
   # 访问 http://localhost:8888
   ```

2. **或修改前端配置**
   - 前端需要重新构建，指向 `http://localhost:5001`

3. **或使用 Docker Compose**
   ```bash
   docker-compose up
   ```

### 如果只需要调试后端

- 使用提供的调试脚本即可，无需启动服务器
- 参考 `backend_api_python/DEBUG_GUIDE.md`

### 如果需要测试API

- 使用 Postman 或 curl
- 先登录获取 token
- 在请求头中添加 `Authorization: Bearer <token>`

## 常用命令

```bash
# 启动后端
cd backend_api_python
source venv/bin/activate
python run.py

# 启动前端（简单HTTP服务器）
cd frontend/dist
python3 -m http.server 8080

# 数据库连接
psql -U quantdinger -d quantdinger

# 运行测试
cd backend_api_python
python simple_test.py
python debug_examples.py

# 交互式调试
python -i simple_test.py
```

## 配置文件

### backend_api_python/.env
```bash
# 数据库
DATABASE_URL=postgresql://quantdinger:quantdinger123@localhost:5432/quantdinger

# 服务器
HOST=0.0.0.0
PORT=5001
DEBUG=true

# 管理员账号
ADMIN_USER=quantdinger
ADMIN_PASSWORD=123456

# LLM配置
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
```

## 问题排查

### 后端无法启动
1. 检查端口是否被占用: `lsof -i :5001`
2. 检查数据库连接: `psql -U quantdinger -d quantdinger`
3. 检查虚拟环境: `which python`

### 前端无法访问后端
1. 检查CORS配置（已启用）
2. 使用 nginx 代理
3. 或直接用 Postman 测试后端API

### 数据库连接失败
1. 确认 PostgreSQL 正在运行: `brew services list`
2. 检查 `.env` 中的 `DATABASE_URL`
3. 测试连接: `psql -U quantdinger -d quantdinger`

## 联系与支持

- 查看项目文档: `docs/` 目录
- 查看服务说明: `backend_api_python/app/services/README.md`
- 调试指南: `backend_api_python/DEBUG_GUIDE.md`
