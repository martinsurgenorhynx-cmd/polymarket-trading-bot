#!/usr/bin/env python
"""
直接从区块链查询钱包余额

检查 Polygon 网络上的 USDC 余额
"""

import os
from dotenv import load_dotenv

load_dotenv('.env')

try:
    from web3 import Web3
except ImportError:
    print("❌ 请先安装: pip install web3")
    exit(1)

print("=" * 80)
print("查询链上余额")
print("=" * 80)

# Polygon RPC (尝试多个)
POLYGON_RPCS = [
    "https://polygon.llamarpc.com",
    "https://rpc-mainnet.matic.network",
    "https://polygon-rpc.com",
    "https://rpc.ankr.com/polygon"
]

# USDC 合约地址 (Polygon)
USDC_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"  # USDC (bridged)
USDC_ADDRESS_NATIVE = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"  # USDC (native)

# ERC20 ABI (只需要 balanceOf 和 decimals)
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "symbol",
        "outputs": [{"name": "", "type": "string"}],
        "type": "function"
    }
]

funder_address = os.getenv("POLYMARKET_FUNDER_ADDRESS")

print(f"\n钱包地址: {funder_address}")
print(f"网络: Polygon (Chain ID: 137)")

try:
    # 连接到 Polygon (尝试多个 RPC)
    w3 = None
    for rpc in POLYGON_RPCS:
        try:
            print(f"\n尝试连接: {rpc}")
            w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={'timeout': 10}))
            if w3.is_connected():
                print(f"✓ 成功连接到: {rpc}")
                break
        except Exception as e:
            print(f"  失败: {e}")
            continue
    
    if not w3 or not w3.is_connected():
        print("\n❌ 无法连接到任何 Polygon RPC")
        print("\n可能的原因:")
        print("1. 网络连接问题")
        print("2. 需要配置代理")
        print("\n你可以直接在浏览器查看余额:")
        print(f"https://polygonscan.com/address/{funder_address}")
        exit(1)
    
    # 检查地址格式
    if not Web3.is_address(funder_address):
        print(f"\n❌ 地址格式不正确: {funder_address}")
        exit(1)
    
    address = Web3.to_checksum_address(funder_address)
    
    # 1. 查询 MATIC 余额
    print("\n" + "=" * 80)
    print("原生代币余额")
    print("=" * 80)
    
    matic_balance_wei = w3.eth.get_balance(address)
    matic_balance = w3.from_wei(matic_balance_wei, 'ether')
    print(f"\nMATIC 余额: {matic_balance:.6f} MATIC")
    
    if matic_balance == 0:
        print("⚠️  MATIC 余额为 0，无法支付 gas 费")
    
    # 2. 查询 USDC (bridged) 余额
    print("\n" + "=" * 80)
    print("USDC 余额")
    print("=" * 80)
    
    usdc_contract = w3.eth.contract(address=USDC_ADDRESS, abi=ERC20_ABI)
    
    try:
        symbol = usdc_contract.functions.symbol().call()
        decimals = usdc_contract.functions.decimals().call()
        balance_raw = usdc_contract.functions.balanceOf(address).call()
        balance = balance_raw / (10 ** decimals)
        
        print(f"\nUSDC (Bridged) 余额: ${balance:.2f}")
        print(f"  合约地址: {USDC_ADDRESS}")
        print(f"  代币符号: {symbol}")
        print(f"  小数位数: {decimals}")
    except Exception as e:
        print(f"\n⚠️  查询 USDC (Bridged) 失败: {e}")
        balance = 0
    
    # 3. 查询 USDC (native) 余额
    print("\n" + "-" * 80)
    
    usdc_native_contract = w3.eth.contract(address=USDC_ADDRESS_NATIVE, abi=ERC20_ABI)
    
    try:
        symbol_native = usdc_native_contract.functions.symbol().call()
        decimals_native = usdc_native_contract.functions.decimals().call()
        balance_native_raw = usdc_native_contract.functions.balanceOf(address).call()
        balance_native = balance_native_raw / (10 ** decimals_native)
        
        print(f"\nUSDC (Native) 余额: ${balance_native:.2f}")
        print(f"  合约地址: {USDC_ADDRESS_NATIVE}")
        print(f"  代币符号: {symbol_native}")
        print(f"  小数位数: {decimals_native}")
    except Exception as e:
        print(f"\n⚠️  查询 USDC (Native) 失败: {e}")
        balance_native = 0
    
    # 总结
    print("\n" + "=" * 80)
    print("总结")
    print("=" * 80)
    
    total_usdc = balance + balance_native
    
    print(f"\n钱包地址: {address}")
    print(f"MATIC 余额: {matic_balance:.6f} MATIC")
    print(f"USDC 总余额: ${total_usdc:.2f}")
    print(f"  - USDC (Bridged): ${balance:.2f}")
    print(f"  - USDC (Native): ${balance_native:.2f}")
    
    if total_usdc == 0:
        print("\n❌ 钱包在 Polygon 网络上没有 USDC")
        print("\n可能的原因:")
        print("1. 资金在其他网络上 (以太坊主网、Arbitrum 等)")
        print("2. 还没有充值")
        print("3. 使用了错误的钱包地址")
        print("\n请检查:")
        print(f"1. 在 Polygonscan 查看地址: https://polygonscan.com/address/{address}")
        print("2. 确认资金在哪个网络上")
        print("3. 如果在其他网络，需要桥接到 Polygon")
    else:
        print("\n✓ 找到 USDC 余额！")
        
        if balance > 0:
            print(f"\n⚠️  注意: Polymarket 使用 USDC (Bridged)")
            print(f"   合约地址: {USDC_ADDRESS}")
        
        if balance_native > 0:
            print(f"\n⚠️  你有 USDC (Native)，可能需要转换为 USDC (Bridged)")
    
    print("\n" + "=" * 80)
    
except Exception as e:
    print(f"\n❌ 查询失败: {e}")
    import traceback
    traceback.print_exc()
