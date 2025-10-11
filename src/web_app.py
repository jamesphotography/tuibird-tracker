#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
慧眼找鸟 Web Application
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
import time
import secrets
from flask_wtf.csrf import CSRFProtect

# 加载环境变量
from dotenv import load_dotenv
load_dotenv()

# 导入现有模块
from config import VERSION, BUILD_DATE, ConfigManager, DB_FILE, AUSTRALIA_STATES, get_resource_path
from database import BirdDatabase
from api_client import EBirdAPIClient, get_api_key_with_validation

app = Flask(__name__)

# 安全配置：从环境变量读取，如果不存在则生成随机值
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
app.config['JSON_AS_ASCII'] = False  # 支持中文 JSON
app.config['WTF_CSRF_TIME_LIMIT'] = None  # CSRF token 不过期
app.config['WTF_CSRF_HEADERS'] = ['X-CSRFToken']  # 接受来自 X-CSRFToken 请求头的 token

# 启用 CSRF 保护
csrf = CSRFProtect(app)

# 全局配置
config_manager = ConfigManager()
bird_db = None
api_client = None

# 匿名用户共享的 API Key（从环境变量读取）
ANONYMOUS_API_KEY = os.environ.get('ANONYMOUS_API_KEY', '')
if not ANONYMOUS_API_KEY:
    print("警告: ANONYMOUS_API_KEY 未配置，访客模式将不可用")
    print("请在 .env 文件中配置 ANONYMOUS_API_KEY=your_key")

# 匿名用户限流配置
ANONYMOUS_LIMITS = {
    'hourly_limit': 10,      # 每小时最多10次查询
    'daily_limit': 30,       # 每天最多30次查询
    'max_species': 1,        # 最多查询1个物种
    'max_radius': 25,        # 最大搜索半径25km
    'max_days': 7            # 最大时间范围7天
}


class APICache:
    """简单的 API 响应缓存（内存缓存 + TTL，线程安全）"""

    def __init__(self, ttl=300, max_size=1000):
        """
        初始化缓存
        :param ttl: 缓存有效期（秒），默认5分钟
        :param max_size: 最大缓存条目数，默认1000条
        """
        import threading
        from collections import OrderedDict
        self.cache = OrderedDict()  # 保持插入顺序，支持LRU
        self.ttl = ttl
        self.max_size = max_size
        self._lock = threading.RLock()  # 可重入锁

    def get(self, key):
        """获取缓存（线程安全）"""
        with self._lock:
            if key in self.cache:
                data, timestamp = self.cache[key]
                # 检查是否过期
                if time.time() - timestamp < self.ttl:
                    # LRU：移到末尾（最近使用）
                    self.cache.move_to_end(key)
                    return data
                else:
                    # 清除过期缓存
                    del self.cache[key]
            return None

    def set(self, key, value):
        """设置缓存（线程安全，支持LRU淘汰）"""
        with self._lock:
            # 如果已存在，先删除（移到末尾）
            if key in self.cache:
                del self.cache[key]

            # 如果超过最大容量，删除最旧的条目
            if len(self.cache) >= self.max_size:
                # 删除最早插入的条目（FIFO/LRU）
                self.cache.popitem(last=False)

            self.cache[key] = (value, time.time())

    def clear(self):
        """清空所有缓存（线程安全）"""
        with self._lock:
            self.cache.clear()

    def cleanup(self):
        """清理过期缓存（线程安全）"""
        with self._lock:
            current_time = time.time()
            # 创建副本进行迭代，避免迭代时修改
            expired_keys = [
                key for key, (_, timestamp) in list(self.cache.items())
                if current_time - timestamp >= self.ttl
            ]
            for key in expired_keys:
                del self.cache[key]


# 创建全局 API 缓存实例
api_cache = APICache(ttl=300)  # 5分钟缓存

# 创建全局 Geolocator 实例（避免频繁初始化导致限流）
_geolocator = None

def get_geolocator():
    """获取全局 Geolocator 单例"""
    global _geolocator
    if _geolocator is None:
        _geolocator = Nominatim(user_agent="tuibird_tracker")
    return _geolocator


class RateLimiter:
    """简单的速率限制器（基于文件存储，线程安全）"""

    def __init__(self):
        import threading
        self.storage_file = get_resource_path('rate_limit.json')
        self.data = {}
        self._lock = threading.Lock()  # 线程锁

    def _load_data(self):
        """加载限流数据（带线程锁）"""
        with self._lock:
            if not os.path.exists(self.storage_file):
                return {}

            try:
                with open(self.storage_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"加载限流数据失败: {e}")
                return {}

    def _save_data(self):
        """保存限流数据（原子写入，防止文件损坏）"""
        with self._lock:
            try:
                # 使用临时文件 + 原子替换，防止写入中断导致文件损坏
                temp_file = self.storage_file + '.tmp'
                with open(temp_file, 'w') as f:
                    json.dump(self.data, f)
                    f.flush()
                    os.fsync(f.fileno())  # 确保写入磁盘

                # 原子替换（在所有平台都是原子操作）
                os.replace(temp_file, self.storage_file)
            except Exception as e:
                print(f"保存限流数据失败: {e}")
                # 清理临时文件
                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except:
                        pass

    def _clean_old_data(self):
        """清理过期数据（超过24小时）"""
        now = time.time()
        to_delete = []
        for ip, records in self.data.items():
            records['requests'] = [r for r in records.get('requests', [])
                                  if now - r < 86400]  # 保留24小时内的记录
            if not records['requests']:
                to_delete.append(ip)

        for ip in to_delete:
            del self.data[ip]

    def check_limit(self, ip_address):
        """检查IP是否超过限制（支持多进程）"""
        # 每次都重新加载数据（支持多进程环境）
        self.data = self._load_data()
        self._clean_old_data()

        now = time.time()
        if ip_address not in self.data:
            self.data[ip_address] = {'requests': []}

        requests = self.data[ip_address]['requests']

        # 检查小时限制
        hour_ago = now - 3600
        hourly_count = sum(1 for r in requests if r > hour_ago)

        # 检查日限制
        day_ago = now - 86400
        daily_count = sum(1 for r in requests if r > day_ago)

        return {
            'allowed': hourly_count < ANONYMOUS_LIMITS['hourly_limit'] and
                      daily_count < ANONYMOUS_LIMITS['daily_limit'],
            'hourly_remaining': max(0, ANONYMOUS_LIMITS['hourly_limit'] - hourly_count),
            'daily_remaining': max(0, ANONYMOUS_LIMITS['daily_limit'] - daily_count),
            'hourly_count': hourly_count,
            'daily_count': daily_count
        }

    def record_request(self, ip_address):
        """记录一次请求（原子操作，支持多进程）"""
        # 重新加载最新数据
        self.data = self._load_data()

        if ip_address not in self.data:
            self.data[ip_address] = {'requests': []}

        self.data[ip_address]['requests'].append(time.time())

        # 立即保存（原子操作）
        self._save_data()


# 全局限流器实例
rate_limiter = RateLimiter()


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


def get_api_key_from_request():
    """
    从请求中获取 API Key
    优先级：Cookie > 请求头 > 服务器配置 > 匿名共享 Key
    """
    # 优先从 Cookie 获取（支持页面导航）
    cookie_api_key = request.cookies.get('ebird_api_key')
    if cookie_api_key:
        return cookie_api_key

    # 其次从请求头获取（支持 AJAX 请求）
    client_api_key = request.headers.get('X-eBird-API-Key')
    if client_api_key:
        return client_api_key

    # 再从服务器配置获取（向后兼容）
    server_key = config_manager.get_api_key()
    if server_key:
        return server_key

    # 最后使用匿名共享 Key（供游客测试）
    return ANONYMOUS_API_KEY


def is_anonymous_user():
    """
    判断当前用户是否为匿名用户（使用共享 API Key）
    """
    api_key = get_api_key_from_request()
    return api_key == ANONYMOUS_API_KEY


