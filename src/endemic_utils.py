#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
特有种工具模块
提供特有种徽章生成等通用功能
"""

from typing import List, Dict, Optional


# 国家特定图标映射
COUNTRY_ICONS = {
    'AU': '🦘',  # 澳大利亚 - 袋鼠
    'NZ': '🥝',  # 新西兰 - 几维鸟
    'ID': '🦜',  # 印度尼西亚 - 鹦鹉
    'PH': '🦜',  # 菲律宾 - 鹦鹉
    'BR': '🦅',  # 巴西 - 鹰
    'MX': '🦅',  # 墨西哥 - 鹰
    'MG': '🦎',  # 马达加斯加 - 变色龙
    'PG': '🦜',  # 巴布亚新几内亚 - 鹦鹉
}

DEFAULT_ICON = '🌟'  # 默认图标（其他国家）


def generate_endemic_badge(endemic_info: Optional[List[Dict]]) -> str:
    """
    生成特有种徽章

    Args:
        endemic_info: 特有种信息列表，例如:
            [
                {
                    "country_code": "AU",
                    "country_name_zh": "澳大利亚",
                    "country_name_en": "Australia",
                    "name_zh": "鸸鹋",
                    "name_en": "Emu"
                }
            ]

    Returns:
        str: 徽章字符串，例如:
            - 单个国家: " 🦘**特有**"
            - 多个国家: " 🦘🥝**特有**"
            - 无特有种: ""

    Examples:
        >>> generate_endemic_badge(None)
        ''

        >>> generate_endemic_badge([{"country_code": "AU"}])
        ' 🦘**特有**'

        >>> generate_endemic_badge([{"country_code": "AU"}, {"country_code": "NZ"}])
        ' 🦘🥝**特有**'
    """
    if not endemic_info:
        return ""

    if len(endemic_info) == 1:
        # 单个国家特有种
        country_code = endemic_info[0].get('country_code', '')
        icon = COUNTRY_ICONS.get(country_code, DEFAULT_ICON)
        return f" {icon}**特有**"
    else:
        # 多个国家特有种（显示所有国家图标）
        icons = []
        for info in endemic_info:
            country_code = info.get('country_code', '')
            icon = COUNTRY_ICONS.get(country_code, DEFAULT_ICON)
            icons.append(icon)
        return f" {''.join(icons)}**特有**"


def get_country_icon(country_code: str) -> str:
    """
    获取国家对应的图标

    Args:
        country_code: 国家代码（如 'AU', 'NZ'）

    Returns:
        str: 对应的 emoji 图标

    Examples:
        >>> get_country_icon('AU')
        '🦘'

        >>> get_country_icon('UNKNOWN')
        '🌟'
    """
    return COUNTRY_ICONS.get(country_code, DEFAULT_ICON)


def format_endemic_info_text(endemic_info: Optional[List[Dict]]) -> str:
    """
    格式化特有种信息为可读文本（用于非 Markdown 场景）

    Args:
        endemic_info: 特有种信息列表

    Returns:
        str: 格式化的文本，例如 "澳大利亚特有" 或 "澳大利亚、新西兰特有"

    Examples:
        >>> format_endemic_info_text([{"country_name_zh": "澳大利亚"}])
        '澳大利亚特有'

        >>> format_endemic_info_text([{"country_name_zh": "澳大利亚"}, {"country_name_zh": "新西兰"}])
        '澳大利亚、新西兰特有'
    """
    if not endemic_info:
        return ""

    country_names = [info.get('country_name_zh', '') for info in endemic_info if info.get('country_name_zh')]
    if not country_names:
        return ""

    return '、'.join(country_names) + '特有'
