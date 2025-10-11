#!/usr/bin/env python3
"""
为countries表添加中文名称
"""

import sqlite3

DB_PATH = "ebird_reference.sqlite"

# 国家中文名称映射
COUNTRY_CHINESE_NAMES = {
    'AO': '安哥拉',
    'AR': '阿根廷',
    'AU': '澳大利亚',
    'BB': '巴巴多斯',
    'BO': '玻利维亚',
    'BR': '巴西',
    'BS': '巴哈马',
    'CA': '加拿大',
    'CD': '刚果（金）',
    'CL': '智利',
    'CN': '中国',
    'CO': '哥伦比亚',
    'CR': '哥斯达黎加',
    'CU': '古巴',
    'DJ': '吉布提',
    'DO': '多米尼加',
    'EC': '厄瓜多尔',
    'ES': '西班牙',
    'ET': '埃塞俄比亚',
    'FR': '法国',
    'GR': '希腊',
    'GT': '危地马拉',
    'HN': '洪都拉斯',
    'ID': '印度尼西亚',
    'IN': '印度',
    'IR': '伊朗',
    'IT': '意大利',
    'JM': '牙买加',
    'JP': '日本',
    'KE': '肯尼亚',
    'KH': '柬埔寨',
    'LA': '老挝',
    'LK': '斯里兰卡',
    'MA': '摩洛哥',
    'MG': '马达加斯加',
    'MW': '马拉维',
    'MX': '墨西哥',
    'MY': '马来西亚',
    'MZ': '莫桑比克',
    'NC': '新喀里多尼亚',
    'NZ': '新西兰',
    'PA': '巴拿马',
    'PE': '秘鲁',
    'PF': '法属波利尼西亚',
    'PG': '巴布亚新几内亚',
    'PH': '菲律宾',
    'PT': '葡萄牙',
    'PY': '巴拉圭',
    'SA': '沙特阿拉伯',
    'SB': '所罗门群岛',
    'SO': '索马里',
    'SR': '苏里南',
    'ST': '圣多美和普林西比',
    'TH': '泰国',
    'TO': '汤加',
    'TR': '土耳其',
    'TW': '台湾',
    'TZ': '坦桑尼亚',
    'US': '美国',
    'VE': '委内瑞拉',
    'VN': '越南',
    'VU': '瓦努阿图',
    'WS': '萨摩亚',
    'YE': '也门',
    'ZA': '南非',
    'ZM': '赞比亚',
    'ZW': '津巴布韦',
}

def update_chinese_names():
    """更新国家中文名称"""

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("=" * 80)
    print("更新国家中文名称")
    print("=" * 80)

    updated_count = 0

    for country_code, chinese_name in COUNTRY_CHINESE_NAMES.items():
        cursor.execute("""
            UPDATE countries
            SET country_name_zh = ?
            WHERE country_code = ?
        """, (chinese_name, country_code))

        if cursor.rowcount > 0:
            updated_count += 1
            print(f"✅ {country_code:4s} → {chinese_name}")

    conn.commit()

    print("\n" + "=" * 80)
    print(f"更新完成: {updated_count} 个国家")
    print("=" * 80)

    # 验证更新
    cursor.execute("""
        SELECT COUNT(*) FROM countries WHERE country_name_zh IS NOT NULL
    """)
    total_with_chinese = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM countries")
    total_countries = cursor.fetchone()[0]

    print(f"\n📊 统计:")
    print(f"   总国家数: {total_countries}")
    print(f"   有中文名: {total_with_chinese}")
    print(f"   覆盖率: {total_with_chinese/total_countries*100:.1f}%")

    # 显示Top 10国家（更新后）
    print("\n🏆 特有种最多的10个国家（更新后）:")
    print("-" * 80)

    cursor.execute("""
        SELECT c.country_code, c.country_name_en, c.country_name_zh,
               COUNT(sbc.id) as endemic_count
        FROM countries c
        JOIN special_bird_countries sbc ON c.country_id = sbc.country_id
        WHERE sbc.is_endemic = 1
        GROUP BY c.country_id
        ORDER BY endemic_count DESC
        LIMIT 10
    """)

    for i, (code, name_en, name_zh, count) in enumerate(cursor.fetchall(), 1):
        display_name = name_zh if name_zh else name_en
        print(f"{i:2d}. {code:4s} {display_name:20s} ({name_en:20s}) {count:4d} 种")

    conn.close()

if __name__ == "__main__":
    update_chinese_names()