def get_api_client_from_request():
    """
    根据请求头中的 API Key 创建 API 客户端
    """
    api_key = get_api_key_from_request()
    if not api_key:
        return None
    return EBirdAPIClient(api_key)


def get_user_id_from_api_key(api_key):
    """
    根据 API Key 生成用户ID（使用哈希，保护隐私）
    """
    import hashlib
    if not api_key:
        return 'anonymous'
    # 使用 SHA256 哈希前8位作为用户ID
    hash_object = hashlib.sha256(api_key.encode())
    return hash_object.hexdigest()[:8]


def get_user_output_dir(api_key):
    """
    获取用户专属的输出目录
    """
    from config import get_resource_path
    user_id = get_user_id_from_api_key(api_key)
    output_base = get_resource_path('output')
    user_dir = os.path.join(output_base, f"user_{user_id}")
    os.makedirs(user_dir, exist_ok=True)
    return user_dir


def clean_old_reports(user_output_dir, days=7):
    """
    清理指定天数之前的旧报告
    """
    import time
    cutoff_time = time.time() - (days * 24 * 60 * 60)

    if not os.path.exists(user_output_dir):
        return

    deleted_count = 0
    for root, dirs, files in os.walk(user_output_dir, topdown=False):
        # 删除旧文件
        for filename in files:
            filepath = os.path.join(root, filename)
            try:
                if os.path.getmtime(filepath) < cutoff_time:
                    os.remove(filepath)
                    deleted_count += 1
            except Exception as e:
                print(f"删除文件失败 {filepath}: {e}")

        # 删除空目录
        for dirname in dirs:
            dirpath = os.path.join(root, dirname)
            try:
                if not os.listdir(dirpath):  # 目录为空
                    os.rmdir(dirpath)
            except Exception as e:
                print(f"删除目录失败 {dirpath}: {e}")

    if deleted_count > 0:
        print(f"清理了 {deleted_count} 个超过 {days} 天的旧报告")

    return deleted_count


def add_bird_name_links(html_content):
    """
    在HTML内容中为鸟名添加可点击链接
    只链接中文鸟名，避免英文名中的特殊字符（括号、引号）造成显示错误
    """
    try:
        import re
        import sqlite3
        from bs4 import BeautifulSoup

        db = init_database()
        if not db:
            return html_content

        # 获取所有中文鸟名
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT chinese_simplified FROM BirdCountInfo WHERE chinese_simplified != '' AND chinese_simplified IS NOT NULL")
        bird_names = cursor.fetchall()
        conn.close()

        # 创建中文鸟名集合用于快速查找
        bird_name_set = set()
        for (cn_name,) in bird_names:
            if cn_name and len(cn_name) >= 2:  # 中文名至少2个字
                bird_name_set.add(cn_name)

        # 解析HTML
        soup = BeautifulSoup(html_content, 'html.parser')

        # 处理所有文本节点（在 p, li, blockquote, td 等标签中）
        for tag in soup.find_all(['p', 'li', 'blockquote', 'td', 'dd']):
            # 遍历标签内的所有文本节点
            for text_node in tag.find_all(text=True, recursive=False):
                if text_node.parent.name == 'a':
                    # 跳过已经在链接中的文本
                    continue

                text = str(text_node)
                modified_text = text

                # 按长度降序排列鸟名，优先匹配长名字（避免短名字被误匹配）
                for bird_name in sorted(bird_name_set, key=len, reverse=True):
                    if bird_name in modified_text:
                        # 使用正则替换，确保只替换独立的鸟名
                        # 前后不能是汉字、字母、数字，避免误匹配（如"姬地鸠"不应匹配"戈氏姬地鸠"中的部分）
                        # 同时避免替换HTML标签内的内容
                        pattern = r'(?<![\u4e00-\u9fa5a-zA-Z0-9>])(?<!</a>)' + re.escape(bird_name) + r'(?![\u4e00-\u9fa5a-zA-Z0-9<])'
                        # 转义单引号和双引号，避免JavaScript字符串错误
                        escaped_bird_name = bird_name.replace("'", "\\'").replace('"', '\\"')
                        link = f'<a href="javascript:void(0)" class="bird-name-link" onclick="showBirdInfo(\'{escaped_bird_name}\')">{bird_name}</a>'
                        modified_text = re.sub(pattern, link, modified_text, count=1)  # 每个鸟名只替换第一次出现

                # 如果文本被修改，替换原节点
                if modified_text != text:
                    # 使用 BeautifulSoup 解析修改后的 HTML，保留所有内容
                    from bs4 import NavigableString
                    new_soup = BeautifulSoup(modified_text, 'html.parser')
                    # 获取解析后的所有子节点（包括文本和标签）
                    replacement_nodes = list(new_soup.children)
                    if replacement_nodes:
                        # 先插入第一个节点替换当前节点
                        first_node = replacement_nodes[0]
                        text_node.replace_with(first_node)
                        # 然后在第一个节点后面插入其余节点
                        for node in replacement_nodes[1:]:
                            first_node.insert_after(node)
                            first_node = node

        return str(soup)
    except Exception as e:
        print(f"添加鸟名链接失败: {e}")
        import traceback
        traceback.print_exc()
        return html_content


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


@app.route('/route')
def route():
    """路线热点搜索页面"""
    return render_template('route.html',
                         version=VERSION)


