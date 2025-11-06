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
import threading

# 加载环境变量
from dotenv import load_dotenv
load_dotenv()

# 导入现有模块
from config import VERSION, BUILD_DATE, ConfigManager, DB_FILE, AUSTRALIA_STATES, get_resource_path
from database import BirdDatabase
from api_client import EBirdAPIClient, get_api_key_with_validation
from endemic_utils import generate_endemic_badge

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
endemic_birds_map = None  # 特有种缓存字典 {scientific_name: [endemic_info, ...]}

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
    """
    API 响应缓存（内存缓存 + TTL + 自动清理，线程安全）

    性能优化：
    1. LRU（Least Recently Used）淘汰策略
    2. 自动后台清理过期缓存，减少内存占用
    3. 线程安全设计，支持并发访问
    """

    def __init__(self, ttl=300, max_size=1000, cleanup_interval=60):
        """
        初始化缓存

        Args:
            ttl: 缓存有效期（秒），默认5分钟
            max_size: 最大缓存条目数，默认1000条
            cleanup_interval: 自动清理间隔（秒），默认60秒
        """
        import threading
        from collections import OrderedDict
        self.cache = OrderedDict()  # 保持插入顺序，支持LRU
        self.ttl = ttl
        self.max_size = max_size
        self.cleanup_interval = cleanup_interval
        self._lock = threading.RLock()  # 可重入锁
        self._shutdown = False

        # 启动后台自动清理线程
        self._cleanup_thread = threading.Thread(target=self._background_cleanup, daemon=True)
        self._cleanup_thread.start()

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

            if expired_keys:
                print(f"API缓存自动清理: 删除了 {len(expired_keys)} 个过期条目，当前缓存数: {len(self.cache)}")

    def _background_cleanup(self):
        """后台定期清理过期缓存"""
        import time
        while not self._shutdown:
            time.sleep(self.cleanup_interval)
            self.cleanup()

    def shutdown(self):
        """关闭缓存，停止后台清理线程"""
        self._shutdown = True
        print("API缓存已关闭")


# 创建全局 API 缓存实例
api_cache = APICache(ttl=300)  # 5分钟缓存


class GeocodeCache:
    """
    持久化的地理编码LRU缓存

    特点：
    1. LRU (Least Recently Used) 淘汰策略
    2. 持久化到本地文件，应用重启后缓存依然有效
    3. 线程安全，支持并发访问
    4. 定期后台保存，减少I/O开销

    性能提升：
    - 避免对相同地点的重复 Nominatim API 调用
    - Nominatim 限流：1次/秒，缓存可大幅减少等待时间
    """

    def __init__(self, cache_file='data/geocode_cache.json', max_size=1000, save_interval=60):
        """
        初始化地理编码缓存

        Args:
            cache_file: 缓存文件路径
            max_size: 最大缓存条目数（LRU淘汰）
            save_interval: 后台保存间隔（秒）
        """
        from config import get_resource_path
        self.cache_file = get_resource_path(cache_file)
        self.max_size = max_size
        self.save_interval = save_interval

        # 使用 OrderedDict 实现 LRU
        from collections import OrderedDict
        self.cache = OrderedDict()

        self._lock = threading.Lock()
        self._dirty = False
        self._shutdown = False

        # 启动时加载缓存
        self._load_from_file()

        # 启动后台保存线程
        self._save_thread = threading.Thread(target=self._background_saver, daemon=True)
        self._save_thread.start()

    def _normalize_place_name(self, place_name):
        """标准化地点名称，用作缓存键"""
        return place_name.strip().lower()

    def _load_from_file(self):
        """从文件加载缓存"""
        if not os.path.exists(self.cache_file):
            return

        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            from collections import OrderedDict
            # 恢复 LRU 顺序（最近使用的在最后）
            self.cache = OrderedDict(data.get('cache', {}))
            print(f"地理编码缓存已加载: {len(self.cache)} 条记录")
        except Exception as e:
            print(f"加载地理编码缓存失败: {e}")
            from collections import OrderedDict
            self.cache = OrderedDict()

    def _save_to_file(self):
        """保存缓存到文件"""
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)

            # 写入临时文件，然后原子性替换（避免写入中断导致文件损坏）
            temp_file = self.cache_file + '.tmp'
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'cache': dict(self.cache),
                    'last_updated': time.time()
                }, f, ensure_ascii=False, indent=2)

            # 原子性替换
            os.replace(temp_file, self.cache_file)
        except Exception as e:
            print(f"保存地理编码缓存失败: {e}")

    def _background_saver(self):
        """后台定期保存线程"""
        while not self._shutdown:
            time.sleep(self.save_interval)
            if self._dirty:
                with self._lock:
                    self._save_to_file()
                    self._dirty = False

    def get(self, place_name, country_code=None):
        """
        获取缓存的地理编码结果

        Args:
            place_name: 地点名称
            country_code: 国家代码（如 'au'）

        Returns:
            dict: 缓存的结果，包含 latitude, longitude, display_name
            None: 缓存未命中
        """
        cache_key = self._normalize_place_name(place_name)
        if country_code:
            cache_key = f"{country_code}:{cache_key}"

        with self._lock:
            if cache_key in self.cache:
                # 移到末尾（标记为最近使用）
                self.cache.move_to_end(cache_key)
                result = self.cache[cache_key]
                print(f"地理编码缓存命中: {place_name}")
                return result

        return None

    def set(self, place_name, result, country_code=None):
        """
        设置地理编码缓存

        Args:
            place_name: 地点名称
            result: 地理编码结果字典
            country_code: 国家代码（如 'au'）
        """
        cache_key = self._normalize_place_name(place_name)
        if country_code:
            cache_key = f"{country_code}:{cache_key}"

        with self._lock:
            # 如果已存在，先移除（会重新添加到末尾）
            if cache_key in self.cache:
                del self.cache[cache_key]

            # 添加到末尾（最近使用）
            self.cache[cache_key] = result

            # LRU 淘汰：如果超过最大容量，移除最旧的（第一个）
            while len(self.cache) > self.max_size:
                oldest_key = next(iter(self.cache))
                del self.cache[oldest_key]
                print(f"地理编码缓存淘汰: {oldest_key}")

            self._dirty = True

    def shutdown(self):
        """关闭缓存，保存到文件"""
        self._shutdown = True
        if self._dirty:
            with self._lock:
                self._save_to_file()
        print("地理编码缓存已保存")


