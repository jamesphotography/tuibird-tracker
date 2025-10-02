#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🌍 eBird 区域鸟种查询器 V3.0 (增强版)
根据用户输入的区域，显示该区域内所有鸟种的最近观测记录

🆕 新增功能：
1. eBird热点精确查询 - 直接查询指定热点的观测记录
2. 热点搜索功能 - 根据地名搜索相关的eBird热点
3. 改进的用户界面和查询选项

基于你最早的代码设计，专门用于区域查询功能
"""

import requests
import sys
import datetime
import os
import sqlite3
import time
import json
import geocoder
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable
from collections import Counter

def resource_path(relative_path):
    """获取资源的绝对路径，适用于开发环境和 PyInstaller 打包后的环境"""
    try:
        base_path = getattr(sys, '_MEIPASS', None)
        if base_path is None:
            raise AttributeError
    except AttributeError:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# 【核心】指定您的鸟类资料库文件
DB_FILE = resource_path("ebird_reference.sqlite")
# 【配置文件】保存API Key等配置
CONFIG_FILE = "ebird_config.json"

def load_config():
    """加载配置文件"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            print("⚠️ 配置文件损坏，请在主菜单中重新设置API Key。")
    return {}

def get_api_key():
    """获取API Key"""
    config = load_config()
    if 'api_key' in config:
        return config['api_key']
    else:
        print("❌ 未找到API Key配置！")
        print("请先在主菜单中设置API Key（选项2: API Key管理）")
        input("按回车键返回主菜单...")
        sys.exit(1)

def load_bird_database(db_file):
    """加载鸟类数据库"""
    if not os.path.exists(db_file):
        print(f"❌ 错误: 未找到数据库文件 '{db_file}'")
        print("请确保数据库文件在程序目录中")
        sys.exit(1)
    
    try:
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        cursor.execute("SELECT ebird_code, chinese_simplified, english_name FROM BirdCountInfo WHERE ebird_code IS NOT NULL AND ebird_code != ''")
        birds = [{'code': row[0], 'cn_name': row[1], 'en_name': row[2]} for row in cursor.fetchall()]
        conn.close()
        print(f"✅ 成功加载鸟类数据库: {len(birds)} 种鸟类")
        return birds
    except sqlite3.Error as e:
        print(f"❌ 数据库访问错误: {e}")
        sys.exit(1)