@app.route('/endemic')
def endemic():
    """特有种检索页面"""
    return render_template('endemic.html',
                         version=VERSION,
                         build_date=BUILD_DATE)


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
    """历史报告列表（仅显示当前用户的报告）"""
    # 获取当前用户的专属目录
    api_key = get_api_key_from_request()
    user_output_dir = get_user_output_dir(api_key)

    reports_by_date = {}  # 按日期分组

    # 仅扫描用户专属目录
    if os.path.exists(user_output_dir):
        for date_folder in sorted(os.listdir(user_output_dir), reverse=True):
            date_path = os.path.join(user_output_dir, date_folder)
            if os.path.isdir(date_path):
                date_reports = []
                for report_file in sorted(os.listdir(date_path), reverse=True):
                    # 支持 .md 和 .json 文件
                    if report_file.endswith('.md') or report_file.endswith('.json'):
                        # 获取文件的修改时间
                        file_path = os.path.join(date_path, report_file)
                        mtime = os.path.getmtime(file_path)

                        # 判断文件类型并提取元数据
                        file_type = 'route' if report_file.startswith('route_') else 'markdown'
                        display_name = report_file
                        metadata = {}

                        # 对于区域查询Markdown文件，读取地名
                        if file_type == 'markdown' and report_file.startswith('WebRegion_'):
                            try:
                                with open(file_path, 'r', encoding='utf-8') as f:
                                    # 读取前几行查找位置信息
                                    for _ in range(10):
                                        line = f.readline()
                                        if '**搜索位置:**' in line:
                                            # 提取地名
                                            location_part = line.split('**搜索位置:**')[1].strip()
                                            # 如果有地名（格式：地名 (GPS: x, y)）
                                            if '(' in location_part:
                                                location_name = location_part.split('(')[0].strip()
                                                display_name = location_name
                                            else:
                                                # 没有地名，只有GPS坐标（格式：GPS (x, y)）
                                                display_name = location_part.replace('GPS ', '')
                                            break
                            except Exception as e:
                                print(f"读取区域查询元数据失败: {e}")

                        # 对于路线热点JSON文件，读取元数据
                        elif file_type == 'route':
                            try:
                                with open(file_path, 'r', encoding='utf-8') as f:
                                    route_data = json.load(f)
                                    query = route_data.get('query', {})
                                    summary = route_data.get('summary', {})

                                    start_loc = query.get('start_location', '起点')
                                    end_loc = query.get('end_location', '终点')
                                    hotspots_count = summary.get('hotspots_count', 0)
                                    distance = summary.get('route_distance_km', 0)

                                    # 提取地名主要部分（逗号前的部分）
                                    start_short = start_loc.split(',')[0].strip() if ',' in start_loc else start_loc
                                    end_short = end_loc.split(',')[0].strip() if ',' in end_loc else end_loc

                                    display_name = f"{start_short} → {end_short}"
                                    metadata = {
                                        'start': start_loc,
                                        'end': end_loc,
                                        'hotspots': hotspots_count,
                                        'distance': distance
                                    }
                            except Exception as e:
                                print(f"读取路线元数据失败: {e}")

                        date_reports.append({
                            'filename': report_file,
                            'display_name': display_name,
                            'path': os.path.join(date_folder, report_file),
                            'mtime': mtime,
                            'type': file_type,
                            'metadata': metadata
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
        # 获取当前用户的专属目录
        api_key = get_api_key_from_request()
        user_output_dir = get_user_output_dir(api_key)

        # 仅访问用户专属目录
        report_file = os.path.join(user_output_dir, report_path)

        # 安全检查：确保在用户目录内
        report_file_real = os.path.realpath(report_file)
        user_output_dir_real = os.path.realpath(user_output_dir)
        if not report_file_real.startswith(user_output_dir_real):
            return render_template('error.html',
                                 error_message='非法访问路径',
                                 version=VERSION), 403

        if not os.path.exists(report_file):
            return render_template('error.html',
                                 error_message='报告文件不存在',
                                 version=VERSION), 404

        # 读取 Markdown 文件
        with open(report_file, 'r', encoding='utf-8') as f:
            markdown_content = f.read()

        # 转换为 HTML（允许嵌入的HTML标签）
        md = markdown.Markdown(extensions=['extra', 'codehilite', 'toc', 'md_in_html'])
        html_content = md.convert(markdown_content)

        # 为鸟名添加可点击链接
        html_content = add_bird_name_links(html_content)

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


def parse_dms_coordinate(dms_str):
    """
    解析度分秒格式的GPS坐标
    支持格式：
    - 34°20'29.5"S 139°29'24.3"E
    - 34° 20' 29.5" S, 139° 29' 24.3" E
    - 34°20'29.5"S, 139°29'24.3"E

    返回: (latitude, longitude) 十进制度数格式
    """
    import re

    # 移除所有空格
    dms_str = dms_str.strip()

    # 正则表达式匹配度分秒格式
    # 格式: 度°分'秒"方向
    pattern = r"(\d+)[°\s]+(\d+)['\s]+([0-9.]+)[\"'\s]*([NSEW])"

    matches = re.findall(pattern, dms_str.upper())

    if len(matches) < 2:
        return None, None

    # 解析纬度和经度
    coords = []
    for match in matches[:2]:  # 只取前两个（纬度和经度）
        degrees = float(match[0])
        minutes = float(match[1])
        seconds = float(match[2])
        direction = match[3]

        # 转换为十进制度数
        decimal = degrees + minutes / 60 + seconds / 3600

        # 根据方向调整符号
        if direction in ['S', 'W']:
            decimal = -decimal

        coords.append(decimal)

    if len(coords) == 2:
        return coords[0], coords[1]  # (lat, lng)

    return None, None


def check_checklist_for_species(client, sub_id, target_species_set, first_species_obs):
    """
    检查清单是否包含所有目标物种（公共函数）

    :param client: eBird API 客户端
    :param sub_id: 清单ID
    :param target_species_set: 目标物种代码集合
    :param first_species_obs: 第一个物种的观测记录列表
    :return: 匹配的观测记录列表，如果不匹配则返回空列表
    """
    try:
        checklist = client.get_checklist_details(sub_id)
        if not checklist or 'obs' not in checklist:
            return []

        # 检查清单中是否包含所有目标物种
        found_species = set()
        for obs_item in checklist['obs']:
            species_code = obs_item.get('speciesCode')
            if species_code in target_species_set:
                found_species.add(species_code)

        # 如果不包含所有目标物种，返回空列表
        if found_species != target_species_set:
            return []

        # 构建索引以优化查找（避免重复遍历）
        sub_id_to_obs = {}
        for orig_obs in first_species_obs:
            if orig_obs.get('subId') == sub_id:
                sub_id_to_obs = orig_obs
                break

        if not sub_id_to_obs:
            return []

        # 构造匹配的观测记录
        matching_obs = []
        for obs_item in checklist['obs']:
            species_code = obs_item.get('speciesCode')
            if species_code in target_species_set:
                # 复制观测信息并更新物种相关字段
                new_obs = sub_id_to_obs.copy()
                new_obs['speciesCode'] = species_code
                new_obs['comName'] = obs_item.get('comName') or species_code or 'Unknown'
                new_obs['howMany'] = obs_item.get('howMany') or 'X'
                matching_obs.append(new_obs)

        return matching_obs

    except Exception as e:
        print(f"检查清单失败 ({sub_id}): {e}")
        return []


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
        analysis_mode = data.get('analysis_mode', 'and')  # 分析模式：and(同时出现) 或 or(任一物种)
        days_back = data.get('days_back', 14)
        radius = data.get('radius', 25)

        if not species_codes:
            return jsonify({'error': '请至少选择一个物种'}), 400

        # 匿名用户限流和功能限制
        if is_anonymous_user():
            client_ip = request.remote_addr
            limit_status = rate_limiter.check_limit(client_ip)

            if not limit_status['allowed']:
                return jsonify({
                    'error': '⏱️ 访客模式已达使用上限',
                    'message': f'每小时限制{ANONYMOUS_LIMITS["hourly_limit"]}次，每天限制{ANONYMOUS_LIMITS["daily_limit"]}次。\n'
                              f'请注册免费的 eBird API Key 以解除限制。',
                    'limit_info': limit_status,
                    'register_url': 'https://ebird.org/api/keygen'
                }), 429

            # 功能限制检查
            if len(species_codes) > ANONYMOUS_LIMITS['max_species']:
                return jsonify({
                    'error': f'访客模式最多查询 {ANONYMOUS_LIMITS["max_species"]} 个物种',
                    'message': '请注册免费的 eBird API Key 以解除限制。',
                    'register_url': 'https://ebird.org/api/keygen'
                }), 400

            if radius > ANONYMOUS_LIMITS['max_radius']:
                return jsonify({
                    'error': f'访客模式最大搜索半径为 {ANONYMOUS_LIMITS["max_radius"]} km',
                    'message': '请注册免费的 eBird API Key 以解除限制。'
                }), 400

            if days_back > ANONYMOUS_LIMITS['max_days']:
                return jsonify({
                    'error': f'访客模式最大查询天数为 {ANONYMOUS_LIMITS["max_days"]} 天',
                    'message': '请注册免费的 eBird API Key 以解除限制。'
                }), 400

            # 记录本次请求
            rate_limiter.record_request(client_ip)

        # 从请求头获取 API Key 并初始化客户端
        client = get_api_client_from_request()
        if not client:
            return jsonify({'error': 'API Key 未配置，请前往设置页面配置'}), 401

        db = init_database()

        # 获取观测数据
        all_observations = []

        # 单物种或"任一物种"模式：分别查询每个物种
        is_single_species = len(species_codes) == 1
        use_or_mode = analysis_mode == 'or'

        if search_mode == 'gps':
            # GPS模式：使用坐标和半径
            gps_location = data.get('gps_location', '').strip()
            radius = data.get('radius', 25)

            if not gps_location:
                return jsonify({'error': 'GPS模式需要提供坐标或地点名称'}), 400

            # 尝试解析为坐标
            location_name = None
            geolocator = get_geolocator()
            lat = None
            lng = None

            try:
                # 优先尝试度分秒格式
                lat_dms, lng_dms = parse_dms_coordinate(gps_location)
                if lat_dms is not None and lng_dms is not None:
                    lat, lng = lat_dms, lng_dms
                else:
                    # 支持十进制格式：-12.4634, 130.8456 或 -12.4634 130.8456
                    coords = gps_location.replace(',', ' ').split()
                    if len(coords) == 2:
                        lat = float(coords[0])
                        lng = float(coords[1])

                # 如果成功解析坐标
                if lat is not None and lng is not None:
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

            # 判断使用哪种查询模式
            if is_single_species or use_or_mode:
                # 单物种或"任一物种"模式：分别查询每个物种
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
                # "同时出现"模式：查询第一个物种，然后过滤包含所有物种的清单
                target_species_set = set(species_codes)

                # 只查询第一个物种的观测记录
                first_species_obs = client.get_recent_observations_by_location(
                    lat=lat,
                    lng=lng,
                    radius=radius,
                    days_back=days_back,
                    species_code=species_codes[0]
                )

                if first_species_obs:
                    # 收集所有唯一的清单ID
                    sub_ids_to_check = set()
                    for obs in first_species_obs:
                        sub_id = obs.get('subId')
                        if sub_id:
                            sub_ids_to_check.add(sub_id)

                    # 并发获取清单详情并过滤（使用公共函数）
                    from concurrent.futures import ThreadPoolExecutor, as_completed

                    with ThreadPoolExecutor(max_workers=10) as executor:
                        futures = {
                            executor.submit(check_checklist_for_species, client, sub_id, target_species_set, first_species_obs): sub_id
                            for sub_id in sub_ids_to_check
                        }
                        for future in as_completed(futures):
                            matching_obs = future.result()
                            if matching_obs:
                                all_observations.extend(matching_obs)

        else:
            # 区域模式：使用行政区划代码
            region_code = data.get('region_code', 'AU')

            if is_single_species or use_or_mode:
                # 单物种或"任一物种"模式
                for species_code in species_codes:
                    obs = client.get_recent_observations_by_species(
                        region_code=region_code,
                        species_code=species_code,
                        days_back=days_back
                    )
                    if obs:
                        all_observations.extend(obs)
            else:
                # "同时出现"模式
                target_species_set = set(species_codes)

                # 只查询第一个物种
                first_species_obs = client.get_recent_observations_by_species(
                    region_code=region_code,
                    species_code=species_codes[0],
                    days_back=days_back
                )

                if first_species_obs:
                    # 收集清单ID并过滤（使用公共函数）
                    sub_ids_to_check = set()
                    for obs in first_species_obs:
                        sub_id = obs.get('subId')
                        if sub_id:
                            sub_ids_to_check.add(sub_id)

                    from concurrent.futures import ThreadPoolExecutor, as_completed

                    with ThreadPoolExecutor(max_workers=10) as executor:
                        futures = {
                            executor.submit(check_checklist_for_species, client, sub_id, target_species_set, first_species_obs): sub_id
                            for sub_id in sub_ids_to_check
                        }
                        for future in as_completed(futures):
                            matching_obs = future.result()
                            if matching_obs:
                                all_observations.extend(matching_obs)

        if not all_observations:
            return jsonify({
                'success': False,
                'message': '未找到任何观测记录',
                'observations_count': 0
            })

        # 生成 Markdown 报告 - 使用用户专属目录
        api_key = get_api_key_from_request()
        user_output_dir = get_user_output_dir(api_key)

        # 清理旧报告（7天前）
        clean_old_reports(user_output_dir, days=7)

        today_str = datetime.datetime.now().strftime("%Y-%m-%d")
        today_folder = os.path.join(user_output_dir, today_str)
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

            # 获取目标鸟种代码集合（用于过滤伴生鸟种）
            target_species_codes = set(species_codes)
            code_to_name_map = db.get_code_to_name_map()
            code_to_full_name_map = db.get_code_to_full_name_map()

            # 性能优化：批量获取所有唯一的清单详情
            unique_sub_ids = set()
            for obs in all_observations:
                sub_id = obs.get('subId')
                if sub_id:
                    unique_sub_ids.add(sub_id)

            # 并发获取所有清单详情（使用线程池）
            checklist_cache = {}
            if unique_sub_ids:
                from concurrent.futures import ThreadPoolExecutor, as_completed

                def fetch_checklist(sub_id):
                    try:
                        return sub_id, client.get_checklist_details(sub_id)
                    except Exception as e:
                        print(f"获取清单详情失败 ({sub_id}): {e}")
                        return sub_id, None

                # 使用线程池并发获取（最多10个并发）
                with ThreadPoolExecutor(max_workers=10) as executor:
                    futures = {executor.submit(fetch_checklist, sub_id): sub_id for sub_id in unique_sub_ids}
                    for future in as_completed(futures):
                        sub_id, checklist = future.result()
                        if checklist:
                            checklist_cache[sub_id] = checklist

            # 写入每个地点的观测
            for i, (loc_id, loc_data) in enumerate(sorted(locations.items(),
                                                          key=lambda x: len(x[1]['observations']),
                                                          reverse=True), 1):
                lat, lng = loc_data['lat'], loc_data['lng']
                maps_link = f"https://maps.google.com/?q={lat},{lng}" if lat and lng else "#"

                f.write(f"### No.{i} [{loc_data['name']}]({maps_link})\n")

                # 按清单ID分组观测记录
                checklists_at_location = {}
                for obs in loc_data['observations']:
                    sub_id = obs.get('subId')
                    if sub_id:
                        if sub_id not in checklists_at_location:
                            checklists_at_location[sub_id] = {
                                'obs_date': obs.get('obsDt', 'Unknown'),
                                'species': []
                            }
                        # 确保物种名称不为 None
                        species_code = obs.get('speciesCode')
                        species_name = obs.get('comName') or species_code or 'Unknown Species'

                        checklists_at_location[sub_id]['species'].append({
                            'code': species_code,
                            'name': species_name,
                            'count': obs.get('howMany', 'X')
                        })

                # 显示每个清单（同一清单只显示一次）
                for sub_id, checklist_data in sorted(checklists_at_location.items(),
                                                     key=lambda x: x[1]['obs_date'],
                                                     reverse=True):
                    obs_date = checklist_data['obs_date']
                    target_species_in_checklist = checklist_data['species']

                    # 如果是"同时出现"模式且有多个目标物种，显示为"多物种观测"
                    if analysis_mode == 'and' and len(target_species_in_checklist) > 1:
                        species_list = ', '.join([sp['name'] for sp in target_species_in_checklist])
                        f.write(f"- **{obs_date}**: 🎯 目标物种 ({len(target_species_in_checklist)}种): {species_list}")
                    else:
                        # 单物种或"任一物种"模式
                        for sp in target_species_in_checklist:
                            species_name = sp['name']
                            count = sp['count']
                            f.write(f"- **{obs_date}**: {species_name} - 观测数量: {count} 只")
                            break  # 只显示第一个

                    f.write(f", <button class='btn-view-checklist' data-subid='{sub_id}' onclick='viewChecklist(\"{sub_id}\")'>📋 查看 {sub_id} 清单</button>\n")

                    # 从缓存中获取该观测清单的详细信息
                    if sub_id in checklist_cache:
                        checklist = checklist_cache[sub_id]
                        if checklist and 'obs' in checklist:
                            total_species = len(checklist['obs'])
                            f.write(f"  - 📋 观测清单: 共记录 **{total_species} 种**鸟类\n")

                            # 找出伴生的目标鸟种（数据库中的其他鸟种）
                            # 排除当前查询的所有鸟种
                            target_codes_in_checklist = set([sp['code'] for sp in target_species_in_checklist])
                            companion_species = []
                            for checklist_obs in checklist['obs']:
                                obs_species_code = checklist_obs.get('speciesCode')
                                # 排除当前查询的鸟种，只显示其他目标鸟种
                                if (obs_species_code and
                                    obs_species_code not in target_codes_in_checklist and
                                    obs_species_code in code_to_full_name_map):
                                    names = code_to_full_name_map[obs_species_code]
                                    companion_species.append({
                                        'code': obs_species_code,
                                        'cn_name': names['cn_name'],
                                        'en_name': names['en_name'],
                                        'count': checklist_obs.get('howMany', 'X')
                                    })

                            if companion_species:
                                # 简洁格式：一行显示所有伴生鸟种，中英文名，用逗号分隔
                                species_names_list = [f"{comp['cn_name']}({comp['en_name']})" for comp in companion_species]
                                f.write(f"  - 🐦 伴生目标鸟种 ({len(companion_species)}种): {', '.join(species_names_list)}\n")

                f.write("\n")

            f.write("---\n\n")
            f.write(f"*报告由 慧眼找鸟 Web V{VERSION} 生成*\n")
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

        if not lat or not lng:
            return jsonify({'error': '请提供有效的 GPS 坐标'}), 400

        # 匿名用户限流和功能限制
        if is_anonymous_user():
            client_ip = request.remote_addr
            limit_status = rate_limiter.check_limit(client_ip)

            if not limit_status['allowed']:
                return jsonify({
                    'error': '⏱️ 访客模式已达使用上限',
                    'message': f'每小时限制{ANONYMOUS_LIMITS["hourly_limit"]}次，每天限制{ANONYMOUS_LIMITS["daily_limit"]}次。\n'
                              f'请注册免费的 eBird API Key 以解除限制。',
                    'limit_info': limit_status,
                    'register_url': 'https://ebird.org/api/keygen'
                }), 429

            # 功能限制检查
            if radius > ANONYMOUS_LIMITS['max_radius']:
                return jsonify({
                    'error': f'访客模式最大搜索半径为 {ANONYMOUS_LIMITS["max_radius"]} km',
                    'message': '请注册免费的 eBird API Key 以解除限制。'
                }), 400

            if days_back > ANONYMOUS_LIMITS['max_days']:
                return jsonify({
                    'error': f'访客模式最大查询天数为 {ANONYMOUS_LIMITS["max_days"]} 天',
                    'message': '请注册免费的 eBird API Key 以解除限制。'
                }), 400

            # 记录本次请求
            rate_limiter.record_request(client_ip)

        # 从请求头获取 API Key 并初始化客户端
        client = get_api_client_from_request()
        if not client:
            return jsonify({'error': 'API Key 未配置，请前往设置页面配置'}), 401

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
        api_key = get_api_key_from_request()
        user_output_dir = get_user_output_dir(api_key)

        # 清理旧报告（7天前的）
        clean_old_reports(user_output_dir, days=7)

        today_str = datetime.datetime.now().strftime("%Y-%m-%d")
        today_folder = os.path.join(user_output_dir, today_str)
        os.makedirs(today_folder, exist_ok=True)

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
        filename = f"WebRegion_{lat:.4f}_{lng:.4f}_{timestamp}.md"
        filepath = os.path.join(today_folder, filename)

        # 反向地理编码获取地名
        location_name = None
        try:
            import requests
            geocode_url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lng}&format=json"
            geocode_response = requests.get(geocode_url, headers={'User-Agent': 'TuiBirdTracker/1.0'}, timeout=5)
            if geocode_response.status_code == 200:
                geocode_data = geocode_response.json()
                address = geocode_data.get('address', {})
                # 尝试获取城市、镇或村
                location_name = (address.get('city') or
                               address.get('town') or
                               address.get('village') or
                               address.get('county') or
                               address.get('state'))
        except Exception as e:
            print(f"反向地理编码失败: {e}")

        # 写入报告
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f"# 🦅 鸟类区域查询报告 (Web版)\n\n")
            f.write(f"**生成时间:** {datetime.datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}\n")
            if location_name:
                f.write(f"**搜索位置:** {location_name} (GPS: {lat:.4f}, {lng:.4f})\n")
            else:
                f.write(f"**搜索位置:** GPS ({lat:.4f}, {lng:.4f})\n")
            f.write(f"**搜索半径:** {radius} km\n")
            f.write(f"**时间范围:** 最近 {days_back} 天\n\n")

            # 统计不同的清单数量
            unique_checklists = set()
            total_obs_count = 0
            for group in sorted_species:
                total_obs_count += len(group['observations'])
                for obs in group['observations']:
                    sub_id = obs.get('subId')
                    if sub_id:
                        unique_checklists.add(sub_id)

            f.write(f"**分析摘要:** 在指定范围内，共发现 **{len(sorted_species)}** 种目标鸟类，")
            f.write(f"来自 **{len(unique_checklists)}** 个观测清单，")
            f.write(f"共 **{total_obs_count}** 次观测记录。\n\n")

            f.write("---\n\n")
            f.write("## 📋 目标鸟种记录（按鸟种排序）\n\n")

            # 创建鸟种索引
            species_index = {}
            for i, group in enumerate(sorted_species, 1):
                species_code = group['species_code']
                cn_name = group['cn_name']
                en_name = group['en_name']
                obs_count = len(group['observations'])
                species_index[species_code] = {
                    'index': i,
                    'cn_name': cn_name,
                    'en_name': en_name,
                    'obs_count': obs_count
                }

            # 按清单分组所有观测记录
            checklist_groups = {}
            for group in sorted_species:
                for obs in group['observations']:
                    sub_id = obs.get('subId')
                    if sub_id:
                        if sub_id not in checklist_groups:
                            checklist_groups[sub_id] = {
                                'date': obs.get('obsDt', 'Unknown'),
                                'location': obs.get('locName', 'Unknown Location'),
                                'lat': obs.get('lat'),
                                'lng': obs.get('lng'),
                                'is_private': obs.get('locPrivate', False),
                                'species': []
                            }
                        checklist_groups[sub_id]['species'].append({
                            'code': group['species_code'],
                            'cn_name': group['cn_name'],
                            'en_name': group['en_name'],
                            'count': obs.get('howMany', 'X'),
                            'index': species_index[group['species_code']]['index']
                        })

            # 按时间排序清单
            sorted_checklists = sorted(checklist_groups.items(),
                                      key=lambda x: x[1]['date'],
                                      reverse=True)

            # 显示每个清单
            for sub_id, checklist_data in sorted_checklists:
                obs_date = checklist_data['date']
                location = checklist_data['location']
                lat_obs = checklist_data['lat']
                lng_obs = checklist_data['lng']
                is_private = checklist_data['is_private']
                species_list = checklist_data['species']

                # 生成地图链接
                if lat_obs and lng_obs:
                    maps_link = f"https://maps.google.com/?q={lat_obs},{lng_obs}"
                    location_link = f"[{location}]({maps_link})"
                else:
                    location_link = location

                location_type = "📍私人" if is_private else "🔥热点"

                # 按鸟种索引排序（保持原有的鸟种排序）
                species_list.sort(key=lambda x: x['index'])

                # 清单标题
                f.write(f"### 📋 {obs_date} - {location_link} {location_type}\n")
                f.write(f"**清单ID:** {sub_id} ")
                f.write(f"<button class='btn-view-checklist' data-subid='{sub_id}' onclick='viewChecklist(\"{sub_id}\")'>📋 查看完整清单</button>\n\n")
                f.write(f"**目标鸟种数:** {len(species_list)} 种\n\n")

                # 列出该清单中的所有目标鸟种
                for species in species_list:
                    f.write(f"- **No.{species['index']}** {species['cn_name']} ({species['en_name']}) - 观测数量: {species['count']} 只\n")

                f.write("\n")

            f.write("---\n\n")
            f.write(f"*报告由 慧眼找鸟 Web V{VERSION} 生成*\n")
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


