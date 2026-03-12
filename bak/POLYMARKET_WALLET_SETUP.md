# Polymarket 钱包配置指南

## 概览

要使用 Polymarket API 进行交易，你需要：
1. 一个 Web3 钱包（推荐 MetaMask）
2. 钱包的私钥
3. 钱包地址
4. Polygon 网络上的 USDC.e 余额

---

## 方案 1: 使用 MetaMask（推荐）

### 步骤 1: 安装 MetaMask

1. 访问 [metamask.io](https://metamask.io/)
2. 下载并安装浏览器扩展
3. 创建新钱包或导入现有钱包
4. **重要**: 安全保存你的助记词（12 个单词）

### 步骤 2: 切换到 Polygon 网络

1. 打开 MetaMask
2. 点击顶部的网络下拉菜单
3. 点击"添加网络"
4. 选择"Polygon Mainnet"或手动添加：

```
网络名称: Polygon Mainnet
RPC URL: https://polygon-rpc.com
链 ID: 137
货币符号: MATIC
区块浏览器: https://polygonscan.com
```

### 步骤 3: 获取钱包地址

1. 打开 MetaMask
2. 点击账户名称下方的地址
3. 复制地址（格式：`0x1234...abcd`）

**这就是你的 `POLYMARKET_FUNDER_ADDRESS`**

示例：
```
POLYMARKET_FUNDER_ADDRESS=0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb
```

### 步骤 4: 导出私钥

⚠️ **警告**: 私钥非常重要，永远不要分享给任何人！

1. 打开 MetaMask
2. 点击右上角的三个点 (⋮)
3. 选择"账户详情"
4. 点击"导出私钥"
5. 输入 MetaMask 密码
6. 复制私钥（格式：`0x1234...` 或 `1234...`）

**这就是你的 `POLYMARKET_PRIVATE_KEY`**

⚠️ **重要**: 
- 移除 `0x` 前缀（如果有）
- 只保留 64 个十六进制字符

示例：
```
# 错误 ❌
POLYMARKET_PRIVATE_KEY=0x1234567890abcdef...

# 正确 ✅
POLYMARKET_PRIVATE_KEY=1234567890abcdef...
```

### 步骤 5: 获取 USDC.e

在 Polygon 网络上交易需要 USDC.e（Bridged USDC）：

**选项 A: 从交易所提现**
1. 在 Binance/OKX/Bybit 等交易所购买 USDC
2. 提现到你的钱包地址
3. **重要**: 选择 Polygon 网络（手续费低）

**选项 B: 使用跨链桥**
1. 访问 [Polygon Bridge](https://wallet.polygon.technology/bridge)
2. 连接 MetaMask
3. 从以太坊主网桥接 USDC 到 Polygon

**选项 C: 在 Polygon 上购买**
1. 访问 [Uniswap](https://app.uniswap.org/)
2. 切换到 Polygon 网络
3. 用 MATIC 兑换 USDC

### 步骤 6: 配置环境变量

在 `backend_api_python/.env` 文件中添加：

```bash
# Polymarket 钱包配置
POLYMARKET_PRIVATE_KEY=你的私钥（不带0x前缀）
POLYMARKET_FUNDER_ADDRESS=你的钱包地址（带0x前缀）
```

完整示例：
```bash
# Polymarket 配置
POLYMARKET_PRIVATE_KEY=1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef
POLYMARKET_FUNDER_ADDRESS=0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb
```

---

## 方案 2: 创建新的测试钱包（开发用）

如果你想创建一个专门用于测试的新钱包：

### 使用 Python 创建

```python
from eth_account import Account
import secrets

# 创建新钱包
private_key = "0x" + secrets.token_hex(32)
account = Account.from_key(private_key)

print("=" * 80)
print("新钱包已创建")
print("=" * 80)
print(f"钱包地址: {account.address}")
print(f"私钥 (带0x): {private_key}")
print(f"私钥 (不带0x): {private_key[2:]}")
print("=" * 80)
print("\n⚠️  警告: 请安全保存这些信息！")
print("⚠️  这是一个新钱包，需要充值 USDC.e 才能交易")
```

运行脚本：
```bash
cd backend_api_python
python -c "
from eth_account import Account
import secrets
pk = '0x' + secrets.token_hex(32)
acc = Account.from_key(pk)
print(f'Address: {acc.address}')
print(f'Private Key: {pk[2:]}')
"
```

### 配置到 .env

```bash
POLYMARKET_PRIVATE_KEY=生成的私钥（不带0x）
POLYMARKET_FUNDER_ADDRESS=生成的地址（带0x）
```

---

## 方案 3: 使用 Polymarket 网站导出

如果你已经在 Polymarket.com 上有账户：

### 步骤 1: 登录 Polymarket

1. 访问 [polymarket.com](https://polymarket.com)
2. 使用 MetaMask 登录

### 步骤 2: 查看钱包地址

1. 点击右上角的钱包图标
2. 你会看到你的钱包地址
3. 这个地址就是 `POLYMARKET_FUNDER_ADDRESS`

### 步骤 3: 导出私钥

从 MetaMask 导出（见方案 1 步骤 4）

---

## 验证配置

创建测试脚本验证配置是否正确：

```python
#!/usr/bin/env python
"""验证 Polymarket 钱包配置"""

import os
import sys
from dotenv import load_dotenv

# 加载环境变量
load_dotenv('.env')

def verify_config():
    """验证配置"""
    print("=" * 80)
    print("验证 Polymarket 钱包配置")
    print("=" * 80)
    
    # 1. 检查环境变量
    private_key = os.getenv("POLYMARKET_PRIVATE_KEY")
    funder_address = os.getenv("POLYMARKET_FUNDER_ADDRESS")
    
    if not private_key:
        print("❌ 错误: 未设置 POLYMARKET_PRIVATE_KEY")
        return False
    
    if not funder_address:
        print("❌ 错误: 未设置 POLYMARKET_FUNDER_ADDRESS")
        return False
    
    print("✓ 环境变量已设置")
    
    # 2. 验证私钥格式
    if private_key.startswith("0x"):
        print("⚠️  警告: 私钥包含 0x 前缀，将自动移除")
        private_key = private_key[2:]
    
    if len(private_key) != 64:
        print(f"❌ 错误: 私钥长度不正确 (应为64字符，实际{len(private_key)})")
        return False
    
    try:
        int(private_key, 16)
        print("✓ 私钥格式正确")
    except ValueError:
        print("❌ 错误: 私钥不是有效的十六进制")
        return False
    
    # 3. 验证地址格式
    if not funder_address.startswith("0x"):
        print("❌ 错误: 钱包地址应以 0x 开头")
        return False
    
    if len(funder_address) != 42:
        print(f"❌ 错误: 钱包地址长度不正确 (应为42字符，实际{len(funder_address)})")
        return False
    
    print("✓ 钱包地址格式正确")
    
    # 4. 验证私钥和地址匹配
    try:
        from eth_account import Account
        account = Account.from_key("0x" + private_key)
        
        if account.address.lower() == funder_address.lower():
            print("✓ 私钥和地址匹配")
        else:
            print("❌ 错误: 私钥和地址不匹配")
            print(f"   私钥对应地址: {account.address}")
            print(f"   配置的地址: {funder_address}")
            return False
    except Exception as e:
        print(f"❌ 错误: 无法验证私钥 - {e}")
        return False
    
    # 5. 测试连接 Polymarket
    try:
        from py_clob_client.client import ClobClient
        
        client = ClobClient(
            host="https://clob.polymarket.com",
            chain_id=137,
            key=private_key,
            signature_type=2,
            funder=funder_address
        )
        
        # 尝试获取余额
        balance = client.get_balance()
        print("✓ 成功连接到 Polymarket")
        print(f"  USDC 余额: ${balance.get('usdc', 0)}")
        
        if balance.get('usdc', 0) == 0:
            print("⚠️  警告: USDC 余额为 0，需要充值才能交易")
        
    except ImportError:
        print("⚠️  跳过连接测试: 未安装 py-clob-client")
        print("   运行: pip install py-clob-client")
    except Exception as e:
        print(f"⚠️  连接测试失败: {e}")
        print("   这可能是网络问题，配置本身可能是正确的")
    
    print("\n" + "=" * 80)
    print("✓ 配置验证完成")
    print("=" * 80)
    
    return True

if __name__ == "__main__":
    success = verify_config()
    sys.exit(0 if success else 1)
```

运行验证：
```bash
cd backend_api_python
python verify_polymarket_config.py
```

---

## 安全最佳实践

### ✅ 应该做的

1. **使用测试钱包进行开发**
   - 创建专门的测试钱包
   - 只存放少量资金

2. **保护私钥**
   - 永远不要提交到 Git
   - 使用 `.env` 文件（已在 `.gitignore` 中）
   - 定期更换私钥

3. **使用环境变量**
   ```bash
   # 好 ✅
   export POLYMARKET_PRIVATE_KEY=...
   
   # 坏 ❌
   private_key = "1234567890abcdef..."
   ```

4. **限制权限**
   - 设置交易限额
   - 使用只读 API（如果可能）
   - 定期审计交易

### ❌ 不应该做的

1. **不要分享私钥**
   - 不要通过聊天工具发送
   - 不要截图包含私钥的内容
   - 不要存储在云端

2. **不要在主钱包上测试**
   - 使用专门的测试钱包
   - 主钱包只用于生产环境

3. **不要忽略安全警告**
   - 验证所有交易
   - 检查合约地址
   - 使用硬件钱包（生产环境）

---

## 常见问题

### Q1: 私钥和助记词有什么区别？

**助记词（Seed Phrase）**:
- 12 或 24 个单词
- 可以恢复整个钱包
- 示例: `apple banana cherry ...`

**私钥（Private Key）**:
- 64 个十六进制字符
- 对应单个账户
- 示例: `1234567890abcdef...`

Polymarket API 需要**私钥**，不是助记词。

### Q2: 为什么私钥不能有 0x 前缀？

`py-clob-client` 库期望私钥是纯十六进制字符串（64 字符），不包含 `0x` 前缀。

```python
# 错误 ❌
POLYMARKET_PRIVATE_KEY=0x1234567890abcdef...

# 正确 ✅
POLYMARKET_PRIVATE_KEY=1234567890abcdef...
```

### Q3: 什么是 Funder Address？

Funder Address 是持有资金的钱包地址。对于大多数用户，这就是你的钱包地址。

```python
# 你的钱包地址
POLYMARKET_FUNDER_ADDRESS=0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb
```

### Q4: 需要多少 USDC.e？

建议：
- **测试**: $10-50 USDC.e
- **小规模交易**: $100-500 USDC.e
- **生产环境**: 根据策略需求

### Q5: 如何获取测试网代币？

Polymarket 只在主网运行，没有测试网。建议：
1. 使用小额资金测试
2. 创建专门的测试钱包
3. 先在纸上模拟交易

---

## 快速开始检查清单

- [ ] 安装 MetaMask
- [ ] 创建/导入钱包
- [ ] 切换到 Polygon 网络
- [ ] 获取钱包地址
- [ ] 导出私钥
- [ ] 获取 USDC.e（至少 $10）
- [ ] 配置 `.env` 文件
- [ ] 运行验证脚本
- [ ] 测试连接

---

## 下一步

配置完成后，你可以：

1. **运行示例代码**
   ```bash
   python examples/polymarket_trading_example.py
   ```

2. **查看交易指南**
   - 阅读 `POLYMARKET_TRADING_GUIDE.md`
   - 了解 API 使用方法

3. **开始自动交易**
   - 集成 AI 分析结果
   - 实施风险管理
   - 监控交易表现

---

## 获取帮助

如果遇到问题：

1. **检查配置**
   ```bash
   python verify_polymarket_config.py
   ```

2. **查看日志**
   ```python
   import logging
   logging.basicConfig(level=logging.DEBUG)
   ```

3. **参考文档**
   - [Polymarket 官方文档](https://docs.polymarket.com/)
   - [py-clob-client GitHub](https://github.com/Polymarket/py-clob-client)

4. **常见错误**
   - "Insufficient allowance" → 需要先授权 USDC.e
   - "Invalid signature" → 检查 signature_type
   - "Insufficient balance" → 充值 USDC.e
