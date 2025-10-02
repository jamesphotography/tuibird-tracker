#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
eBird 鸟类追踪器 - 极简版本
只保留核心功能，最大化稳定性
"""

import requests
import sys
import datetime
import os
import sqlite3
import json

# 配置文件
CONFIG_FILE = "ebird_config.json"
DB_FILE = "ebird_reference.sqlite"

def load_config():
    """加载配置"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {}

def save_config(config):
    """保存配置"""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except:
        pass

def get_api_key():
    """获取API Key"""
    config = load_config()
    
    if 'api_key' in config:
        print(f"当前API Key: {config['api_key'][:4]}...{config['api_key'][-4:]}")
        choice = input("是否使用当前API Key? [Y/n]: ").strip().lower()
        if choice in ['', 'y', 'yes']:
            return config['api_key']
    
    print("\n请输入eBird API Key:")
    print("申请地址: https://ebird.org/api/keygen")
    
    while True:
        api_key = input("API Key: ").strip()
        if len(api_key) >= 8:
            config['api_key'] = api_key
            save_config(config)
            print("✅ API Key已保存")
            return api_key
        print("❌ API Key太短，请重新输入")

def search_bird(query):
    """搜索鸟类"""
    if not os.path.exists(DB_FILE):
        print("❌ 数据库文件不存在")
        return None
    
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # 搜索鸟类
        cursor.execute("""
            SELECT code, species_english, scientific_name 
            FROM bird_ioc 
            WHERE species_english LIKE ? OR scientific_name LIKE ?
            ORDER BY species_english
            LIMIT 10
        """, (f'%{query}%', f'%{query}%'))
        
        results = cursor.fetchall()
        conn.close()
        
        if not results:
            print(f"未找到包含 '{query}' 的鸟类")
            return None
        
        if len(results) == 1:
            return results[0]
        
        # 多个结果，让用户选择
        print(f"\n找到 {len(results)} 个匹配结果:")
        for i, (code, en_name, sci_name) in enumerate(results, 1):
            print(f"  {i}. {en_name} ({sci_name})")
        
        while True:
            try:
                choice = input(f"请选择 (1-{len(results)}): ").strip()
                if not choice:
                    return None
                choice = int(choice)
                if 1 <= choice <= len(results):
                    return results[choice - 1]
                print(f"请输入 1-{len(results)} 之间的数字")
            except ValueError:
                print("请输入有效的数字")
            except (KeyboardInterrupt, EOFError):
                return None
    
    except Exception as e:
        print(f"❌ 搜索出错: {e}")
        return None

def get_observations(species_code, api_key, days=14):
    """获取观测记录"""
    print(f"🔍 查询 {species_code} 最近 {days} 天的观测记录...")
    
    try:
        url = f"https://api.ebird.org/v2/data/obs/AU/recent/{species_code}"
        headers = {'X-eBirdApiToken': api_key}
        params = {'back': days, 'detail': 'full'}
        
        response = requests.get(url, headers=headers, params=params, timeout=10)
        
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 401:
            print("❌ API Key无效")
            return None
        else:
            print(f"❌ API请求失败: {response.status_code}")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"❌ 网络请求失败: {e}")
        return None

def show_observations(observations, species_name):
    """显示观测记录"""
    if not observations:
        print("📭 未找到观测记录")
        return
    
    print(f"\n🎯 {species_name} - 共找到 {len(observations)} 条记录")
    print("-" * 50)
    
    # 按地点分组
    locations = {}
    for obs in observations:
        loc = obs.get('locName', '未知地点')
        if loc not in locations:
            locations[loc] = []
        locations[loc].append(obs)
    
    for loc, records in locations.items():
        print(f"\n📍 {loc}")
        
        for record in records[:3]:  # 每个地点最多显示3条
            date = record.get('obsDt', '未知时间')
            count = record.get('howMany', '未知')
            observer = record.get('userDisplayName', '匿名')
            
            print(f"   • 日期: {date}")
            print(f"     数量: {count}")
            print(f"     观察者: {observer}")
            
            if len(records) > 3:
                print(f"   ... 还有 {len(records) - 3} 条记录")
            print()

def main():
    """主函数"""
    print("🦅 eBird 鸟类追踪器 - 极简版本")
    print("=" * 40)
    
    # 获取API Key
    api_key = get_api_key()
    if not api_key:
        return
    
    while True:
        try:
            print("\n" + "=" * 40)
            query = input("🔍 请输入要查询的鸟类名称 (回车退出): ").strip()
            
            if not query:
                print("👋 退出程序")
                break
            
            # 搜索鸟类
            bird = search_bird(query)
            if not bird:
                continue
            
            species_code, en_name, sci_name = bird
            species_name = f"{en_name} ({sci_name})"
            
            print(f"✅ 选择: {species_name}")
            
            # 获取观测记录
            observations = get_observations(species_code, api_key)
            
            # 显示结果
            show_observations(observations, species_name)
            
        except (KeyboardInterrupt, EOFError):
            print("\n👋 退出程序")
            break
        except Exception as e:
            print(f"\n❌ 程序出错: {e}")
            continue

if __name__ == "__main__":
    main()