# 创建全局地理编码缓存实例
geocode_cache = GeocodeCache(max_size=1000, save_interval=60)

# 创建全局 Geolocator 实例（避免频繁初始化导致限流）
_geolocator = None

def get_geolocator():
    """获取全局 Geolocator 单例"""
    global _geolocator
    if _geolocator is None:
        # 使用更详细的 user_agent,符合 OpenStreetMap 使用政策
        # 添加超时设置和重试机制,提高在云环境(如 Render)中的连接成功率
        from geopy.adapters import RequestsAdapter
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        # 配置重试策略
        retry_strategy = Retry(
            total=3,  # 总共重试3次
            backoff_factor=1,  # 重试间隔: 1s, 2s, 4s
            status_forcelist=[429, 500, 502, 503, 504],  # 这些状态码会触发重试
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST"]  # 允许重试的HTTP方法
        )

        # 创建自定义适配器工厂
        def adapter_factory(proxies=None, ssl_context=None):
            adapter = RequestsAdapter(proxies=proxies, ssl_context=ssl_context)
            # 为 HTTP 和 HTTPS 设置重试策略
            http_adapter = HTTPAdapter(max_retries=retry_strategy)
            adapter.session.mount("http://", http_adapter)
            adapter.session.mount("https://", http_adapter)
            return adapter

        _geolocator = Nominatim(
            user_agent="TuiBird_Tracker/1.0 (https://github.com/jameszhenyu/tuibird-tracker; tuibird@example.com)",
            adapter_factory=adapter_factory,
            timeout=15
        )
    return _geolocator


