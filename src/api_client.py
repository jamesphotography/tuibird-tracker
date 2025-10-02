#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
eBird API客户端模块
统一管理所有与eBird API的交互
"""

import requests
from typing import List, Dict, Optional, Any
from datetime import datetime
from config import (
    EBIRD_API_BASE_URL,
    API_TIMEOUT,
    ConfigManager
)


class EBirdAPIClient:
    """eBird API客户端"""

    def __init__(self, api_key: str):
        """
        初始化API客户端

        Args:
            api_key: eBird API密钥
        """
        self.api_key = api_key
        self.headers = {'X-eBirdApiToken': api_key}
        self.base_url = EBIRD_API_BASE_URL

    def _make_request(
        self,
        endpoint: str,
        params: Optional[Dict] = None,
        timeout: int = API_TIMEOUT
    ) -> Optional[Any]:
        """
        发起API请求的通用方法

        Args:
            endpoint: API端点
            params: 请求参数
            timeout: 超时时间（秒）

        Returns:
            响应JSON数据或None
        """
        url = f"{self.base_url}/{endpoint}"

        try:
            response = requests.get(
                url,
                headers=self.headers,
                params=params,
                timeout=timeout
            )

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 401:
                print("❌ API Key无效或已过期")
                return None
            elif response.status_code == 403:
                print("❌ API Key权限不足")
                return None
            elif response.status_code == 404:
                print("⚠️ 未找到相关数据")
                return None
            else:
                print(f"⚠️ API请求失败，状态码: {response.status_code}")
                return None

        except requests.exceptions.Timeout:
            print(f"❌ 请求超时（{timeout}秒）")
            return None
        except requests.exceptions.RequestException as e:
            print(f"❌ 网络请求出错: {e}")
            return None

    def validate_api_key(self) -> tuple[bool, str]:
        """
        验证API Key是否有效

        Returns:
            (是否有效, 消息)
        """
        if not self.api_key or len(self.api_key.strip()) < 8:
            return False, "API Key格式不正确（太短）"

        print("🔍 正在验证API Key...")
        endpoint = "ref/taxonomy/ebird"
        params = {'fmt': 'json', 'limit': 1}

        try:
            response = requests.get(
                f"{self.base_url}/{endpoint}",
                headers=self.headers,
                params=params,
                timeout=10
            )

            if response.status_code == 200:
                return True, "API Key验证成功！"
            elif response.status_code == 401:
                return False, "API Key无效或已过期"
            elif response.status_code == 403:
                return False, "API Key权限不足"
            else:
                return False, f"API验证失败 (状态码: {response.status_code})"

        except requests.exceptions.RequestException as e:
            return False, f"网络连接失败: {e}"

    def get_recent_observations_by_species(
        self,
        species_code: str,
        region_code: str = "AU",
        days_back: int = 14
    ) -> Optional[List[Dict]]:
        """
        获取特定物种在某区域的最近观测记录

        Args:
            species_code: 物种代码
            region_code: 区域代码（如"AU"代表澳大利亚）
            days_back: 查询最近几天的记录

        Returns:
            观测记录列表或None
        """
        endpoint = f"data/obs/{region_code}/recent/{species_code}"
        params = {
            'back': days_back,
            'detail': 'full'
        }
        return self._make_request(endpoint, params)

    def get_recent_observations_by_location(
        self,
        lat: float,
        lng: float,
        radius: int = 25,
        days_back: int = 14,
        species_code: Optional[str] = None
    ) -> Optional[List[Dict]]:
        """
        获取指定地理位置周围的观测记录

        Args:
            lat: 纬度
            lng: 经度
            radius: 搜索半径（公里）
            days_back: 查询最近几天的记录
            species_code: 可选的物种代码

        Returns:
            观测记录列表或None
        """
        if species_code:
            endpoint = f"data/obs/geo/recent/{species_code}"
        else:
            endpoint = "data/obs/geo/recent"

        params = {
            'lat': lat,
            'lng': lng,
            'dist': radius,
            'back': days_back,
            'detail': 'full'
        }
        return self._make_request(endpoint, params)

    def get_checklist_details(self, sub_id: str) -> Optional[Dict]:
        """
        获取观测清单的详细信息

        Args:
            sub_id: 清单ID

        Returns:
            清单详细信息或None
        """
        endpoint = f"product/checklist/view/{sub_id}"
        return self._make_request(endpoint, timeout=8)

    def search_hotspots(
        self,
        query: str,
        region_code: str = "world"
    ) -> Optional[List[Dict]]:
        """
        搜索eBird热点

        Args:
            query: 搜索关键词
            region_code: 区域代码

        Returns:
            热点列表或None
        """
        endpoint = "ref/hotspot/find"
        params = {
            'q': query,
            'fmt': 'json'
        }
        return self._make_request(endpoint, params)

    def get_hotspot_observations(
        self,
        location_id: str,
        days_back: int = 14
    ) -> Optional[List[Dict]]:
        """
        获取指定热点的所有观测记录

        Args:
            location_id: 热点ID
            days_back: 查询最近几天的记录

        Returns:
            观测记录列表或None
        """
        endpoint = f"data/obs/{location_id}/recent"
        params = {
            'back': days_back,
            'detail': 'full'
        }
        return self._make_request(endpoint, params, timeout=30)


# ==================== API Key管理 ====================

def setup_api_key_interactive(config_manager: ConfigManager) -> Optional[str]:
    """
    交互式设置API Key

    Args:
        config_manager: 配置管理器实例

    Returns:
        API Key或None
    """
    print("\n🔑 eBird API Key 设置")
    print("=" * 30)

    current_api_key = config_manager.get_api_key()

    if current_api_key:
        print(f"\n当前API Key: {current_api_key[:4]}...{current_api_key[-4:]}")
        choice = input("\n要更换API Key吗？[y/N]: ").lower().strip()
        if choice not in ['y', 'yes']:
            return current_api_key

    while True:
        print("\n请选择操作：")
        print("1. 输入现有的API Key")
        print("2. 查看API Key申请指南")
        print("0. 退出程序")

        choice = input("\n请输入选择 [1]: ").strip() or '1'

        if choice == '1':
            api_key = input("\n请输入您的eBird API Key: ").strip()
            if api_key:
                client = EBirdAPIClient(api_key)
                is_valid, message = client.validate_api_key()
                print(f"\n{message}")

                if is_valid:
                    config_manager.set_api_key(api_key)
                    if config_manager.save():
                        print("✅ API Key已保存到配置文件")
                    return api_key
                else:
                    print("❌ API Key验证失败，请重试")
                    continue
            else:
                print("❌ API Key不能为空")
                continue

        elif choice == '2':
            show_api_key_guide()
            input("\n按回车键继续...")
            continue

        elif choice == '0':
            print("\n👋 感谢使用，再见！")
            return None

        else:
            print("❌ 无效选择，请重试")
            continue


def get_api_key_with_validation(config_manager: ConfigManager) -> str:
    """
    获取API Key并进行智能验证

    Args:
        config_manager: 配置管理器实例

    Returns:
        有效的API Key
    """
    api_key = config_manager.get_api_key()

    if api_key:
        # 检查是否需要重新验证
        should_validate = config_manager.should_revalidate_api_key()

        if not should_validate:
            # 使用缓存的API Key
            print(f"✅ 使用已保存的API Key: {api_key[:4]}...{api_key[-4:]}")
            return api_key
        else:
            # 需要重新验证
            print("🔍 检查API Key有效性...")
            client = EBirdAPIClient(api_key)
            is_valid, message = client.validate_api_key()

            if is_valid:
                # 更新最后验证时间
                config_manager.update_last_validated()
                config_manager.save()
                print(f"✅ API Key验证通过: {api_key[:4]}...{api_key[-4:]}")
                return api_key
            else:
                print(f"⚠️ 已保存的API Key无效: {message}")

    # 如果没有有效的API Key，则进行设置
    api_key = setup_api_key_interactive(config_manager)
    if not api_key:
        import sys
        sys.exit(0)
    return api_key


def show_api_key_guide() -> None:
    """显示API Key申请指南"""
    print("\n📋 eBird API Key 申请指南")
    print("=" * 50)
    print("\n🔗 申请步骤：")
    print("1. 访问 eBird 网站: https://ebird.org")
    print("2. 点击右上角登录，创建账户或登录现有账户")
    print("3. 登录后，直接访问 API 申请页面: https://ebird.org/api/keygen")
    print("4. 或者点击页面底部的 'Developers' 链接，然后选择 'Request an API Key'")
    print("5. 填写申请表单（以下为详细指导）")
    print("6. 提交申请并等待审批（通常即时至几小时）")
    print("7. 审批通过后，您会收到包含API Key的邮件")

    print("\n📝 表单填写指导：")
    print("- First Name: 填写您的名字")
    print("- Last Name: 填写您的姓氏")
    print("- Email: 与您eBird账户相同的邮箱")
    print("- Intended Use: 选择 'Personal Use' 或 'Research/Education'")
    print("- Project Title: 例如 '个人观鸟记录查询' 或 'Bird Tracking Tool'")
    print("- Project Description: 例如 '用于查询和分析特定地区的观鸟记录'")
    print("- Estimated monthly requests: 选择 '1-100' 或 '101-1000'")

    print("\n💡 申请技巧：")
    print("- 给出具体的项目描述，例如观鸟路线规划、科研分析等")
    print("- 估计请求量不要过高，新用户建议选择较低档位")
    print("- 使用真实信息，不要随意填写")
    print("- 如果被拒绝，可以修改项目描述后再次申请")

    print("\n🔑 API Key 格式：")
    print("- 通常是一串字母和数字组合")
    print("- 长度大约10-15个字符")
    print("- 示例格式：abc123def456")

    print("\n⚠️  重要提醒：")
    print("- 请勿分享您的API Key")
    print("- API Key有使用频率限制（每小时100-1000次请求）")
    print("- 遵守eBird API使用条款")
    print("- 不要用于商业目的")

    print("\n🚫 常见问题：")
    print("- 如果申请被拒：检查项目描述是否清晰，避免使用模糊语言")
    print("- 如果没收到邮件：检查垃圾邮件夹，或重新申请")
    print("- API Key不工作：检查网络连接，或联系eBird支持")
    print("=" * 50)
