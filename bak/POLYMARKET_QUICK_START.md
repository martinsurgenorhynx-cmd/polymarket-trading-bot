# Polymarket 快速开始指南

## 🚀 5 分钟配置指南

### 第 1 步: 获取钱包地址和私钥

#### 选项 A: 使用 MetaMask（推荐）

1. **安装 MetaMask**
   - 访问 https://metamask.io/
   - 下载浏览器扩展
   - 创建新钱包

2. **获取钱包地址**
   ```
   打开 MetaMask → 点击账户名 → 复制地址
   
   示例: 0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb
   ```

3. **导出私钥**
   ```
   MetaMask → 三个点 (⋮) → 账户详情 → 导出私钥 → 输入密码
   
   示例: 1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef
   
   ⚠️ 重要: 移除 0x 前缀（如果有）
   ```

#### 选项 B: 创建新钱包（测试用）

```bash
cd backend_api_python
python -c "
from eth_account import Account
import secrets
pk = '0x' + secrets.token_hex(32)
acc = Account.from_key(pk)
print('钱包地址:', acc.address)
print('私钥:', pk[2:])
"
```

---

### 第 2 步: 配置环境变量

编辑 `backend_api_python/.env` 文件，添加：

```bash
# Polymarket 配置
POLYMARKET_PRIVATE_KEY=你的私钥（64个字符，不带0x）
POLYMARKET_FUNDER_ADDRESS=你的钱包地址（42个字符，带0x）
```

**完整示例**:
```bash
# 错误示例 ❌
POLYMARKET_PRIVATE_KEY=0x1234567890abcdef...  # 不要带 0x
POLYMARKET_FUNDER_ADDRESS=1234567890abcdef...  # 要带 0x

# 正确示例 ✅
POLYMARKET_PRIVATE_KEY=1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef
POLYMARKET_FUNDER_ADDRESS=0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb
```

---

### 第 3 步: 获取 USDC.e

在 Polygon 网络上需要 USDC.e 才能交易：

#### 方法 1: 从交易所提现（推荐）

```
1. 在 Binance/OKX/Bybit 购买 USDC
2. 提现到你的钱包地址
3. ⚠️ 选择 Polygon 网络（手续费低）
4. 最少 $10 用于测试
```

#### 方法 2: 使用跨链桥

```
1. 访问 https://wallet.polygon.technology/bridge
2. 连接 MetaMask
3. 从以太坊桥接 USDC 到 Polygon
```

#### 方法 3: 在 Polygon 上购买

```
1. 访问 https://app.uniswap.org/
2. 切换到 Polygon 网络
3. 用 MATIC 兑换 USDC
```

---

### 第 4 步: 验证配置

```bash
cd backend_api_python
python verify_polymarket_config.py
```

**期望输出**:
```
================================================================================
验证 Polymarket 钱包配置
================================================================================

[1] 检查环境变量...
  ✓ POLYMARKET_PRIVATE_KEY 已设置
  ✓ POLYMARKET_FUNDER_ADDRESS 已设置: 0x742d35Cc...

[2] 验证私钥格式...
  ✓ 私钥长度正确 (64字符)
  ✓ 私钥是有效的十六进制

[3] 验证钱包地址格式...
  ✓ 地址以 0x 开头
  ✓ 地址长度正确 (42字符)
  ✓ 地址是有效的十六进制

[4] 验证私钥和地址匹配...
  ✓ 私钥和地址匹配
    地址: 0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb

[5] 测试连接 Polymarket...
  ✓ 客户端初始化成功
  ✓ 成功连接到 Polymarket
    USDC 余额: $50.00

================================================================================
✓ 配置验证通过！

你可以开始使用 Polymarket API 了:
  python examples/polymarket_trading_example.py
================================================================================
```

---

### 第 5 步: 运行示例

```bash
cd backend_api_python
python examples/polymarket_trading_example.py
```

---

