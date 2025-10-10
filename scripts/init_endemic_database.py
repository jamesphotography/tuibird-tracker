#!/usr/bin/env python3
"""
特有鸟种数据库初始化脚本
将endemic.json和country_mapping.json数据导入SQLite数据库
"""

import json
import sqlite3
from pathlib import Path

# 路径配置
PROJECT_ROOT = Path(__file__).parent.parent
ENDEMIC_JSON = "/Users/jameszhenyu/Pictures/Flickr Photo/Bird ID Master_0.0.10_APKPure/assets/flutter_assets/data/endemic.json"
BIRDINFO_JSON = "/Users/jameszhenyu/Pictures/Flickr Photo/Bird ID Master_0.0.10_APKPure/assets/flutter_assets/data/birdinfo.json"
COUNTRY_MAPPING_JSON = PROJECT_ROOT / "data" / "country_mapping.json"
DB_PATH = PROJECT_ROOT / "data" / "ebird_reference.sqlite"

def create_tables(conn):
    """创建特有种相关表结构"""
    cursor = conn.cursor()

    # 1. 创建国家信息表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS countries (
            country_id INTEGER PRIMARY KEY,
            country_name_en TEXT NOT NULL,
            country_name_cn TEXT,
            iso_code TEXT,
            region TEXT,
            endemic_count INTEGER DEFAULT 0,
            verified BOOLEAN DEFAULT 0
        )
    """)

    # 2. 创建特有种关系表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS endemic_birds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bird_id INTEGER NOT NULL,
            country_id INTEGER NOT NULL,
            FOREIGN KEY (country_id) REFERENCES countries(country_id),
            UNIQUE(bird_id, country_id)
        )
    """)

    # 3. 创建索引
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_endemic_country ON endemic_birds(country_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_endemic_bird ON endemic_birds(bird_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_country_name_en ON countries(country_name_en)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_country_name_cn ON countries(country_name_cn)")

    conn.commit()
    print("✅ 表结构创建成功")

def import_countries(conn, country_mapping_path):
    """导入国家映射数据"""
    with open(country_mapping_path, 'r', encoding='utf-8') as f:
        countries = json.load(f)

    cursor = conn.cursor()

    for country in countries:
        cursor.execute("""
            INSERT OR REPLACE INTO countries
            (country_id, country_name_en, country_name_cn, iso_code, region, endemic_count, verified)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            country['country_id'],
            country['country_name_en'],
            country['country_name_cn'],
            country['iso_code'],
            country['region'],
            country['endemic_count'],
            1 if country['verified'] else 0
        ))

    conn.commit()
    print(f"✅ 已导入 {len(countries)} 个国家")

def import_endemic_birds(conn, endemic_json_path):
    """导入特有种关系数据"""
    with open(endemic_json_path, 'r', encoding='utf-8') as f:
        endemic_data = json.load(f)

    cursor = conn.cursor()

    count = 0
    for bird_id, country_id in endemic_data.items():
        cursor.execute("""
            INSERT OR IGNORE INTO endemic_birds (bird_id, country_id)
            VALUES (?, ?)
        """, (int(bird_id), int(country_id)))
        count += 1

    conn.commit()
    print(f"✅ 已导入 {count} 条特有种关系")

def verify_data(conn):
    """验证数据导入结果"""
    cursor = conn.cursor()

    # 统计国家数
    cursor.execute("SELECT COUNT(*) FROM countries")
    country_count = cursor.fetchone()[0]

    # 统计已验证国家数
    cursor.execute("SELECT COUNT(*) FROM countries WHERE verified = 1")
    verified_count = cursor.fetchone()[0]

    # 统计特有种关系数
    cursor.execute("SELECT COUNT(*) FROM endemic_birds")
    endemic_count = cursor.fetchone()[0]

    # 统计总特有种数
    cursor.execute("SELECT SUM(endemic_count) FROM countries")
    total_species = cursor.fetchone()[0]

    # 获取前10个特有种最多的国家
    cursor.execute("""
        SELECT country_name_cn, country_name_en, endemic_count, verified
        FROM countries
        ORDER BY endemic_count DESC
        LIMIT 10
    """)
    top_countries = cursor.fetchall()

    print("\n" + "="*70)
    print("📊 数据导入验证结果")
    print("="*70)
    print(f"总国家数: {country_count}")
    print(f"已验证国家: {verified_count} ({verified_count/country_count*100:.1f}%)")
    print(f"特有种关系数: {endemic_count}")
    print(f"总特有种数: {total_species}")
    print("\n🏆 特有种最多的前10个国家:")
    print(f"{'排名':<6} {'中文名':<20} {'英文名':<30} {'特有种数':<10} {'已验证'}")
    print("-"*70)

    for i, (cn_name, en_name, count, verified) in enumerate(top_countries, 1):
        status = "✅" if verified else "❌"
        print(f"{i:<6} {cn_name:<20} {en_name:<30} {count:<10} {status}")

def main():
    """主函数"""
    print("🚀 开始初始化特有鸟种数据库...")

    # 确保数据目录存在
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    # 连接数据库
    conn = sqlite3.connect(DB_PATH)

    try:
        # 1. 创建表结构
        create_tables(conn)

        # 2. 导入国家数据
        import_countries(conn, COUNTRY_MAPPING_JSON)

        # 3. 导入特有种关系
        import_endemic_birds(conn, ENDEMIC_JSON)

        # 4. 验证数据
        verify_data(conn)

        print("\n✅ 数据库初始化完成！")
        print(f"📍 数据库位置: {DB_PATH}")

    except Exception as e:
        print(f"❌ 错误: {e}")
        conn.rollback()
        raise

    finally:
        conn.close()

if __name__ == "__main__":
    main()
