#!/usr/bin/env python3
"""
将 ebird_regions.json 导入到 SQLite 数据库
创建 ebird_countries 和 ebird_regions 表
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime

DB_PATH = "ebird_reference.sqlite"
JSON_PATH = "ebird_regions.json"

def create_ebird_regions_schema(conn):
    """创建 eBird 区域数据库表"""

    cursor = conn.cursor()

    # 1. eBird 国家表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ebird_countries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            country_code TEXT UNIQUE NOT NULL,
            country_name_en TEXT NOT NULL,
            country_name_zh TEXT,
            has_regions BOOLEAN DEFAULT 0,
            regions_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 2. eBird 区域表（省/州等一级行政区）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ebird_regions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            region_code TEXT UNIQUE NOT NULL,
            region_name_en TEXT NOT NULL,
            region_name_zh TEXT,
            country_id INTEGER NOT NULL,
            country_code TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (country_id) REFERENCES ebird_countries(id)
        )
    """)

    # 创建索引
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_ebird_countries_code
        ON ebird_countries(country_code)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_ebird_regions_code
        ON ebird_regions(region_code)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_ebird_regions_country
        ON ebird_regions(country_id)
    """)

    conn.commit()
    print("✅ eBird 区域数据库表结构创建完成")

def import_regions_data(conn):
    """导入 ebird_regions.json 数据"""

    cursor = conn.cursor()

    # 读取 JSON 文件
    with open(JSON_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)

    countries_data = data.get('countries', [])
    total_countries = len(countries_data)

    print(f"\n📊 准备导入 {total_countries} 个国家的数据...")

    imported_countries = 0
    imported_regions = 0

    for country in countries_data:
        country_code = country['code']
        country_name_en = country['name']
        country_name_zh = country.get('name_cn', None)
        has_regions = country.get('has_regions', False)
        regions_count = country.get('regions_count', 0)

        # 插入国家数据
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO ebird_countries
                (country_code, country_name_en, country_name_zh, has_regions, regions_count)
                VALUES (?, ?, ?, ?, ?)
            """, (country_code, country_name_en, country_name_zh, has_regions, regions_count))

            country_id = cursor.lastrowid

            # 如果插入的是已存在记录，需要获取实际ID
            if country_id == 0:
                cursor.execute("""
                    SELECT id FROM ebird_countries WHERE country_code = ?
                """, (country_code,))
                country_id = cursor.fetchone()[0]

            imported_countries += 1

            # 导入该国家的区域
            regions = country.get('regions', [])
            for region in regions:
                region_code = region['code']
                region_name_en = region['name']
                region_name_zh = region.get('name_cn', None)

                cursor.execute("""
                    INSERT OR REPLACE INTO ebird_regions
                    (region_code, region_name_en, region_name_zh, country_id, country_code)
                    VALUES (?, ?, ?, ?, ?)
                """, (region_code, region_name_en, region_name_zh, country_id, country_code))

                imported_regions += 1

        except Exception as e:
            print(f"❌ 导入 {country_code} 失败: {e}")

    conn.commit()

    return imported_countries, imported_regions

def update_countries_table_with_ebird_data(conn):
    """
    将 ebird_countries 的中文名称同步到 countries 表
    （如果 countries 表中有该国家但缺少中文名）
    """

    cursor = conn.cursor()

    # 检查 countries 表是否存在
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='countries'
    """)

    if not cursor.fetchone():
        print("⚠️  countries 表不存在，跳过同步")
        return

    # 同步中文名称
    cursor.execute("""
        UPDATE countries
        SET country_name_zh = (
            SELECT country_name_zh
            FROM ebird_countries
            WHERE ebird_countries.country_code = countries.country_code
        )
        WHERE country_name_zh IS NULL
        AND EXISTS (
            SELECT 1 FROM ebird_countries
            WHERE ebird_countries.country_code = countries.country_code
            AND ebird_countries.country_name_zh IS NOT NULL
        )
    """)

    updated_count = cursor.rowcount
    conn.commit()

    if updated_count > 0:
        print(f"✅ 同步了 {updated_count} 个国家的中文名称到 countries 表")

def show_import_summary(conn):
    """显示导入汇总信息"""

    cursor = conn.cursor()

    print("\n" + "=" * 80)
    print("导入完成汇总")
    print("=" * 80)

    # 统计国家数
    cursor.execute("SELECT COUNT(*) FROM ebird_countries")
    total_countries = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM ebird_countries WHERE has_regions = 1")
    countries_with_regions = cursor.fetchone()[0]

    # 统计区域数
    cursor.execute("SELECT COUNT(*) FROM ebird_regions")
    total_regions = cursor.fetchone()[0]

    print(f"\n📊 统计:")
    print(f"   总国家数: {total_countries}")
    print(f"   有区域的国家数: {countries_with_regions}")
    print(f"   总区域数: {total_regions}")

    # 显示区域最多的前10个国家
    cursor.execute("""
        SELECT ec.country_code, ec.country_name_en, ec.country_name_zh,
               COUNT(er.id) as region_count
        FROM ebird_countries ec
        LEFT JOIN ebird_regions er ON ec.id = er.country_id
        WHERE ec.has_regions = 1
        GROUP BY ec.id
        ORDER BY region_count DESC
        LIMIT 10
    """)

    print(f"\n🏆 区域最多的10个国家:")
    print("-" * 80)

    for code, name_en, name_zh, count in cursor.fetchall():
        display_name = name_zh if name_zh else name_en
        print(f"   {code:4s} {display_name:30s} {count:4d} 个区域")

    # 显示部分示例
    print(f"\n📋 示例数据 (中国):")
    print("-" * 80)

    cursor.execute("""
        SELECT er.region_code, er.region_name_en, er.region_name_zh
        FROM ebird_regions er
        JOIN ebird_countries ec ON er.country_id = ec.id
        WHERE ec.country_code = 'CN'
        ORDER BY er.region_code
        LIMIT 10
    """)

    cn_regions = cursor.fetchall()
    if cn_regions:
        for code, name_en, name_zh in cn_regions:
            display = name_zh if name_zh else name_en
            print(f"   {code:8s} {display}")
    else:
        print("   (中国暂无区域数据)")

def main():
    print("=" * 80)
    print("eBird 区域数据导入工具")
    print("=" * 80)

    # 检查 JSON 文件是否存在
    if not Path(JSON_PATH).exists():
        print(f"❌ 文件不存在: {JSON_PATH}")
        return

    # 连接数据库
    conn = sqlite3.connect(DB_PATH)

    try:
        # 创建表结构
        create_ebird_regions_schema(conn)

        # 导入数据
        countries_count, regions_count = import_regions_data(conn)

        print(f"\n✅ 导入完成:")
        print(f"   国家数: {countries_count}")
        print(f"   区域数: {regions_count}")

        # 同步到 countries 表
        update_countries_table_with_ebird_data(conn)

        # 显示汇总
        show_import_summary(conn)

        print("\n" + "=" * 80)
        print("✅ 数据导入完成！")
        print("=" * 80)
        print(f"\n💾 数据库路径: {Path(DB_PATH).absolute()}")

    finally:
        conn.close()

if __name__ == "__main__":
    main()
