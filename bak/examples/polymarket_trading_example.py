#!/usr/bin/env python
"""
Polymarket 交易示例

演示如何使用 py-clob-client 进行 Polymarket 交易

安装依赖:
    pip install py-clob-client

环境变量:
    POLYMARKET_PRIVATE_KEY - 你的钱包私钥
    POLYMARKET_FUNDER_ADDRESS - 资金地址（通常是你的钱包地址）
"""

import os
import sys
import time
from decimal import Decimal

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

try:
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import OrderArgs, OrderType, PostOrdersArgs
    from py_clob_client.order_builder.constants import BUY, SELL
except ImportError:
    print("错误: 请先安装 py-clob-client")
    print("运行: pip install py-clob-client")
    sys.exit(1)


class PolymarketTrader:
    """Polymarket 交易客户端"""
    
    def __init__(self, private_key: str = None, funder_address: str = None):
        """
        初始化 Polymarket 交易客户端
        
        Args:
            private_key: 钱包私钥（不带 0x 前缀）
            funder_address: 资金地址（你的钱包地址）
        """
        self.host = "https://clob.polymarket.com"
        self.chain_id = 137  # Polygon Mainnet
        
        # 从环境变量或参数获取
        self.private_key = private_key or os.getenv("POLYMARKET_PRIVATE_KEY")
        self.funder_address = funder_address or os.getenv("POLYMARKET_FUNDER_ADDRESS")
        
        if not self.private_key:
            raise ValueError("需要提供 POLYMARKET_PRIVATE_KEY")
        
        # 移除 0x 前缀（如果有）
        if self.private_key.startswith("0x"):
            self.private_key = self.private_key[2:]
        
        # 初始化客户端
        # signature_type: 2 = GNOSIS_SAFE (最常用)
        self.client = ClobClient(
            host=self.host,
            chain_id=self.chain_id,
            key=self.private_key,
            signature_type=2,  # GNOSIS_SAFE
            funder=self.funder_address
        )
        
        print(f"✓ Polymarket 客户端初始化成功")
        print(f"  Host: {self.host}")
        print(f"  Chain ID: {self.chain_id}")
        print(f"  Funder: {self.funder_address}")
    
    def get_market_info(self, condition_id: str) -> dict:
        """
        获取市场信息
        
        Args:
            condition_id: 市场条件 ID
            
        Returns:
            市场信息字典
        """
        try:
            market = self.client.get_market(condition_id)
            return market
        except Exception as e:
            print(f"✗ 获取市场信息失败: {e}")
            return None
    
    def place_limit_order(
        self,
        token_id: str,
        side: str,  # "BUY" or "SELL"
        price: float,
        size: float,
        tick_size: str = "0.01",
        neg_risk: bool = False
    ) -> dict:
        """
        下限价单
        
        Args:
            token_id: 代币 ID（YES 或 NO 代币）
            side: "BUY" 或 "SELL"
            price: 价格（0-1 之间，如 0.65 表示 65%）
            size: 数量（美元金额）
            tick_size: 价格精度（"0.1", "0.01", "0.001", "0.0001"）
            neg_risk: 是否为多结果市场
            
        Returns:
            订单响应
        """
        try:
            print(f"\n下限价单:")
            print(f"  Token ID: {token_id}")
            print(f"  Side: {side}")
            print(f"  Price: {price}")
            print(f"  Size: ${size}")
            
            # 转换 side
            order_side = BUY if side.upper() == "BUY" else SELL
            
            # 创建并提交订单
            response = self.client.create_and_post_order(
                OrderArgs(
                    token_id=token_id,
                    price=price,
                    size=size,
                    side=order_side,
                    order_type=OrderType.GTC  # Good-Til-Cancelled
                ),
                options={
                    "tick_size": tick_size,
                    "neg_risk": neg_risk
                }
            )
            
            print(f"✓ 订单已提交")
            print(f"  Order ID: {response.get('orderID')}")
            print(f"  Status: {response.get('status')}")
            
            return response
            
        except Exception as e:
            print(f"✗ 下单失败: {e}")
            return {"error": str(e)}
    
    def place_market_order(
        self,
        token_id: str,
        side: str,  # "BUY" or "SELL"
        amount: float,
        tick_size: str = "0.01",
        neg_risk: bool = False
    ) -> dict:
        """
        下市价单（立即成交）
        
        Args:
            token_id: 代币 ID
            side: "BUY" 或 "SELL"
            amount: BUY 时为花费金额，SELL 时为卖出数量
            tick_size: 价格精度
            neg_risk: 是否为多结果市场
            
        Returns:
            订单响应
        """
        try:
            print(f"\n下市价单:")
            print(f"  Token ID: {token_id}")
            print(f"  Side: {side}")
            print(f"  Amount: ${amount}")
            
            # 转换 side
            order_side = BUY if side.upper() == "BUY" else SELL
            
            # 创建市价单（使用 FOK - Fill-Or-Kill）
            response = self.client.create_market_order(
                OrderArgs(
                    token_id=token_id,
                    amount=amount,
                    side=order_side,
                ),
                options={
                    "tick_size": tick_size,
                    "neg_risk": neg_risk
                }
            )
            
            print(f"✓ 市价单已提交")
            print(f"  Order ID: {response.get('orderID')}")
            print(f"  Status: {response.get('status')}")
            
            return response
            
        except Exception as e:
            print(f"✗ 市价单失败: {e}")
            return {"error": str(e)}
    
    def place_batch_orders(
        self,
        orders: list,
        tick_size: str = "0.01",
        neg_risk: bool = False
    ) -> dict:
        """
        批量下单（最多 15 个订单）
        
        Args:
            orders: 订单列表，每个订单包含 {token_id, side, price, size}
            tick_size: 价格精度
            neg_risk: 是否为多结果市场
            
        Returns:
            批量订单响应
        """
        try:
            print(f"\n批量下单: {len(orders)} 个订单")
            
            # 创建订单列表
            order_args_list = []
            for order in orders:
                order_side = BUY if order['side'].upper() == "BUY" else SELL
                
                # 创建订单（不提交）
                signed_order = self.client.create_order(
                    OrderArgs(
                        token_id=order['token_id'],
                        price=order['price'],
                        size=order['size'],
                        side=order_side,
                    ),
                    options={
                        "tick_size": tick_size,
                        "neg_risk": neg_risk
                    }
                )
                
                order_args_list.append(
                    PostOrdersArgs(
                        order=signed_order,
                        order_type=OrderType.GTC
                    )
                )
            
            # 批量提交
            response = self.client.post_orders(order_args_list)
            
            print(f"✓ 批量订单已提交")
            print(f"  成功: {len(response.get('success', []))}")
            print(f"  失败: {len(response.get('errors', []))}")
            
            return response
            
        except Exception as e:
            print(f"✗ 批量下单失败: {e}")
            return {"error": str(e)}
    
    def cancel_order(self, order_id: str) -> dict:
        """
        取消订单
        
        Args:
            order_id: 订单 ID
            
        Returns:
            取消响应
        """
        try:
            print(f"\n取消订单: {order_id}")
            
            response = self.client.cancel(order_id)
            
            print(f"✓ 订单已取消")
            return response
            
        except Exception as e:
            print(f"✗ 取消订单失败: {e}")
            return {"error": str(e)}
    
    def cancel_all_orders(self, market_id: str = None) -> dict:
        """
        取消所有订单（可选指定市场）
        
        Args:
            market_id: 市场 ID（可选）
            
        Returns:
            取消响应
        """
        try:
            if market_id:
                print(f"\n取消市场 {market_id} 的所有订单")
                response = self.client.cancel_market_orders(market_id)
            else:
                print(f"\n取消所有订单")
                response = self.client.cancel_all()
            
            print(f"✓ 订单已取消")
            return response
            
        except Exception as e:
            print(f"✗ 取消订单失败: {e}")
            return {"error": str(e)}
    
    def get_open_orders(self, market_id: str = None) -> list:
        """
        获取未成交订单
        
        Args:
            market_id: 市场 ID（可选）
            
        Returns:
            订单列表
        """
        try:
            if market_id:
                orders = self.client.get_orders(market=market_id)
            else:
                orders = self.client.get_orders()
            
            print(f"\n未成交订单: {len(orders)}")
            for order in orders[:5]:  # 只显示前 5 个
                print(f"  Order ID: {order.get('id')}")
                print(f"  Side: {order.get('side')}")
                print(f"  Price: {order.get('price')}")
                print(f"  Size: {order.get('size')}")
                print()
            
            return orders
            
        except Exception as e:
            print(f"✗ 获取订单失败: {e}")
            return []
    
    def get_balance(self) -> dict:
        """
        获取账户余额
        
        Returns:
            余额信息
        """
        try:
            # 获取 USDC 余额
            balance = self.client.get_balance()
            
            print(f"\n账户余额:")
            print(f"  USDC: ${balance.get('usdc', 0)}")
            
            return balance
            
        except Exception as e:
            print(f"✗ 获取余额失败: {e}")
            return {}