@app.route('/api/validate-key', methods=['POST'])
def api_validate_key():
    """验证 API Key 是否有效（不保存）"""
    try:
        data = request.json
        api_key = data.get('api_key', '').strip()

        if not api_key:
            return jsonify({'valid': False, 'error': 'API Key 不能为空'}), 400

        # 创建临时客户端进行验证
        test_client = EBirdAPIClient(api_key)
        is_valid, message = test_client.validate_api_key()

        return jsonify({
            'valid': is_valid,
            'message': message if is_valid else None,
            'error': None if is_valid else message
        })

    except Exception as e:
        return jsonify({'valid': False, 'error': str(e)}), 500


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
        # 获取当前用户的专属目录
        api_key = get_api_key_from_request()
        user_output_dir = get_user_output_dir(api_key)

        # 仅访问用户专属目录
        report_file = os.path.join(user_output_dir, report_path)

        # 安全检查：确保在用户目录内
        report_file_real = os.path.realpath(report_file)
        user_output_dir_real = os.path.realpath(user_output_dir)
        if not report_file_real.startswith(user_output_dir_real):
            return jsonify({'error': '非法访问路径'}), 403

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


@app.route('/api/usage-status')
def api_usage_status():
    """获取当前用户的使用状态（匿名用户专用）"""
    if not is_anonymous_user():
        return jsonify({
            'is_anonymous': False,
            'message': '您正在使用自己的 API Key，无使用限制'
        })

    client_ip = request.remote_addr
    limit_status = rate_limiter.check_limit(client_ip)

    return jsonify({
        'is_anonymous': True,
        'limits': ANONYMOUS_LIMITS,
        'usage': {
            'hourly_remaining': limit_status['hourly_remaining'],
            'daily_remaining': limit_status['daily_remaining'],
            'hourly_used': limit_status['hourly_count'],
            'daily_used': limit_status['daily_count']
        },
        'register_url': 'https://ebird.org/api/keygen'
    })