class RateLimiter:
    """
    优化的速率限制器（内存缓存 + 后台持久化）

    性能优化：
    1. 内存存储：所有查询和写入都在内存中完成 O(1)
    2. 后台持久化：每30秒自动保存一次到文件
    3. 懒惰清理：查询时顺便清理过期记录
    4. 启动加载：从文件恢复之前的限流状态

    原时间复杂度：O(n) 每次请求读写文件
    优化后：O(1) 内存操作，定期批量写入
    """

    def __init__(self, save_interval=30):
        """
        初始化限流器

        :param save_interval: 自动保存间隔（秒），默认30秒
        """
        import threading
        from collections import defaultdict

        self.storage_file = get_resource_path('rate_limit.json')
        self.save_interval = save_interval
        self._lock = threading.RLock()  # 递归锁，支持嵌套调用
        self._dirty = False  # 标记是否有未保存的更改
        self._shutdown = False  # 停止标志

        # 使用 defaultdict 简化代码
        self.data = defaultdict(lambda: {'requests': []})

        # 启动时加载已有数据
        self._load_data_on_startup()

        # 启动后台保存线程
        self._save_thread = threading.Thread(target=self._background_saver, daemon=True)
        self._save_thread.start()

        print(f"✓ RateLimiter 已启动（内存缓存模式，每{save_interval}秒自动保存）")

    def _load_data_on_startup(self):
        """启动时从文件加载数据"""
        if not os.path.exists(self.storage_file):
            print("✓ RateLimiter: 未找到已有限流数据，从空白开始")
            return

        try:
            with open(self.storage_file, 'r') as f:
                loaded_data = json.load(f)

            # 转换为 defaultdict 并清理过期数据
            now = time.time()
            for ip, records in loaded_data.items():
                # 只保留24小时内的记录
                valid_requests = [r for r in records.get('requests', [])
                                 if now - r < 86400]
                if valid_requests:
                    self.data[ip] = {'requests': valid_requests}

            print(f"✓ RateLimiter: 已加载 {len(self.data)} 个IP的限流记录")
        except Exception as e:
            print(f"⚠ RateLimiter: 加载数据失败: {e}，从空白开始")

    def _background_saver(self):
        """后台线程：定期保存数据到文件"""
        while not self._shutdown:
            time.sleep(self.save_interval)

            if self._dirty:
                self._save_to_file()
                self._dirty = False

    def _save_to_file(self):
        """保存数据到文件（原子写入）"""
        with self._lock:
            try:
                # 转换 defaultdict 为普通 dict（用于 JSON 序列化）
                data_to_save = dict(self.data)

                # 使用临时文件 + 原子替换
                temp_file = self.storage_file + '.tmp'
                with open(temp_file, 'w') as f:
                    json.dump(data_to_save, f)
                    f.flush()
                    os.fsync(f.fileno())

                os.replace(temp_file, self.storage_file)

            except Exception as e:
                print(f"⚠ RateLimiter: 保存失败: {e}")
                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except:
                        pass

    def _clean_expired_requests(self, ip_address):
        """懒惰清理：查询时顺便清理该IP的过期记录"""
        now = time.time()
        day_ago = now - 86400

        # 过滤掉超过24小时的记录
        requests = self.data[ip_address]['requests']
        valid_requests = [r for r in requests if r > day_ago]

        if len(valid_requests) < len(requests):
            self.data[ip_address]['requests'] = valid_requests
            self._dirty = True

    def check_limit(self, ip_address):
        """
        检查IP是否超过限制（O(1) 内存查询）

        :param ip_address: IP地址
        :return: 限制状态字典
        """
        with self._lock:
            # 懒惰清理过期记录
            self._clean_expired_requests(ip_address)

            now = time.time()
            requests = self.data[ip_address]['requests']

            # 计算小时和日限制
            hour_ago = now - 3600
            hourly_count = sum(1 for r in requests if r > hour_ago)
            daily_count = len(requests)  # 已经清理过期，剩下的都是24小时内的

            return {
                'allowed': (hourly_count < ANONYMOUS_LIMITS['hourly_limit'] and
                           daily_count < ANONYMOUS_LIMITS['daily_limit']),
                'hourly_remaining': max(0, ANONYMOUS_LIMITS['hourly_limit'] - hourly_count),
                'daily_remaining': max(0, ANONYMOUS_LIMITS['daily_limit'] - daily_count),
                'hourly_count': hourly_count,
                'daily_count': daily_count
            }

    def record_request(self, ip_address):
        """
        记录一次请求（O(1) 内存写入）

        :param ip_address: IP地址
        """
        with self._lock:
            self.data[ip_address]['requests'].append(time.time())
            self._dirty = True  # 标记为需要保存

    def force_save(self):
        """强制立即保存（用于应用关闭时）"""
        if self._dirty:
            print("正在保存限流数据...")
            self._save_to_file()
            self._dirty = False
            print("✓ 限流数据已保存")

    def shutdown(self):
        """优雅关闭：保存数据并停止后台线程"""
        self._shutdown = True
        self.force_save()
        if self._save_thread.is_alive():
            self._save_thread.join(timeout=2)


# 全局限流器实例
rate_limiter = RateLimiter()


