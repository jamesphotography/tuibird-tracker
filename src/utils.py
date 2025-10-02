#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工具函数模块
包含输入验证、地理位置处理等通用工具函数
"""

import re
from typing import Optional, Tuple, Any, Union
import geocoder
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable


# ==================== 输入验证工具 ====================

def safe_input(
    prompt: str,
    input_type: str = "string",
    min_val: Optional[Union[int, float]] = None,
    max_val: Optional[Union[int, float]] = None,
    allow_empty: bool = True,
    default: Any = None
) -> Any:
    """
    安全的输入函数，包含完整的验证和错误处理

    Args:
        prompt: 提示信息
        input_type: 输入类型 ('string', 'int', 'float')
        min_val: 最小值 (仅限数字类型)
        max_val: 最大值 (仅限数字类型)
        allow_empty: 是否允许空输入
        default: 默认值

    Returns:
        验证后的输入值或None(用户中断)
    """
    while True:
        try:
            user_input = input(prompt).strip()

            # 处理空输入
            if not user_input:
                if allow_empty:
                    return default
                else:
                    print("⚠️ 不能为空，请重新输入。")
                    continue

            # 字符串类型直接返回
            if input_type == "string":
                return user_input

            # 数字类型验证
            elif input_type == "int":
                value = int(user_input)
                if min_val is not None and value < min_val:
                    print(f"⚠️ 值必须大于等于{min_val}，请重新输入。")
                    continue
                if max_val is not None and value > max_val:
                    print(f"⚠️ 值必须小于等于{max_val}，请重新输入。")
                    continue
                return value

            elif input_type == "float":
                value = float(user_input)
                if min_val is not None and value < min_val:
                    print(f"⚠️ 值必须大于等于{min_val}，请重新输入。")
                    continue
                if max_val is not None and value > max_val:
                    print(f"⚠️ 值必须小于等于{max_val}，请重新输入。")
                    continue
                return value

        except ValueError:
            if input_type == "int":
                print("⚠️ 请输入有效的整数。")
            elif input_type == "float":
                print("⚠️ 请输入有效的数字。")
            else:
                print("⚠️ 输入格式不正确，请重新输入。")
        except (KeyboardInterrupt, EOFError):
            print("\n❌ 用户中断操作")
            return None


# ==================== 地理位置处理 ====================

def get_location_from_ip() -> Tuple[Optional[str], Optional[Tuple[float, float]]]:
    """
    通过IP地址自动定位用户的大致位置

    Returns:
        (城市名称, (纬度, 经度)) 或 (None, None)
    """
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


def get_coords_from_string(input_str: str) -> Optional[Tuple[float, float]]:
    """
    从字符串中解析GPS坐标

    Args:
        input_str: 输入字符串，格式如 "39.9042, 116.4074"

    Returns:
        (纬度, 经度) 或 None
    """
    match = re.search(r'([-]?\d+\.?\d*)[,\s]+([-]?\d+\.?\d*)', input_str)
    if match:
        try:
            lat, lng = float(match.group(1)), float(match.group(2))
            if -90 <= lat <= 90 and -180 <= lng <= 180:
                return lat, lng
        except (ValueError, IndexError):
            pass
    return None


def get_coords_from_placename(placename: str, geolocator: Nominatim) -> Optional[Tuple[float, float]]:
    """
    从地名获取GPS坐标

    Args:
        placename: 地名
        geolocator: Nominatim地理编码器实例

    Returns:
        (纬度, 经度) 或 None
    """
    print(f"正在查询 '{placename}' 的坐标...")
    try:
        location = geolocator.geocode(placename, timeout=10)
        if location:
            print(f"✅ 查询成功: {location.address}")
            print(f"   经纬度: ({location.latitude:.4f}, {location.longitude:.4f})")
            return location.latitude, location.longitude
    except (GeocoderTimedOut, GeocoderUnavailable) as e:
        print(f"❌ 地理编码服务出错: {e}")
    except Exception as e:
        print(f"❌ 地理编码错误: {e}")

    print(f"❌ 未能找到 '{placename}' 的坐标。")
    return None


def get_placename_from_coords(lat: float, lng: float, geolocator: Nominatim) -> str:
    """
    从GPS坐标获取地名

    Args:
        lat: 纬度
        lng: 经度
        geolocator: Nominatim地理编码器实例

    Returns:
        地名或默认描述
    """
    try:
        location = geolocator.reverse(f"{lat}, {lng}", timeout=10)
        if location:
            return location.address
    except (GeocoderTimedOut, GeocoderUnavailable):
        pass
    except Exception:
        pass
    return f"GPS位置 ({lat:.4f}, {lng:.4f})"


def create_geolocator(user_agent: str = "tuibird_tracker_v4") -> Nominatim:
    """
    创建Nominatim地理编码器实例

    Args:
        user_agent: 用户代理字符串

    Returns:
        Nominatim实例
    """
    return Nominatim(user_agent=user_agent)


# ==================== 数据处理工具 ====================

def format_count(count: Any) -> str:
    """
    格式化观测数量

    Args:
        count: 观测数量

    Returns:
        格式化后的字符串
    """
    if count is None or count == '':
        return '未知数量'
    if isinstance(count, (int, float)):
        return str(int(count))
    return str(count)


def create_google_maps_link(lat: float, lng: float) -> str:
    """
    创建Google地图链接

    Args:
        lat: 纬度
        lng: 经度

    Returns:
        Google地图URL
    """
    return f"https://maps.google.com/?q={lat},{lng}"


def create_ebird_checklist_link(sub_id: str) -> str:
    """
    创建eBird清单链接

    Args:
        sub_id: 清单ID

    Returns:
        eBird清单URL
    """
    return f"https://ebird.org/checklist/{sub_id}"


# ==================== 显示工具 ====================

def print_banner(title: str, width: int = 60) -> None:
    """
    打印程序标题横幅

    Args:
        title: 标题文本
        width: 横幅宽度
    """
    print("=" * width)
    print(title.center(width))
    print("=" * width)


def print_divider(char: str = "-", width: int = 40) -> None:
    """
    打印分隔线

    Args:
        char: 分隔符字符
        width: 分隔线宽度
    """
    print(char * width)
