# bird_tracker_unified.py
# 欢迎使用 eBird 统一鸟类追踪工具 V4.0
# 集成单一物种和多物种追踪功能

# 导入所需库
import requests
import sys
import datetime
import os
import sqlite3
import time
import re
import json
from collections import Counter
import geocoder
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable

# --- 1. 全局设定与核心数据库 ---

def resource_path(relative_path):
    """ 获取资源的绝对路径，适用于开发环境和 PyInstaller 打包后的环境 """
    try:
        # PyInstaller 创建一个临时资料夹并将路径存在 _MEIPASS 中
        base_path = getattr(sys, '_MEIPASS', None)
        if base_path is None:
            raise AttributeError
    except AttributeError:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# 【核心】指定您的鸟类资料库文件
DB_FILE = resource_path("ebird_reference.sqlite")
# 【设定档】文件名
PROFILES_FILE = resource_path("profiles.json")
# 【配置文件】保存API Key等配置
CONFIG_FILE = "ebird_config.json"

# --- API Key 管理功能 ---

def load_config():
    """加载配置文件"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            print("⚠️ 配置文件损坏，将重新创建。")
    return {}

def save_config(config):
    """保存配置文件"""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        return True
    except IOError:
        print("❌ 保存配置文件失败！")
        return False

def should_revalidate_api_key(config):
    """判断是否需要重新验证API Key（智能缓存策略）"""
    # 如果没有last_validated字段，需要验证
    if 'last_validated' not in config:
        return True
    
    try:
        last_validated = datetime.datetime.fromisoformat(config['last_validated'])
        now = datetime.datetime.now()
        
        # 如果距离上次验证超过24小时，需要重新验证
        validation_interval = datetime.timedelta(hours=24)
        if now - last_validated > validation_interval:
            return True
        
        return False
    except (ValueError, TypeError):
        # 如果时间格式错误，需要重新验证
        return True

def show_api_key_guide():
    """显示API Key申请指南"""
    print("\n📋 eBird API Key 申请指南")
    print("=" * 50)
    print("\n🔗 申请步骤：")
    print("1. 访问 eBird 网站: https://ebird.org")
    print("2. 点击右上角登录，创建账户或登录现有账户")
    print("3. 登录后，直接访问 API 申请页面: https://ebird.org/api/keygen")
    print("4. 或者点击页面底部的 'Developers' 链接，然后选择 'Request an API Key'")
    print("5. 填写申请表单（以下为详细指导）")
    print("6. 提交申请并等待审批（通常即时至几小时）")
    print("7. 审批通过后，您会收到包含API Key的邮件")
    
    print("\n📝 表单填写指导：")
    print("- First Name: 填写您的名字")
    print("- Last Name: 填写您的姓氏")
    print("- Email: 与您eBird账户相同的邮箱")
    print("- Intended Use: 选择 'Personal Use' 或 'Research/Education'")
    print("- Project Title: 例如 '个人观鸟记录查询' 或 'Bird Tracking Tool'")
    print("- Project Description: 例如 '用于查询和分析特定地区的观鸟记录'")
    print("- Estimated monthly requests: 选择 '1-100' 或 '101-1000'")
    
    print("\n💡 申请技巧：")
    print("- 给出具体的项目描述，例如观鸟路线规划、科研分析等")
    print("- 估计请求量不要过高，新用户建议选择较低档位")
    print("- 使用真实信息，不要随意填写")
    print("- 如果被拒绝，可以修改项目描述后再次申请")
    
    print("\n🔑 API Key 格式：")
    print("- 通常是一串字母和数字组合")
    print("- 长度大约10-15个字符")
    print("- 示例格式：abc123def456")
    
    print("\n⚠️  重要提醒：")
    print("- 请勿分享您的API Key")
    print("- API Key有使用频率限制（每小时100-1000次请求）")
    print("- 遵守eBird API使用条款")
    print("- 不要用于商业目的")
    
    print("\n🚫 常见问题：")
    print("- 如果申请被拒：检查项目描述是否清晰，避免使用模糊语言")
    print("- 如果没收到邮件：检查垃圾邮件夹，或重新申请")
    print("- API Key不工作：检查网络连接，或联系eBird支持")
    print("=" * 50)

def validate_api_key(api_key):
    """验证API Key是否有效"""
    if not api_key or len(api_key.strip()) < 8:
        return False, "API Key格式不正确（太短）"
    
    # 测试API Key是否有效
    test_url = "https://api.ebird.org/v2/ref/taxonomy/ebird?fmt=json"
    headers = {'X-eBirdApiToken': api_key.strip()}
    
    try:
        print("🔍 正在验证API Key...")
        response = requests.get(test_url, headers=headers, timeout=10)
        if response.status_code == 200:
            return True, "API Key验证成功！"
        elif response.status_code == 401:
            return False, "API Key无效或已过期"
        elif response.status_code == 403:
            return False, "API Key权限不足"
        else:
            return False, f"API验证失败 (状态码: {response.status_code})"
    except requests.exceptions.RequestException as e:
        return False, f"网络连接失败: {e}"

def setup_api_key():
    """设置API Key"""
    config = load_config()
    
    print("\n🔑 eBird API Key 设置")
    print("=" * 30)
    
    if 'api_key' in config:
        print(f"\n当前API Key: {config['api_key'][:4]}...{config['api_key'][-4:]}")
        choice = input("\n要更换API Key吗？[y/N]: ").lower().strip()
        if choice not in ['y', 'yes']:
            return config['api_key']
    
    while True:
        print("\n请选择操作：")
        print("1. 输入现有的API Key")
        print("2. 查看API Key申请指南")
        print("3. 使用临时演示Key（功能受限）")
        print("0. 退出程序")
        
        choice = input("\n请输入选择 [1]: ").strip() or '1'
        
        if choice == '1':
            api_key = input("\n请输入您的eBird API Key: ").strip()
            if api_key:
                is_valid, message = validate_api_key(api_key)
                print(f"\n{message}")
                if is_valid:
                    config['api_key'] = api_key
                    config['setup_date'] = datetime.datetime.now().isoformat()
                    config['last_validated'] = datetime.datetime.now().isoformat()
                    if save_config(config):
                        print("✅ API Key已保存到配置文件")
                        return api_key
                    else:
                        print("⚠️ 配置保存失败，将使用临时Key")
                        return api_key
                else:
                    print("❌ API Key验证失败，请重试")
                    continue
            else:
                print("❌ API Key不能为空")
                continue
                
        elif choice == '2':
            show_api_key_guide()
            input("\n按回车键继续...")
            continue
            
        elif choice == '3':
            print("\n⚠️ 使用演示Key，功能可能受限")
            demo_key = "demo123key456"  # 示例演示key（实际不可用）
            print("使用演示Key可能有以下限制：")
            print("- 查询频率严格限制")
            print("- 数据可能不是最新")
            print("- 部分功能可能无法使用")
            print("- 强烈建议申请个人API Key")
            confirm = input("\n确认使用演示Key? [y/N]: ").lower().strip()
            if confirm in ['y', 'yes']:
                print("\n⚠️ 注意：演示Key仅供测试，请尽快申请个人API Key")
                return demo_key
            continue
            
        elif choice == '0':
            print("\n👋 感谢使用，再见！")
            sys.exit(0)
            
        else:
            print("❌ 无效选择，请重试")
            continue

def get_api_key():
    """获取API Key（优先从配置文件读取，智能缓存验证）"""
    config = load_config()
    
    if 'api_key' in config:
        # 检查是否需要重新验证（智能缓存机制）
        should_validate = should_revalidate_api_key(config)
        
        if not should_validate:
            # 使用缓存的API Key，无需验证
            print(f"✅ 使用已保存的API Key: {config['api_key'][:4]}...{config['api_key'][-4:]}")
            return config['api_key']
        else:
            # 需要重新验证
            print("🔍 检查API Key有效性...")
            is_valid, message = validate_api_key(config['api_key'])
            if is_valid:
                # 更新最后验证时间
                config['last_validated'] = datetime.datetime.now().isoformat()
                save_config(config)
                print(f"✅ API Key验证通过: {config['api_key'][:4]}...{config['api_key'][-4:]}")
                return config['api_key']
            else:
                print(f"⚠️ 已保存的API Key无效: {message}")
    
    # 如果没有有效的API Key，则进行设置
    return setup_api_key()

def load_bird_database(db_path):
    print(f"初始化: 正在从您的资料库 '{db_path}' 加载鸟种名录...")
    bird_database = []
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        query = "SELECT ebird_code, chinese_simplified, english_name FROM BirdCountInfo WHERE ebird_code IS NOT NULL AND ebird_code != ''"
        cursor.execute(query)
        all_birds_data = cursor.fetchall()
        conn.close()
        for bird in all_birds_data:
            bird_database.append({
                'code': bird['ebird_code'],
                'cn_name': bird['chinese_simplified'],
                'en_name': bird['english_name']
            })
        if not bird_database:
            print(f"❌ 错误: 从资料库 '{db_path}' 中没有载入任何有效的鸟种数据。")
            sys.exit(1)
        print(f"✅ 成功加载 {len(bird_database)} 条鸟种记录，搜寻功能已就绪。")
        return bird_database
    except sqlite3.Error as e:
        print(f"❌ 严重错误: 连接或读取资料库 '{db_path}' 失败: {e}")
        sys.exit(1)

def find_species_by_name(query, database):
    matches = []
    query = query.lower().strip()
    if not query:
        return matches
    for bird in database:
        if query in bird['en_name'].lower() or query in bird['cn_name'].lower():
            matches.append(bird)
    return matches

def select_target_species_unified(database):
    """统一的物种选择函数：支持单一物种或多物种选择"""
    print("\n请选择追踪模式:")
    print("  1. 🎯 单一物种深度追踪")
    print("  2. 📊 多物种情报分析")
    mode_choice = input("请输入模式编号 [默认为 1]: ").strip()
    if mode_choice == "": mode_choice = '1'
    is_multi_species = (mode_choice == '2')
    
    if is_multi_species:
        # 多物种模式
        target_codes = []
        target_names = []
        while True:
            query_str = input("\n请输入您想查询的鸟种名称 (可输入多个，用英文逗号 ',' 分隔): ")
            queries = [q.strip() for q in query_str.split(',') if q.strip()]
            selected_species_for_queries = {}
            all_valid = True
            for query in queries:
                matches = find_species_by_name(query, database)
                if not matches:
                    print(f"❌ 未找到与 '{query}' 匹配的鸟种，请重新输入所有目标。")
                    all_valid = False
                    break
                if len(matches) == 1:
                    selected_species_for_queries[query] = matches[0]
                else:
                    print(f"\n对于查询 '{query}'，我们找到了多个可能的鸟种，请选择一个:")
                    for i, bird in enumerate(matches, 1):
                        print(f"  {i}. {bird['cn_name']} ({bird['en_name']})")
                    try:
                        choice = int(input("请输入编号进行选择: "))
                        if 1 <= choice <= len(matches):
                            selected_species_for_queries[query] = matches[choice - 1]
                        else:
                            print("⚠️ 无效的编号。")
                            all_valid = False
                            break
                    except ValueError:
                        print("⚠️ 请输入数字编号。")
                        all_valid = False
                        break
            if not all_valid:
                continue
            print("\n您已选择以下目标:")
            for query, bird in selected_species_for_queries.items():
                print(f"- {bird['cn_name']} ({bird['en_name']})")
                if bird['code'] not in target_codes:
                    target_codes.append(bird['code'])
                    target_names.append(f"{bird['cn_name']} ({bird['en_name']})")
            confirm = input("确认以上目标? [Y/n]: ").lower()
            if confirm in ['', 'y', 'yes']:
                return target_codes, target_names, is_multi_species
            else:
                target_codes, target_names = [], []
    else:
        # 单一物种模式
        while True:
            query = input("\n请输入您想查询的鸟种名称 (中/英文模糊查询): ")
            matches = find_species_by_name(query, database)
            if not matches:
                print("❌ 未找到匹配的鸟种，请尝试其他关键词。")
                continue
            if len(matches) == 1:
                bird = matches[0]
                confirm = input(f"您要查询的是否为: {bird['cn_name']} ({bird['en_name']})? [Y/n]: ").lower()
                if confirm in ['', 'y', 'yes']:
                    species_code = bird['code']
                    species_name = f"{bird['cn_name']} ({bird['en_name']})"
                    return [species_code], [species_name], is_multi_species
                else:
                    continue
            print("\n我们找到了多个可能的鸟种，请选择一个:")
            for i, bird in enumerate(matches, 1):
                print(f"  {i}. {bird['cn_name']} ({bird['en_name']})")
            try:
                choice = int(input("请输入编号进行选择: "))
                if 1 <= choice <= len(matches):
                    bird = matches[choice - 1]
                    species_code = bird['code']
                    species_name = f"{bird['cn_name']} ({bird['en_name']})"
                    return [species_code], [species_name], is_multi_species
                else:
                    print("⚠️ 无效的编号，请重新输入。")
            except ValueError:
                print("⚠️ 请输入数字编号。")

# --- 配置文件管理 ---
def load_profiles(filepath):
    if not os.path.exists(filepath):
        return {}
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        print(f"⚠️ 无法读取或解析设定档 {filepath}。")
        return {}

def save_profile(filepath, profiles, profile_name, profile_data):
    profiles[profile_name] = profile_data
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(profiles, f, indent=4, ensure_ascii=False)
        print(f"✅ 成功将 '{profile_name}' 保存到设定档。")
    except IOError:
        print(f"❌ 保存设定档失败！")

def select_profile(profiles):
    if not profiles:
        print("没有可用的设定档。")
        return None
    print("\n请选择一个已保存的搜索设定:")
    profile_list = list(profiles.items())
    for i, (name, data) in enumerate(profile_list, 1):
        print(f"  {i}. {name} (地点: {data['placename']}, 半径: {data['radius']}km, 范围: {data['days_back']}天)")
    try:
        choice = int(input("请输入编号进行选择: "))
        if 1 <= choice <= len(profile_list):
            return profile_list[choice - 1][1]
        else:
            print("⚠️ 无效的编号。")
    except ValueError:
        print("⚠️ 请输入数字编号。")
    return None

# 地理位置处理函数 (简化版本)
def get_location_from_ip():
    print("正在尝试通过IP地址自动定位您的大致位置...")
    try:
        g = geocoder.ip('me')
        if g.ok and g.city:
            print(f"✅ 定位成功！检测到城市：{g.city}")
            return g.city, g.latlng
    except Exception:
        pass
    print("⚠️ 无法自动确定城市，请手动输入。")
    return None, None

def get_coords_from_string(input_str):
    match = re.search(r'([-]?\d+\.\d+)[,\s]+([-]?\d+\.\d+)', input_str)
    if match:
        try:
            lat, lng = float(match.group(1)), float(match.group(2))
            if -90 <= lat <= 90 and -180 <= lng <= 180: return lat, lng
        except (ValueError, IndexError):
            pass
    return None

def get_coords_from_placename(placename, geolocator):
    print(f"正在查询 '{placename}' 的坐标...")
    try:
        location = geolocator.geocode(placename, timeout=10)
        if location:
            print(f"✅ 查询成功: {location.address}")
            print(f"   经纬度: ({location.latitude:.4f}, {location.longitude:.4f})")
            return location.latitude, location.longitude
    except (GeocoderTimedOut, GeocoderUnavailable) as e:
        print(f"❌ 地理编码服务出错: {e}")
    print(f"❌ 未能找到 '{placename}' 的坐标。")
    return None, None

def get_placename_from_coords(lat, lng, geolocator):
    try:
        location = geolocator.reverse(f"{lat}, {lng}", timeout=10)
        if location: return location.address
    except (GeocoderTimedOut, GeocoderUnavailable):
        pass
    return "未知地点"

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
                detail_url = f"https://api.ebird.org/v2/product/checklist/view/{sub_id}"
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
    if not os.path.exists('output'):
        os.makedirs('output')
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    today_folder = os.path.join('output', today_str)
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
                    gmaps_link = f"https://maps.google.com/?q={lat},{lng}"
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
                    f.write(f"  - **{obs['obsDt']}**: 观测到 {species_display}{count_val} 只{num_species_str} {tags_string} - [查看清单](https://ebird.org/checklist/{obs['subId']})\n")
                    species_comment = obs.get('obsComments')
                    if species_comment: f.write(f"    > *{species_comment.strip()}*\n")
                    companion_list = obs.get('companionSpecies')
                    if companion_list: f.write(f"    > **伴生鸟种:** {'、'.join(companion_list)}\n")
                f.write("\n")
        f.write("---\n\n*报告由 BirdTracker Unified V4.0 生成*\n")
        f.write("*数据由 eBird (www.ebird.org) 提供，感谢全球观鸟者的贡献。*\n")
    return md_filename

def main():
    """主程序入口"""
    start_time = time.time()
    try:
        print("--- 欢迎使用 eBird 统一鸟类追踪工具 V4.0 ---")
        print("🎯 支持单一物种深度追踪和多物种情报分析")
        
        # 首先获取API Key（智能缓存，避免不必要的验证）
        print("\n🔑 初始化API Key...")
        EBIRD_API_KEY = get_api_key()
        
        BIRD_DATABASE = load_bird_database(DB_FILE)
        CODE_TO_NAME_MAP = {bird['code']: bird['cn_name'] for bird in BIRD_DATABASE}
        PROFILES = load_profiles(PROFILES_FILE)
        
        # 统一的物种选择
        target_species_codes, target_species_names, is_multi_species = select_target_species_unified(BIRD_DATABASE)
        if is_multi_species:
            print(f"\n✅ 已锁定目标: {', '.join(target_species_names)}")
        else:
            print(f"\n✅ 已锁定目标: {target_species_names[0]} (Code: {target_species_codes[0]})")
        
        print(f"\n🔑 使用API Key: {EBIRD_API_KEY[:4]}...{EBIRD_API_KEY[-4:]}")
        
        days_back, search_area_name, api_url_template, search_params_to_save = 14, "", "", None
        
        print("\n请选择搜索模式:")
        if PROFILES and is_multi_species: print("  p. 使用已保存的设定档")
        print("  1. 澳大利亚全境 (AU)")
        print("  2. 按州/领地代码")
        print("  3. 按GPS位置/地名 (推荐)")
        
        mode_choice = input("请输入模式编号 [默认为 3]: ").lower()
        if mode_choice == "": mode_choice = '3'
        
        # 处理已保存的配置文件
        if mode_choice == 'p' and is_multi_species:
            profile_data = select_profile(PROFILES)
            if profile_data:
                days_back = profile_data['days_back']
                search_area_name = f"围绕 '{profile_data['placename']}' 的 {profile_data['radius']}km 范围 (来自设定档)"
                api_url_template = f"https://api.ebird.org/v2/data/obs/geo/recent/{{speciesCode}}?lat={profile_data['lat']}&lng={profile_data['lng']}&dist={profile_data['radius']}"
        
        if not api_url_template:
            # 时间范围选择
            print("\n请选择查询的时间范围:")
            print("  1. 最近 7 天")
            print("  2. 最近 14 天 (eBird默认)")
            print("  3. 最近 30 天 (最长)")
            print("  4. 自定义天数 (1-30)")
            time_choice = input("请输入选项编号 [默认为 2]: ")
            if time_choice == '1': days_back = 7
            elif time_choice == '3': days_back = 30
            elif time_choice == '4':
                try:
                    custom_days = int(input("请输入天数 (1-30): "))
                    if 1 <= custom_days <= 30: days_back = custom_days
                    else: print("⚠️ 天数无效，将使用默认14天。")
                except ValueError: print("⚠️ 输入无效，将使用默认14天。")
            print(f"✅ 时间范围设定为: 最近 {days_back} 天")
            
            if mode_choice == '1':
                search_area_name = "澳大利亚全境"
                api_url_template = "https://api.ebird.org/v2/data/obs/AU/recent/{speciesCode}"
                print(f"\n--- 模式一: 区域搜索 [{search_area_name}] ---")
            elif mode_choice == '2':
                au_states = ["AU-NT", "AU-NSW", "AU-QLD", "AU-WA", "AU-SA", "AU-VIC", "AU-ACT", "AU-TAS"]
                print("\n请选择州/领地:")
                for i, s in enumerate(au_states, 1): print(f"  {i}. {s}")
                REGION_CODE = "AU-NT"
                try:
                    choice_str = input(f"请输入州/领地编号 [默认为 1. {REGION_CODE}]: ")
                    if choice_str: REGION_CODE = au_states[int(choice_str) - 1]
                except (ValueError, IndexError): print(f"⚠️ 输入无效，将使用默认值 {REGION_CODE}。")
                search_area_name = REGION_CODE
                api_url_template = f"https://api.ebird.org/v2/data/obs/{REGION_CODE}/recent/{{speciesCode}}"
                print(f"\n--- 模式二: 区域搜索 [{search_area_name}] ---")
            elif mode_choice == '3':
                print("\n--- 模式三: GPS/地名搜索 ---")
                geolocator = Nominatim(user_agent="bird_tracker_unified_v4.0")
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
                try:
                    radius_str = input(f"请输入搜索半径(公里, 1-50) [默认: {radius}km]: ")
                    if radius_str:
                        r = int(radius_str)
                        radius = r if 1 <= r <= 50 else 25
                except ValueError: print(f"⚠️ 输入无效，使用默认半径 {radius}km。")
                
                search_area_name = f"围绕 '{final_placename}' 的 {radius}km 范围"
                api_url_template = f"https://api.ebird.org/v2/data/obs/geo/recent/{{speciesCode}}?lat={final_lat}&lng={final_lng}&dist={radius}"
                search_params_to_save = {'lat': final_lat, 'lng': final_lng, 'placename': final_placename, 'radius': radius, 'days_back': days_back}
            else:
                print("无效的模式选择，程序退出。")
                return
        
        headers = {'X-eBirdApiToken': EBIRD_API_KEY}
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
                if profile_name: save_profile(PROFILES_FILE, PROFILES, profile_name, search_params_to_save)
    
    finally:
        end_time = time.time()
        elapsed_time = end_time - start_time
        print(f"\n--- 累计用时: {elapsed_time:.2f} 秒 ---")

# --- 主程序 ---
if __name__ == "__main__":
    main()