## 📋 配置检查清单

- [ ] 安装 MetaMask
- [ ] 获取钱包地址（42 字符，带 0x）
- [ ] 导出私钥（64 字符，不带 0x）
- [ ] 配置 `.env` 文件
- [ ] 充值 USDC.e（至少 $10）
- [ ] 运行验证脚本
- [ ] 测试通过 ✓

---

## 🔍 常见问题

### Q: 私钥应该是什么格式？

```bash
# 正确 ✅
POLYMARKET_PRIVATE_KEY=1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef

# 错误 ❌
POLYMARKET_PRIVATE_KEY=0x1234567890abcdef...  # 不要 0x 前缀
POLYMARKET_PRIVATE_KEY=1234567890abcdef       # 长度不够（需要64字符）
```

### Q: 钱包地址应该是什么格式？

```bash
# 正确 ✅
POLYMARKET_FUNDER_ADDRESS=0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb

# 错误 ❌
POLYMARKET_FUNDER_ADDRESS=742d35Cc6634C0532925a3b844Bc9e7595f0bEb  # 缺少 0x
```

### Q: 如何检查 USDC.e 余额？

```bash
# 方法 1: 使用验证脚本
python verify_polymarket_config.py

# 方法 2: 在 MetaMask 中查看
# 切换到 Polygon 网络 → 查看 USDC 余额

# 方法 3: 在区块浏览器查看
# 访问 https://polygonscan.com/
# 输入你的钱包地址
```

### Q: 需要多少 USDC.e？

```
测试: $10-50
小规模交易: $100-500
生产环境: 根据策略需求
```

### Q: 验证失败怎么办？

```bash
# 1. 检查错误信息
python verify_polymarket_config.py

# 2. 常见错误
- "私钥长度不正确" → 确保是 64 个字符
- "私钥和地址不匹配" → 检查是否使用了正确的账户
- "USDC 余额为 0" → 需要充值

# 3. 查看详细文档
cat POLYMARKET_WALLET_SETUP.md
```

---

## 🎯 下一步

配置完成后，你可以：

### 1. 查看交易示例
```bash
cat examples/polymarket_trading_example.py
```

### 2. 阅读完整指南
```bash
cat POLYMARKET_TRADING_GUIDE.md
```

### 3. 开始自动交易
```bash
# 查看 AI 分析结果
python query_polymarket_results.py

# 根据 AI 建议自动交易
python examples/polymarket_trading_example.py
```

---

## ⚠️ 安全提示

### 永远不要：
- ❌ 分享私钥给任何人
- ❌ 将私钥提交到 Git
- ❌ 在主钱包上测试
- ❌ 截图包含私钥的内容

### 应该做的：
- ✅ 使用测试钱包进行开发
- ✅ 使用 `.env` 文件存储私钥
- ✅ 定期更换私钥
- ✅ 设置交易限额

---

## 📚 相关文档

- `POLYMARKET_WALLET_SETUP.md` - 详细的钱包配置指南
- `POLYMARKET_TRADING_GUIDE.md` - 完整的交易指南
- `examples/polymarket_trading_example.py` - 交易示例代码
- `verify_polymarket_config.py` - 配置验证脚本

---

## 🆘 获取帮助

如果遇到问题：

1. **运行验证脚本**
   ```bash
   python verify_polymarket_config.py
   ```

2. **查看详细文档**
   ```bash
   cat POLYMARKET_WALLET_SETUP.md
   ```

3. **参考官方文档**
   - https://docs.polymarket.com/
   - https://github.com/Polymarket/py-clob-client

---

## ✅ 配置成功！

如果验证脚本显示 "✓ 配置验证通过"，恭喜你！

你现在可以：
- 📊 查看 AI 分析结果
- 💰 执行自动交易
- 📈 监控交易表现
- 🤖 构建交易策略

开始交易：
```bash
python examples/polymarket_trading_example.py
```
