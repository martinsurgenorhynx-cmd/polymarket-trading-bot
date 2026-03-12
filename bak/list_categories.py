#!/usr/bin/env python
"""
列出Polymarket所有可用的分类（标签）
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

def main():
    print("=" * 80)
    print("Polymarket 可用分类列表")
    print("=" * 80)
    
    # 方法1：尝试从API获取标签
    print("\n正在从API获取标签...")
    try:
        import requests
        url = "https://gamma-api.polymarket.com/tags"
        response = requests.get(url, timeout=10)
        
        print(f"API状态码: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"API返回数据类型: {type(data)}")
            
            if isinstance(data, list):
                print(f"\n找到 {len(data)} 个标签:\n")
                for i, item in enumerate(data[:50], 1):  # 只显示前50个
                    if isinstance(item, dict):
                        slug = item.get('slug', '')
                        label = item.get('label', '')
                        count = item.get('market_count', 0)
                        print(f"{i:3d}. {slug:30s} {label:30s} ({count} markets)")
                    else:
                        print(f"{i:3d}. {item}")
            elif isinstance(data, dict):
                print(f"API返回字典，keys: {list(data.keys())}")
                if 'data' in data:
                    items = data['data']
                    print(f"\n找到 {len(items)} 个标签:\n")
                    for i, item in enumerate(items[:50], 1):
                        if isinstance(item, dict):
                            slug = item.get('slug', '')
                            label = item.get('label', '')
                            count = item.get('market_count', 0)
                            print(f"{i:3d}. {slug:30s} {label:30s} ({count} markets)")
                else:
                    print(f"完整响应: {str(data)[:500]}")
        else:
            print(f"响应内容: {response.text[:500]}")
    except Exception as e:
        print(f"获取标签失败: {e}")
        import traceback
        traceback.print_exc()
    
    # 方法2：从数据库查看已有市场的分类
    print("\n" + "=" * 80)
    print("从数据库查看已有市场的分类分布")
    print("=" * 80)
    
    try:
        from app.utils.db import get_db_connection
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            query = """
                SELECT category, COUNT(*) as count
                FROM qd_polymarket_markets
                GROUP BY category
                ORDER BY count DESC
            """
            
            cursor.execute(query)
            rows = cursor.fetchall()
            
            if rows:
                print(f"\n找到 {len(rows)} 个分类:\n")
                for i, row in enumerate(rows, 1):
                    print(f"{i:3d}. {row['category']:30s} ({row['count']} markets)")
            else:
                print("\n数据库中暂无市场数据")
    except Exception as e:
        print(f"查询数据库失败: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 80)

if __name__ == '__main__':
    main()
