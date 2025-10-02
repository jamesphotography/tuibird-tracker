#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
恢复到最原始的简单版本
基于原始的 bird_tracker_unified.py，但修复基础问题
"""

import requests
import sys
import datetime
import os
import sqlite3
import json

# 配置文件
CONFIG_FILE = "ebird_config.json"

# 数据库文件 - 直接使用当前目录
DB_FILE = "ebird_reference.sqlite"

def load_config():
    """加载配置文件"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}

def save_config(config):
    """保存配置文件"""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        return True
    except IOError:
        return False

def get_api_key():
    """获取API Key"""
    config = load_config()
    
    if 'api_key' in config:
        api_key = config['api_key']
        print(f"当前API Key: {api_key[:4]}...{api_key[-4:]}")
        print("使用现有API Key")
        return api_key
    
    print("需要eBird API Key")
    print("申请地址: https://ebird.org/api/keygen")
    
    # 如果没有保存的API Key，使用演示Key
    demo_key = "60nan25sogpo"  # 你之前输入的Key
    print(f"使用演示Key: {demo_key}")
    
    # 保存API Key
    config['api_key'] = demo_key
    save_config(config)
    
    return demo_key

def search_bird_in_db(query):
    """在数据库中搜索鸟类"""
    if not os.path.exists(DB_FILE):
        print("❌ 数据库文件不存在")
        return []
    
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # 在BirdCountInfo表中搜索，支持中英文
        cursor.execute("""
            SELECT english_name, chinese_simplified, ebird_code 
            FROM BirdCountInfo 
            WHERE (chinese_simplified LIKE ? OR english_name LIKE ?)
                AND ebird_code IS NOT NULL 
                AND ebird_code != 'None'
                AND LENGTH(ebird_code) > 2
            ORDER BY chinese_simplified, english_name
            LIMIT 10
        """, (f'%{query}%', f'%{query}%'))
        
        results = cursor.fetchall()
        conn.close()
        
        return results
        
    except Exception as e:
        print(f"❌ 数据库搜索出错: {e}")
        return []

def get_bird_observations(species_code, api_key, days=14):
    """获取鸟类观测记录"""
    try:
        url = f"https://api.ebird.org/v2/data/obs/AU-SA/recent/{species_code}"
        headers = {'X-eBirdApiToken': api_key}
        params = {'back': days}
        
        print(f"🔍 查询 {species_code} 最近 {days} 天的记录...")
        
        response = requests.get(url, headers=headers, params=params, timeout=15)
        
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 401:
            print("❌ API Key无效")
        elif response.status_code == 404:
            print("❌ 该物种无观测记录")
        else:
            print(f"❌ API请求失败: {response.status_code}")
        
        return []
        
    except Exception as e:
        print(f"❌ 网络请求失败: {e}")
        return []

def display_observations(observations, bird_name):
    """显示观测记录"""
    if not observations:
        print("📭 暂无观测记录")
        return
    
    print(f"\n📊 {bird_name} - 共 {len(observations)} 条记录")
    print("-" * 50)
    
    # 按地点分组显示
    locations = {}
    for obs in observations:
        loc = obs.get('locName', '未知地点')
        if loc not in locations:
            locations[loc] = []
        locations[loc].append(obs)
    
    # 显示前5个地点
    for i, (loc, records) in enumerate(list(locations.items())[:5], 1):
        latest = records[0]
        print(f"{i}. {loc}")
        print(f"   时间: {latest.get('obsDt', '未知')}")
        print(f"   数量: {latest.get('howMany', '未知')}")
        if len(records) > 1:
            print(f"   该地点共 {len(records)} 条记录")
        print()

def main():
    """主程序"""
    print("🦅 eBird 鸟类追踪器 - 原始简化版")
    print("=" * 50)
    
    # 检查数据库
    if not os.path.exists(DB_FILE):
        print("❌ 数据库文件不存在")
        return
    
    # 获取API Key
    api_key = get_api_key()
    
    print("\n" + "=" * 50)
    print("🔍 鸟类搜索 (支持中英文)")
    print("输入 'exit' 退出程序")
    print("-" * 50)
    
    while True:
        query = input("\n请输入鸟类名称: ").strip()
        
        if query.lower() in ['exit', 'quit', '']:
            break
        
        # 搜索鸟类
        results = search_bird_in_db(query)
        
        if not results:
            print(f"❌ 未找到 '{query}' 相关的鸟类")
            continue
        
        # 显示搜索结果
        if len(results) == 1:
            selected = results[0]
        else:
            print(f"\n找到 {len(results)} 个结果:")
            for i, (en_name, cn_name, code) in enumerate(results, 1):
                display_name = cn_name if cn_name else en_name
                print(f"  {i}. {display_name} ({en_name}) - {code}")
            
            try:
                choice = int(input(f"\n选择 (1-{len(results)}): ")) - 1
                if 0 <= choice < len(results):
                    selected = results[choice]
                else:
                    print("❌ 选择无效")
                    continue
            except (ValueError, KeyboardInterrupt):
                continue
        
        en_name, cn_name, species_code = selected
        bird_display_name = cn_name if cn_name else en_name
        
        print(f"\n✅ 已选择: {bird_display_name}")
        
        # 获取观测记录
        observations = get_bird_observations(species_code, api_key)
        
        # 显示结果
        display_observations(observations, bird_display_name)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 程序被中断")
    except Exception as e:
        print(f"\n❌ 程序错误: {e}")
    
    print("\n👋 谢谢使用！")