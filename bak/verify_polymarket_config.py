#!/usr/bin/env python
"""
验证 Polymarket 钱包配置

检查环境变量、私钥格式、地址匹配等
"""

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
    
    errors = []
    warnings = []
    
    # 1. 检查环境变量
    print("\n[1] 检查环境变量...")
    private_key = os.getenv("POLYMARKET_PRIVATE_KEY")
    funder_address = os.getenv("POLYMARKET_FUNDER_ADDRESS")
    
    if not private_key:
        errors.append("未设置 POLYMARKET_PRIVATE_KEY")
    else:
        print("  ✓ POLYMARKET_PRIVATE_KEY 已设置")
    
    if not funder_address:
        errors.append("未设置 POLYMARKET_FUNDER_ADDRESS")
    else:
        print(f"  ✓ POLYMARKET_FUNDER_ADDRESS 已设置: {funder_address}")
    
    if errors:
        print("\n" + "=" * 80)
        print("❌ 配置错误:")
        for error in errors:
            print(f"  - {error}")
        print("\n请在 .env 文件中设置:")
        print("  POLYMARKET_PRIVATE_KEY=你的私钥（不带0x前缀）")
        print("  POLYMARKET_FUNDER_ADDRESS=你的钱包地址（带0x前缀）")
        print("\n参考: POLYMARKET_WALLET_SETUP.md")
        print("=" * 80)
        return False
    
    # 2. 验证私钥格式
    print("\n[2] 验证私钥格式...")
    
    if private_key.startswith("0x"):
        warnings.append("私钥包含 0x 前缀，将自动移除")
        private_key = private_key[2:]
    
    if len(private_key) != 64:
        errors.append(f"私钥长度不正确 (应为64字符，实际{len(private_key)})")
    else:
        print(f"  ✓ 私钥长度正确 (64字符)")
    
    try:
        int(private_key, 16)
        print("  ✓ 私钥是有效的十六进制")
    except ValueError:
        errors.append("私钥不是有效的十六进制字符串")
    
    # 3. 验证地址格式
    print("\n[3] 验证钱包地址格式...")
    
    if not funder_address.startswith("0x"):
        errors.append("钱包地址应以 0x 开头")
    else:
        print("  ✓ 地址以 0x 开头")
    
    if len(funder_address) != 42:
        errors.append(f"钱包地址长度不正确 (应为42字符，实际{len(funder_address)})")
    else:
        print("  ✓ 地址长度正确 (42字符)")
    
    try:
        int(funder_address[2:], 16)
        print("  ✓ 地址是有效的十六进制")
    except ValueError:
        errors.append("钱包地址不是有效的十六进制字符串")
    
    if errors:
        print("\n" + "=" * 80)
        print("❌ 格式错误:")
        for error in errors:
            print(f"  - {error}")
        print("=" * 80)
        return False
    
    # 4. 验证私钥和地址匹配
    print("\n[4] 验证私钥和地址匹配...")
    
    try:
        from eth_account import Account
        
        account = Account.from_key("0x" + private_key)
        derived_address = account.address
        
        if derived_address.lower() == funder_address.lower():
            print(f"  ✓ 私钥和地址匹配")
            print(f"    地址: {derived_address}")
        else:
            errors.append("私钥和地址不匹配")
            print(f"  ❌ 私钥对应地址: {derived_address}")
            print(f"  ❌ 配置的地址: {funder_address}")
            print("\n  请检查:")
            print("  1. 私钥是否正确")
            print("  2. 地址是否正确")
            print("  3. 是否使用了正确的账户")
    except ImportError:
        warnings.append("未安装 eth-account，跳过私钥验证")
        print("  ⚠️  跳过验证: 未安装 eth-account")
        print("     运行: pip install eth-account")
    except Exception as e:
        errors.append(f"验证私钥时出错: {e}")
    
    if errors:
        print("\n" + "=" * 80)
        print("❌ 验证失败:")
        for error in errors:
            print(f"  - {error}")
        print("=" * 80)
        return False
    
    # 5. 测试连接 Polymarket
    print("\n[5] 测试连接 Polymarket...")
    
    try:
        from py_clob_client.client import ClobClient
        
        client = ClobClient(
            host="https://clob.polymarket.com",
            chain_id=137,
            key=private_key,
            signature_type=2,
            funder=funder_address
        )
        
        print("  ✓ 客户端初始化成功")
        
        # 尝试获取余额
        try:
            balance = client.get_balance()
            usdc_balance = balance.get('usdc', 0)
            
            print(f"  ✓ 成功连接到 Polymarket")
            print(f"    USDC 余额: ${usdc_balance}")
            
            if usdc_balance == 0:
                warnings.append("USDC 余额为 0，需要充值才能交易")
            elif usdc_balance < 10:
                warnings.append(f"USDC 余额较低 (${usdc_balance})，建议充值")
            
        except Exception as e:
            warnings.append(f"获取余额失败: {e}")
            print(f"  ⚠️  获取余额失败: {e}")
        
    except ImportError:
        warnings.append("未安装 py-clob-client，跳过连接测试")
        print("  ⚠️  跳过测试: 未安装 py-clob-client")
        print("     运行: pip install py-clob-client")
    except Exception as e:
        warnings.append(f"连接测试失败: {e}")
        print(f"  ⚠️  连接失败: {e}")
        print("     这可能是网络问题，配置本身可能是正确的")
    
    # 显示警告
    if warnings:
        print("\n" + "=" * 80)
        print("⚠️  警告:")
        for warning in warnings:
            print(f"  - {warning}")
        print("=" * 80)
    
    # 最终结果
    print("\n" + "=" * 80)
    if not errors:
        print("✓ 配置验证通过！")
        print("\n你可以开始使用 Polymarket API 了:")
        print("  python examples/polymarket_trading_example.py")
    else:
        print("❌ 配置验证失败")
        print("\n请修复上述错误后重试")
    print("=" * 80)
    
    return len(errors) == 0


def main():
    """主函数"""
    try:
        success = verify_config()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 验证过程出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
