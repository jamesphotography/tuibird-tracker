#!/usr/bin/env python3
"""调试API调用"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from config import ConfigManager, EBIRD_API_BASE_URL

# 获取API Key
config = ConfigManager()
api_key = config.get_api_key()

print("=" * 60)
print("🔍 调试API调用")
print("=" * 60)
print(f"\nAPI Key: {api_key[:4]}...{api_key[-4:]}")
print(f"Base URL: {EBIRD_API_BASE_URL}")

# 测试URL构建
species_code = "goufin3"
region_code = "AU"
days_back = 14

# 方法1: 按区域查询
url1 = f"{EBIRD_API_BASE_URL}data/obs/{region_code}/recent/{species_code}"
print(f"\n方法1 URL: {url1}")

# 实际测试
import requests

headers = {'X-eBirdApiToken': api_key}
params = {'back': days_back, 'detail': 'full'}

print("\n测试API调用...")
print(f"Headers: {headers}")
print(f"Params: {params}")

try:
    response = requests.get(url1, headers=headers, params=params, timeout=20)
    print(f"\n状态码: {response.status_code}")
    print(f"Response URL: {response.url}")

    if response.status_code == 200:
        data = response.json()
        print(f"✅ 成功！获取到 {len(data)} 条记录")
        if data:
            print("\n第一条记录示例:")
            print(data[0])
    else:
        print(f"❌ 失败！")
        print(f"Response Text: {response.text[:200]}")

except Exception as e:
    print(f"❌ 错误: {e}")
