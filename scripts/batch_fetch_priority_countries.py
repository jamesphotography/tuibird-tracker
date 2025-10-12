#!/usr/bin/env python3
"""
批量抓取优先级国家的特有种数据
按照 P0 > P1 > P2 的优先级顺序抓取
"""

import sys
import time
import sqlite3
from pathlib import Path

# 导入现有的抓取脚本
sys.path.append(str(Path(__file__).parent))
from fetch_avibase_endemic_v2 import fetch_endemic_birds, save_to_json

DB_PATH = "ebird_reference.sqlite"

# P0 高优先级国家（岛屿国家和大型国家，很可能有特有种）
P0_COUNTRIES = [
    ("RU", "Russia"),
    ("GB", "United Kingdom"),
    ("FR", "France"),
    ("IT", "Italy"),
    ("GR", "Greece"),
    ("TR", "Türkiye"),
    ("KR", "South Korea"),
    ("MU", "Mauritius"),
    ("SC", "Seychelles"),
    ("RE", "Réunion"),
    ("CV", "Cape Verde"),
    ("ST", "São Tomé and Príncipe"),
    ("KI", "Kiribati"),
    ("FM", "Micronesia"),
    ("PW", "Palau"),
    ("MH", "Marshall Islands"),
    ("CK", "Cook Islands"),
    ("SG", "Singapore"),
]

# P1 中优先级国家（区域性国家，可能有少量特有种）
P1_COUNTRIES = [
    ("DE", "Germany"),
    ("ES", "Spain"),
    ("PL", "Poland"),
    ("UA", "Ukraine"),
    ("RO", "Romania"),
    ("BG", "Bulgaria"),
    ("RS", "Serbia"),
    ("HR", "Croatia"),
    ("NO", "Norway"),
    ("SE", "Sweden"),
    ("FI", "Finland"),
    ("DK", "Denmark"),
    ("IS", "Iceland"),
    ("IE", "Ireland"),
    ("CH", "Switzerland"),
    ("AT", "Austria"),
    ("CZ", "Czech Republic"),
    ("SK", "Slovakia"),
    ("HU", "Hungary"),
    ("SI", "Slovenia"),
    ("BA", "Bosnia and Herzegovina"),
    ("ME", "Montenegro"),
    ("AL", "Albania"),
    ("MK", "North Macedonia"),
    ("PK", "Pakistan"),
    ("BD", "Bangladesh"),
    ("AF", "Afghanistan"),
    ("KZ", "Kazakhstan"),
    ("MN", "Mongolia"),
    ("KP", "North Korea"),
    ("GE", "Georgia"),
    ("AM", "Armenia"),
    ("AZ", "Azerbaijan"),
    ("MA", "Morocco"),
    ("DZ", "Algeria"),
    ("TN", "Tunisia"),
    ("EG", "Egypt"),
    ("LY", "Libya"),
    ("SD", "Sudan"),
    ("SS", "South Sudan"),
    ("NG", "Nigeria"),
    ("GA", "Gabon"),
    ("CG", "Congo"),
    ("NA", "Namibia"),
    ("BW", "Botswana"),
    ("ZW", "Zimbabwe"),
    ("BZ", "Belize"),
    ("SV", "El Salvador"),
    ("PY", "Paraguay"),
    ("UY", "Uruguay"),
]

