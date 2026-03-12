#!/usr/bin/env python
"""
调试 Polymarket API 响应
查看实际返回的字段
"""
import requests
import json

def main():
    print("=" * 80)
    print(" 调试 Polymarket Gamma API 响应")
    print("=" * 80)
    
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json'
    })
    
    gamma_api = "https://gamma-api.polymarket.com"
    
    # 获取事件列表
    url = f"{gamma_api}/events"
    params = {
        "active": "true",
        "closed": "false",
        "limit": 3
    }
    
    print(f"\n请求: {url}")
    print(f"参数: {params}")
    
    response = session.get(url, params=params, timeout=10)
    
    print(f"\n状态码: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        
        if isinstance(data, list) and len(data) > 0:
            print(f"\n返回 {len(data)} 个事件")
            
            # 显示第一个事件的所有字段
            first_event = data[0]
            print(f"\n第一个事件的字段:")
            print(json.dumps(first_event, indent=2, ensure_ascii=False)[:2000])
            
            # 检查是否有 conditionId
            if "conditionId" in first_event:
                print(f"\n✓ 事件包含 conditionId: {first_event['conditionId']}")
            else:
                print(f"\n✗ 事件不包含 conditionId")
            
            # 检查 markets 字段
            if "markets" in first_event:
                markets = first_event["markets"]
                print(f"\n事件包含 {len(markets)} 个市场")
                
                if len(markets) > 0:
                    first_market = markets[0]
                    print(f"\n第一个市场的字段:")
                    print(json.dumps(first_market, indent=2, ensure_ascii=False)[:2000])
                    
                    if "conditionId" in first_market:
                        print(f"\n✓ 市场包含 conditionId: {first_market['conditionId']}")
                    else:
                        print(f"\n✗ 市场不包含 conditionId")
        else:
            print(f"\n返回数据格式: {type(data)}")
            print(json.dumps(data, indent=2, ensure_ascii=False)[:1000])
    else:
        print(f"\n请求失败: {response.text[:500]}")


if __name__ == '__main__':
    main()
