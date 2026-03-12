# 检查 Polymarket 余额指南

## 问题诊断

我们发现了配置问题：**私钥和地址不匹配**

### 原配置（错误）
- 地址: `0x362BFA0ffAfE9Ad87B5cA48fcb0D5CeCC16eEe0c`
- 私钥对应地址: `0xd2176aC3F8E77c35B69e5ad5A0fe476822Cdbc70`

### 已更新配置（正确）
- 地址: `0xd2176aC3F8E77c35B69e5ad5A0fe476822Cdbc70`
- 私钥: 匹配 ✓

## 检查余额的方法

### 方法 1: 通过 Polygonscan 查看（推荐）

直接在浏览器打开以下链接查看你的钱包余额：

**你的钱包地址:**
```
0xd2176aC3F8E77c35B69e5ad5A0fe476822Cdbc70
```

**Polygonscan 链接:**
```
https://polygonscan.com/address/0xd2176aC3F8E77c35B69e5ad5A0fe476822Cdbc70
```

在这个页面你可以看到:
- MATIC 余额（用于支付 gas 费）
- USDC 余额（用于 Polymarket 交易）
- 所有代币余额
- 交易历史

### 方法 2: 通过 Polymarket 网站查看

1. 访问 https://polymarket.com
2. 连接钱包（使用地址 `0xd2176aC3F8E77c35B69e5ad5A0fe476822Cdbc70`）
3. 查看右上角的余额显示

### 方法 3: 使用我们的脚本（需要网络连接）

```bash
# 检查 Polymarket API 余额
python check_polymarket_balance.py

# 检查链上余额（需要能连接到 Polygon RPC）
python check_onchain_balance.py
```

## 可能的情况

### 情况 1: 资金在正确的地址上
如果你在 Polygonscan 上看到了 USDC 余额，但 API 查询显示为 0，可能是：
- Polymarket 需要授权 USDC 使用权限
- 需要在 Polymarket 网站上先存款（Deposit）

### 情况 2: 资金在错误的地址上
如果资金在 `0x362BFA0ffAfE9Ad87B5cA48fcb0D5CeCC16eEe0c`：
- 你需要将资金转移到正确的地址 `0xd2176aC3F8E77c35B69e5ad5A0fe476822Cdbc70`
- 或者使用正确的私钥（对应 `0x362BFA0ffAfE9Ad87B5cA48fcb0D5CeCC16eEe0c` 的私钥）

### 情况 3: 资金在其他网络上
如果资金在以太坊主网或其他网络：
- 需要桥接到 Polygon 网络
- 使用 Polygon Bridge: https://wallet.polygon.technology/

## 下一步

### 1. 确认资金位置
在浏览器打开这两个链接，看看哪个有余额：

**当前配置的地址（私钥匹配）:**
```
https://polygonscan.com/address/0xd2176aC3F8E77c35B69e5ad5A0fe476822Cdbc70
```

**原来配置的地址:**
```
https://polygonscan.com/address/0x362BFA0ffAfE9Ad87B5cA48fcb0D5CeCC16eEe0c
```

### 2. 根据情况处理

#### 如果资金在 `0xd2176aC3F8E77c35B69e5ad5A0fe476822Cdbc70`
✓ 配置正确，可以直接使用

#### 如果资金在 `0x362BFA0ffAfE9Ad87B5cA48fcb0D5CeCC16eEe0c`
需要更新 `.env` 文件，使用正确的私钥：
```bash
# 在 .env 文件中更新
POLYMARKET_PRIVATE_KEY=<对应 0x362BFA0ffAfE9Ad87B5cA48fcb0D5CeCC16eEe0c 的私钥>
POLYMARKET_FUNDER_ADDRESS=0x362BFA0ffAfE9Ad87B5cA48fcb0D5CeCC16eEe0c
```

### 3. 验证配置
```bash
# 验证私钥和地址是否匹配
python verify_wallet.py

# 检查余额
python check_polymarket_balance.py
```

## 重要提示

### USDC 类型
Polygon 上有两种 USDC：
- **USDC (Bridged)**: `0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174` - Polymarket 使用这个
- **USDC (Native)**: `0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359` - 新版本

如果你有 USDC (Native)，可能需要转换为 USDC (Bridged)。

### 授权问题
即使有 USDC 余额，也需要授权 Polymarket 合约使用你的 USDC。这通常在第一次使用时自动完成。

## 测试脚本

我们创建了以下脚本帮助你诊断：

1. `verify_wallet.py` - 验证私钥和地址是否匹配
2. `check_polymarket_balance.py` - 通过 Polymarket API 查询余额
3. `check_onchain_balance.py` - 直接从区块链查询余额
4. `test_polymarket_api.py` - 完整的 API 功能测试

## 需要帮助？

如果还有问题，请提供：
1. Polygonscan 上显示的余额截图
2. 你想使用哪个地址
3. 资金在哪个网络上