# P2 低优先级国家（小岛屿、海外领地、极地地区，特有种较少或数据难获取）
P2_COUNTRIES = [
    ("CA", "Canada"),
    ("GL", "Greenland"),
    ("SJ", "Svalbard and Jan Mayen"),
    ("AQ", "Antarctica"),
    ("FO", "Faroe Islands"),
    ("HK", "Hong Kong"),
    ("MO", "Macao"),
    ("BM", "Bermuda"),
    ("AI", "Anguilla"),
    ("AG", "Antigua and Barbuda"),
    ("DM", "Dominica"),
    ("GD", "Grenada"),
    ("KN", "Saint Kitts and Nevis"),
    ("LC", "Saint Lucia"),
    ("VC", "Saint Vincent and the Grenadines"),
    ("KY", "Cayman Islands"),
    ("TC", "Turks and Caicos Islands"),
    ("VG", "British Virgin Islands"),
    ("VI", "U.S. Virgin Islands"),
    ("GP", "Guadeloupe"),
    ("MQ", "Martinique"),
    ("BL", "Saint Barthélemy"),
    ("MF", "Saint Martin"),
    ("SX", "Sint Maarten"),
    ("CW", "Curaçao"),
    ("AW", "Aruba"),
    ("BQ", "Caribbean Netherlands"),
    ("MS", "Montserrat"),
    ("AS", "American Samoa"),
    ("GU", "Guam"),
    ("MP", "Northern Mariana Islands"),
    ("NU", "Niue"),
    ("TK", "Tokelau"),
    ("TV", "Tuvalu"),
    ("NR", "Nauru"),
    ("PN", "Pitcairn Islands"),
    ("WF", "Wallis and Futuna"),
    ("NF", "Norfolk Island"),
    ("CX", "Christmas Island"),
    ("CC", "Cocos (Keeling) Islands"),
    ("IO", "British Indian Ocean Territory"),
    ("YT", "Mayotte"),
    ("FK", "Falkland Islands"),
    ("GS", "South Georgia and the South Sandwich Islands"),
    ("SH", "Saint Helena, Ascension and Tristan da Cunha"),
    ("PM", "Saint Pierre and Miquelon"),
    ("BV", "Bouvet Island"),
    ("HM", "Heard Island and McDonald Islands"),
    ("TF", "French Southern Territories"),
    ("UM", "U.S. Minor Outlying Islands"),
    ("LI", "Liechtenstein"),
    ("MC", "Monaco"),
    ("SM", "San Marino"),
    ("VA", "Vatican City"),
    ("AD", "Andorra"),
    ("LU", "Luxembourg"),
    ("MT", "Malta"),
    ("CY", "Cyprus"),
    ("IM", "Isle of Man"),
    ("JE", "Jersey"),
    ("GG", "Guernsey"),
    ("GI", "Gibraltar"),
    ("BY", "Belarus"),
    ("MD", "Moldova"),
    ("LV", "Latvia"),
    ("LT", "Lithuania"),
    ("EE", "Estonia"),
    ("KG", "Kyrgyzstan"),
    ("TJ", "Tajikistan"),
    ("TM", "Turkmenistan"),
    ("UZ", "Uzbekistan"),
    ("BT", "Bhutan"),
    ("NP", "Nepal"),
    ("TL", "Timor-Leste"),
    ("BN", "Brunei"),
    ("MV", "Maldives"),
    ("BH", "Bahrain"),
    ("QA", "Qatar"),
    ("KW", "Kuwait"),
    ("OM", "Oman"),
    ("AE", "United Arab Emirates"),
    ("IL", "Israel"),
    ("JO", "Jordan"),
    ("LB", "Lebanon"),
    ("PS", "Palestine"),
    ("SY", "Syria"),
    ("IQ", "Iraq"),
    ("XK", "Kosovo"),
    ("GN", "Guinea"),
    ("GW", "Guinea-Bissau"),
    ("SL", "Sierra Leone"),
    ("LR", "Liberia"),
    ("CI", "Côte d'Ivoire"),
    ("GH", "Ghana"),
    ("TG", "Togo"),
    ("BJ", "Benin"),
    ("NE", "Niger"),
    ("BF", "Burkina Faso"),
    ("ML", "Mali"),
    ("MR", "Mauritania"),
    ("SN", "Senegal"),
    ("GM", "Gambia"),
    ("BI", "Burundi"),
    ("RW", "Rwanda"),
    ("CF", "Central African Republic"),
    ("TD", "Chad"),
    ("GQ", "Equatorial Guinea"),
    ("ER", "Eritrea"),
    ("DJ", "Djibouti"),
    ("KM", "Comoros"),
    ("SZ", "Eswatini"),
    ("LS", "Lesotho"),
    ("EH", "Western Sahara"),
]

def get_country_name_from_db(country_code):
    """从数据库获取国家名称"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT country_name_en, country_name_zh
        FROM ebird_countries
        WHERE country_code = ?
    """, (country_code,))
    result = cursor.fetchone()
    conn.close()

    if result:
        return result[0]  # 返回英文名
    return country_code

def save_to_database(data, country_code):
    """将抓取的特有种数据保存到数据库"""
    if not data or not data.get('birds'):
        print(f"  ⚠️  没有特有种数据需要保存")
        return 0

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 获取国家ID
    cursor.execute("""
        SELECT id FROM ebird_countries WHERE country_code = ?
    """, (country_code,))
    result = cursor.fetchone()

    if not result:
        print(f"  ❌ 国家代码 {country_code} 在数据库中不存在")
        conn.close()
        return 0

    country_id = result[0]

    # 插入特有种数据
    inserted_count = 0
    for bird in data['birds']:
        try:
            cursor.execute("""
                INSERT OR IGNORE INTO endemic_birds
                (country_id, name_zh, name_en, scientific_name, data_source)
                VALUES (?, ?, ?, ?, ?)
            """, (
                country_id,
                bird.get('name_zh', bird['scientific_name']),
                bird.get('name_en', ''),
                bird['scientific_name'],
                'Avibase'
            ))

            if cursor.rowcount > 0:
                inserted_count += 1
        except Exception as e:
            print(f"  ⚠️  插入失败: {bird['scientific_name']} - {e}")

    conn.commit()
    conn.close()

    print(f"  ✅ 成功插入 {inserted_count}/{len(data['birds'])} 条记录到数据库")
    return inserted_count