def init_database():
    """初始化数据库"""
    global bird_db, endemic_birds_map
    if bird_db is None:
        bird_db = BirdDatabase(DB_FILE)
        bird_db.load_all_birds()

        # 加载特有种缓存到内存（用于快速查询）
        if endemic_birds_map is None:
            endemic_birds_map = bird_db.load_endemic_birds_map()

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

    性能优化：使用 os.scandir() 替代 os.walk() + os.path.join()
    - os.scandir() 返回 DirEntry 对象，直接提供 stat 信息，无需额外系统调用
    - 对于大量文件，性能提升 2-3 倍
    """
    import time
    cutoff_time = time.time() - (days * 24 * 60 * 60)

    if not os.path.exists(user_output_dir):
        return 0

    deleted_count = 0

    def _clean_directory_recursive(dir_path):
        """递归清理目录（使用 os.scandir）"""
        nonlocal deleted_count

        try:
            with os.scandir(dir_path) as entries:
                subdirs = []  # 收集子目录，稍后递归处理

                for entry in entries:
                    try:
                        if entry.is_file(follow_symlinks=False):
                            # 文件：检查修改时间，删除旧文件
                            stat_info = entry.stat(follow_symlinks=False)
                            if stat_info.st_mtime < cutoff_time:
                                os.remove(entry.path)
                                deleted_count += 1

                        elif entry.is_dir(follow_symlinks=False):
                            # 目录：收集待递归处理
                            subdirs.append(entry.path)

                    except Exception as e:
                        print(f"处理条目失败 {entry.path}: {e}")
                        continue

                # 递归处理子目录
                for subdir in subdirs:
                    _clean_directory_recursive(subdir)

                # 尝试删除空目录（递归完成后）
                try:
                    # 使用 scandir 检查目录是否为空（比 listdir 更快）
                    with os.scandir(dir_path) as check_entries:
                        if not any(True for _ in check_entries):  # 目录为空
                            # 不删除用户根目录本身
                            if dir_path != user_output_dir:
                                os.rmdir(dir_path)
                except:
                    pass

        except Exception as e:
            print(f"扫描目录失败 {dir_path}: {e}")

    # 开始递归清理
    _clean_directory_recursive(user_output_dir)

    if deleted_count > 0:
        print(f"清理了 {deleted_count} 个超过 {days} 天的旧报告")

    return deleted_count


# 全局缓存鸟名列表和正则模式，避免每次都查询数据库
_bird_names_cache = None
_bird_names_pattern = None
_bird_names_cache_time = 0
BIRD_NAMES_CACHE_TTL = 3600  # 缓存1小时

def _get_bird_names_pattern():
    """
    获取或构建鸟名正则模式（带缓存）

    Returns:
        tuple: (bird_names_list, compiled_pattern) 或 (None, None)
    """
    global _bird_names_cache, _bird_names_pattern, _bird_names_cache_time

    import time
    current_time = time.time()

    # 检查缓存是否有效
    if (_bird_names_cache is not None and
        _bird_names_pattern is not None and
        current_time - _bird_names_cache_time < BIRD_NAMES_CACHE_TTL):
        return _bird_names_cache, _bird_names_pattern

    # 重新加载鸟名
    try:
        import re
        import sqlite3

        db = init_database()
        if not db:
            return None, None

        # 获取所有中文鸟名
        with sqlite3.connect(db.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT chinese_simplified
                FROM BirdCountInfo
                WHERE chinese_simplified != ''
                  AND chinese_simplified IS NOT NULL
                  AND length(chinese_simplified) >= 2
            """)
            bird_names = [row[0] for row in cursor.fetchall() if row[0]]

        if not bird_names:
            return None, None

        # 按长度降序排列（优先匹配长名字，避免短名字误匹配）
        bird_names.sort(key=len, reverse=True)

        # 构建单个正则表达式匹配所有鸟名
        # 使用 | 连接所有鸟名，一次匹配完成
        escaped_names = [re.escape(name) for name in bird_names]
        # 边界条件：前后不能是汉字、字母、数字或HTML标签
        pattern_str = r'(?<![\u4e00-\u9fa5a-zA-Z0-9>])(' + '|'.join(escaped_names) + r')(?![\u4e00-\u9fa5a-zA-Z0-9<])'
        compiled_pattern = re.compile(pattern_str)

        # 更新缓存
        _bird_names_cache = bird_names
        _bird_names_pattern = compiled_pattern
        _bird_names_cache_time = current_time

        print(f"✓ 已加载 {len(bird_names)} 个鸟名到缓存")
        return bird_names, compiled_pattern

    except Exception as e:
        print(f"加载鸟名失败: {e}")
        import traceback
        traceback.print_exc()
        return None, None


