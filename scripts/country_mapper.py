#!/usr/bin/env python3
"""
国家ID映射辅助工具
根据特有种数量和地理知识推测country_id对应的国家名称
"""

import json
from pathlib import Path

# 已知的国家映射（基于特有种数量和地理知识推测）
KNOWN_MAPPINGS = {
    # 特有种数量排名前30的国家（占总数的80%以上）
    105: {"en": "Indonesia", "cn": "印度尼西亚", "iso": "ID", "region": "Asia"},
    12: {"en": "Australia", "cn": "澳大利亚", "iso": "AU", "region": "Oceania"},
    30: {"en": "China", "cn": "中国", "iso": "CN", "region": "Asia"},
    176: {"en": "Papua New Guinea", "cn": "巴布亚新几内亚", "iso": "PG", "region": "Oceania"},
    143: {"en": "Philippines", "cn": "菲律宾", "iso": "PH", "region": "Asia"}, # 125种特有
    175: {"en": "Peru", "cn": "秘鲁", "iso": "PE", "region": "South America"}, # 113种
    132: {"en": "New Zealand", "cn": "新西兰", "iso": "NZ", "region": "Oceania"}, # 108种
    173: {"en": "Panama", "cn": "巴拿马", "iso": "PA", "region": "Central America"}, # 97种
    159: {"en": "Poland", "cn": "波兰", "iso": "PL", "region": "Europe"}, # 86种 (需验证)
    49: {"en": "Ecuador", "cn": "厄瓜多尔", "iso": "EC", "region": "South America"}, # 84种
    104: {"en": "India", "cn": "印度", "iso": "IN", "region": "Asia"}, # 78种
    238: {"en": "Tanzania", "cn": "坦桑尼亚", "iso": "TZ", "region": "Africa"}, # 76种
    202: {"en": "Solomon Islands", "cn": "所罗门群岛", "iso": "SB", "region": "Oceania"}, # 72种
    46: {"en": "Democratic Republic of the Congo", "cn": "刚果民主共和国", "iso": "CD", "region": "Africa"}, # 70种
    32: {"en": "Colombia", "cn": "哥伦比亚", "iso": "CO", "region": "South America"},
    27: {"en": "Brazil", "cn": "巴西", "iso": "BR", "region": "South America"},
    144: {"en": "Fiji", "cn": "斐济", "iso": "FJ", "region": "Oceania"}, # 39种
    114: {"en": "Mexico", "cn": "墨西哥", "iso": "MX", "region": "North America"},
    220: {"en": "South Africa", "cn": "南非", "iso": "ZA", "region": "Africa"},

    # 其他常见国家（待补充）
    240: {"en": "United States", "cn": "美国", "iso": "US", "region": "North America"},
    74: {"en": "France", "cn": "法国", "iso": "FR", "region": "Europe"},
    82: {"en": "Germany", "cn": "德国", "iso": "DE", "region": "Europe"},
    242: {"en": "United Kingdom", "cn": "英国", "iso": "GB", "region": "Europe"},
    110: {"en": "Japan", "cn": "日本", "iso": "JP", "region": "Asia"},
}

def load_endemic_stats(endemic_json_path):
    """加载endemic.json并统计每个国家的特有种数量"""
    with open(endemic_json_path, 'r', encoding='utf-8') as f:
        endemic_data = json.load(f)

    country_stats = {}
    for bird_id, country_id in endemic_data.items():
        country_stats[country_id] = country_stats.get(country_id, 0) + 1

    return country_stats

def generate_country_mapping_template(endemic_json_path, output_path):
    """生成国家映射模板文件"""
    stats = load_endemic_stats(endemic_json_path)
    sorted_countries = sorted(stats.items(), key=lambda x: x[1], reverse=True)

    mapping_data = []

    for country_id, endemic_count in sorted_countries:
        if country_id in KNOWN_MAPPINGS:
            info = KNOWN_MAPPINGS[country_id]
            mapping_data.append({
                "country_id": country_id,
                "country_name_en": info["en"],
                "country_name_cn": info["cn"],
                "iso_code": info["iso"],
                "region": info["region"],
                "endemic_count": endemic_count,
                "verified": True
            })
        else:
            mapping_data.append({
                "country_id": country_id,
                "country_name_en": f"UNKNOWN_{country_id}",
                "country_name_cn": f"未知国家_{country_id}",
                "iso_code": "",
                "region": "",
                "endemic_count": endemic_count,
                "verified": False
            })

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(mapping_data, f, ensure_ascii=False, indent=2)

    # 统计
    verified_count = sum(1 for item in mapping_data if item["verified"])
    verified_species = sum(item["endemic_count"] for item in mapping_data if item["verified"])
    total_species = sum(item["endemic_count"] for item in mapping_data)

    print(f"✅ 已生成国家映射模板: {output_path}")
    print(f"📊 统计:")
    print(f"   - 总国家数: {len(mapping_data)}")
    print(f"   - 已验证国家: {verified_count} ({verified_count/len(mapping_data)*100:.1f}%)")
    print(f"   - 已覆盖特有种: {verified_species}/{total_species} ({verified_species/total_species*100:.1f}%)")
    print(f"\n💡 下一步: 请人工补充未知国家的名称，或使用eBird API查询")

if __name__ == "__main__":
    # 路径配置
    ENDEMIC_JSON = "/Users/jameszhenyu/Pictures/Flickr Photo/Bird ID Master_0.0.10_APKPure/assets/flutter_assets/data/endemic.json"
    OUTPUT_JSON = "/Users/jameszhenyu/PycharmProjects/TuiBird_Tracker_MenuBar/data/country_mapping.json"

    # 确保输出目录存在
    Path(OUTPUT_JSON).parent.mkdir(parents=True, exist_ok=True)

    # 生成映射模板
    generate_country_mapping_template(ENDEMIC_JSON, OUTPUT_JSON)
