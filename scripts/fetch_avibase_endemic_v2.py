#!/usr/bin/env python3
"""
从Avibase获取特有鸟种数据 (V2 - 修正版)
只抓取标记为"Endemic"的鸟种，不包括"Endemic (country/region)"和"Near-endemic"
"""

import requests
from bs4 import BeautifulSoup
import json
import sqlite3
import re
from pathlib import Path

# Avibase URL模板 - 使用英文版本
AVIBASE_URL = "https://avibase.bsc-eoc.org/checklist.jsp?region={region}&list=clements&lang=EN"

# 国家/地区代码映射
REGION_CODES = {
    "Malaysia": "MY",
    "Australia": "AU",
    "New Zealand": "NZ",
    "China": "CN",
    "Indonesia": "ID",
    "Philippines": "PH",
    "Papua New Guinea": "PG",
    "Peru": "PE",
    "Ecuador": "EC",
    "India": "IN",
    "Brazil": "BR",
    "Colombia": "CO",
    "Tanzania": "TZ",
    "South Africa": "ZA",
    "Mexico": "MX",
    "Panama": "PA",
}

def fetch_endemic_birds(region_code, region_name, db_path="ebird_reference.sqlite"):
    """
    从Avibase获取某个地区的特有鸟种（仅真正的Endemic）

    Args:
        region_code: 地区代码，如 'AU'
        region_name: 地区名称，如 'Australia'
        db_path: 本地数据库路径

    Returns:
        dict: 包含特有鸟种信息的字典
    """
    url = AVIBASE_URL.format(region=region_code)

    print(f"\n{'='*70}")
    print(f"正在获取 {region_name} ({region_code}) 的特有鸟种数据...")
    print(f"URL: {url}")
    print(f"{'='*70}")

    try:
        # 发送请求
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=30)
        response.encoding = 'utf-8'

        if response.status_code != 200:
            print(f"❌ 请求失败: HTTP {response.status_code}")
            return None

        # 解析HTML
        soup = BeautifulSoup(response.text, 'html.parser')

        # 查找endemic count
        endemic_count_declared = None
        for text in soup.find_all(string=re.compile(r'Number of endemics:')):
            match = re.search(r'Number of endemics:\s*(\d+)', text)
            if match:
                endemic_count_declared = int(match.group(1))
                print(f"📋 页面声明特有种数量: {endemic_count_declared}")
                break

        # 查找所有标记为"Endemic"的鸟种（不包括"Endemic (country/region)"和"Near-endemic"）
        endemic_birds = []
        seen_species = set()

        for td in soup.find_all('td'):
            text = td.get_text().strip()

            # 只匹配纯"Endemic"，排除其他变体
            # 使用正则确保精确匹配
            if re.search(r'\bEndemic\b', text) and 'Endemic (country/region)' not in text and 'Near-endemic' not in text:
                # 获取同一行的鸟种信息
                row = td.find_parent('tr')
                if row:
                    link = row.find('a', href=re.compile(r'species\.jsp'))
                    sci_elem = row.find('i') or row.find('em')

                    if link and sci_elem:
                        bird_name = link.get_text().strip()
                        sci_name = sci_elem.get_text().strip()

                        # 避免重复
                        if sci_name not in seen_species:
                            seen_species.add(sci_name)
                            endemic_birds.append({
                                'scientific_name': sci_name,
                                'name_en': bird_name
                            })

        print(f"✅ 找到 {len(endemic_birds)} 种特有鸟")

        # 验证数量
        if endemic_count_declared and len(endemic_birds) != endemic_count_declared:
            print(f"⚠️  警告: 抓取数量({len(endemic_birds)})与页面声明({endemic_count_declared})不一致!")

        # 使用本地数据库enrichment
        if Path(db_path).exists():
            print(f"\n🔍 正在从本地数据库匹配中文名...")
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            matched_count = 0
            for bird in endemic_birds:
                cursor.execute("""
                    SELECT chinese_simplified, english_name
                    FROM BirdCountInfo
                    WHERE scientific_name = ?
                """, (bird['scientific_name'],))

                result = cursor.fetchone()
                if result:
                    bird['name_zh'] = result[0]
                    # 可以选择覆盖英文名或保留Avibase的
                    # bird['name_en'] = result[1]
                    matched_count += 1
                else:
                    bird['name_zh'] = bird['scientific_name']  # 未找到使用学名

            conn.close()
            if len(endemic_birds) > 0:
                print(f"✅ 匹配成功: {matched_count}/{len(endemic_birds)} ({matched_count/len(endemic_birds)*100:.1f}%)")
            else:
                print(f"⚠️  未找到任何特有鸟种")

        # 显示前10种
        if endemic_birds:
            print(f"\n前10种特有鸟:")
            for i, bird in enumerate(endemic_birds[:10], 1):
                zh_name = bird.get('name_zh', bird['scientific_name'])
                print(f"  {i:2d}. {zh_name:<25} | {bird['name_en']:<35} | {bird['scientific_name']}")

        return {
            "country_code": region_code,
            "country_name_en": region_name,
            "data_source": "Avibase",
            "classification": "Clements",
            "endemic_count_declared": endemic_count_declared,
            "endemic_count_found": len(endemic_birds),
            "birds": endemic_birds
        }

    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        return None

def save_to_json(data, output_dir="data/avibase"):
    """保存数据到JSON文件"""
    if not data:
        print("❌ 没有数据可保存")
        return None

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    country_code = data['country_code']
    filename = output_path / f"{country_code}_endemic.json"

    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n💾 数据已保存到: {filename}")
    return filename

if __name__ == "__main__":
    import sys

    # 支持命令行参数
    if len(sys.argv) > 1:
        region_code = sys.argv[1].upper()

        # 尝试从REGION_CODES映射中查找国家名，如果找不到就用代码作为名称
        region_name = None
        for name, code in REGION_CODES.items():
            if code == region_code:
                region_name = name
                break

        if not region_name:
            # 如果映射中没有，尝试从国家清单JSON获取
            countries_file = Path("data/avibase/countries_with_endemics.json")
            if countries_file.exists():
                with open(countries_file, 'r', encoding='utf-8') as f:
                    countries_data = json.load(f)
                    for country in countries_data.get('countries', []):
                        if country['country_code'] == region_code:
                            region_name = country['country_name_en']
                            break

        if not region_name:
            region_name = region_code  # 最后使用代码本身

        data = fetch_endemic_birds(region_code, region_name)

        if data:
            save_to_json(data)
            print(f"\n✅ {region_name} 完成！")
            sys.exit(0)
        else:
            print(f"\n❌ {region_name} 失败！")
            sys.exit(1)
    else:
        # 默认测试：处理多个国家
        countries = ["Malaysia", "Australia", "New Zealand", "China"]

        for country in countries:
            region_code = REGION_CODES[country]
            data = fetch_endemic_birds(region_code, country)

            if data:
                save_to_json(data)
                print(f"\n✅ {country} 完成！")
            else:
                print(f"\n❌ {country} 失败！")

            print("\n" + "="*70 + "\n")
