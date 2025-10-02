#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TuiBird Tracker Web Application
基于 Flask 的 Web 界面
"""

from flask import Flask, render_template, request, jsonify, send_file
import os
import sys
from datetime import datetime
import json
import markdown
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

# 导入现有模块
from config import VERSION, BUILD_DATE, ConfigManager, DB_FILE, AUSTRALIA_STATES
from database import BirdDatabase
from api_client import EBirdAPIClient, get_api_key_with_validation

app = Flask(__name__)
app.config['SECRET_KEY'] = 'tuibird-tracker-secret-key'
app.config['JSON_AS_ASCII'] = False  # 支持中文 JSON

# 全局配置
config_manager = ConfigManager()
bird_db = None
api_client = None


def init_database():
    """初始化数据库"""
    global bird_db
    if bird_db is None:
        bird_db = BirdDatabase(DB_FILE)
        bird_db.load_all_birds()
    return bird_db


def init_api_client():
    """初始化 API 客户端"""
    global api_client
    if api_client is None:
        api_key = get_api_key_with_validation(config_manager)
        if api_key:
            api_client = EBirdAPIClient(api_key)
    return api_client


def _reset_api_client():
    """重置 API 客户端"""
    global api_client
    api_client = None


@app.route('/')
def index():
    """主页"""
    return render_template('index.html',
                         version=VERSION,
                         build_date=BUILD_DATE)


@app.route('/tracker')
def tracker():
    """单物种/多物种追踪页面"""
    db = init_database()
    all_birds = db.load_all_birds()

    return render_template('tracker.html',
                         version=VERSION,
                         birds_count=len(all_birds),
                         australia_states=AUSTRALIA_STATES)


@app.route('/region')
def region():
    """区域查询页面"""
    return render_template('region.html',
                         version=VERSION)


@app.route('/settings')
def settings():
    """设置页面"""
    api_key = config_manager.get_api_key()
    masked_key = None
    if api_key:
        masked_key = f"{api_key[:4]}...{api_key[-4:]}"

    return render_template('settings.html',
                         version=VERSION,
                         api_key=masked_key,
                         has_api_key=bool(api_key))


@app.route('/reports')
def reports():
    """历史报告列表"""
    output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output')
    reports_by_date = {}  # 按日期分组

    if os.path.exists(output_dir):
        for date_folder in sorted(os.listdir(output_dir), reverse=True):
            date_path = os.path.join(output_dir, date_folder)
            if os.path.isdir(date_path):
                date_reports = []
                for report_file in sorted(os.listdir(date_path), reverse=True):
                    if report_file.endswith('.md'):
                        # 获取文件的修改时间
                        file_path = os.path.join(date_path, report_file)
                        mtime = os.path.getmtime(file_path)

                        date_reports.append({
                            'filename': report_file,
                            'path': os.path.join(date_folder, report_file),
                            'mtime': mtime
                        })

                # 按修改时间排序（最新的在前）
                date_reports.sort(key=lambda x: x['mtime'], reverse=True)

                if date_reports:
                    reports_by_date[date_folder] = date_reports

    return render_template('reports.html',
                         version=VERSION,
                         reports_by_date=reports_by_date)


@app.route('/result/<path:report_path>')
def view_result(report_path):
    """查看报告详情（在线预览）"""
    try:
        output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output')
        report_file = os.path.join(output_dir, report_path)

        if not os.path.exists(report_file):
            return render_template('error.html',
                                 error_message='报告文件不存在',
                                 version=VERSION), 404

        # 读取 Markdown 文件
        with open(report_file, 'r', encoding='utf-8') as f:
            markdown_content = f.read()

        # 转换为 HTML
        md = markdown.Markdown(extensions=['extra', 'codehilite', 'toc'])
        html_content = md.convert(markdown_content)

        # 解析报告信息（从文件名或内容中提取）
        filename = os.path.basename(report_file)

        # 简单统计
        species_count = markdown_content.count('### No.')
        total_observations = markdown_content.count('条记录')

        # 获取生成时间
        mtime = os.path.getmtime(report_file)
        timestamp = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')

        return render_template('result.html',
                             report_html=html_content,
                             species_count=species_count if species_count > 0 else '未知',
                             total_observations=total_observations if total_observations > 0 else '未知',
                             timestamp=timestamp,
                             report_path=report_path,
                             version=VERSION)

    except Exception as e:
        return render_template('error.html',
                             error_message=f'读取报告失败: {str(e)}',
                             version=VERSION), 500


# ==================== API 端点 ====================

@app.route('/api/search_species', methods=['POST'])
def api_search_species():
    """搜索鸟种（模糊搜索）"""
    try:
        data = request.json
        query = data.get('query', '').strip()

        if not query:
            return jsonify({'error': '搜索关键词不能为空'}), 400

        db = init_database()
        results = db.fuzzy_search(query)

        return jsonify({
            'success': True,
            'results': results[:20],  # 限制返回前20个结果
            'total': len(results)
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/track', methods=['POST'])
def api_track():
    """执行追踪任务"""
    import datetime
    from config import get_resource_path

    try:
        data = request.json
        species_codes = data.get('species_codes', [])
        species_names = data.get('species_names', [])  # 前端传递的物种名称
        search_mode = data.get('search_mode', 'region')
        days_back = data.get('days_back', 14)

        if not species_codes:
            return jsonify({'error': '请至少选择一个物种'}), 400

        # 初始化 API 客户端和数据库
        client = init_api_client()
        if not client:
            return jsonify({'error': 'API Key 未配置或无效'}), 401

        db = init_database()

        # 获取观测数据
        all_observations = []

        if search_mode == 'gps':
            # GPS模式：使用坐标和半径
            gps_location = data.get('gps_location', '').strip()
            radius = data.get('radius', 25)

            if not gps_location:
                return jsonify({'error': 'GPS模式需要提供坐标或地点名称'}), 400

            # 尝试解析为坐标
            location_name = None
            from geopy.geocoders import Nominatim
            geolocator = Nominatim(user_agent="tuibird_tracker")

            try:
                # 支持多种格式：-12.4634, 130.8456 或 -12.4634 130.8456
                coords = gps_location.replace(',', ' ').split()
                if len(coords) == 2:
                    lat = float(coords[0])
                    lng = float(coords[1])

                    # 反向地理编码：根据坐标查询地点名称
                    try:
                        reverse_location = geolocator.reverse(f"{lat}, {lng}", timeout=10, language='zh')
                        if reverse_location:
                            location_name = reverse_location.address
                    except:
                        location_name = f"GPS ({lat:.4f}, {lng:.4f})"

                else:
                    # 如果不是坐标，尝试地理编码（地点名称转坐标）
                    location = geolocator.geocode(gps_location, country_codes='au', timeout=10)

                    if not location:
                        location = geolocator.geocode(gps_location, timeout=10)

                    if not location:
                        return jsonify({'error': '无法识别该地点，请输入有效的GPS坐标或地点名称'}), 400

                    lat = location.latitude
                    lng = location.longitude
                    location_name = location.address
            except ValueError:
                return jsonify({'error': 'GPS坐标格式错误，请使用格式：纬度, 经度'}), 400

            # 使用GPS坐标查询每个物种
            for species_code in species_codes:
                obs = client.get_recent_observations_by_location(
                    lat=lat,
                    lng=lng,
                    radius=radius,
                    days_back=days_back,
                    species_code=species_code
                )
                if obs:
                    all_observations.extend(obs)

        else:
            # 区域模式：使用行政区划代码
            region_code = data.get('region_code', 'AU')

            for species_code in species_codes:
                obs = client.get_recent_observations_by_species(
                    region_code=region_code,
                    species_code=species_code,
                    days_back=days_back
                )
                if obs:
                    all_observations.extend(obs)

        if not all_observations:
            return jsonify({
                'success': False,
                'message': '未找到任何观测记录',
                'observations_count': 0
            })

        # 生成 Markdown 报告
        output_base = get_resource_path('output')
        os.makedirs(output_base, exist_ok=True)

        today_str = datetime.datetime.now().strftime("%Y-%m-%d")
        today_folder = os.path.join(output_base, today_str)
        os.makedirs(today_folder, exist_ok=True)

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")

        # 构建物种名称字符串
        if species_names:
            species_str = "_".join([name['cn_name'] for name in species_names[:3]])
            if len(species_names) > 3:
                species_str += f"_等{len(species_names)}种"
        else:
            species_str = "_".join(species_codes[:3])

        filename = f"WebTracker_{species_str}_{timestamp}.md"
        filepath = os.path.join(today_folder, filename)

        # 写入报告
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f"# 🎯 eBird 物种追踪报告 (Web版)\n\n")
            f.write(f"**生成时间:** {datetime.datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}\n")

            # 根据搜索模式显示不同信息
            if search_mode == 'gps':
                f.write(f"**查询模式:** GPS搜索\n")
                if location_name:
                    f.write(f"**搜索位置:** {location_name}\n")
                f.write(f"**搜索中心:** GPS ({lat:.4f}, {lng:.4f})\n")
                f.write(f"**搜索半径:** {radius} km\n")
            else:
                f.write(f"**查询模式:** 区域搜索\n")
                f.write(f"**查询区域:** {region_code}\n")

            f.write(f"**时间范围:** 最近 {days_back} 天\n")
            f.write(f"**物种数量:** {len(species_codes)}\n\n")

            if species_names:
                f.write("**查询物种:**\n")
                for sp in species_names:
                    f.write(f"- {sp['cn_name']} ({sp['en_name']}) - `{sp['code']}`\n")
                f.write("\n")

            f.write(f"**分析摘要:** 共找到 **{len(all_observations)}** 条观测记录\n\n")
            f.write("---\n\n")
            f.write("## 📊 观测记录\n\n")

            # 按地点分组
            locations = {}
            for obs in all_observations:
                loc_id = obs.get('locId')
                if loc_id not in locations:
                    locations[loc_id] = {
                        'name': obs.get('locName', 'Unknown'),
                        'lat': obs.get('lat'),
                        'lng': obs.get('lng'),
                        'observations': []
                    }
                locations[loc_id]['observations'].append(obs)

            # 写入每个地点的观测
            for i, (loc_id, loc_data) in enumerate(sorted(locations.items(),
                                                          key=lambda x: len(x[1]['observations']),
                                                          reverse=True), 1):
                lat, lng = loc_data['lat'], loc_data['lng']
                maps_link = f"https://maps.google.com/?q={lat},{lng}" if lat and lng else "#"

                obs_count = len(loc_data['observations'])
                obs_text = f"{obs_count} 次观测" if obs_count > 1 else "1 次观测"

                f.write(f"### No.{i} [{loc_data['name']}]({maps_link})\n")
                f.write(f"**观测次数:** {obs_text}\n\n")

                for obs in sorted(loc_data['observations'],
                                key=lambda x: x.get('obsDt', ''), reverse=True):
                    species_code = obs.get('speciesCode')
                    species_name = obs.get('comName', species_code)
                    obs_date = obs.get('obsDt', 'Unknown')
                    count = obs.get('howMany', 'X')

                    f.write(f"- **{obs_date}**: {species_name} - 观测数量: {count} 只\n")

                f.write("\n")

            f.write("---\n\n")
            f.write(f"*报告由 TuiBird Tracker Web V{VERSION} 生成*\n")
            f.write("*数据由 eBird (www.ebird.org) 提供*\n")

        # 生成简单的结果摘要
        unique_locations = len(locations)

        return jsonify({
            'success': True,
            'message': '查询完成',
            'observations_count': len(all_observations),
            'unique_locations': unique_locations,
            'species_count': len(species_codes),
            'report_file': filename,
            'report_path': f"{today_str}/{filename}"
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/region_query', methods=['POST'])
def api_region_query():
    """区域查询"""
    import datetime
    from config import get_resource_path

    try:
        data = request.json
        lat = data.get('lat')
        lng = data.get('lng')
        radius = data.get('radius', 25)
        days_back = data.get('days_back', 14)
        display_mode = data.get('display_mode', 'brief')

        if not lat or not lng:
            return jsonify({'error': '请提供有效的 GPS 坐标'}), 400

        # 初始化 API 客户端和数据库
        client = init_api_client()
        if not client:
            return jsonify({'error': 'API Key 未配置或无效'}), 401

        db = init_database()
        code_to_name_map = db.get_code_to_name_map()

        # 获取该区域所有观测记录
        all_observations = client.get_recent_observations_by_location(
            lat=lat,
            lng=lng,
            radius=radius,
            days_back=days_back
        )

        if not all_observations:
            return jsonify({
                'success': False,
                'message': '该区域内未找到任何观测记录',
                'observations_count': 0
            })

        # 过滤出数据库中的鸟种
        filtered_observations = []
        for obs in all_observations:
            species_code = obs.get('speciesCode')
            if species_code in code_to_name_map:
                obs['cn_name'] = code_to_name_map[species_code]
                filtered_observations.append(obs)

        if not filtered_observations:
            return jsonify({
                'success': False,
                'message': '该区域内没有找到数据库中的目标鸟种',
                'total_observations': len(all_observations),
                'filtered_count': 0
            })

        # 按鸟种分组
        species_groups = {}
        for obs in filtered_observations:
            species_code = obs.get('speciesCode')
            if species_code not in species_groups:
                species_groups[species_code] = {
                    'species_code': species_code,
                    'cn_name': obs.get('cn_name', ''),
                    'en_name': obs.get('comName', ''),
                    'observations': []
                }
            species_groups[species_code]['observations'].append(obs)

        # 排序
        sorted_species = sorted(species_groups.values(),
                               key=lambda x: len(x['observations']),
                               reverse=True)

        # 生成 Markdown 报告
        output_base = get_resource_path('output')
        os.makedirs(output_base, exist_ok=True)

        today_str = datetime.datetime.now().strftime("%Y-%m-%d")
        today_folder = os.path.join(output_base, today_str)
        os.makedirs(today_folder, exist_ok=True)

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
        filename = f"WebRegion_{lat:.4f}_{lng:.4f}_{timestamp}.md"
        filepath = os.path.join(today_folder, filename)

        # 写入报告
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f"# 🦅 鸟类区域查询报告 (Web版)\n\n")
            f.write(f"**生成时间:** {datetime.datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}\n")
            f.write(f"**搜索位置:** GPS ({lat:.4f}, {lng:.4f})\n")
            f.write(f"**搜索半径:** {radius} km\n")
            f.write(f"**时间范围:** 最近 {days_back} 天\n")
            f.write(f"**显示模式:** {'完整模式' if display_mode == 'full' else '简要模式'}\n\n")

            f.write(f"**分析摘要:** 在指定范围内，共发现 **{len(sorted_species)}** 种目标鸟类，")
            f.write(f"共 **{len(filtered_observations)}** 次观测记录。\n\n")

            f.write("---\n\n")
            f.write("## 📋 目标鸟种记录\n\n")

            for i, group in enumerate(sorted_species, 1):
                species_code = group['species_code']
                cn_name = group['cn_name']
                en_name = group['en_name']
                obs_count = len(group['observations'])

                f.write(f"### No.{i} ({species_code}) 🐦 {cn_name} ({en_name})\n")
                f.write(f"**观测次数:** {obs_count} 次\n\n")

                # 按时间排序
                sorted_obs = sorted(group['observations'],
                                   key=lambda x: x.get('obsDt', ''),
                                   reverse=True)

                # 根据显示模式选择数量
                if display_mode == 'full':
                    display_obs = sorted_obs
                else:
                    display_obs = sorted_obs[:5]
                    if len(sorted_obs) > 5:
                        f.write(f"**显示最新 5 条记录（共 {len(sorted_obs)} 条）:**\n\n")

                for obs in display_obs:
                    obs_date = obs.get('obsDt', 'Unknown')
                    location = obs.get('locName', 'Unknown Location')
                    lat_obs = obs.get('lat')
                    lng_obs = obs.get('lng')
                    count = obs.get('howMany', 'X')

                    # 生成地图链接
                    if lat_obs and lng_obs:
                        maps_link = f"https://maps.google.com/?q={lat_obs},{lng_obs}"
                        location_link = f"[{location}]({maps_link})"
                    else:
                        location_link = location

                    location_type = "📍私人" if obs.get('locPrivate', False) else "🔥热点"

                    f.write(f"- **{obs_date}**: {location_link} {location_type} - 观测数量: {count} 只\n")

                f.write("\n")

            f.write("---\n\n")
            f.write(f"*报告由 TuiBird Tracker Web V{VERSION} 生成*\n")
            f.write("*数据由 eBird (www.ebird.org) 提供*\n")

        # 统计信息
        unique_locations = len(set(obs.get('locId') for obs in filtered_observations if obs.get('locId')))

        # 准备详细观测数据（用于地图显示）
        observations_data = []
        for obs in filtered_observations:
            observations_data.append({
                'species_code': obs.get('speciesCode'),
                'species_name': obs.get('cn_name', obs.get('comName', '')),
                'en_name': obs.get('comName', ''),
                'lat': obs.get('lat'),
                'lng': obs.get('lng'),
                'location_name': obs.get('locName', ''),
                'location_id': obs.get('locId', ''),
                'observation_date': obs.get('obsDt', ''),
                'count': obs.get('howMany', 'X'),
                'is_private': obs.get('locPrivate', False)
            })

        return jsonify({
            'success': True,
            'message': '查询完成',
            'observations_count': len(filtered_observations),
            'total_observations': len(all_observations),
            'unique_locations': unique_locations,
            'species_count': len(sorted_species),
            'report_file': filename,
            'report_path': f"{today_str}/{filename}",
            'observations': observations_data,  # 详细观测数据
            'center': {'lat': lat, 'lng': lng},  # 搜索中心点
            'radius': radius  # 搜索半径
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/config/api_key', methods=['GET', 'POST', 'DELETE'])
def api_config_api_key():
    """API Key 管理"""
    try:
        if request.method == 'GET':
            # 获取 API Key（脱敏）
            api_key = config_manager.get_api_key()
            if api_key:
                return jsonify({
                    'success': True,
                    'api_key': f"{api_key[:4]}...{api_key[-4:]}",
                    'full_length': len(api_key)
                })
            else:
                return jsonify({
                    'success': False,
                    'message': '未设置 API Key'
                })

        elif request.method == 'POST':
            # 设置新的 API Key
            data = request.json
            new_key = data.get('api_key', '').strip()

            if not new_key:
                return jsonify({'error': 'API Key 不能为空'}), 400

            # 验证 API Key
            test_client = EBirdAPIClient(new_key)
            is_valid, message = test_client.validate_api_key()

            if is_valid:
                config_manager.set_api_key(new_key)
                config_manager.save()

                # 重置全局 API 客户端
                _reset_api_client()

                return jsonify({
                    'success': True,
                    'message': 'API Key 已保存并验证成功'
                })
            else:
                return jsonify({
                    'success': False,
                    'error': message
                }), 400

        elif request.method == 'DELETE':
            # 删除 API Key
            config_manager.set_api_key('')
            config_manager.save()

            _reset_api_client()

            return jsonify({
                'success': True,
                'message': 'API Key 已删除'
            })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/report/<path:report_path>')
def api_get_report(report_path):
    """获取报告内容"""
    try:
        output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output')
        report_file = os.path.join(output_dir, report_path)

        if not os.path.exists(report_file):
            return jsonify({'error': '报告文件不存在'}), 404

        with open(report_file, 'r', encoding='utf-8') as f:
            content = f.read()

        return jsonify({
            'success': True,
            'content': content,
            'filename': os.path.basename(report_file)
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/geocode', methods=['POST'])
def api_geocode():
    """将地点名称转换为GPS坐标"""
    try:
        data = request.json
        place_name = data.get('place_name', '').strip()

        if not place_name:
            return jsonify({'error': '地点名称不能为空'}), 400

        # 使用 Nominatim 地理编码服务
        geolocator = Nominatim(user_agent="tuibird_tracker")

        try:
            # 优先在澳大利亚范围内搜索
            location = geolocator.geocode(
                place_name,
                country_codes='au',
                timeout=10
            )

            # 如果在澳大利亚没找到，扩大搜索范围
            if not location:
                location = geolocator.geocode(place_name, timeout=10)

            if location:
                return jsonify({
                    'success': True,
                    'latitude': location.latitude,
                    'longitude': location.longitude,
                    'display_name': location.address,
                    'message': f'找到位置: {location.address}'
                })
            else:
                return jsonify({
                    'success': False,
                    'error': '未找到该地点，请检查拼写或尝试使用更具体的地点名称'
                }), 404

        except GeocoderTimedOut:
            return jsonify({
                'success': False,
                'error': '地理编码服务超时，请稍后重试'
            }), 408

        except GeocoderServiceError as e:
            return jsonify({
                'success': False,
                'error': f'地理编码服务错误: {str(e)}'
            }), 503

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    # 生产环境会使用 gunicorn，这里仅用于本地开发
    PORT = int(os.environ.get('PORT', 5001))  # 支持 Render 的 PORT 环境变量
    DEBUG = os.environ.get('DEBUG', 'True').lower() == 'true'

    print("=" * 60)
    print(f"🦅 TuiBird Tracker Web App V{VERSION}")
    print("=" * 60)
    print(f"🌐 启动 Web 服务器...")
    print(f"📍 访问地址: http://127.0.0.1:{PORT}")
    print(f"🔑 按 Ctrl+C 停止服务器")
    print("=" * 60)

    app.run(host='0.0.0.0', port=PORT, debug=DEBUG)
