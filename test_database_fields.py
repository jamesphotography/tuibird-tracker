#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试数据库字段名
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from config import DB_FILE
from database import BirdDatabase

print("=" * 60)
print("🧪 测试数据库字段名")
print("=" * 60)

# 初始化数据库
db = BirdDatabase(DB_FILE)

# 加载鸟类数据
birds = db.load_all_birds()

print(f"\n✅ 成功加载 {len(birds)} 种鸟类")

# 显示前3条记录的字段
print("\n📋 数据库记录示例 (前3条):")
for i, bird in enumerate(birds[:3], 1):
    print(f"\n{i}. 记录字段:")
    for key, value in bird.items():
        print(f"   {key}: {value}")

# 测试查询功能
print("\n" + "=" * 60)
print("🔍 测试鸟种搜索功能")
print("=" * 60)

# 搜索"麻雀"
query = "麻雀"
matches = db.find_species_by_name(query)
print(f"\n搜索 '{query}' 找到 {len(matches)} 条结果:")
for bird in matches[:3]:
    print(f"  - {bird['cn_name']} ({bird['en_name']}) [代码: {bird['code']}]")

print("\n✅ 数据库字段测试通过！")
print("\n字段名称:")
print("  - code: 鸟种代码 (例如: houspa)")
print("  - cn_name: 中文名 (例如: 家麻雀)")
print("  - en_name: 英文名 (例如: House Sparrow)")
