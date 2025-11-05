#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库操作模块
统一管理所有数据库相关操作
"""

import sqlite3
import sys
from typing import List, Dict, Optional
from contextlib import contextmanager


class BirdDatabase:
    """鸟类数据库管理类"""

    def __init__(self, db_path: str):
        """
        初始化数据库连接

        Args:
            db_path: 数据库文件路径
        """
        self.db_path = db_path
        self._birds_cache: Optional[List[Dict]] = None
        self._code_to_name_map: Optional[Dict[str, str]] = None

    @contextmanager
    def get_connection(self):
        """
        获取数据库连接的上下文管理器

        Yields:
            sqlite3.Connection: 数据库连接对象
        """
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            yield conn
        except sqlite3.Error as e:
            print(f"❌ 数据库连接错误: {e}")
            raise
        finally:
            if conn:
                conn.close()

    def load_all_birds(self) -> List[Dict]:
        """
        从数据库加载所有鸟种信息

        Returns:
            鸟种信息列表，每个元素包含 code, cn_name, en_name
        """
        if self._birds_cache is not None:
            return self._birds_cache

        print(f"初始化: 正在从数据库 '{self.db_path}' 加载鸟种名录...")

        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                query = """
                    SELECT ebird_code, chinese_simplified, english_name
                    FROM BirdCountInfo
                    WHERE ebird_code IS NOT NULL AND ebird_code != ''
                """
                cursor.execute(query)
                all_birds_data = cursor.fetchall()

                birds = []
                for bird in all_birds_data:
                    birds.append({
                        'code': bird['ebird_code'],
                        'cn_name': bird['chinese_simplified'],
                        'en_name': bird['english_name']
                    })

                if not birds:
                    print(f"❌ 错误: 从数据库 '{self.db_path}' 中没有载入任何有效的鸟种数据。")
                    sys.exit(1)

                self._birds_cache = birds
                print(f"✅ 成功加载 {len(birds)} 条鸟种记录，搜寻功能已就绪。")
                return birds

        except sqlite3.Error as e:
            print(f"❌ 严重错误: 连接或读取数据库 '{self.db_path}' 失败: {e}")
            sys.exit(1)

    def get_code_to_name_map(self) -> Dict[str, str]:
        """
        获取鸟种代码到中文名的映射

        Returns:
            {鸟种代码: 中文名} 的字典
        """
        if self._code_to_name_map is not None:
            return self._code_to_name_map

        birds = self.load_all_birds()
        self._code_to_name_map = {bird['code']: bird['cn_name'] for bird in birds}
        return self._code_to_name_map

    def get_code_to_full_name_map(self) -> Dict[str, Dict[str, str]]:
        """
        获取鸟种代码到中英文名的完整映射

        Returns:
            {鸟种代码: {'cn_name': 中文名, 'en_name': 英文名}} 的字典
        """
        birds = self.load_all_birds()
        return {bird['code']: {'cn_name': bird['cn_name'], 'en_name': bird['en_name']} for bird in birds}

    def find_species_by_name(self, query: str) -> List[Dict]:
        """
        根据名称模糊搜索鸟种

        Args:
            query: 搜索关键词（中文或英文）

        Returns:
            匹配的鸟种列表
        """
        query = query.lower().strip()
        if not query:
            return []

        birds = self.load_all_birds()
        matches = []

        for bird in birds:
            if query in bird['en_name'].lower() or query in bird['cn_name'].lower():
                matches.append(bird)

        return matches

    def fuzzy_search(self, query: str) -> List[Dict]:
        """
        模糊搜索鸟种（find_species_by_name 的别名，用于 Web API）

        Args:
            query: 搜索关键词（中文或英文）

        Returns:
            匹配的鸟种列表
        """
        return self.find_species_by_name(query)

    def select_species_interactive(self) -> Optional[Dict]:
        """
        交互式选择单个鸟种

        Returns:
            选中的鸟种信息或None
        """
        while True:
            query = input("\n请输入您想查询的鸟种名称 (中/英文模糊查询): ").strip()
            if not query:
                return None

            matches = self.find_species_by_name(query)

            if not matches:
                print("❌ 未找到匹配的鸟种，请尝试其他关键词。")
                continue

            if len(matches) == 1:
                bird = matches[0]
                confirm = input(
                    f"您要查询的是否为: {bird['cn_name']} ({bird['en_name']})? [Y/n]: "
                ).lower().strip()
                if confirm in ['', 'y', 'yes']:
                    return bird
                else:
                    continue

            # 多个匹配结果
            print("\n我们找到了多个可能的鸟种，请选择一个:")
            for i, bird in enumerate(matches, 1):
                print(f"  {i}. {bird['cn_name']} ({bird['en_name']})")

            while True:
                try:
                    choice_input = input("请输入编号进行选择 (或回车返回): ").strip()
                    if not choice_input:
                        break

                    choice = int(choice_input)
                    if 1 <= choice <= len(matches):
                        return matches[choice - 1]
                    else:
                        print(f"⚠️ 请输入1-{len(matches)}之间的数字。")
                except ValueError:
                    print("⚠️ 请输入有效的数字编号。")
                except (KeyboardInterrupt, EOFError):
                    print("\n❌ 用户中断操作")
                    return None

    def select_multiple_species_interactive(self) -> Optional[List[Dict]]:
        """
        交互式选择多个鸟种

        Returns:
            选中的鸟种列表或None
        """
        selected_species = []
        seen_codes = set()

        while True:
            query_str = input(
                "\n请输入您想查询的鸟种名称 (可输入多个，用英文逗号 ',' 分隔): "
            ).strip()

            if not query_str:
                if selected_species:
                    return selected_species
                return None

            queries = [q.strip() for q in query_str.split(',') if q.strip()]
            all_valid = True

            for query in queries:
                matches = self.find_species_by_name(query)

                if not matches:
                    print(f"❌ 未找到与 '{query}' 匹配的鸟种，请重新输入所有目标。")
                    all_valid = False
                    break

                if len(matches) == 1:
                    bird = matches[0]
                    if bird['code'] not in seen_codes:
                        selected_species.append(bird)
                        seen_codes.add(bird['code'])
                else:
                    # 多个匹配，让用户选择
                    print(f"\n对于查询 '{query}'，我们找到了多个可能的鸟种，请选择一个:")
                    for i, bird in enumerate(matches, 1):
                        print(f"  {i}. {bird['cn_name']} ({bird['en_name']})")

                    while True:
                        try:
                            choice_input = input("请输入编号进行选择: ").strip()
                            if not choice_input:
                                print("⚠️ 不能为空，请重新输入。")
                                continue

                            choice = int(choice_input)
                            if 1 <= choice <= len(matches):
                                bird = matches[choice - 1]
                                if bird['code'] not in seen_codes:
                                    selected_species.append(bird)
                                    seen_codes.add(bird['code'])
                                break
                            else:
                                print(f"⚠️ 请输入1-{len(matches)}之间的数字。")
                        except ValueError:
                            print("⚠️ 请输入有效的数字编号。")
                        except (KeyboardInterrupt, EOFError):
                            print("\n❌ 用户中断操作")
                            all_valid = False
                            break

                    if not all_valid:
                        break

            if not all_valid:
                selected_species.clear()
                seen_codes.clear()
                continue

            # 显示已选择的物种
            if selected_species:
                print("\n您已选择以下目标:")
                for bird in selected_species:
                    print(f"- {bird['cn_name']} ({bird['en_name']})")

                confirm = input("确认以上目标? [Y/n]: ").lower().strip()
                if confirm in ['', 'y', 'yes']:
                    return selected_species
                else:
                    selected_species.clear()
                    seen_codes.clear()

    def load_endemic_birds_map(self) -> Dict[str, List[Dict]]:
        """
        加载所有特有种信息到内存字典（用于快速查询）

        Returns:
            字典: {scientific_name: [{"country_code": "AU", "country_name_zh": "澳大利亚", ...}, ...]}

        性能优化：
        - 一次性加载全部特有种到内存（~3,000条记录，约0.6MB）
        - O(1) 查找时间复杂度
        - 应用启动时调用一次，运行期间无SQL开销
        """
        endemic_map = {}

        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                query = """
                    SELECT
                        eb.scientific_name,
                        eb.name_zh,
                        eb.name_en,
                        ec.country_code,
                        ec.country_name_zh,
                        ec.country_name_en
                    FROM endemic_birds eb
                    JOIN ebird_countries ec ON eb.country_id = ec.id
                    ORDER BY eb.scientific_name
                """
                cursor.execute(query)
                rows = cursor.fetchall()

                for row in rows:
                    sci_name = row['scientific_name']

                    # 标准化学名（去掉亚种后缀，仅保留属名+种名）
                    # 例如: "Dromaius novaehollandiae rothschildi" -> "Dromaius novaehollandiae"
                    parts = sci_name.split()
                    normalized_name = " ".join(parts[:2]) if len(parts) >= 2 else sci_name

                    endemic_info = {
                        'country_code': row['country_code'],
                        'country_name_zh': row['country_name_zh'],
                        'country_name_en': row['country_name_en'],
                        'name_zh': row['name_zh'],
                        'name_en': row['name_en']
                    }

                    # 支持一对多关系（某鸟可能是多个国家的特有种）
                    if normalized_name not in endemic_map:
                        endemic_map[normalized_name] = []
                    endemic_map[normalized_name].append(endemic_info)

                print(f"✅ 特有种数据已加载: {len(endemic_map)} 个物种，来自 {len(set(info['country_code'] for infos in endemic_map.values() for info in infos))} 个国家")

        except sqlite3.Error as e:
            print(f"⚠️ 加载特有种数据失败: {e}")
            print("   特有种标识功能将不可用")

        return endemic_map

    def get_endemic_info(self, scientific_name: str, endemic_map: Dict) -> Optional[List[Dict]]:
        """
        查询某个物种是否为特有种

        Args:
            scientific_name: 鸟类学名（如 "Dromaius novaehollandiae"）
            endemic_map: 特有种字典（由 load_endemic_birds_map() 返回）

        Returns:
            特有种信息列表，如果不是特有种则返回 None

            示例返回值:
            [
                {
                    "country_code": "AU",
                    "country_name_zh": "澳大利亚",
                    "country_name_en": "Australia",
                    "name_zh": "鸸鹋",
                    "name_en": "Emu"
                }
            ]
        """
        if not scientific_name or not endemic_map:
            return None

        # 标准化学名（去掉亚种后缀）
        parts = scientific_name.split()
        normalized_name = " ".join(parts[:2]) if len(parts) >= 2 else scientific_name

        return endemic_map.get(normalized_name)
