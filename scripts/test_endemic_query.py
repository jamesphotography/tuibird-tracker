#!/usr/bin/env python3
"""
特有种查询测试脚本
"""

import json
import sqlite3
from pathlib import Path

# 路径配置
PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "data" / "ebird_reference.sqlite"
BIRDINFO_JSON = "/Users/jameszhenyu/Pictures/Flickr Photo/Bird ID Master_0.0.10_APKPure/assets/flutter_assets/data/birdinfo.json"

# 加载鸟种信息
print("📚 加载鸟种信息...")
with open(BIRDINFO_JSON, 'r', encoding='utf-8') as f:
    bird_info_list = json.load(f)

# 构建 bird_id -> bird_info 映射 (bird_id = index + 1)
bird_info_map = {}
for i, bird_data in enumerate(bird_info_list):
    bird_id = i + 1
    if len(bird_data) >= 3:
        bird_info_map[bird_id] = {
            "cn_name": bird_data[0],
            "en_name": bird_data[1],
            "sci_name": bird_data[2]
        }

def query_endemic_birds(country_name):
    """查询某个国家的特有鸟种"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 查询国家ID（支持中英文搜索）
    cursor.execute("""
        SELECT country_id, country_name_cn, country_name_en, endemic_count, verified
        FROM countries
        WHERE country_name_cn LIKE ? OR country_name_en LIKE ?
    """, (f"%{country_name}%", f"%{country_name}%"))

    countries = cursor.fetchall()

    if not countries:
        print(f"❌ 未找到国家: {country_name}")
        conn.close()
        return

    # 如果找到多个，显示列表供选择
    if len(countries) > 1:
        print(f"\n找到 {len(countries)} 个匹配的国家:")
        for i, (cid, cn, en, count, verified) in enumerate(countries, 1):
            status = "✅" if verified else "❓"
            print(f"{i}. {cn} ({en}) - {count}种特有鸟 {status}")
        country_id, cn_name, en_name, endemic_count, verified = countries[0]
    else:
        country_id, cn_name, en_name, endemic_count, verified = countries[0]

    print("\n" + "="*70)
    print(f"🌍 国家: {cn_name} ({en_name})")
    print(f"🦜 特有种数量: {endemic_count} 种")
    print(f"{'✅ 已验证' if verified else '❓ 待验证'}")
    print("="*70)

    # 查询该国特有鸟种
    cursor.execute("""
        SELECT bird_id
        FROM endemic_birds
        WHERE country_id = ?
        ORDER BY bird_id
    """, (country_id,))

    bird_ids = [row[0] for row in cursor.fetchall()]
    conn.close()

    # 获取鸟种详细信息
    endemic_birds = []
    for bird_id in bird_ids:
        if bird_id in bird_info_map:
            endemic_birds.append({
                "bird_id": bird_id,
                **bird_info_map[bird_id]
            })

    # 显示结果
    print(f"\n📋 特有鸟种名录 ({len(endemic_birds)} 种):\n")
    print(f"{'序号':<6} {'中文名':<25} {'英文名':<40} {'学名'}")
    print("-"*110)

    for i, bird in enumerate(endemic_birds, 1):
        cn = bird.get('cn_name', 'N/A')
        en = bird.get('en_name', 'N/A')
        sci = bird.get('sci_name', 'N/A')
        print(f"{i:<6} {cn:<25} {en:<40} {sci}")

    return endemic_birds

if __name__ == "__main__":
    # 测试查询
    test_countries = ["中国", "澳大利亚", "Indonesia"]

    for country in test_countries:
        print("\n" + "🔍"*35 + "\n")
        birds = query_endemic_birds(country)
        if birds:
            print(f"\n✅ 成功查询到 {len(birds)} 种特有鸟")
        input("\n按回车继续下一个查询...")