def search_hotspots(query, api_key, region_code="world"):
    """搜索eBird热点"""
    print(f"🔍 搜索eBird热点: {query}...")
    
    url = "https://api.ebird.org/v2/ref/hotspot/find"
    headers = {'X-eBirdApiToken': api_key}
    params = {
        'q': query,
        'fmt': 'json'
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        if response.status_code == 200:
            hotspots = response.json()
            print(f"✅ 找到 {len(hotspots)} 个相关热点")
            return hotspots
        else:
            print(f"⚠️ 热点搜索失败 (状态码: {response.status_code})")
            return []
    except requests.exceptions.RequestException as e:
        print(f"❌ 热点搜索网络请求失败: {e}")
        return []

def fetch_hotspot_observations(location_id, days_back, api_key):
    """获取指定热点的所有观测记录"""
    print(f"🔍 查询热点观测记录: {location_id}...")
    
    url = f"https://api.ebird.org/v2/data/obs/{location_id}/recent"
    headers = {'X-eBirdApiToken': api_key}
    params = {
        'back': days_back,
        'detail': 'full'
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 找到 {len(data)} 条观测记录")
            return data
        elif response.status_code == 404:
            print("⚠️ 该热点没有观测记录")
            return []
        else:
            print(f"❌ API请求失败 (状态码: {response.status_code})")
            return []
    except requests.exceptions.RequestException as e:
        print(f"❌ 网络请求失败: {e}")
        return []

def get_location_from_ip():
    """从IP地址获取大概位置"""
    try:
        g = geocoder.ip('me')
        if g.ok and g.latlng:
            return g.city or g.address, g.latlng
    except Exception:
        pass
    return None, None

def get_coords_from_string(input_str):
    """从字符串中提取GPS坐标"""
    try:
        if ',' in input_str:
            parts = input_str.split(',')
            if len(parts) == 2:
                lat = float(parts[0].strip())
                lng = float(parts[1].strip())
                if -90 <= lat <= 90 and -180 <= lng <= 180:
                    return lat, lng
    except (ValueError, IndexError):
        pass
    return None

def get_coords_from_placename(placename, geolocator):
    """从地名获取GPS坐标"""
    try:
        location = geolocator.geocode(placename, timeout=10)
        if location:
            return location.latitude, location.longitude
    except (GeocoderTimedOut, GeocoderUnavailable):
        print("⚠️ 地理编码服务暂时不可用，请稍后重试")
    except Exception as e:
        print(f"⚠️ 地理编码错误: {e}")
    return None

def get_placename_from_coords(lat, lng, geolocator):
    """从GPS坐标获取地名"""
    try:
        location = geolocator.reverse(f"{lat}, {lng}", timeout=10)
        if location:
            return location.address
    except Exception:
        pass
    return f"GPS位置 {lat:.4f}, {lng:.4f}"

def fetch_region_observations(lat, lng, radius, days_back, api_key):
    """获取指定区域内的所有观测记录"""
    print(f"🔍 查询区域内所有观测记录...")
    
    url = f"https://api.ebird.org/v2/data/obs/geo/recent"
    headers = {'X-eBirdApiToken': api_key}
    params = {
        'lat': lat,
        'lng': lng,
        'dist': radius,
        'back': days_back,
        'detail': 'full'
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 找到 {len(data)} 条观测记录")
            return data
        elif response.status_code == 404:
            print("⚠️ 该区域内没有观测记录")
            return []
        else:
            print(f"❌ API请求失败 (状态码: {response.status_code})")
            return []
    except requests.exceptions.RequestException as e:
        print(f"❌ 网络请求失败: {e}")
        return []

def filter_database_birds(observations, bird_database):
    """过滤出数据库中存在的鸟种观测记录"""
    db_codes = {bird['code'] for bird in bird_database}
    code_to_name_map = {bird['code']: bird['cn_name'] for bird in bird_database}
    
    filtered_obs = []
    for obs in observations:
        species_code = obs.get('speciesCode')
        if species_code in db_codes:
            obs['cn_name'] = code_to_name_map[species_code]
            filtered_obs.append(obs)
    
    print(f"✅ 在数据库中找到 {len(filtered_obs)} 条目标鸟种记录")
    return filtered_obs

def group_observations_by_species(observations):
    """按鸟种分组观测记录"""
    species_groups = {}
    
    for obs in observations:
        species_code = obs.get('speciesCode')
        if species_code not in species_groups:
            species_groups[species_code] = {
                'species_code': species_code,
                'cn_name': obs.get('cn_name', ''),
                'en_name': obs.get('comName', ''),
                'observations': []
            }
        species_groups[species_code]['observations'].append(obs)
    
    # 按观测次数排序
    sorted_groups = sorted(species_groups.values(), 
                         key=lambda x: len(x['observations']), 
                         reverse=True)
    
    return sorted_groups

def generate_region_report(species_groups, placename, radius, days_back, total_observations, show_all_records=False, query_mode="geo", hotspot_info=None):
    """生成区域鸟种记录报告"""
    # 创建输出目录
    output_dir = f"output/{datetime.datetime.now().strftime('%Y-%m-%d')}"
    os.makedirs(output_dir, exist_ok=True)
    
    # 生成文件名
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')
    report_type = "Complete" if show_all_records else "Brief"
    if query_mode == "hotspot":
        filename = f"Hotspot_{report_type}_{timestamp}.md"
    else:
        filename = f"Birding_{report_type}_{timestamp}.md"
    filepath = os.path.join(output_dir, filename)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write("# 🦅 鸟类摄影作战简报\n\n")
        f.write(f"**报告生成时间:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        if query_mode == "hotspot" and hotspot_info:
            f.write(f"**搜索模式:** eBird热点查询\n")
            f.write(f"**热点名称:** {hotspot_info['locName']}\n")
            f.write(f"**热点代码:** {hotspot_info['locId']}\n")
            f.write(f"**热点位置:** {hotspot_info.get('subnational1Name', '')}, {hotspot_info.get('countryName', '')}\n")
            if hotspot_info.get('lat') and hotspot_info.get('lng'):
                f.write(f"**GPS坐标:** {hotspot_info['lat']:.4f}, {hotspot_info['lng']:.4f}\n")
        else:
            f.write(f"**搜索模式:** 按GPS位置 (中心点: `{placename}`, 半径: `{radius}km`)\n")
        
        f.write(f"**查询范围:** 最近 **{days_back}** 天\n")
        f.write(f"**显示模式:** {'完整记录（所有观察）' if show_all_records else '简要记录（最新5条）'}\n\n")
        f.write("---\n")
        f.write("## 📋 目标鸟种记录\n\n")
        
        if not species_groups:
            f.write("*范围内未发现您数据库中的任何目标鸟种。*\n\n")
        else:
            for i, group in enumerate(species_groups, 1):
                species_code = group['species_code']
                cn_name = group['cn_name']
                en_name = group['en_name']
                obs_count = len(group['observations'])
                
                f.write(f"### No.{i}. ({species_code}) 🐦 {cn_name} ({en_name}) - {obs_count}个目击清单\n")
                
                # 按时间排序观测记录，最新的在前
                sorted_obs = sorted(group['observations'], 
                                  key=lambda x: x.get('obsDt', ''), 
                                  reverse=True)
                
                # 根据显示模式选择显示记录数量
                if show_all_records:
                    display_obs = sorted_obs  
                    if len(sorted_obs) > 5:
                        f.write(f"**显示所有 {len(sorted_obs)} 条观察记录:**\n\n")
                else:
                    display_obs = sorted_obs[:5]  
                    if len(sorted_obs) > 5:
                        f.write(f"**显示最新 5 条记录（共 {len(sorted_obs)} 条）:**\n\n")
                
                for j, obs in enumerate(display_obs, 1):
                    obs_date = obs.get('obsDt', 'Unknown')
                    location = obs.get('locName', 'Unknown Location')
                    lat = obs.get('lat')
                    lng = obs.get('lng')
                    count = obs.get('howMany', 'N/A')
                    
                    # 生成Google地图链接
                    if lat and lng:
                        maps_link = f"https://www.google.com/maps/search/?api=1&query={lat},{lng}"
                        location_link = f"[{location}]({maps_link})"
                    else:
                        location_link = location
                    
                    # 确定观测地点类型
                    if obs.get('locPrivate', False):
                        location_type = "📍私人"
                    else:
                        location_type = "🔥热点"
                    
                    # 确定时间段
                    try:
                        obs_time = obs.get('obsTime', '')
                        if obs_time:
                            hour = int(obs_time.split(':')[0])
                            if 5 <= hour < 8:
                                time_period = "🌅清晨出没"
                            elif 8 <= hour < 17:
                                time_period = "☀️日间活动"
                            else:
                                time_period = "🌇傍晚出没"
                        else:
                            time_period = "🌅清晨出没"
                    except:
                        time_period = "🌅清晨出没"
                    
                    # 如果显示所有记录，添加序号
                    if show_all_records and len(display_obs) > 5:
                        f.write(f"  {j}. **{obs_date}**: {location_link} {location_type} [{time_period}] (数量: {count})\n")
                    else:
                        f.write(f"- {obs_date}: {location_link} {location_type} [{time_period}] (数量: {count})\n")
                
                f.write("\n")
        
        f.write("---\n\n")
        f.write("### 总结报告\n")
        f.write(f"在您指定的范围内，共发现了 **{len(species_groups)}** 种在您数据库中的鸟类。\n")
        if show_all_records:
            total_obs = sum(len(group['observations']) for group in species_groups)
            f.write(f"总观察记录数: **{total_obs}** 条\n")
        
        # 生成多地点地图链接
        if species_groups:
            location_stats = {}
            
            # 收集所有观测地点信息
            for group in species_groups:
                for obs in group['observations']:
                    lat = obs.get('lat')
                    lng = obs.get('lng') 
                    loc_name = obs.get('locName', 'Unknown Location')
                    
                    if lat and lng:
                        # 使用坐标作为唯一标识
                        coord_key = f"{lat:.4f},{lng:.4f}"
                        if coord_key not in location_stats:
                            location_stats[coord_key] = {
                                'name': loc_name,
                                'lat': lat,
                                'lng': lng,
                                'count': 0
                            }
                        location_stats[coord_key]['count'] += 1
            
            # 按观测次数排序，选择前9个地点
            top_locations = sorted(location_stats.values(), key=lambda x: x['count'], reverse=True)[:9]
            
            if len(top_locations) > 1:
                f.write(f"\n---\n\n")
                f.write("### 🗺️ 观鸟地点导航\n\n")
                f.write(f"**主要观测地点:** {len(top_locations)} 个热门地点\n\n")
                
                # 生成Google地图多地点链接
                # 使用Google Maps的多个标记功能
                map_url = "https://www.google.com/maps/dir/"
                
                # 添加每个地点的坐标
                coordinates = []
                for i, loc in enumerate(top_locations, 1):
                    coord_str = f"{loc['lat']},{loc['lng']}"
                    coordinates.append(coord_str)
                    f.write(f"{i}. **{loc['name']}** (观测次数: {loc['count']})\n")
                
                # 生成路线规划链接
                map_url += "/".join(coordinates)
                
                f.write(f"\n🎯 **[点击查看所有地点路线规划]({map_url})**\n")
                
                # 生成显示所有地点的搜索链接
                search_coords = "||".join([f"{loc['lat']},{loc['lng']}" for loc in top_locations])
                search_url = f"https://www.google.com/maps/search/?api=1&query={search_coords}"
                f.write(f"🗺️ **[点击在地图上同时显示所有地点](https://www.google.com/maps/search/?api=1&query={top_locations[0]['lat']},{top_locations[0]['lng']})**\n")
                
                # 额外提供一个包含所有地点名称的搜索
                location_names = " OR ".join([f'{loc["name"]}' for loc in top_locations[:5]])  # 限制前5个避免URL过长
                location_search_url = f"https://www.google.com/maps/search/{location_names.replace(' ', '+')}"
                f.write(f"📍 **[按地点名称搜索]({location_search_url})**\n")
        
        f.write("\n*报告由 Tui Bird Intelligence 生成*\n\n")
        f.write("*本报告数据由 eBird (www.ebird.org) 提供，感谢全球观鸟者的贡献。*\n")
    
    return filepath

def main():
    """主程序"""
    print("=" * 60)
    print("🌍 eBird 区域鸟种查询器 V3.0")
    print("=" * 60)
    print("根据区域查询该区域内所有鸟种的观测记录")
    print("🎆 新增：eBird热点精确查询功能")
    print()
    
    try:
        # 获取API Key
        api_key = get_api_key()
        print(f"🔑 使用API Key: {api_key[:4]}...{api_key[-4:]}")
        
        # 加载鸟类数据库
        bird_database = load_bird_database(DB_FILE)
        
        # 选择查询模式
        print("\n📋 查询模式说明:")
        print("✅ 地理区域查询 - 根据GPS坐标+半径范围查询该区域内的所有观测记录")
        print("💡 提示: 您可以直接输入地名（如'北京'、'上海'），程序会自动转换为GPS坐标")
        print("💡 提示: 也可以直接输入GPS坐标（如'39.9042,116.4074'）")
        print("💡 提示: 推荐半径范围: 5-25公里（城市内），25-50公里（郊区/自然保护区）")
        print()
        
        query_mode = "geo"
        final_lat = None
        final_lng = None
        final_placename = None
        radius = 25
        
        # 地理区域查询模式
        print("\n📍 请输入搜索区域:")
        geolocator = Nominatim(user_agent="bird_region_query_v3.0")
        default_city, auto_coords = get_location_from_ip()
        
        if default_city:
            prompt = f"回车搜索 [{default_city}]，或输入新地点/GPS坐标: "
        else:
            prompt = "请输入地点名称或GPS坐标 (纬度,经度): "
        
        while final_lat is None:
            user_input = input(prompt).strip()
            
            if user_input == "" and auto_coords:
                final_lat, final_lng = auto_coords
                final_placename = default_city or get_placename_from_coords(final_lat, final_lng, geolocator)
                break
            
            # 尝试解析GPS坐标
            coords = get_coords_from_string(user_input)
            if coords:
                final_lat, final_lng = coords
                final_placename = get_placename_from_coords(final_lat, final_lng, geolocator) or f"GPS {final_lat:.4f},{final_lng:.4f}"
            else:
                # 尝试通过地名获取坐标
                coords_from_name = get_coords_from_placename(user_input, geolocator)
                if coords_from_name:
                    final_lat, final_lng = coords_from_name
                    final_placename = user_input
                else:
                    print("❌ 无法识别输入的位置，请重试")
                    continue
        
        print(f"✅ 搜索位置: {final_placename} ({final_lat:.4f}, {final_lng:.4f})")
        
        # 设置搜索半径
        try:
            radius_input = input(f"请输入搜索半径(公里, 1-50) [默认: {radius}km]: ").strip()
            if radius_input:
                r = int(radius_input)
                radius = r if 1 <= r <= 50 else 25
        except ValueError:
            print(f"⚠️ 输入无效，使用默认半径 {radius}km")
        
        # 设置时间范围
        print("\n⏰ 请选择查询时间范围:")
        print("  1. 最近 7 天")
        print("  2. 最近 14 天 (推荐)")
        print("  3. 最近 30 天")
        
        days_back = 14
        time_choice = input("请输入选项编号 [默认为 2]: ").strip()
        if time_choice == '1':
            days_back = 7
        elif time_choice == '3':
            days_back = 30
        
        # 设置显示模式
        print("\n📊 请选择显示模式:")
        print("  1. 简要模式 - 每个鸟种仅显示最新5条观察记录")
        print("  2. 完整模式 - 每个鸟种显示所有观察记录 🆕")
        
        show_all_records = False
        display_choice = input("请输入选项编号 [默认为 1]: ").strip()
        if display_choice == '2':
            show_all_records = True
            print("✅ 已选择完整模式：将显示每个鸟种的所有观察记录")
        else:
            print("✅ 已选择简要模式：每个鸟种仅显示最新5条记录")
        
        # 显示查询设置
        print(f"\n✅ 查询设置:")
        print(f"   📍 位置: '{final_placename}' 周围 {radius}km")
        print(f"   ⏰ 时间: 最近 {days_back} 天")
        print(f"   📊 模式: {'完整显示' if show_all_records else '简要显示'}")
        
        # 开始查询
        print(f"\n🚀 开始查询eBird数据...")
        start_time = time.time()
        
        # 获取区域内所有观测记录
        all_observations = fetch_region_observations(final_lat, final_lng, radius, days_back, api_key)
        
        if not all_observations:
            print("❌ 该区域内没有找到任何观测记录")
            return
        
        # 过滤出数据库中的鸟种
        filtered_observations = filter_database_birds(all_observations, bird_database)
        
        if not filtered_observations:
            print("❌ 该区域内没有找到数据库中的目标鸟种")
            return
        
        # 按鸟种分组
        species_groups = group_observations_by_species(filtered_observations)
        
        # 生成报告
        report_file = generate_region_report(species_groups, final_placename, radius, days_back, len(all_observations), show_all_records, "geo")
        
        end_time = time.time()
        elapsed_time = end_time - start_time
        
        total_obs_count = sum(len(group['observations']) for group in species_groups)
        
        print(f"\n🎉 区域鸟种查询完成！")
        print(f"📊 发现 {len(species_groups)} 种目标鸟类，共 {total_obs_count} 条观察记录")
        if show_all_records:
            print(f"📝 完整报告（包含所有观察记录）已保存到: {report_file}")
        else:
            print(f"📝 简要报告（每种鸟显示最新5条）已保存到: {report_file}")
        print(f"⏱️ 查询用时: {elapsed_time:.2f} 秒")
        
    except KeyboardInterrupt:
        print("\n⚠️ 程序被用户中断")
    except Exception as e:
        print(f"\n❌ 程序运行出错: {e}")
        import traceback
        traceback.print_exc()
    
    input("\n按回车键返回主菜单...")

if __name__ == "__main__":
    main()