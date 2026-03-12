#!/usr/bin/env python
"""
测试 LLM API 调用

检查 LLM 服务是否正常工作
"""
import os
import sys
import json

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 加载环境变量
from dotenv import load_dotenv
load_dotenv()

from app.services.llm import LLMService
import requests

print("=" * 80)
print("LLM API 调用测试")
print("=" * 80)

# 测试0: 检查配置
print("\n[测试0] 检查 LLM 配置")
print("-" * 80)

print(f"LLM_PROVIDER: {os.getenv('LLM_PROVIDER', 'Not set')}")
print(f"LLM_MODEL: {os.getenv('LLM_MODEL', 'Not set')}")
print(f"LLM_API_KEY: {'已设置' if os.getenv('LLM_API_KEY') else '未设置'}")
print(f"LLM_BASE_URL: {os.getenv('LLM_BASE_URL', 'Not set')}")

print(f"\nOPENAI_API_KEY: {'已设置' if os.getenv('OPENAI_API_KEY') else '未设置'}")
print(f"OPENAI_BASE_URL: {os.getenv('OPENAI_BASE_URL', 'Not set')}")
print(f"OPENAI_MODEL: {os.getenv('OPENAI_MODEL', 'Not set')}")

print(f"\nDEEPSEEK_API_KEY: {'已设置' if os.getenv('DEEPSEEK_API_KEY') else '未设置'}")
print(f"DEEPSEEK_BASE_URL: {os.getenv('DEEPSEEK_BASE_URL', 'Not set')}")
print(f"DEEPSEEK_MODEL: {os.getenv('DEEPSEEK_MODEL', 'Not set')}")

# 测试1: 直接调用 DeepSeek API
print("\n" + "=" * 80)
print("[测试1] 直接调用 DeepSeek API（不通过 LLMService）")
print("-" * 80)

api_key = os.getenv('DEEPSEEK_API_KEY')
base_url = os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com/v1')
model = os.getenv('DEEPSEEK_MODEL', 'deepseek-chat')

if api_key:
    print(f"API Key: {api_key[:20]}...")
    print(f"Base URL: {base_url}")
    print(f"Model: {model}")
    
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    
    payload = {
        'model': model,
        'messages': [
            {
                'role': 'user',
                'content': '你好，请回复"测试成功"。'
            }
        ],
        'temperature': 0.7
    }
    
    print(f"\n请求 URL: {base_url}/chat/completions")
    print(f"请求 Payload: {json.dumps(payload, ensure_ascii=False, indent=2)}")
    
    try:
        response = requests.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=30
        )
        
        print(f"\n响应状态码: {response.status_code}")
        print(f"响应内容: {response.text[:500]}")
        
        if response.status_code == 200:
            result = response.json()
            content = result['choices'][0]['message']['content']
            print(f"\n✓ 直接调用成功")
            print(f"回复: {content}")
        else:
            print(f"\n✗ 直接调用失败")
            
    except Exception as e:
        print(f"\n✗ 直接调用异常: {e}")
        import traceback
        traceback.print_exc()
else:
    print("✗ DEEPSEEK_API_KEY 未设置")

# 测试2: 通过 LLMService 调用
print("\n" + "=" * 80)
print("[测试2] 通过 LLMService 调用（use_json_mode=False）")
print("-" * 80)

llm_service = LLMService()

messages = [
    {
        "role": "user",
        "content": "你好，请回复'测试成功'。"
    }
]

try:
    print("正在调用 LLM API...")
    response = llm_service.call_llm_api(
        messages=messages,
        temperature=0.7,
        use_json_mode=False  # 关键：不使用 JSON 模式
    )
    print(f"✓ 调用成功")
    print(f"\n回复:\n{response}")
except Exception as e:
    print(f"✗ 调用失败: {e}")
    import traceback
    traceback.print_exc()

# 测试3: 通过 LLMService 调用（use_json_mode=True，测试是否支持）
print("\n" + "=" * 80)
print("[测试3] 通过 LLMService 调用（use_json_mode=True）")
print("-" * 80)

try:
    print("正在调用 LLM API...")
    response = llm_service.call_llm_api(
        messages=messages,
        temperature=0.7,
        use_json_mode=True  # 测试 JSON 模式
    )
    print(f"✓ 调用成功（支持 JSON 模式）")
    print(f"\n回复:\n{response}")
except Exception as e:
    print(f"✗ 调用失败（不支持 JSON 模式或格式不对）: {e}")

print("\n" + "=" * 80)
print("测试完成")
print("=" * 80)