def example_1_simple_buy():
    """示例 1: 简单的买入订单"""
    print("\n" + "=" * 80)
    print("示例 1: 简单的买入订单")
    print("=" * 80)
    
    trader = PolymarketTrader()
    
    # 示例：买入 YES 代币
    # 注意：这些是示例值，实际使用时需要替换为真实的 token_id
    token_id = "YOUR_TOKEN_ID_HERE"
    
    # 以 0.65 的价格（65%）买入 $10 的 YES 代币
    response = trader.place_limit_order(
        token_id=token_id,
        side="BUY",
        price=0.65,
        size=10.0,
        tick_size="0.01",
        neg_risk=False
    )
    
    return response


def example_2_market_making():
    """示例 2: 做市（同时挂买单和卖单）"""
    print("\n" + "=" * 80)
    print("示例 2: 做市策略")
    print("=" * 80)
    
    trader = PolymarketTrader()
    
    token_id = "YOUR_TOKEN_ID_HERE"
    
    # 批量下单：在 0.48 买入，在 0.52 卖出
    orders = [
        {"token_id": token_id, "side": "BUY", "price": 0.48, "size": 100},
        {"token_id": token_id, "side": "BUY", "price": 0.47, "size": 100},
        {"token_id": token_id, "side": "SELL", "price": 0.52, "size": 100},
        {"token_id": token_id, "side": "SELL", "price": 0.53, "size": 100},
    ]
    
    response = trader.place_batch_orders(orders, tick_size="0.01", neg_risk=False)
    
    return response


