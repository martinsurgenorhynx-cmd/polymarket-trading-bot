#!/usr/bin/env python
"""
调试 _parse_gamma_events 方法
查看解析过程中的 condition_id
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.data_sources.polymarket import PolymarketDataSource
import requests

def main():
    print("=" * 80)
    print(" 调试 _parse_gamma_events")
    print("=" * 80)
    
    # 直接获取 API 数据
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json'
    })
    
    gamma_api = "https://gamma-api.polymarket.com"
    url = f"{gamma_api}/events"
    params = {"active": "true", "closed": "false", "limit": 2}
    
    print(f"\n获取 API 数据...")
    response = session.get(url, params=params, timeout=10)
    
    if response.status_code != 200:
        print(f"✗ API 请求失败: {response.status_code}")
        return
    
    events_data = response.json()
    print(f"✓ 获取到 {len(events_data)} 个事件")
    
    # 检查第一个事件的 markets
    if len(events_data) > 0:
        event = events_data[0]
        markets = event.get("markets", [])
        
        print(f"\n第一个事件包含 {len(markets)} 个市场")
        
        if len(markets) > 0:
            market = markets[0]
            print(f"\n第一个市场:")
            print(f"  id: {market.get('id')}")
            print(f"  question: {market.get('question', '')[:60]}")
            print(f"  conditionId: {market.get('conditionId')}")
    
    # 使用 PolymarketDataSource 解析
    print(f"\n使用 _parse_gamma_events 解析...")
    polymarket = PolymarketDataSource()
    parsed_markets = polymarket._parse_gamma_events(events_data)
    
    print(f"✓ 解析得到 {len(parsed_markets)} 个市场")
    
    if len(parsed_markets) > 0:
        market = parsed_markets[0]
        print(f"\n第一个解析后的市场:")
        print(f"  market_id: {market.get('market_id')}")
        print(f"  question: {market.get('question', '')[:60]}")
        print(f"  condition_id: {market.get('condition_id')}")
        
        if market.get('condition_id'):
            print(f"\n✓ condition_id 存在于解析结果中")
        else:
            print(f"\n✗ condition_id 不存在于解析结果中")
            print(f"\n所有字段: {list(market.keys())}")


if __name__ == '__main__':
    main()
