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

# 导入标准库
import sys
import datetime
import os
import time
from collections import Counter

# 导入第三方库
import requests

# 导入新的基础模块
from config import ConfigManager, DB_FILE, EBIRD_API_BASE_URL
from database import BirdDatabase
from api_client import get_api_key_with_validation, EBirdAPIClient
from utils import (
    safe_input,
    get_location_from_ip,
    get_coords_from_string,
    get_coords_from_placename,
    get_placename_from_coords,
    create_geolocator,
    create_google_maps_link
)

def filter_database_birds(observations, code_to_name_map):
    """过滤出数据库中存在的鸟种观测记录"""
    filtered_obs = []
    for obs in observations:
        species_code = obs.get('speciesCode')
        if species_code in code_to_name_map:
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
    # 使用绝对路径，确保输出到项目根目录
    from config import get_resource_path
    output_base = get_resource_path('output')
    if not os.path.exists(output_base):
        os.makedirs(output_base)

    # 创建日期子目录
    today_str = datetime.datetime.now().strftime('%Y-%m-%d')
    output_dir = os.path.join(output_base, today_str)
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
                        maps_link = create_google_maps_link(lat, lng)
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
                search_url = f"https://www.google.com/maps/search/?api=1&query={top_locations[0]['lat']},{top_locations[0]['lng']}"
                f.write(f"🗺️ **[点击在地图上同时显示所有地点]({search_url})**\n")

                # 额外提供一个包含所有地点名称的搜索
                location_names = " OR ".join([f'{loc["name"]}' for loc in top_locations[:5]])  # 限制前5个避免URL过长
                location_search_url = f"https://www.google.com/maps/search/{location_names.replace(' ', '+')}"
                f.write(f"📍 **[按地点名称搜索]({location_search_url})**\n")

        f.write("\n*报告由 Tui Bird Intelligence 生成*\n\n")
        f.write("*本报告数据由 eBird (www.ebird.org) 提供，感谢全球观鸟者的贡献。*\n")

    return filepath

def main():
    """主程序"""
    from config import VERSION, BUILD_DATE
    print("=" * 60)
    print(f"🌍 eBird 区域鸟种查询器 V{VERSION} ({BUILD_DATE})")
    print("=" * 60)
    print("根据区域查询该区域内所有鸟种的观测记录")
    print("🎆 新增：eBird热点精确查询功能")
    print()

    try:
        # 初始化配置管理器
        config = ConfigManager()

        # 获取API Key
        api_key = get_api_key_with_validation(config)
        if not api_key:
            print("❌ 无法获取有效的API Key，程序退出。")
            return
        print(f"🔑 使用API Key: {api_key[:4]}...{api_key[-4:]}")

        # 创建API客户端
        client = EBirdAPIClient(api_key)

        # 初始化数据库
        database = BirdDatabase(DB_FILE)
        bird_database = database.load_all_birds()
        code_to_name_map = database.get_code_to_name_map()

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
        geolocator = create_geolocator("bird_region_query_v3.0")
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
        radius_input = safe_input(f"请输入搜索半径(公里, 1-50) [默认: {radius}km]: ",
                                  input_type="int", min_val=1, max_val=50, default=radius)
        if radius_input:
            radius = radius_input

        # 设置时间范围
        print("\n⏰ 请选择查询时间范围:")
        print("  1. 最近 7 天")
        print("  2. 最近 14 天 (推荐)")
        print("  3. 最近 30 天")

        days_back = 14
        time_choice = safe_input("请输入选项编号 [默认为 2]: ",
                                input_type="string", default='2')
        if time_choice == '1':
            days_back = 7
        elif time_choice == '3':
            days_back = 30

        # 设置显示模式
        print("\n📊 请选择显示模式:")
        print("  1. 简要模式 - 每个鸟种仅显示最新5条观察记录")
        print("  2. 完整模式 - 每个鸟种显示所有观察记录 🆕")

        show_all_records = False
        display_choice = safe_input("请输入选项编号 [默认为 1]: ",
                                   input_type="string", default='1')
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

        # 获取区域内所有观测记录（使用API客户端）
        all_observations = client.get_recent_observations_by_location(
            lat=final_lat, lng=final_lng,
            radius=radius, days_back=days_back
        )

        if not all_observations:
            print("❌ 该区域内没有找到任何观测记录")
            return

        # 过滤出数据库中的鸟种
        filtered_observations = filter_database_birds(all_observations, code_to_name_map)

        if not filtered_observations:
            print("❌ 该区域内没有找到数据库中的目标鸟种")
            return

        # 按鸟种分组
        species_groups = group_observations_by_species(filtered_observations)

        # 生成报告
        report_file = generate_region_report(
            species_groups, final_placename, radius, days_back,
            len(all_observations), show_all_records, "geo"
        )

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
