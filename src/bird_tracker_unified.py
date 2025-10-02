# bird_tracker_unified.py
# 欢迎使用 eBird 统一鸟类追踪工具 V4.0
# 集成单一物种和多物种追踪功能

# 导入标准库
import sys
import datetime
import os
import time
import json
from collections import Counter

# 导入第三方库
import requests
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable

# 导入新的基础模块
from config import (
    get_resource_path, ConfigManager,
    DB_FILE, PROFILES_FILE,
    EBIRD_API_BASE_URL, DEFAULT_DAYS_BACK
)
from database import BirdDatabase
from api_client import EBirdAPIClient, get_api_key_with_validation
from utils import (
    safe_input,
    get_location_from_ip,
    get_coords_from_string,
    get_coords_from_placename,
    get_placename_from_coords,
    create_geolocator,
    create_google_maps_link,
    create_ebird_checklist_link,
    format_count
)

# --- 配置文件管理 ---
def load_profiles(filepath):
    """加载搜索档案"""
    if not os.path.exists(filepath):
        return {}
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        print(f"⚠️ 无法读取或解析设定档 {filepath}。")
        return {}

def save_profile(filepath, profiles, profile_name, profile_data):
    """保存搜索档案"""
    profiles[profile_name] = profile_data
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(profiles, f, indent=4, ensure_ascii=False)
        print(f"✅ 成功将 '{profile_name}' 保存到设定档。")
    except IOError:
        print(f"❌ 保存设定档失败！")

def select_profile(profiles):
    """选择已保存的档案"""
    if not profiles:
        print("没有可用的设定档。")
        return None
    print("\n请选择一个已保存的搜索设定:")
    profile_list = list(profiles.items())
    for i, (name, data) in enumerate(profile_list, 1):
        print(f"  {i}. {name} (地点: {data['placename']}, 半径: {data['radius']}km, 范围: {data['days_back']}天)")

    choice = safe_input("请输入编号进行选择: ", input_type="int",
                       min_val=1, max_val=len(profile_list), allow_empty=False)
    if choice is None:
        return None
    return profile_list[choice - 1][1]

# --- 物种选择功能 ---
def select_target_species_unified(database):
    """统一的物种选择函数：支持单一物种或多物种选择"""
    print("\n请选择追踪模式:")
    print("  1. 🎯 单一物种深度追踪")
    print("  2. 📊 多物种情报分析")

    mode_choice = safe_input("请输入模式编号 [默认为 1]: ",
                            input_type="string", default='1')
    is_multi_species = (mode_choice == '2')

    if is_multi_species:
        # 多物种模式
        return select_multiple_species(database)
    else:
        # 单物种模式
        return select_single_species(database)

def select_single_species(database):
    """选择单个物种"""
    while True:
        selected = database.select_species_interactive()
        if selected is None:
            return None, None, False

        species_code = selected['code']
        species_name = f"{selected.get('cn_name', '')} ({selected.get('en_name', 'Unknown')})"
        return [species_code], [species_name], False

def select_multiple_species(database):
    """选择多个物种"""
    selected_species = database.select_multiple_species_interactive()
    if not selected_species:
        return None, None, True

    target_codes = []
    target_names = []
    for bird in selected_species:
        target_codes.append(bird['code'])
        target_names.append(f"{bird.get('cn_name', '')} ({bird.get('en_name', 'Unknown')})")

    return target_codes, target_names, True