@app.route('/api/geocode', methods=['POST'])
def api_geocode():
    """将地点名称转换为GPS坐标"""
    try:
        data = request.json
        place_name = data.get('place_name', '').strip()

        if not place_name:
            return jsonify({'error': '地点名称不能为空'}), 400

        # 使用 Nominatim 地理编码服务
        geolocator = get_geolocator()

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


@app.route('/api/checklist/<sub_id>')
def api_get_checklist(sub_id):
    """获取观测清单详情（中文格式，带缓存）"""
    try:
        # 检查缓存
        cache_key = f'checklist:{sub_id}'
        cached_data = api_cache.get(cache_key)
        if cached_data:
            return jsonify(cached_data)

        # 从请求头获取 API Key 并初始化客户端
        client = get_api_client_from_request()
        if not client:
            return jsonify({'error': 'API Key 未配置，请前往设置页面配置'}), 401

        # 获取清单详情
        checklist = client.get_checklist_details(sub_id)

        if not checklist:
            return jsonify({'error': '无法获取清单详情'}), 404

        # 获取物种名称映射
        db = init_database()
        code_to_full_name_map = db.get_code_to_full_name_map()

        # 提取清单信息
        # eBird API 的 checklist view 接口返回字段：
        # - locName: 地点名称（字符串）
        # - obsDt: 观测日期时间
        # - numSpecies: 物种数量
        # - obs: 观测记录数组
        loc_name = checklist.get('locName', '未知地点')
        obs_date = checklist.get('obsDt', '未知日期')
        num_species = checklist.get('numSpecies', 0)

        # 处理观测记录
        observations = []
        if 'obs' in checklist:
            for obs in checklist['obs']:
                species_code = obs.get('speciesCode')

                # 获取中英文名
                cn_name = '未知物种'
                en_name = obs.get('comName', species_code)

                if species_code and species_code in code_to_full_name_map:
                    names = code_to_full_name_map[species_code]
                    cn_name = names['cn_name']
                    if names['en_name']:
                        en_name = names['en_name']

                observations.append({
                    'code': species_code,
                    'cn_name': cn_name,
                    'en_name': en_name,
                    'count': obs.get('howManyStr', 'X')
                })

        response_data = {
            'success': True,
            'sub_id': sub_id,
            'location': loc_name,
            'date': obs_date,
            'num_species': num_species,
            'observations': observations
        }

        # 缓存结果
        api_cache.set(cache_key, response_data)

        return jsonify(response_data)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/hotspot-observations/<loc_id>')
