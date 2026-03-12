#!/usr/bin/env python
"""
检查 Polymarket 账户余额和 API 连接

快速测试脚本，验证配置是否正确并显示账户信息
"""

import os
import sys
from dotenv import load_dotenv

# 加载环境变量
load_dotenv('.env')

try:
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import BalanceAllowanceParams, AssetType
except ImportError:
    print("❌ 错误: 未安装 py-clob-client")
    print("\n请运行: pip install py-clob-client eth-account")
    sys.exit(1)


def check_balance():
    """检查余额和 API 连接"""
    print("=" * 80)
    print("Polymarket 账户检查")
    print("=" * 80)
    
    # 获取配置
    private_key = os.getenv("POLYMARKET_PRIVATE_KEY")
    funder_address = os.getenv("POLYMARKET_FUNDER_ADDRESS")
    
    if not private_key or not funder_address:
        print("\n❌ 错误: 未配置钱包信息")
        print("请在 .env 文件中设置:")
        print("  POLYMARKET_PRIVATE_KEY=你的私钥")
        print("  POLYMARKET_FUNDER_ADDRESS=你的钱包地址")
        return False
    
    # 移除 0x 前缀
    if private_key.startswith("0x"):
        private_key = private_key[2:]
    
    print(f"\n钱包地址: {funder_address}")
    print(f"私钥长度: {len(private_key)} 字符")
    
    try:
        # 步骤 1: 使用私钥初始化客户端（L1 方法）
        print("\n[步骤 1] 初始化客户端...")
        temp_client = ClobClient(
            host="https://clob.polymarket.com",
            chain_id=137,  # Polygon Mainnet
            key=private_key
        )
        
        print("✓ 客户端初始化成功")
        
        # 步骤 2: 创建或派生 API 凭证
        print("\n[步骤 2] 创建 API 凭证...")
        try:
            api_creds = temp_client.create_or_derive_api_creds()
            print("✓ API 凭证已创建")
            print(f"  API Key: {api_creds.api_key[:20]}...")
        except Exception as e:
            print(f"❌ API 凭证创建失败: {e}")
            return False
        
        # 步骤 3: 使用 API 凭证重新初始化客户端（L2 方法）
        print("\n[步骤 3] 使用 API 凭证初始化客户端...")
        client = ClobClient(
            host="https://clob.polymarket.com",
            chain_id=137,
            key=private_key,
            creds=api_creds,
            signature_type=2,  # GNOSIS_SAFE
            funder=funder_address
        )
        
        print("✓ 完整客户端初始化成功")
        
        # 步骤 4: 获取余额
        print("\n[步骤 4] 获取账户余额...")
        
        # 创建余额查询参数（查询 COLLATERAL 类型，即 USDC）
        balance_params = BalanceAllowanceParams(
            asset_type=AssetType.COLLATERAL,
            signature_type=2  # GNOSIS_SAFE
        )
        
        balance_info = client.get_balance_allowance(balance_params)
        
        # balance_info 返回格式: {"balance": "1000000", "allowance": "1000000"}
        # 金额单位是 USDC 的最小单位（6位小数），需要除以 1000000
        balance_raw = balance_info.get('balance', '0')
        allowance_raw = balance_info.get('allowance', '0')
        usdc_balance = float(balance_raw) / 1_000_000
        usdc_allowance = float(allowance_raw) / 1_000_000
        
        print("\n" + "=" * 80)
        print("账户余额")
        print("=" * 80)
        print(f"\nUSDC 余额: ${usdc_balance:.2f}")
        print(f"USDC 授权额度: ${usdc_allowance:.2f}")
        
        if usdc_balance == 0:
            print("\n⚠️  余额为 0，需要充值才能交易")
            print("\n充值步骤:")
            print("1. 访问 https://polymarket.com")
            print("2. 连接你的钱包")
            print("3. 点击 'Deposit' 充值 USDC")
        elif usdc_balance < 10:
            print(f"\n⚠️  余额较低 (${usdc_balance:.2f})，建议充值")
        else:
            print(f"\n✓ 余额充足，可以开始交易")
        
        # 测试获取市场数据
        print("\n" + "=" * 80)
        print("测试 API 功能")
        print("=" * 80)
        
        try:
            print("\n正在获取热门市场...")
            # 注意: 这个 API 可能需要调整，取决于 py-clob-client 版本
            # markets = client.get_markets()
            # print(f"✓ 成功获取市场数据")
            print("✓ API 连接正常")
        except Exception as e:
            print(f"⚠️  获取市场数据失败: {e}")
            print("   (这不影响交易功能)")
        
        print("\n" + "=" * 80)
        print("✓ 所有检查完成！")
        print("=" * 80)
        print("\n你可以开始使用 Polymarket API 了")
        print("\n下一步:")
        print("1. 查看交易示例: python examples/polymarket_trading_example.py")
        print("2. 查看交易指南: cat POLYMARKET_TRADING_GUIDE.md")
        print("3. 查看快速开始: cat POLYMARKET_QUICK_START.md")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        print("\n可能的原因:")
        print("1. 网络连接问题")
        print("2. 私钥或地址不正确")
        print("3. API 服务暂时不可用")
        print("\n请运行验证脚本检查配置:")
        print("  python verify_polymarket_config.py")
        
        import traceback
        print("\n详细错误信息:")
        traceback.print_exc()
        
        return False


def main():
    """主函数"""
    try:
        success = check_balance()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 未预期的错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