def add_bird_name_links(html_content):
    """
    在HTML内容中为鸟名添加可点击链接（优化版本）

    性能优化：
    1. 使用单个正则表达式一次匹配所有鸟名（O(n×k) vs O(n×m×k)）
    2. 缓存鸟名列表和正则模式，避免每次查询数据库
    3. 使用 data 属性替代内联 JavaScript（更安全）

    时间复杂度：O(n×k) 其中 n=节点数，k=文本长度
    原复杂度：O(n×m×k) 其中 m=鸟名数量（1000+）
    """
    try:
        import re
        import html as html_lib
        from bs4 import BeautifulSoup

        # 获取缓存的鸟名模式
        bird_names, pattern = _get_bird_names_pattern()
        if not bird_names or not pattern:
            return html_content

        def replace_bird_name(match):
            """正则替换回调函数"""
            bird_name = match.group(1)
            # 完全转义，防止XSS
            escaped_name = html_lib.escape(bird_name, quote=True)
            # 使用 data 属性而非内联 JavaScript
            return f'<a href="#" class="bird-name-link" data-bird-name="{escaped_name}">{html_lib.escape(bird_name)}</a>'

        # 解析HTML
        soup = BeautifulSoup(html_content, 'html.parser')

        # 处理所有文本节点（在 p, li, blockquote, td, dd 等标签中）
        for tag in soup.find_all(['p', 'li', 'blockquote', 'td', 'dd']):
            # 遍历标签内的所有直接文本节点
            for text_node in tag.find_all(text=True, recursive=False):
                # 跳过已经在链接中的文本
                if text_node.parent.name == 'a':
                    continue

                text = str(text_node)

                # 使用预编译的正则模式，一次替换所有匹配的鸟名
                modified_text = pattern.sub(replace_bird_name, text)

                # 如果文本被修改，替换原节点
                if modified_text != text:
                    # 解析修改后的HTML
                    new_soup = BeautifulSoup(modified_text, 'html.parser')
                    replacement_nodes = list(new_soup.children)

                    if replacement_nodes:
                        # 替换第一个节点
                        first_node = replacement_nodes[0]
                        text_node.replace_with(first_node)
                        # 插入其余节点
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
    """特有种检索页面（按洲分组）"""
    return render_template('endemic_continents.html',
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


def _build_subid_index(observations):
    """
    预构建 subId -> observation 的字典索引

    性能优化：O(n) 构建索引，之后每次查询 O(1)
    避免在每次 check_checklist_for_species 调用时进行 O(n) 线性查找

    :param observations: 观测记录列表
    :return: {sub_id: observation} 字典
    """
    subid_dict = {}
    for obs in observations:
        sub_id = obs.get('subId')
        if sub_id and sub_id not in subid_dict:
            # 保留第一个匹配的观测记录
            subid_dict[sub_id] = obs
    return subid_dict


def check_checklist_for_species(client, sub_id, target_species_set, first_species_obs_dict):
    """
    检查清单是否包含所有目标物种（优化版本）

    性能优化：
    - 使用预构建的字典索引，查找从 O(n) 降低到 O(1)
    - 添加异常超时处理

    :param client: eBird API 客户端
    :param sub_id: 清单ID
    :param target_species_set: 目标物种代码集合
    :param first_species_obs_dict: 预构建的 {sub_id: obs} 字典索引
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

        # O(1) 字典查找，替代之前的 O(n) 线性查找
        sub_id_to_obs = first_species_obs_dict.get(sub_id)
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

                    # 性能优化：预构建 subId -> observation 的字典索引
                    # 从 O(m×n) 降低到 O(m+n)，其中 m=清单数，n=观测记录数
                    first_species_obs_dict = _build_subid_index(first_species_obs)

                    # 并发获取清单详情并过滤（使用优化后的函数）
                    from concurrent.futures import ThreadPoolExecutor, as_completed

                    with ThreadPoolExecutor(max_workers=10) as executor:
                        futures = {
                            executor.submit(check_checklist_for_species, client, sub_id, target_species_set, first_species_obs_dict): sub_id
                            for sub_id in sub_ids_to_check
                        }
                        for future in as_completed(futures):
                            sub_id = futures[future]
                            try:
                                matching_obs = future.result(timeout=30)
                                if matching_obs:
                                    all_observations.extend(matching_obs)
                                    print(f"✓ 清单 {sub_id}: 找到 {len(matching_obs)} 条匹配观测")
                            except TimeoutError:
                                print(f"⚠ 清单 {sub_id} 处理超时")
                            except Exception as e:
                                print(f"✗ 清单 {sub_id} 处理失败: {e}")

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
                    # 收集清单ID
                    sub_ids_to_check = set()
                    for obs in first_species_obs:
                        sub_id = obs.get('subId')
                        if sub_id:
                            sub_ids_to_check.add(sub_id)

                    # 性能优化：预构建 subId -> observation 的字典索引
                    first_species_obs_dict = _build_subid_index(first_species_obs)

                    from concurrent.futures import ThreadPoolExecutor, as_completed

                    with ThreadPoolExecutor(max_workers=10) as executor:
                        futures = {
                            executor.submit(check_checklist_for_species, client, sub_id, target_species_set, first_species_obs_dict): sub_id
                            for sub_id in sub_ids_to_check
                        }
                        for future in as_completed(futures):
                            sub_id = futures[future]
                            try:
                                matching_obs = future.result(timeout=30)
                                if matching_obs:
                                    all_observations.extend(matching_obs)
                                    print(f"✓ 清单 {sub_id}: 找到 {len(matching_obs)} 条匹配观测")
                            except TimeoutError:
                                print(f"⚠ 清单 {sub_id} 处理超时")
                            except Exception as e:
                                print(f"✗ 清单 {sub_id} 处理失败: {e}")

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

        filename = f"{species_str}_{timestamp}_鸟讯.md"
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

            # 性能优化：单次遍历完成地点分组、清单ID收集和特有种信息附加
            # 从 2次遍历 O(2n) 优化为 1次遍历 O(n)
            locations = {}
            unique_sub_ids = set()

            for obs in all_observations:
                # 同时进行地点分组
                loc_id = obs.get('locId')
                if loc_id not in locations:
                    locations[loc_id] = {
                        'name': obs.get('locName', 'Unknown'),
                        'lat': obs.get('lat'),
                        'lng': obs.get('lng'),
                        'observations': []
                    }
                locations[loc_id]['observations'].append(obs)

                # 同时收集唯一的清单ID
                sub_id = obs.get('subId')
                if sub_id:
                    unique_sub_ids.add(sub_id)

                # 附加特有种信息（O(1) 字典查询）
                sci_name = obs.get('sciName')
                if sci_name and endemic_birds_map:
                    endemic_info = db.get_endemic_info(sci_name, endemic_birds_map)
                    obs['endemic_info'] = endemic_info  # None 或 [{"country_code": "AU", ...}, ...]

            # 获取目标鸟种代码集合（用于过滤伴生鸟种）
            target_species_codes = set(species_codes)
            code_to_name_map = db.get_code_to_name_map()
            code_to_full_name_map = db.get_code_to_full_name_map()

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

                        # 获取特有种信息（如果有）
                        endemic_info = obs.get('endemic_info')

                        checklists_at_location[sub_id]['species'].append({
                            'code': species_code,
                            'name': species_name,
                            'count': obs.get('howMany', 'X'),
                            'endemic_info': endemic_info  # 传递特有种信息
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
                            endemic_info = sp.get('endemic_info')

                            # 构建特有种标识（使用统一工具函数）
                            endemic_badge = generate_endemic_badge(endemic_info)

                            f.write(f"- **{obs_date}**: {species_name}{endemic_badge} - 观测数量: {count} 只")
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

        # 过滤出数据库中的鸟种，并附加特有种信息
        filtered_observations = []
        for obs in all_observations:
            species_code = obs.get('speciesCode')
            if species_code in code_to_name_map:
                obs['cn_name'] = code_to_name_map[species_code]

                # 附加特有种信息（O(1) 字典查询）
                sci_name = obs.get('sciName')
                if sci_name and endemic_birds_map:
                    endemic_info = db.get_endemic_info(sci_name, endemic_birds_map)
                    obs['endemic_info'] = endemic_info  # None 或 [{"country_code": "AU", ...}, ...]

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

        # 生成文件名 (在获取地名之后)
        if location_name:
            filename = f"{location_name}_{timestamp}_区域鸟讯.md"
        else:
            filename = f"GPS_{lat:.4f}_{lng:.4f}_{timestamp}_区域鸟讯.md"
        filepath = os.path.join(today_folder, filename)

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

            # 按清单分组所有观测记录，并获取每个清单的总鸟种数
            checklist_groups = {}
            checklist_total_species = {}  # 存储每个清单的总鸟种数

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
                            'index': species_index[group['species_code']]['index'],
                            'endemic_info': obs.get('endemic_info')  # 传递特有种信息
                        })

            # 获取每个清单的完整物种数（通过API）
            print(f"正在获取 {len(checklist_groups)} 个清单的完整物种数...")
            for sub_id in checklist_groups.keys():
                try:
                    checklist_detail = client.get_checklist_details(sub_id)
                    if checklist_detail and 'obs' in checklist_detail:
                        checklist_total_species[sub_id] = len(checklist_detail['obs'])
                    else:
                        checklist_total_species[sub_id] = None
                except Exception as e:
                    print(f"获取清单 {sub_id} 详情失败: {e}")
                    checklist_total_species[sub_id] = None

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

                # 显示总鸟种数和目标鸟种数
                total_species = checklist_total_species.get(sub_id)
                if total_species is not None:
                    f.write(f"**总鸟种数:** {total_species} 种 | **目标鸟种数:** {len(species_list)} 种\n\n")
                else:
                    f.write(f"**目标鸟种数:** {len(species_list)} 种\n\n")

                # 列出该清单中的所有目标鸟种
                for species in species_list:
                    # 构建特有种标识（使用统一工具函数）
                    endemic_info = species.get('endemic_info')
                    endemic_badge = generate_endemic_badge(endemic_info)

                    f.write(f"- **No.{species['index']}** {species['cn_name']} ({species['en_name']}){endemic_badge} - 观测数量: {species['count']} 只\n")

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
    """
    将地点名称转换为GPS坐标（带持久化LRU缓存）

    性能优化：
    1. 优先查询本地缓存（O(1) 查找）
    2. 缓存命中率 >80% 后，避免大部分 Nominatim API 调用
    3. Nominatim 限流1次/秒，缓存可显著提升用户体验
    """
    try:
        data = request.json
        place_name = data.get('place_name', '').strip()

        if not place_name:
            return jsonify({'error': '地点名称不能为空'}), 400

        # 1️⃣ 优先查询缓存（澳大利亚范围）
        cached_result = geocode_cache.get(place_name, country_code='au')
        if cached_result:
            return jsonify({
                'success': True,
                'latitude': cached_result['latitude'],
                'longitude': cached_result['longitude'],
                'display_name': cached_result['display_name'],
                'message': f'找到位置: {cached_result["display_name"]} (缓存)'
            })

        # 2️⃣ 查询缓存（全球范围）
        cached_result = geocode_cache.get(place_name, country_code=None)
        if cached_result:
            return jsonify({
                'success': True,
                'latitude': cached_result['latitude'],
                'longitude': cached_result['longitude'],
                'display_name': cached_result['display_name'],
                'message': f'找到位置: {cached_result["display_name"]} (缓存)'
            })

        # 3️⃣ 缓存未命中，使用 Nominatim 地理编码服务
        try:
            geolocator = get_geolocator()
        except Exception as init_error:
            print(f"初始化地理编码服务失败: {init_error}")
            return jsonify({
                'success': False,
                'error': '地理编码服务初始化失败，请稍后重试或直接输入GPS坐标'
            }), 503

        try:
            # 优先在澳大利亚范围内搜索
            location = geolocator.geocode(
                place_name,
                country_codes='au',
                timeout=15
            )

            # 如果在澳大利亚没找到，扩大搜索范围
            if not location:
                location = geolocator.geocode(place_name, timeout=15)

            if location:
                # 构建结果字典
                result = {
                    'latitude': location.latitude,
                    'longitude': location.longitude,
                    'display_name': location.address
                }

                # 4️⃣ 缓存结果（区分国家代码）
                if hasattr(location, 'raw') and location.raw.get('address', {}).get('country_code') == 'au':
                    geocode_cache.set(place_name, result, country_code='au')
                else:
                    geocode_cache.set(place_name, result, country_code=None)

                return jsonify({
                    'success': True,
                    'latitude': result['latitude'],
                    'longitude': result['longitude'],
                    'display_name': result['display_name'],
                    'message': f'找到位置: {result["display_name"]}'
                })
            else:
                return jsonify({
                    'success': False,
                    'error': '未找到该地点，请检查拼写或尝试使用更具体的地点名称'
                }), 404

        except GeocoderTimedOut:
            print(f"地理编码超时: {place_name}")
            return jsonify({
                'success': False,
                'error': '地理编码服务超时，请稍后重试或直接输入GPS坐标'
            }), 408

        except GeocoderServiceError as e:
            print(f"地理编码服务错误: {e}")
            return jsonify({
                'success': False,
                'error': f'地理编码服务暂时不可用，请直接输入GPS坐标。错误详情: {str(e)}'
            }), 503

        except Exception as e:
            # 捕获网络连接错误等其他异常
            print(f"地理编码意外错误: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({
                'success': False,
                'error': f'地理编码服务遇到网络问题，请稍后重试或直接输入GPS坐标'
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

        # 只返回有特有种的国家，按特有种数量排序
        cursor.execute("""
            SELECT
                c.id as country_id,
                c.country_name_zh as country_name_cn,
                c.country_name_en,
                COUNT(eb.id) as endemic_count
            FROM ebird_countries c
            JOIN endemic_birds eb ON c.id = eb.country_id
            GROUP BY c.id
            ORDER BY endemic_count DESC
        """)

        countries = []
        for row in cursor.fetchall():
            countries.append({
                'country_id': row[0],
                'country_name_cn': row[1],
                'country_name_en': row[2],
                'endemic_count': row[3],
                'region': ''  # region字段暂时为空，如果需要可以后续补充
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
            FROM ebird_countries c
            LEFT JOIN endemic_birds eb ON c.id = eb.country_id
            GROUP BY c.id
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
            SELECT id, country_code, country_name_en, country_name_zh
            FROM ebird_countries
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


@app.route('/api/endemic/countries-by-continent')
def api_get_countries_by_continent():
    """获取按大洲分组的所有有特有种的国家"""
    try:
        import sqlite3

        # 数据库路径
        db_path = os.path.join(os.path.dirname(__file__), '..', 'ebird_reference.sqlite')

        if not os.path.exists(db_path):
            return jsonify({'error': '数据库未找到'}), 404

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 查询所有有特有种的国家，按洲分组
        cursor.execute("""
            SELECT
                c.continent,
                c.country_code,
                c.country_name_en,
                c.country_name_zh,
                COUNT(eb.id) as endemic_count
            FROM ebird_countries c
            JOIN endemic_birds eb ON c.id = eb.country_id
            GROUP BY c.id
            HAVING endemic_count > 0
            ORDER BY c.continent, endemic_count DESC
        """)

        # 按洲组织数据
        continents = {}
        for row in cursor.fetchall():
            continent, code, name_en, name_zh, count = row

            if continent not in continents:
                continents[continent] = []

            continents[continent].append({
                'country_code': code,
                'country_name_en': name_en,
                'country_name_zh': name_zh if name_zh else name_en,
                'endemic_count': count
            })

        conn.close()

        return jsonify({
            'success': True,
            'continents': continents,
            'total_countries': sum(len(countries) for countries in continents.values())
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/ebird/countries')
def api_get_ebird_countries():
    """
    获取所有 eBird 国家列表（智能排序）

    排序规则：
    1. 前20名：按特有种数量降序排列（鸟种最丰富的国家）
    2. 其余国家：按英文名称首字母排序
    """
    try:
        import sqlite3

        db_path = os.path.join(os.path.dirname(__file__), '..', 'ebird_reference.sqlite')

        if not os.path.exists(db_path):
            return jsonify({'error': '数据库未找到'}), 404

        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()

            # 查询所有国家及其特有种数量
            cursor.execute("""
                SELECT
                    ec.country_code,
                    ec.country_name_en,
                    ec.country_name_zh,
                    ec.has_regions,
                    ec.regions_count,
                    COUNT(eb.id) as endemic_count
                FROM ebird_countries ec
                LEFT JOIN endemic_birds eb ON ec.id = eb.country_id
                GROUP BY ec.country_code
                ORDER BY endemic_count DESC, ec.country_name_en ASC
            """)

            all_countries = []
            for row in cursor.fetchall():
                code, name_en, name_zh, has_regions, regions_count, endemic_count = row
                all_countries.append({
                    'code': code,
                    'name_en': name_en,
                    'name_zh': name_zh,
                    'has_regions': bool(has_regions),
                    'regions_count': regions_count,
                    'endemic_count': endemic_count
                })

        # 智能排序：前20名按特有种排序，其余按字母排序
        top_countries = all_countries[:20]  # 前20名（特有种最多）
        other_countries = sorted(all_countries[20:], key=lambda x: x['name_en'])  # 其余按字母排序

        countries = top_countries + other_countries

        return jsonify({
            'success': True,
            'countries': countries,
            'total': len(countries),
            'top_endemic_count': 20  # 前20名是按特有种排序的
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

        # 性能优化：基于实际距离的智能采样算法
        # 旧算法问题：按坐标点数采样，导致采样点分布不均（直线段稀疏，弯道密集）
        # 新算法：每20km采样一个点，确保均匀覆盖路线
        sample_points = []
        sample_interval_km = 20  # 每20公里一个采样点

        if len(route_coords) <= 1:
            sample_points = [(coord[0], coord[1]) for coord in route_coords]
        else:
            # 起点必定包含
            sample_points.append((route_coords[0][0], route_coords[0][1]))

            cumulative_distance = 0  # 累计距离（公里）
            last_sampled_distance = 0  # 上次采样的距离

            for i in range(1, len(route_coords)):
                prev_coord = route_coords[i - 1]
                curr_coord = route_coords[i]

                # 计算这一段的距离
                segment_distance = haversine_distance(
                    prev_coord[0], prev_coord[1],
                    curr_coord[0], curr_coord[1]
                )
                cumulative_distance += segment_distance

                # 如果距离上次采样超过 20km，添加采样点
                if cumulative_distance - last_sampled_distance >= sample_interval_km:
                    sample_points.append((curr_coord[0], curr_coord[1]))
                    last_sampled_distance = cumulative_distance

            # 终点必定包含
            last_coord = route_coords[-1]
            if sample_points[-1] != (last_coord[0], last_coord[1]):
                sample_points.append((last_coord[0], last_coord[1]))

        print(f"路线总长: {route_distance_km:.1f}km, 采样点数: {len(sample_points)}")

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

    try:
        app.run(host='0.0.0.0', port=PORT, debug=DEBUG)
    except KeyboardInterrupt:
        print("\n\n正在关闭服务器...")
        # 优雅关闭：保存限流数据
        rate_limiter.shutdown()
        print("✓ 服务器已关闭")
    except Exception as e:
        print(f"\n⚠ 服务器异常退出: {e}")
        # 确保保存数据
        rate_limiter.shutdown()
        raise