def api_get_hotspot_observations(loc_id):
    """获取热点的最近观测记录"""
    try:
        # 获取参数
        days = request.args.get('days', 14, type=int)

        if not loc_id:
            return jsonify({'error': '缺少热点ID'}), 400

        # 从请求头获取 API Key 并初始化客户端
        client = get_api_client_from_request()
        if not client:
            return jsonify({'error': 'API Key 未配置，请前往设置页面配置'}), 401

        db = init_database()

        # 调用 eBird API 获取该热点的最近观测记录
        observations = client.get_hotspot_observations(
            location_id=loc_id,
            days_back=days
        )

        if not observations:
            return jsonify({
                'success': True,
                'observations': [],
                'loc_id': loc_id
            })

        # 获取物种名称映射
        code_to_full_name_map = db.get_code_to_full_name_map()

        # 处理观测记录，按物种去重（取最近的一次观测）
        species_dict = {}
        for obs in observations:
            species_code = obs.get('speciesCode')
            if not species_code:
                continue

            # 如果该物种还没有记录，或者当前观测更新，则更新
            if species_code not in species_dict:
                species_dict[species_code] = obs

        # 格式化输出
        formatted_obs = []
        for species_code, obs in species_dict.items():
            # 获取中英文名
            com_name = obs.get('comName', species_code)
            cn_name = None

            if species_code in code_to_full_name_map:
                names = code_to_full_name_map[species_code]
                cn_name = names['cn_name']
                if names['en_name']:
                    com_name = names['en_name']

            formatted_obs.append({
                'speciesCode': species_code,
                'comName': com_name,
                'cnName': cn_name,
                'obsDt': obs.get('obsDt', ''),
                'howMany': obs.get('howMany', 'X'),
                'locName': obs.get('locName', '')
            })

        # 按中文名排序（如果有的话）
        formatted_obs.sort(key=lambda x: x['cnName'] or x['comName'])

        return jsonify({
            'success': True,
            'observations': formatted_obs,
            'loc_id': loc_id,
            'total_species': len(formatted_obs)
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/route-result/<path:result_path>')
def view_route_result(result_path):
    """查看路线热点结果（带路径安全检查）"""
    try:
        # 使用用户专属目录（而非全局 output 目录）
        api_key = get_api_key_from_request()
        user_output_dir = get_user_output_dir(api_key)
        file_path = os.path.join(user_output_dir, result_path)

        # 安全检查：防止路径遍历攻击
        file_path_real = os.path.realpath(file_path)
        user_output_dir_real = os.path.realpath(user_output_dir)
        if not file_path_real.startswith(user_output_dir_real):
            return render_template('error.html',
                                 error_message='非法访问路径',
                                 version=VERSION), 403

        if not os.path.exists(file_path):
            return render_template('error.html',
                                 error_message='路线结果文件不存在',
                                 version=VERSION), 404

        # 读取 JSON 文件
        with open(file_path, 'r', encoding='utf-8') as f:
            result_data = json.load(f)

        query = result_data.get('query', {})
        summary = result_data.get('summary', {})
        hotspots = result_data.get('hotspots', [])

        # 提取简短地名
        start_loc = query.get('start_location', '起点')
        end_loc = query.get('end_location', '终点')
        start_short = start_loc.split(',')[0].strip() if ',' in start_loc else start_loc
        end_short = end_loc.split(',')[0].strip() if ',' in end_loc else end_loc

        return render_template('route_result.html',
                             version=VERSION,
                             result_data=result_data,
                             query=query,
                             summary=summary,
                             hotspots=hotspots,
                             start_location=start_short,
                             end_location=end_short,
                             result_path=result_path)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return f'<h1>错误</h1><p>读取路线结果失败: {str(e)}</p><a href="/reports">返回历史报告</a>', 500


@app.route('/api/route-result/<path:result_path>')
def api_get_route_result(result_path):
    """获取路线热点结果（带路径安全检查）"""
    try:
        # 使用用户专属目录
        api_key = get_api_key_from_request()
        user_output_dir = get_user_output_dir(api_key)
        file_path = os.path.join(user_output_dir, result_path)

        # 安全检查：防止路径遍历攻击
        file_path_real = os.path.realpath(file_path)
        user_output_dir_real = os.path.realpath(user_output_dir)
        if not file_path_real.startswith(user_output_dir_real):
            return jsonify({'error': '非法访问路径'}), 403

        if not os.path.exists(file_path):
            return jsonify({'error': '文件不存在'}), 404

        # 读取 JSON 文件
        with open(file_path, 'r', encoding='utf-8') as f:
            result_data = json.load(f)

        return jsonify({
            'success': True,
            'result': result_data,
            'filename': os.path.basename(result_path)
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/bird-info/<bird_name>')
def api_get_bird_info(bird_name):
    """获取鸟类详细信息（带缓存）"""
    try:
        # 检查缓存
        cache_key = f'bird_info:{bird_name}'
        cached_data = api_cache.get(cache_key)
        if cached_data:
            return jsonify(cached_data)

        db = init_database()
        if not db:
            return jsonify({'error': '数据库未初始化'}), 500

        # 查询鸟类信息
        import sqlite3
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                chinese_simplified,
                english_name,
                scientific_name,
                short_description_zh,
                full_description_zh,
                dongniaourl
            FROM BirdCountInfo
            WHERE chinese_simplified = ? OR english_name = ?
        """, (bird_name, bird_name))

        result = cursor.fetchone()
        conn.close()

        if result:
            response_data = {
                'success': True,
                'bird_info': {
                    'chinese_name': result[0],
                    'english_name': result[1],
                    'scientific_name': result[2],
                    'short_description': result[3],
                    'full_description': result[4],
                    'dongniao_url': result[5]
                }
            }
            # 缓存结果
            api_cache.set(cache_key, response_data)
            return jsonify(response_data)
        else:
            response_data = {
                'success': False,
                'message': '未找到该鸟种信息'
            }
            # 也缓存"未找到"的结果，避免重复查询
            api_cache.set(cache_key, response_data)
            return jsonify(response_data)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/countries')
def api_get_countries():
    """获取所有国家列表（用于下拉选择）"""
    try:
        import sqlite3
        db_path = os.path.join(os.path.dirname(__file__), '..', 'ebird_reference.sqlite')

        if not os.path.exists(db_path):
            return jsonify({'error': '特有种数据库未找到'}), 404

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 只返回已验证的国家，按特有种数量排序
        cursor.execute("""
            SELECT country_id, country_name_cn, country_name_en, endemic_count, region
            FROM countries
            WHERE verified = 1
            ORDER BY endemic_count DESC
        """)

        countries = []
        for row in cursor.fetchall():
            countries.append({
                'country_id': row[0],
                'country_name_cn': row[1],
                'country_name_en': row[2],
                'endemic_count': row[3],
                'region': row[4]
            })

        conn.close()

        return jsonify({
            'success': True,
            'countries': countries,
            'total': len(countries)
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/endemic/top-countries')
def api_get_top_endemic_countries():
    """获取特有鸟种最多的前10个国家"""
    try:
        import sqlite3

        db_path = os.path.join(os.path.dirname(__file__), '..', 'ebird_reference.sqlite')

        if not os.path.exists(db_path):
            return jsonify({'error': '数据库未找到'}), 404

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 查询特有种最多的前10个国家
        cursor.execute("""
            SELECT
                c.country_code,
                c.country_name_en,
                c.country_name_zh,
                COUNT(eb.id) as endemic_count
            FROM countries c
            LEFT JOIN endemic_birds eb ON c.country_id = eb.country_id
            GROUP BY c.country_id
            HAVING endemic_count > 0
            ORDER BY endemic_count DESC
            LIMIT 10
        """)

        countries = []
        for row in cursor.fetchall():
            code, name_en, name_zh, count = row
            countries.append({
                'country_code': code,
                'country_name_en': name_en,
                'country_name_zh': name_zh if name_zh else name_en,
                'endemic_count': count
            })

        conn.close()

        return jsonify({
            'success': True,
            'countries': countries
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/endemic-birds/<country_name>')
def api_get_endemic_birds(country_name):
    """获取某个国家的特有鸟种列表"""
    try:
        import sqlite3

        # 数据库路径
        db_path = os.path.join(os.path.dirname(__file__), '..', 'ebird_reference.sqlite')

        if not os.path.exists(db_path):
            return jsonify({'error': '特有种数据库未找到'}), 404

        # 连接数据库
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 查询国家信息（支持中英文和国家代码）
        cursor.execute("""
            SELECT country_id, country_code, country_name_en, country_name_zh
            FROM countries
            WHERE country_name_zh LIKE ?
               OR country_name_en LIKE ?
               OR country_code LIKE ?
        """, (f"%{country_name}%", f"%{country_name}%", f"%{country_name}%"))

        country = cursor.fetchone()

        if not country:
            conn.close()
            return jsonify({'error': f'未找到国家: {country_name}'}), 404

        country_id, country_code, name_en, name_zh = country

        # 直接查询 endemic_birds 表
        cursor.execute("""
            SELECT
                id,
                scientific_name,
                name_zh,
                name_en
            FROM endemic_birds
            WHERE country_id = ?
            ORDER BY scientific_name
        """, (country_id,))

        # 构建鸟种信息列表
        endemic_birds = []
        for row in cursor.fetchall():
            bird_id, scientific_name, chinese_name, english_name = row

            # 如果仍然缺少中文名或英文名，使用学名作为回退
            display_cn = chinese_name if chinese_name else scientific_name
            display_en = english_name if english_name else scientific_name

            endemic_birds.append({
                'bird_id': bird_id,
                'sci_name': scientific_name,
                'cn_name': display_cn,
                'en_name': display_en
            })

        conn.close()

        return jsonify({
            'success': True,
            'country': {
                'country_code': country_code,
                'country_name_en': name_en,
                'country_name_zh': name_zh if name_zh else name_en,
                'endemic_count': len(endemic_birds)
            },
            'birds': endemic_birds,
            'total_species': len(endemic_birds)
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/ebird/countries')
def api_get_ebird_countries():
    """获取所有 eBird 国家列表"""
    try:
        import sqlite3

        db_path = os.path.join(os.path.dirname(__file__), '..', 'ebird_reference.sqlite')

        if not os.path.exists(db_path):
            return jsonify({'error': '数据库未找到'}), 404

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 查询所有国家，按名称排序
        cursor.execute("""
            SELECT country_code, country_name_en, country_name_zh,
                   has_regions, regions_count
            FROM ebird_countries
            ORDER BY country_name_en
        """)

        countries = []
        for row in cursor.fetchall():
            code, name_en, name_zh, has_regions, regions_count = row
            countries.append({
                'code': code,
                'name_en': name_en,
                'name_zh': name_zh,
                'has_regions': bool(has_regions),
                'regions_count': regions_count
            })

        conn.close()

        return jsonify({
            'success': True,
            'countries': countries,
            'total': len(countries)
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/ebird/regions/<country_code>')
def api_get_ebird_regions(country_code):
    """获取指定国家的区域列表"""
    try:
        import sqlite3

        db_path = os.path.join(os.path.dirname(__file__), '..', 'ebird_reference.sqlite')

        if not os.path.exists(db_path):
            return jsonify({'error': '数据库未找到'}), 404

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 查询该国家的所有区域
        cursor.execute("""
            SELECT er.region_code, er.region_name_en, er.region_name_zh
            FROM ebird_regions er
            JOIN ebird_countries ec ON er.country_id = ec.id
            WHERE ec.country_code = ?
            ORDER BY er.region_name_en
        """, (country_code,))

        regions = []
        for row in cursor.fetchall():
            region_code, region_name_en, region_name_zh = row
            regions.append({
                'code': region_code,
                'name_en': region_name_en,
                'name_zh': region_name_zh
            })

        conn.close()

        return jsonify({
            'success': True,
            'country_code': country_code,
            'regions': regions,
            'total': len(regions)
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/route-hotspots', methods=['POST'])
def api_route_hotspots():
    """搜索路线沿途的eBird热点"""
    try:
        data = request.json
        start_lat = float(data.get('start_lat'))
        start_lng = float(data.get('start_lng'))
        end_lat = float(data.get('end_lat'))
        end_lng = float(data.get('end_lng'))
        search_radius = int(data.get('search_radius', 5))
        days_back = int(data.get('days_back', 14))

        if not all([start_lat, start_lng, end_lat, end_lng]):
            return jsonify({'error': '缺少必要的坐标参数'}), 400

        # 从请求头获取 API Key 并初始化客户端
        api_client = get_api_client_from_request()
        if not api_client:
            return jsonify({'error': 'API Key 未配置，请前往设置页面配置'}), 401

        import math
        import requests as req

        print(f"\n========== 路线热点搜索 ==========")
        print(f"起点: ({start_lat}, {start_lng})")
        print(f"终点: ({end_lat}, {end_lng})")
        print(f"搜索半径: {search_radius} km")

        # 计算两点距离（粗略估算）
        def haversine_distance(lat1, lon1, lat2, lon2):
            R = 6371  # 地球半径（公里）
            dlat = math.radians(lat2 - lat1)
            dlon = math.radians(lon2 - lon1)
            a = (math.sin(dlat/2)**2 +
                 math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
                 math.sin(dlon/2)**2)
            c = 2 * math.asin(math.sqrt(a))
            return R * c

        # 获取驾车路线（使用 OSRM 免费API - 无需API key）
        route_coords = []
        route_distance_km = 0

        try:
            # OSRM API（完全免费，无需注册）
            # 格式: /route/v1/driving/{lon},{lat};{lon},{lat}
            osrm_url = f"https://router.project-osrm.org/route/v1/driving/{start_lng},{start_lat};{end_lng},{end_lat}"

            params = {
                'overview': 'full',  # 返回完整路线
                'geometries': 'geojson'  # GeoJSON格式
            }

            print(f"正在请求OSRM路线...")
            response = req.get(osrm_url, params=params, timeout=15)

            if response.status_code == 200:
                route_data = response.json()

                if route_data.get('code') == 'Ok' and 'routes' in route_data and len(route_data['routes']) > 0:
                    route = route_data['routes'][0]
                    geometry = route['geometry']

                    if geometry['type'] == 'LineString':
                        # 转换为 [lat, lng] 格式（OSRM返回[lng, lat]）
                        route_coords = [[coord[1], coord[0]] for coord in geometry['coordinates']]

                        # 获取路线距离（米转公里）
                        route_distance_km = route['distance'] / 1000
                        print(f"✓ 成功获取OSRM驾车路线: {route_distance_km:.1f} km，{len(route_coords)} 个路点")
                else:
                    print(f"OSRM响应异常: {route_data.get('code', 'Unknown')}")
            else:
                print(f"OSRM API请求失败: HTTP {response.status_code}")

        except Exception as e:
            print(f"获取驾车路线失败: {e}")
            import traceback
            traceback.print_exc()

        # 如果无法获取驾车路线，使用直线作为后备
        if not route_coords:
            print("使用直线路线作为后备")
            route_coords = [[start_lat, start_lng], [end_lat, end_lng]]
            route_distance_km = haversine_distance(start_lat, start_lng, end_lat, end_lng)

        # 沿路线采样点（每20公里一个点，或每50个坐标点选一个）
        sample_points = []
        if len(route_coords) > 50:
            # 路线点很多，按间隔采样
            step = len(route_coords) // min(20, len(route_coords) // 2)
            sample_points = [(route_coords[i][0], route_coords[i][1])
                           for i in range(0, len(route_coords), max(1, step))]
        else:
            # 路线点较少，全部使用
            sample_points = [(coord[0], coord[1]) for coord in route_coords]

        # 确保起点和终点都包含
        if sample_points[0] != (start_lat, start_lng):
            sample_points.insert(0, (start_lat, start_lng))
        if sample_points[-1] != (end_lat, end_lng):
            sample_points.append((end_lat, end_lng))

        # 在每个采样点附近搜索热点
        all_hotspots = {}  # 使用字典去重（按locId）

        for lat, lng in sample_points:
            try:
                hotspots = api_client.get_nearby_hotspots(
                    lat=lat,
                    lng=lng,
                    dist=search_radius,
                    back=days_back
                )

                if hotspots:
                    for hotspot in hotspots:
                        loc_id = hotspot.get('locId')
                        if loc_id and loc_id not in all_hotspots:
                            all_hotspots[loc_id] = hotspot

            except Exception as e:
                print(f"搜索点 ({lat}, {lng}) 附近热点失败: {e}")
                continue

        # 按最近观测时间排序
        hotspots_list = sorted(
            all_hotspots.values(),
            key=lambda x: x.get('latestObsDt', ''),
            reverse=True
        )

        # 反向地理编码获取地点名称
        geolocator = get_geolocator()
        start_location = None
        end_location = None

        try:
            start_loc = geolocator.reverse(f"{start_lat}, {start_lng}", timeout=5, language='zh')
            if start_loc:
                start_location = start_loc.address
        except:
            pass

        try:
            end_loc = geolocator.reverse(f"{end_lat}, {end_lng}", timeout=5, language='zh')
            if end_loc:
                end_location = end_loc.address
        except:
            pass

        # 保存路线热点搜索结果
        import datetime as dt
        import json

        # 获取当前用户的专属目录
        api_key = get_api_key_from_request()
        user_output_dir = get_user_output_dir(api_key)

        # 清理旧报告（7天前的）
        clean_old_reports(user_output_dir, days=7)

        today_str = dt.datetime.now().strftime("%Y-%m-%d")
        today_folder = os.path.join(user_output_dir, today_str)
        os.makedirs(today_folder, exist_ok=True)

        timestamp = dt.datetime.now().strftime('%Y%m%d_%H%M%S')
        result_filename = f"route_{timestamp}.json"
        result_path = os.path.join(today_folder, result_filename)

        # 准备保存的数据（包含完整信息）
        saved_data = {
            'type': 'route_hotspots',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'query': {
                'start_lat': start_lat,
                'start_lng': start_lng,
                'end_lat': end_lat,
                'end_lng': end_lng,
                'start_location': start_location or f"({start_lat}, {start_lng})",
                'end_location': end_location or f"({end_lat}, {end_lng})",
                'search_radius': search_radius,
                'days_back': days_back
            },
            'route': {
                'distance_km': round(route_distance_km, 1),
                'coords': route_coords
            },
            'hotspots': hotspots_list,
            'summary': {
                'hotspots_count': len(hotspots_list),
                'route_distance_km': round(route_distance_km, 1)
            }
        }

        try:
            with open(result_path, 'w', encoding='utf-8') as f:
                json.dump(saved_data, f, ensure_ascii=False, indent=2)
            print(f"✓ 路线热点搜索结果已保存: {result_filename}")
        except Exception as e:
            print(f"保存路线热点搜索结果失败: {e}")

        return jsonify({
            'success': True,
            'start_location': start_location,
            'end_location': end_location,
            'search_radius': search_radius,
            'route_distance_km': round(route_distance_km, 1),
            'route_coords': route_coords,  # 完整的驾车路线坐标
            'sample_points_count': len(sample_points),
            'hotspots_count': len(hotspots_list),
            'hotspots': hotspots_list[:50],  # 限制返回数量
            'result_file': result_filename,  # 添加保存的文件名
            'message': f'沿 {route_distance_km:.1f}km 驾车路线找到 {len(hotspots_list)} 个活跃热点'
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    # 生产环境会使用 gunicorn，这里仅用于本地开发
    PORT = int(os.environ.get('PORT', 5001))  # 支持 Render 的 PORT 环境变量
    DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'  # 默认关闭调试模式,仅开发环境启用

    print("=" * 60)
    print(f"🦅 慧眼找鸟 Web App V{VERSION}")
    print("=" * 60)
    print(f"🌐 启动 Web 服务器...")
    print(f"📍 访问地址: http://127.0.0.1:{PORT}")
    print(f"🔑 按 Ctrl+C 停止服务器")
    print("=" * 60)

    app.run(host='0.0.0.0', port=PORT, debug=DEBUG)