# --- API调用和数据处理 ---
def fetch_initial_observations(api_url_template, headers, params, target_species_codes):
    """统一的观测数据获取函数 - 使用正确的方法获取完整信息"""
    print("\n正在从eBird API获取初始观测列表...")
    all_observations = []

    # 重要：确保使用 detail='full' 参数获取完整信息
    full_detail_params = params.copy()
    full_detail_params['detail'] = 'full'

    for species_code in target_species_codes:
        if '{speciesCode}' in api_url_template:
            api_url = api_url_template.replace('{speciesCode}', species_code)
        else:
            api_url = api_url_template
        print(f"  正在查询物种: {species_code}")
        try:
            response = requests.get(api_url, headers=headers, params=full_detail_params, timeout=20)
            if response.status_code == 200:
                species_observations = response.json()
                all_observations.extend(species_observations)
                print(f"    ✅ 获取到 {len(species_observations)} 条记录")
            else:
                print(f"    ⚠️ API请求失败，状态码: {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"    ❌ 网络请求出错: {e}")

    # 去重处理
    unique_observations = []
    seen_sub_ids = set()
    for obs in all_observations:
        sub_id = obs.get('subId')
        if sub_id and sub_id not in seen_sub_ids:
            unique_observations.append(obs)
            seen_sub_ids.add(sub_id)
    print(f"✅ 总计获取 {len(all_observations)} 条记录，去重后 {len(unique_observations)} 条独特记录")
    return unique_observations

def process_direct_observations(observations, code_to_name_map, headers, target_species_codes):
    """直接处理观测数据，并获取伴生鸟种信息"""
    print("\n🔄 处理观测数据并获取伴生鸟种...")

    processed_observations = []
    target_codes_set = set(target_species_codes)
    total = len(observations)

    for i, obs in enumerate(observations, 1):
        sub_id = obs.get('subId')

        # 简化进度显示
        if i == 1 or i % 10 == 0 or i == total:
            progress_text = f"  进度: {i}/{total}"
            print(progress_text)

        # 获取伴生鸟种信息（只对前5个清单获取，以提高速度）
        companion_species = []
        num_species_on_checklist = 1  # 默认值

        if sub_id and i <= 5:  # 只对前5个清单获取伴生鸟种
            try:
                detail_url = f"{EBIRD_API_BASE_URL}product/checklist/view/{sub_id}"
                response = requests.get(detail_url, headers=headers, timeout=8)
                if response.status_code == 200:
                    checklist_detail = response.json()
                    all_species_in_checklist = checklist_detail.get('obs', [])
                    num_species_on_checklist = len(all_species_in_checklist)

                    # 获取伴生鸟种（排除目标物种）
                    companion_species = [
                        code_to_name_map.get(species_obs.get('speciesCode'), species_obs.get('speciesCode', 'Unknown'))
                        for species_obs in all_species_in_checklist
                        if species_obs.get('speciesCode') not in target_codes_set and species_obs.get('speciesCode')
                    ]
                    companion_species = companion_species[:10]  # 限制前10个
            except requests.exceptions.RequestException:
                pass  # 如果失败，使用默认值

            # 添加小延迟避免过于频繁的请求
            time.sleep(0.2)

        # 直接使用初始 API 数据中的完整信息
        processed_obs = {
            'speciesCode': obs.get('speciesCode'),
            'locId': obs.get('locId'),
            'locName': obs.get('locName') if obs.get('locName') is not None else '未知地点',
            'lat': obs.get('lat'),
            'lng': obs.get('lng'),
            'obsDt': obs.get('obsDt'),
            'howMany': obs.get('howMany') if obs.get('howMany') is not None else '未知数量',
            'obsComments': obs.get('speciesComments'),
            'hasRichMedia': obs.get('hasRichMedia', False),
            'obsReviewed': obs.get('obsReviewed', False),
            'obsValid': obs.get('obsValid', True),
            'subId': obs.get('subId'),
            'numSpeciesOnChecklist': num_species_on_checklist,
            'companionSpecies': companion_species
        }
        processed_observations.append(processed_obs)

    print(f"✅ 处理完成，共 {len(processed_observations)} 条记录")
    return processed_observations

def process_and_group_data(detailed_obs_list):
    """按地点分组观测数据"""
    if not detailed_obs_list:
        return []
    locations_dict = {}
    for obs in detailed_obs_list:
        loc_id = obs['locId']
        if loc_id not in locations_dict:
            locations_dict[loc_id] = {
                'locId': loc_id,
                'locName': obs['locName'],
                'lat': obs['lat'],
                'lng': obs['lng'],
                'observations': []
            }
        locations_dict[loc_id]['observations'].append(obs)
    sorted_locations = sorted(locations_dict.values(), key=lambda x: len(x['observations']), reverse=True)
    return sorted_locations

def generate_markdown_report(data, species_names, search_area, days_back, code_to_name_map, is_multi_species=None):
    """生成Markdown格式的报告"""
    # 使用绝对路径，确保输出到项目根目录
    from config import get_resource_path
    output_base = get_resource_path('output')

    if not os.path.exists(output_base):
        os.makedirs(output_base)
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    today_folder = os.path.join(output_base, today_str)
    if not os.path.exists(today_folder):
        os.makedirs(today_folder)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    if is_multi_species is None:
        is_multi_species = len(species_names) > 1
    if is_multi_species:
        filename_prefix = "Birding_Briefing"
    else:
        species_clean = species_names[0].split('(')[0].strip()
        filename_prefix = f"Tracker_{species_clean}"
    md_filename = os.path.join(today_folder, f"{filename_prefix}_{timestamp}.md")

    has_media_icon = any(
        obs.get('hasRichMedia', False)
        for hotspot in data
        for obs in hotspot['observations']
    )
    has_verified_icon = any(
        obs.get('obsReviewed', False) and obs.get('obsValid', True)
        for hotspot in data
        for obs in hotspot['observations']
    )

    with open(md_filename, 'w', encoding='utf-8') as f:
        if is_multi_species:
            f.write("# 🌍 eBird 多物种情报分析报告\n\n")
        else:
            f.write(f"# 🎯 eBird 物种追踪报告\n\n")
        f.write(f"**生成时间:** {datetime.datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}\n")
        f.write(f"**查询物种:** `{', '.join(species_names)}`\n")
        f.write(f"**搜索区域:** `{search_area}`\n")
        f.write(f"**时间范围:** 最近 `{days_back}` 天\n\n")
        total_obs_count = sum(len(hotspot['observations']) for hotspot in data)
        f.write(f"**分析摘要:** 在指定范围内，共在 **{len(data)}** 个公开热点发现了 **{total_obs_count}** 筆目标物种观测记录。\n\n")

        legend_parts = []
        if has_media_icon: legend_parts.append('📸 = 有照片/录音')
        if has_verified_icon: legend_parts.append(', ✔️ = 记录已由eBird管理员验证')
        if legend_parts: f.write(f"**图例:** {''.join(legend_parts)}\n\n")
        f.write("---\n\n")

        if not data:
            f.write("### 结果\n\n*在此时间范围和区域内，未发现该物种在任何公开热点的观测记录。*\n\n")
        else:
            f.write("## 🔥 热门观测地点 (按观测次数排序)\n\n")
            for i, hotspot in enumerate(data, 1):
                obs_count = len(hotspot['observations'])
                # 处理坐标空值，生成地图链接
                lat = hotspot.get('lat')
                lng = hotspot.get('lng')
                if lat is not None and lng is not None:
                    gmaps_link = create_google_maps_link(lat, lng)
                else:
                    gmaps_link = "#"  # 无坐标时不提供地图链接

                hotspot_id = hotspot['locId']
                location_name = hotspot.get('locName')
                if location_name is None:
                    location_name = '未知地点'
                title_text = f"No.{i} {location_name} ({hotspot_id}) - {obs_count} 次观测"

                if lat is not None and lng is not None:
                    f.write(f"### [{title_text}]({gmaps_link})\n\n")
                else:
                    f.write(f"### {title_text}\n\n")
                sorted_obs = sorted(hotspot['observations'], key=lambda x: x['obsDt'], reverse=True)
                for obs in sorted_obs:
                    tags = []
                    if obs.get('hasRichMedia', False): tags.append('📸')
                    if obs.get('obsReviewed', False) and obs.get('obsValid', True): tags.append('✔️')
                    tags_string = ' '.join(tags)
                    num_species_str = f" (清单共 {obs.get('numSpeciesOnChecklist', 'N/A')} 种)"
                    count_val = obs.get('howMany', obs.get('obsCount', 'N/A'))
                    if count_val is None:
                        count_val = '未知数量'
                    if is_multi_species:
                        obs_species_code = obs.get('speciesCode')
                        obs_species_name = code_to_name_map.get(obs_species_code, obs_species_code)
                        species_display = f"**{obs_species_name}** "
                    else:
                        species_display = ""
                    checklist_link = create_ebird_checklist_link(obs['subId'])
                    f.write(f"  - **{obs['obsDt']}**: 观测到 {species_display}{count_val} 只{num_species_str} {tags_string} - [查看清单]({checklist_link})\n")
                    species_comment = obs.get('obsComments')
                    if species_comment: f.write(f"    > *{species_comment.strip()}*\n")
                    companion_list = obs.get('companionSpecies')
                    if companion_list: f.write(f"    > **伴生鸟种:** {'、'.join(companion_list)}\n")
                f.write("\n")
        from config import VERSION
        f.write(f"---\n\n*报告由 BirdTracker Unified V{VERSION} 生成*\n")
        f.write("*数据由 eBird (www.ebird.org) 提供，感谢全球观鸟者的贡献。*\n")
    return md_filename

def main():
    """主程序入口"""
    from config import VERSION, BUILD_DATE
    start_time = time.time()
    try:
        print(f"--- 欢迎使用 eBird 统一鸟类追踪工具 V{VERSION} ({BUILD_DATE}) ---")
        print("🎯 支持单一物种深度追踪和多物种情报分析")

        # 初始化配置管理器
        config = ConfigManager()

        # 获取API Key（智能缓存，避免不必要的验证）
        print("\n🔑 初始化API Key...")
        api_key = get_api_key_with_validation(config)
        if not api_key:
            print("❌ 无法获取有效的API Key，程序退出。")
            return

        # 创建API客户端
        client = EBirdAPIClient(api_key)

        # 初始化数据库
        database = BirdDatabase(DB_FILE)

        # 加载鸟类数据
        bird_database = database.load_all_birds()
        CODE_TO_NAME_MAP = database.get_code_to_name_map()

        # 加载档案
        PROFILES = load_profiles(PROFILES_FILE)

        # 统一的物种选择
        target_species_codes, target_species_names, is_multi_species = select_target_species_unified(database)
        if target_species_codes is None:
            print("❌ 未选择物种，程序退出。")
            return

        if is_multi_species:
            print(f"\n✅ 已锁定目标: {', '.join(target_species_names)}")
        else:
            print(f"\n✅ 已锁定目标: {target_species_names[0]} (Code: {target_species_codes[0]})")

        print(f"\n🔑 使用API Key: {api_key[:4]}...{api_key[-4:]}")

        days_back, search_area_name, api_url_template, search_params_to_save = DEFAULT_DAYS_BACK, "", "", None

        print("\n请选择搜索模式:")
        if PROFILES and is_multi_species: print("  p. 使用已保存的设定档")
        print("  1. 澳大利亚全境 (AU)")
        print("  2. 按州/领地代码")
        print("  3. 按GPS位置/地名 (推荐)")

        mode_choice = safe_input("请输入模式编号 [默认为 3]: ",
                               input_type="string", default='3')

        # 处理已保存的配置文件
        if mode_choice == 'p' and is_multi_species:
            profile_data = select_profile(PROFILES)
            if profile_data:
                days_back = profile_data['days_back']
                search_area_name = f"围绕 '{profile_data['placename']}' 的 {profile_data['radius']}km 范围 (来自设定档)"
                api_url_template = f"{EBIRD_API_BASE_URL}data/obs/geo/recent/{{speciesCode}}?lat={profile_data['lat']}&lng={profile_data['lng']}&dist={profile_data['radius']}"

        if not api_url_template:
            # 时间范围选择
            print("\n请选择查询的时间范围:")
            print("  1. 最近 7 天")
            print("  2. 最近 14 天 (eBird默认)")
            print("  3. 最近 30 天 (最长)")
            print("  4. 自定义天数 (1-30)")
            time_choice = safe_input("请输入选项编号 [默认为 2]: ",
                                    input_type="string", default='2')
            if time_choice == '1':
                days_back = 7
            elif time_choice == '3':
                days_back = 30
            elif time_choice == '4':
                custom_days = safe_input("请输入天数 (1-30): ",
                                        input_type="int", min_val=1, max_val=30)
                if custom_days:
                    days_back = custom_days
            print(f"✅ 时间范围设定为: 最近 {days_back} 天")

            if mode_choice == '1':
                search_area_name = "澳大利亚全境"
                api_url_template = f"{EBIRD_API_BASE_URL}data/obs/AU/recent/{{speciesCode}}"
                print(f"\n--- 模式一: 区域搜索 [{search_area_name}] ---")
            elif mode_choice == '2':
                from config import AUSTRALIA_STATES
                print("\n请选择州/领地:")
                for i, s in enumerate(AUSTRALIA_STATES, 1):
                    print(f"  {i}. {s}")
                REGION_CODE = "AU-NT"
                choice_num = safe_input(f"请输入州/领地编号 [默认为 1. {REGION_CODE}]: ",
                                       input_type="int", min_val=1, max_val=len(AUSTRALIA_STATES),
                                       default=1)
                if choice_num:
                    REGION_CODE = AUSTRALIA_STATES[choice_num - 1]
                search_area_name = REGION_CODE
                api_url_template = f"{EBIRD_API_BASE_URL}data/obs/{REGION_CODE}/recent/{{speciesCode}}"
                print(f"\n--- 模式二: 区域搜索 [{search_area_name}] ---")
            elif mode_choice == '3':
                print("\n--- 模式三: GPS/地名搜索 ---")
                geolocator = create_geolocator("bird_tracker_unified_v4.0")
                default_city, auto_coords = get_location_from_ip()
                prompt = f"回车搜索 [{default_city}]，或输入新地点/GPS: " if default_city else "请输入地点/GPS: "
                final_lat, final_lng, final_placename = None, None, None
                while final_lat is None:
                    user_input = input(prompt)
                    if user_input == "" and auto_coords:
                        final_lat, final_lng = auto_coords
                        final_placename = default_city or get_placename_from_coords(final_lat, final_lng, geolocator)
                        break
                    coords = get_coords_from_string(user_input)
                    if coords:
                        final_lat, final_lng = coords
                        final_placename = get_placename_from_coords(final_lat, final_lng, geolocator)
                    else:
                        coords_from_name = get_coords_from_placename(user_input, geolocator)
                        if coords_from_name:
                            final_lat, final_lng = coords_from_name
                            final_placename = user_input
                        else:
                            print("❌ 无法识别输入，请重试。")

                radius = 25
                radius_input = safe_input(f"请输入搜索半径(公里, 1-50) [默认: {radius}km]: ",
                                         input_type="int", min_val=1, max_val=50, default=radius)
                if radius_input:
                    radius = radius_input

                search_area_name = f"围绕 '{final_placename}' 的 {radius}km 范围"
                api_url_template = f"{EBIRD_API_BASE_URL}data/obs/geo/recent/{{speciesCode}}?lat={final_lat}&lng={final_lng}&dist={radius}"
                search_params_to_save = {'lat': final_lat, 'lng': final_lng, 'placename': final_placename, 'radius': radius, 'days_back': days_back}
            else:
                print("无效的模式选择，程序退出。")
                return

        headers = {'X-eBirdApiToken': api_key}
        params = {'back': days_back, 'detail': 'full'}

        print(f"\n🚀 开始查询eBird数据...")
        initial_observations = fetch_initial_observations(api_url_template, headers, params, target_species_codes)

        if initial_observations:
            # 🔄 关键修改：直接处理初始观测数据，但恢复伴生鸟种功能
            processed_obs_list = process_direct_observations(initial_observations, CODE_TO_NAME_MAP, headers, target_species_codes)
            sorted_data = process_and_group_data(processed_obs_list)
            report_file = generate_markdown_report(sorted_data, target_species_names, search_area_name, days_back, CODE_TO_NAME_MAP, is_multi_species)
            print(f"🎉 追踪报告生成完毕！\n   文件已保存到: {report_file}")
        else:
            print("\n⏹️ 在指定范围内未发现目标鸟种的任何记录。")

        # 保存配置文件（仅多物种模式）
        if search_params_to_save and is_multi_species:
            save_prompt = input("\n要将本次GPS搜索参数保存为设定档吗? (y/N): ").lower()
            if save_prompt == 'y':
                profile_name = input("请输入设定档名称 (例如: 我的达尔文周边): ")
                if profile_name:
                    save_profile(PROFILES_FILE, PROFILES, profile_name, search_params_to_save)

    finally:
        end_time = time.time()
        elapsed_time = end_time - start_time
        print(f"\n--- 累计用时: {elapsed_time:.2f} 秒 ---")

# --- 主程序 ---
if __name__ == "__main__":
    main()