def example_3_ai_driven_trading():
    """示例 3: 基于 AI 分析的自动交易"""
    print("\n" + "=" * 80)
    print("示例 3: AI 驱动的自动交易")
    print("=" * 80)
    
    # 1. 从数据库读取 AI 分析结果
    from app.utils.db import get_db_connection
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # 获取高分机会（机会评分 > 80）
        cursor.execute("""
            SELECT 
                a.market_id,
                a.recommendation,
                a.confidence_score,
                a.opportunity_score,
                a.ai_predicted_probability,
                a.market_probability,
                m.slug
            FROM qd_polymarket_ai_analysis a
            LEFT JOIN qd_polymarket_markets m ON a.market_id = m.market_id
            WHERE a.opportunity_score > 80
            AND a.created_at > NOW() - INTERVAL '1 hour'
            ORDER BY a.opportunity_score DESC
            LIMIT 5
        """)
        
        opportunities = cursor.fetchall()
        cursor.close()
    
    if not opportunities:
        print("没有找到高分机会")
        return
    
    print(f"找到 {len(opportunities)} 个高分机会\n")
    
    # 2. 初始化交易客户端
    trader = PolymarketTrader()
    
    # 3. 根据 AI 建议下单
    for opp in opportunities:
        market_id = opp['market_id']
        recommendation = opp['recommendation']
        confidence = opp['confidence_score']
        opportunity_score = opp['opportunity_score']
        ai_prob = opp['ai_predicted_probability']
        market_prob = opp['market_probability']
        
        print(f"市场 ID: {market_id}")
        print(f"AI 建议: {recommendation}")
        print(f"置信度: {confidence}%")
        print(f"机会评分: {opportunity_score}")
        print(f"AI 预测概率: {ai_prob}%")
        print(f"市场概率: {market_prob}%")
        print()
        
        # 根据建议决定交易
        if recommendation == "BUY_YES" and confidence > 70:
            # 买入 YES 代币
            # 注意：需要获取 token_id
            print(f"→ 执行买入 YES 代币")
            # token_id = get_yes_token_id(market_id)
            # trader.place_limit_order(
            #     token_id=token_id,
            #     side="BUY",
            #     price=market_prob / 100,  # 当前市场价
            #     size=10.0,  # $10
            #     tick_size="0.01",
            #     neg_risk=False
            # )
        
        elif recommendation == "BUY_NO" and confidence > 70:
            # 买入 NO 代币
            print(f"→ 执行买入 NO 代币")
            # token_id = get_no_token_id(market_id)
            # trader.place_limit_order(...)
        
        print("-" * 80)


def main():
    """主函数"""
    print("=" * 80)
    print("Polymarket 交易示例")
    print("=" * 80)
    
    # 检查环境变量
    if not os.getenv("POLYMARKET_PRIVATE_KEY"):
        print("\n⚠️  警告: 未设置 POLYMARKET_PRIVATE_KEY 环境变量")
        print("请在 .env 文件中设置:")
        print("  POLYMARKET_PRIVATE_KEY=your_private_key_here")
        print("  POLYMARKET_FUNDER_ADDRESS=your_wallet_address_here")
        print("\n注意: 私钥不要包含 0x 前缀")
        return
    
    # 运行示例
    try:
        # 取消注释以运行不同的示例
        
        # example_1_simple_buy()
        # example_2_market_making()
        example_3_ai_driven_trading()
        
    except Exception as e:
        print(f"\n✗ 错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
