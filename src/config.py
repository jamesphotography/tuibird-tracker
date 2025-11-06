#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置管理模块
统一管理所有配置项、常量和文件路径
"""

import os
import sys
import json
from typing import Dict, Any, Optional
from datetime import datetime, timedelta


# ==================== 版本信息 ====================

VERSION = "0.4.2"
BUILD_DATE = "2025-11-05"
AUTHOR = "TuiBird Team"
DESCRIPTION = "eBird 统一鸟类追踪工具"


# ==================== 路径配置 ====================

def get_resource_path(relative_path: str) -> str:
    """
    获取资源文件的正确路径，支持开发和打包后的环境

    Args:
        relative_path: 相对路径

    Returns:
        绝对路径
    """
    try:
        # PyInstaller 打包后的路径
        base_path = getattr(sys, '_MEIPASS', None)
        if base_path is None:
            raise AttributeError
    except AttributeError:
        # 开发环境的路径，回到项目根目录
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    return os.path.join(base_path, relative_path)


# ==================== 文件路径常量 ====================

DB_FILE = get_resource_path("ebird_reference.sqlite")
CONFIG_FILE = "ebird_config.json"
PROFILES_FILE = get_resource_path("profiles.json")
OUTPUT_DIR = "output"


# ==================== API配置 ====================

EBIRD_API_BASE_URL = "https://api.ebird.org/v2/"  # 注意：必须以斜杠结尾
API_TIMEOUT = 20  # 秒
API_VALIDATION_INTERVAL = timedelta(hours=24)  # API Key缓存时间


# ==================== 区域代码 ====================

AUSTRALIA_STATES = [
    "AU-NT",   # 北领地
    "AU-NSW",  # 新南威尔士
    "AU-QLD",  # 昆士兰
    "AU-WA",   # 西澳大利亚
    "AU-SA",   # 南澳大利亚
    "AU-VIC",  # 维多利亚
    "AU-ACT",  # 首都领地
    "AU-TAS"   # 塔斯马尼亚
]


# ==================== 默认参数 ====================

DEFAULT_DAYS_BACK = 14  # 默认查询天数
DEFAULT_RADIUS_KM = 25  # 默认搜索半径（公里）
MAX_RADIUS_KM = 50      # 最大搜索半径
MIN_RADIUS_KM = 1       # 最小搜索半径
MAX_DAYS_BACK = 30      # 最大查询天数
MIN_DAYS_BACK = 1       # 最小查询天数


# ==================== 配置文件管理 ====================

class ConfigManager:
    """配置文件管理器"""

    def __init__(self, config_file: str = CONFIG_FILE):
        self.config_file = config_file
        self._config: Dict[str, Any] = {}
        self.load()

    def load(self) -> Dict[str, Any]:
        """加载配置文件"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self._config = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"⚠️ 配置文件损坏: {e}")
                self._config = {}
        return self._config

    def save(self) -> bool:
        """保存配置文件"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=4, ensure_ascii=False)
            return True
        except IOError as e:
            print(f"❌ 保存配置文件失败: {e}")
            return False

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置项"""
        return self._config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """设置配置项"""
        self._config[key] = value

    def get_api_key(self) -> Optional[str]:
        """获取API Key"""
        return self._config.get('api_key')

    def set_api_key(self, api_key: str) -> None:
        """设置API Key"""
        self._config['api_key'] = api_key
        self._config['setup_date'] = datetime.now().isoformat()
        self._config['last_validated'] = datetime.now().isoformat()

    def update_last_validated(self) -> None:
        """更新最后验证时间"""
        self._config['last_validated'] = datetime.now().isoformat()

    def should_revalidate_api_key(self) -> bool:
        """判断是否需要重新验证API Key"""
        if 'last_validated' not in self._config:
            return True

        try:
            last_validated = datetime.fromisoformat(self._config['last_validated'])
            now = datetime.now()
            return now - last_validated > API_VALIDATION_INTERVAL
        except (ValueError, TypeError):
            return True


# ==================== 配置文件操作（向后兼容） ====================

def load_config() -> Dict[str, Any]:
    """加载配置文件（向后兼容的函数）"""
    manager = ConfigManager()
    return manager._config


def save_config(config: Dict[str, Any]) -> bool:
    """保存配置文件（向后兼容的函数）"""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        return True
    except IOError:
        return False


# ==================== 档案管理 ====================

def load_profiles(filepath: str = PROFILES_FILE) -> Dict[str, Any]:
    """加载搜索档案"""
    if not os.path.exists(filepath):
        return {}
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        print(f"⚠️ 无法读取档案文件 {filepath}")
        return {}


def save_profile(filepath: str, profiles: Dict, profile_name: str, profile_data: Dict) -> None:
    """保存搜索档案"""
    profiles[profile_name] = profile_data
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(profiles, f, indent=4, ensure_ascii=False)
        print(f"✅ 成功将 '{profile_name}' 保存到档案")
    except IOError:
        print("❌ 保存档案失败！")
