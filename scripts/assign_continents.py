#!/usr/bin/env python3
"""
为所有国家分配洲信息
"""

import sqlite3

DB_PATH = "ebird_reference.sqlite"

# 根据ISO国家代码分配大洲
CONTINENT_MAPPING = {
    # 亚洲
    'Asia': [
        'CN', 'JP', 'KR', 'KP', 'MN', 'TW', 'HK', 'MO',  # 东亚
        'TH', 'VN', 'LA', 'KH', 'MM', 'MY', 'SG', 'ID', 'PH', 'BN', 'TL',  # 东南亚
        'IN', 'PK', 'BD', 'LK', 'NP', 'BT', 'MV',  # 南亚
        'AF', 'IR', 'IQ', 'SY', 'JO', 'IL', 'PS', 'LB', 'TR', 'CY',  # 西亚
        'SA', 'YE', 'OM', 'AE', 'QA', 'BH', 'KW',  # 阿拉伯半岛
        'KZ', 'UZ', 'TM', 'TJ', 'KG', 'AM', 'AZ', 'GE',  # 中亚和高加索
    ],

    # 欧洲
    'Europe': [
        'GB', 'IE', 'IS', 'NO', 'SE', 'FI', 'DK',  # 北欧
        'FR', 'DE', 'NL', 'BE', 'LU', 'CH', 'AT', 'LI', 'MC', 'AD',  # 西欧和中欧
        'ES', 'PT', 'IT', 'GR', 'MT', 'SM', 'VA', 'GI',  # 南欧
        'PL', 'CZ', 'SK', 'HU', 'SI', 'HR', 'BA', 'RS', 'ME', 'AL', 'MK', 'BG', 'RO',  # 东欧
        'EE', 'LV', 'LT', 'BY', 'UA', 'MD', 'RU',  # 东欧和俄罗斯
        'FO', 'GG', 'JE', 'IM', 'AX', 'SJ', 'XK',  # 其他欧洲地区
    ],

    # 非洲
    'Africa': [
        'EG', 'LY', 'TN', 'DZ', 'MA', 'EH',  # 北非
        'MR', 'ML', 'NE', 'TD', 'SD', 'SS',  # 萨赫勒地区
        'SN', 'GM', 'GW', 'GN', 'SL', 'LR', 'CI', 'GH', 'TG', 'BJ', 'NG', 'BF',  # 西非
        'CM', 'CF', 'GQ', 'GA', 'CG', 'CD', 'AO',  # 中非
        'ER', 'DJ', 'ET', 'SO', 'KE', 'UG', 'RW', 'BI', 'TZ',  # 东非
        'ZM', 'ZW', 'MW', 'MZ', 'NA', 'BW', 'ZA', 'LS', 'SZ',  # 南部非洲
        'MG', 'MU', 'SC', 'KM', 'YT', 'RE', 'CV', 'ST', 'SH',  # 印度洋岛屿
    ],

    # 北美洲
    'North America': [
        'US', 'CA', 'MX',  # 主要国家
        'GT', 'BZ', 'HN', 'SV', 'NI', 'CR', 'PA',  # 中美洲
        'CU', 'JM', 'HT', 'DO', 'BS', 'TT',  # 加勒比海
        'BB', 'GD', 'VC', 'LC', 'DM', 'AG', 'KN', 'AI', 'MS', 'VG', 'VI', 'PR',  # 小安的列斯群岛
        'KY', 'TC', 'BM',  # 其他加勒比
        'GP', 'MQ', 'BL', 'MF', 'SX', 'CW', 'AW', 'BQ',  # 法属和荷属加勒比
        'GL', 'PM',  # 北美其他地区
    ],

    # 南美洲
    'South America': [
        'BR', 'AR', 'CL', 'PE', 'CO', 'VE', 'EC', 'BO', 'PY', 'UY', 'GY', 'SR', 'GF',
        'FK', 'GS',  # 南大西洋岛屿
    ],

    # 大洋洲
    'Oceania': [
        'AU', 'NZ',  # 澳大利亚和新西兰
        'PG', 'SB', 'VU', 'NC', 'FJ', 'WS', 'TO', 'TV', 'NR', 'KI',  # 美拉尼西亚和波利尼西亚
        'PW', 'FM', 'MH', 'GU', 'MP', 'AS',  # 密克罗尼西亚
        'CK', 'NU', 'TK', 'WF', 'PN', 'PF',  # 其他太平洋岛屿
        'NF', 'CX', 'CC', 'HM',  # 澳大利亚领地
        'UM',  # 美国太平洋领地
    ],

    # 南极洲
    'Antarctica': [
        'AQ', 'TF', 'BV',  # 南极及附近岛屿
    ],
}

# 反向映射：国家代码 -> 洲
COUNTRY_TO_CONTINENT = {}
for continent, countries in CONTINENT_MAPPING.items():
    for country_code in countries:
        COUNTRY_TO_CONTINENT[country_code] = continent

def assign_continents():
    """为所有国家分配洲信息"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 获取所有国家
    cursor.execute("SELECT country_code FROM ebird_countries")
    countries = cursor.fetchall()

    updated = 0
    unknown = 0

    for (country_code,) in countries:
        continent = COUNTRY_TO_CONTINENT.get(country_code, 'Unknown')

        cursor.execute("""
            UPDATE ebird_countries
            SET continent = ?
            WHERE country_code = ?
        """, (continent, country_code))

        if continent == 'Unknown':
            unknown += 1
            print(f"⚠️  未知洲: {country_code}")
        else:
            updated += 1

    conn.commit()
    conn.close()

    print(f"\n✅ 成功分配 {updated} 个国家的洲信息")
    if unknown > 0:
        print(f"⚠️  {unknown} 个国家未能识别洲信息")

    return updated, unknown

def verify_continent_distribution():
    """验证洲分布"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT continent, COUNT(*) as country_count
        FROM ebird_countries
        GROUP BY continent
        ORDER BY country_count DESC
    """)

    print("\n" + "=" * 60)
    print("各大洲国家分布")
    print("=" * 60)

    for continent, count in cursor.fetchall():
        print(f"{continent:20s} {count:3d} 个国家")

    conn.close()

if __name__ == "__main__":
    print("开始为国家分配洲信息...")
    assign_continents()
    verify_continent_distribution()