def check_already_fetched(country_code):
    """检查国家是否已经抓取过"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(e.id)
        FROM ebird_countries c
        JOIN endemic_birds e ON c.id = e.country_id
        WHERE c.country_code = ?
    """, (country_code,))

    count = cursor.fetchone()[0]
    conn.close()

    return count > 0, count

def batch_fetch_countries(countries, priority="P0", delay=5):
    """
    批量抓取国家列表

    Args:
        countries: 国家代码和名称的列表 [(code, name), ...]
        priority: 优先级标记
        delay: 请求之间的延迟（秒）
    """
    print("\n" + "=" * 80)
    print(f"🚀 开始批量抓取 {priority} 优先级国家")
    print(f"   共 {len(countries)} 个国家")
    print("=" * 80)

    stats = {
        'total': len(countries),
        'success': 0,
        'skipped': 0,
        'failed': 0,
        'total_species': 0
    }

    for i, (country_code, country_name) in enumerate(countries, 1):
        print(f"\n[{i}/{len(countries)}] 处理: {country_name} ({country_code})")

        # 检查是否已抓取
        already_fetched, existing_count = check_already_fetched(country_code)
        if already_fetched:
            print(f"  ⏭️  已存在 {existing_count} 条记录，跳过")
            stats['skipped'] += 1
            continue

        # 抓取数据
        try:
            # 从数据库获取标准国家名称
            db_country_name = get_country_name_from_db(country_code)

            data = fetch_endemic_birds(country_code, db_country_name or country_name, DB_PATH)

            if data:
                # 保存到JSON
                save_to_json(data)

                # 保存到数据库
                inserted_count = save_to_database(data, country_code)

                if inserted_count > 0:
                    stats['success'] += 1
                    stats['total_species'] += inserted_count
                    print(f"  ✅ 成功: {country_name} ({inserted_count} 种)")
                else:
                    stats['skipped'] += 1
                    print(f"  ⚠️  无特有种数据: {country_name}")
            else:
                stats['failed'] += 1
                print(f"  ❌ 失败: {country_name}")

        except Exception as e:
            stats['failed'] += 1
            print(f"  ❌ 异常: {country_name} - {e}")

        # 延迟避免过于频繁请求
        if i < len(countries):
            print(f"  ⏳ 等待 {delay} 秒...")
            time.sleep(delay)

    # 打印统计
    print("\n" + "=" * 80)
    print(f"📊 {priority} 批量抓取完成")
    print("=" * 80)
    print(f"  总计国家: {stats['total']}")
    print(f"  ✅ 成功: {stats['success']}")
    print(f"  ⏭️  跳过: {stats['skipped']}")
    print(f"  ❌ 失败: {stats['failed']}")
    print(f"  🐦 总特有种: {stats['total_species']}")
    print("=" * 80)

    return stats

def main():
    import argparse

    parser = argparse.ArgumentParser(description='批量抓取优先级国家的特有种数据')
    parser.add_argument('--priority', choices=['P0', 'P1', 'P2', 'all'], default='P0',
                        help='选择优先级: P0(高), P1(中), P2(低), all(全部)')
    parser.add_argument('--delay', type=int, default=5,
                        help='请求之间的延迟秒数 (默认: 5)')
    parser.add_argument('--start', type=int, default=0,
                        help='从第N个国家开始（用于断点续传）')

    args = parser.parse_args()

    # 根据优先级选择国家列表
    if args.priority == 'P0':
        countries = P0_COUNTRIES
    elif args.priority == 'P1':
        countries = P1_COUNTRIES
    elif args.priority == 'P2':
        countries = P2_COUNTRIES
    elif args.priority == 'all':
        print("⚠️  all 模式将抓取所有未抓取的国家（可能需要很长时间）")
        print("   建议先运行 P0, 然后 P1, 最后 P2")
        return
    else:
        print(f"❌ 暂不支持 {args.priority}，请使用 P0、P1 或 P2")
        return

    # 应用起始位置
    if args.start > 0:
        countries = countries[args.start:]
        print(f"📍 从第 {args.start + 1} 个国家开始")

    # 执行批量抓取
    stats = batch_fetch_countries(countries, args.priority, args.delay)

    # 最终统计
    print("\n✅ 全部完成！")
    if stats['failed'] > 0:
        print(f"⚠️  有 {stats['failed']} 个国家抓取失败，可以稍后重试")

if __name__ == "__main__":
    main()
