#!/usr/bin/env python
"""
测试 Polymarket API 功能

测试各种 API 调用，确保一切正常工作
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


def test_api():
    """测试 API 功能"""
    print("=" * 80)
    print("Polymarket API 功能测试")
    print("=" * 80)
    
    # 获取配置
    private_key = os.getenv("POLYMARKET_PRIVATE_KEY")
    funder_address = os.getenv("POLYMARKET_FUNDER_ADDRESS")
    
    if not private_key or not funder_address:
        print("\n❌ 错误: 未配置钱包信息")
        return False
    
    # 移除 0x 前缀
    if private_key.startswith("0x"):
        private_key = private_key[2:]
    
    try:
        # 初始化客户端
        print("\n[1] 初始化客户端...")
        temp_client = ClobClient(
            host="https://clob.polymarket.com",
            chain_id=137,
            key=private_key
        )
        print("✓ 成功")
        
        # 创建 API 凭证
        print("\n[2] 创建 API 凭证...")
        api_creds = temp_client.create_or_derive_api_creds()
        print(f"✓ 成功 (API Key: {api_creds.api_key[:20]}...)")
        
        # 使用凭证初始化完整客户端
        print("\n[3] 初始化完整客户端...")
        client = ClobClient(
            host="https://clob.polymarket.com",
            chain_id=137,
            key=private_key,
            creds=api_creds,
            signature_type=2,
            funder=funder_address
        )
        print("✓ 成功")
        
        # 测试 1: 获取余额
        print("\n[4] 测试获取余额...")
        balance_params = BalanceAllowanceParams(
            asset_type=AssetType.COLLATERAL,
            signature_type=2
        )
        balance_info = client.get_balance_allowance(balance_params)
        usdc_balance = float(balance_info.get('balance', '0')) / 1_000_000
        print(f"✓ 成功 - USDC 余额: ${usdc_balance:.2f}")
        
        # 测试 2: 获取市场列表
        print("\n[5] 测试获取市场列表...")
        try:
            markets = client.get_markets()
            print(f"✓ 成功 - 获取到 {len(markets)} 个市场")
            
            # 显示前 3 个市场
            if markets and len(markets) > 0:
                print("\n前 3 个市场:")
                market_list = list(markets)[:3] if hasattr(markets, '__iter__') else []
                for i, market in enumerate(market_list, 1):
                    print(f"\n  市场 {i}:")
                    print(f"    Condition ID: {market.get('condition_id', 'N/A')}")
                    print(f"    Question: {market.get('question', 'N/A')}")
                    print(f"    Active: {market.get('active', 'N/A')}")
                    print(f"    Closed: {market.get('closed', 'N/A')}")
        except Exception as e:
            print(f"⚠️  获取市场列表失败: {e}")
        
        # 测试 3: 获取简化市场列表
        print("\n[6] 测试获取简化市场列表...")
        try:
            simplified_markets = client.get_simplified_markets()
            print(f"✓ 成功 - 获取到 {len(simplified_markets)} 个简化市场")
            
            # 显示前 3 个
            if simplified_markets and len(simplified_markets) > 0:
                print("\n前 3 个简化市场:")
                market_list = list(simplified_markets)[:3] if hasattr(simplified_markets, '__iter__') else []
                for i, market in enumerate(market_list, 1):
                    print(f"\n  市场 {i}:")
                    print(f"    Condition ID: {market.get('condition_id', 'N/A')}")
                    question = market.get('question', 'N/A')
                    if len(question) > 80:
                        question = question[:80] + "..."
                    print(f"    Question: {question}")
                    
                    # 显示代币信息
                    tokens = market.get('tokens', [])
                    if tokens:
                        for token in tokens[:2]:  # 只显示前 2 个代币
                            print(f"    Token: {token.get('outcome', 'N/A')} - Price: ${token.get('price', 0)}")
        except Exception as e:
            print(f"⚠️  获取简化市场列表失败: {e}")
        
        # 测试 4: 获取服务器时间
        print("\n[7] 测试获取服务器时间...")
        try:
            server_time = client.get_server_time()
            print(f"✓ 成功 - 服务器时间: {server_time}")
        except Exception as e:
            print(f"⚠️  获取服务器时间失败: {e}")
        
        # 测试 5: 获取未成交订单
        print("\n[8] 测试获取未成交订单...")
        try:
            open_orders = client.get_orders()
            print(f"✓ 成功 - 未成交订单数: {len(open_orders)}")
            
            if open_orders:
                print("\n未成交订单:")
                for order in open_orders[:3]:
                    print(f"  Order ID: {order.get('id')}")
                    print(f"  Side: {order.get('side')}")
                    print(f"  Price: {order.get('price')}")
                    print(f"  Size: {order.get('original_size')}")
                    print()
            else:
                print("  (没有未成交订单)")
        except Exception as e:
            print(f"⚠️  获取未成交订单失败: {e}")
        
        # 测试 6: 获取交易历史
        print("\n[9] 测试获取交易历史...")
        try:
            trades = client.get_trades()
            print(f"✓ 成功 - 交易记录数: {len(trades)}")
            
            if trades:
                print("\n最近的交易:")
                for trade in trades[:3]:
                    print(f"  Trade ID: {trade.get('id')}")
                    print(f"  Side: {trade.get('side')}")
                    print(f"  Price: {trade.get('price')}")
                    print(f"  Size: {trade.get('size')}")
                    print()
            else:
                print("  (没有交易记录)")
        except Exception as e:
            print(f"⚠️  获取交易历史失败: {e}")
        
        print("\n" + "=" * 80)
        print("✓ API 测试完成！")
        print("=" * 80)
        print("\n总结:")
        print(f"  钱包地址: {funder_address}")
        print(f"  USDC 余额: ${usdc_balance:.2f}")
        print(f"  API 状态: 正常")
        
        if usdc_balance == 0:
            print("\n⚠️  提示: 余额为 0，需要充值才能交易")
            print("  充值方法:")
            print("  1. 访问 https://polymarket.com")
            print("  2. 连接你的钱包 (地址: {})".format(funder_address))
            print("  3. 点击 'Deposit' 充值 USDC (Polygon 网络)")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主函数"""
    try:
        success = test_api()
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
