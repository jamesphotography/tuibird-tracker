#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
回到最原始、最简单的状态
不需要用户输入，直接演示几个预设查询
这就是你要的最早期版本的效果
"""

import requests
import sqlite3
import json
import os

# 配置
CONFIG_FILE = "ebird_config.json"
DB_FILE = "ebird_reference.sqlite"

def load_api_key():
    """加载保存的API Key"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                return config.get('api_key', '')
        except:
            pass
    return ''

def search_bird(query):
    """搜索鸟类"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT english_name, chinese_simplified, ebird_code 
            FROM BirdCountInfo 
            WHERE (chinese_simplified LIKE ? OR english_name LIKE ?)
                AND ebird_code IS NOT NULL 
                AND ebird_code != 'None'
                AND LENGTH(ebird_code) > 2
            LIMIT 5
        """, (f'%{query}%', f'%{query}%'))
        
        return cursor.fetchall()
        
    except Exception as e:
        print(f"搜索出错: {e}")
        return []
    finally:
        conn.close()

def get_observations(species_code, api_key):
    """获取观测记录"""
    try:
        url = f"https://api.ebird.org/v2/data/obs/AU-SA/recent/{species_code}"
        headers = {'X-eBirdApiToken': api_key}
        params = {'back': 7}
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            return response.json()
        else:
            return []
    except:
        return []

def show_results(birds, query):
    """显示搜索结果"""
    if not birds:
        print(f"未找到 '{query}' 相关鸟类")
        return
    
    print(f"搜索 '{query}' 的结果:")
    for i, (en_name, cn_name, code) in enumerate(birds, 1):
        name = cn_name if cn_name else en_name
        print(f"  {i}. {name} ({en_name})")

def demo_query(query, api_key):
    """演示一个查询"""
    print(f"\n{'='*20}")
    print(f"🔍 搜索: {query}")
    
    birds = search_bird(query)
    show_results(birds, query)
    
    if birds:
        # 使用第一个结果
        en_name, cn_name, species_code = birds[0]
        bird_name = cn_name if cn_name else en_name
        
        print(f"选择: {bird_name}")
        
        observations = get_observations(species_code, api_key)
        
        if observations:
            print(f"✅ 找到 {len(observations)} 条澳大利亚观测记录")
            
            # 显示前3条
            for i, obs in enumerate(observations[:3], 1):
                print(f"  {i}. {obs.get('locName', '未知地点')}")
                print(f"     时间: {obs.get('obsDt', '未知')}")
                print(f"     数量: {obs.get('howMany', '未知')}")
        else:
            print("📭 南澳州地区暂无观测记录")

def main():
    """主程序"""
    print("🦅 eBird 鸟类追踪器 - 回到最原始状态")
    print("=" * 50)
    
    # 检查环境
    if not os.path.exists(DB_FILE):
        print("❌ 数据库文件不存在")
        return
        
    api_key = load_api_key()
    if not api_key:
        print("❌ 没有API Key")
        return
    
    print(f"✅ API Key: {api_key[:4]}...{api_key[-4:]}")
    
    print("\n这就是最早期版本的简单演示:")
    print("- 支持中英文搜索")
    print("- 查询南澳州(AU-SA)观测记录")  
    print("- 没有复杂的GUI问题")
    print("- 回到最基础的状态")
    
    # 演示几个查询
    demo_queries = ["笑翠鸟", "robin", "鹦鹉", "magpie"]
    
    for query in demo_queries:
        demo_query(query, api_key)
    
    print(f"\n{'='*50}")
    print("🎉 演示完成！")
    print("这就是最原始、最简单的版本效果")
    print("没有GUI问题，没有复杂的输入处理")
    print("就是纯粹的鸟类搜索和数据展示")

if __name__ == "__main__":
    main()