#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TuiBird Tracker - eBird 鸟类追踪工具

一个功能强大的 eBird 数据查询和分析工具，支持单一物种追踪、
多物种分析和区域鸟种查询。
"""

from .config import VERSION, BUILD_DATE, AUTHOR, DESCRIPTION

__version__ = VERSION
__author__ = AUTHOR
__description__ = DESCRIPTION
__build_date__ = BUILD_DATE

__all__ = [
    'VERSION',
    'BUILD_DATE',
    'AUTHOR',
    'DESCRIPTION',
    '__version__',
    '__author__',
    '__description__',
    '__build_date__',
]
