#!/usr/bin/env python
"""
验证钱包私钥和地址是否匹配
"""

import os
from dotenv import load_dotenv

load_dotenv('.env')

try:
    from eth_account import Account
except ImportError:
    print("❌ 请先安装: pip install eth-account")
    exit(1)

print("=" * 80)
print("验证钱包配置")
print("=" * 80)

private_key = os.getenv("POLYMARKET_PRIVATE_KEY")
funder_address = os.getenv("POLYMARKET_FUNDER_ADDRESS")

print(f"\n配置的地址: {funder_address}")

# 移除 0x 前缀
if private_key.startswith("0x"):
    private_key_clean = private_key[2:]
else:
    private_key_clean = private_key

# 从私钥派生地址
account = Account.from_key("0x" + private_key_clean)
derived_address = account.address

print(f"私钥对应地址: {derived_address}")

if derived_address.lower() == funder_address.lower():
    print("\n✓ 私钥和地址匹配！")
else:
    print("\n❌ 私钥和地址不匹配！")
    print("\n这是问题所在！你需要:")
    print("1. 使用正确的私钥")
    print("2. 或者使用正确的地址")
    print(f"\n如果私钥是正确的，请将 POLYMARKET_FUNDER_ADDRESS 改为: {derived_address}")

print("\n" + "=" * 80)
