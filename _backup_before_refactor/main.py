#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
eBird CLI 追踪器 V2.0
统一的命令行入口程序

功能:
- 鸟类追踪器（支持单一或多物种）

作者: TuiBird Tracker
版本: 2.0
"""

# 抑制SSL警告
import warnings
warnings.filterwarnings('ignore', message='urllib3 v2 only supports OpenSSL 1.1.1+')

import os
import sys
import subprocess
from datetime import datetime

# 为 PyInstaller 打包后的环境添加模块搜索路径
if getattr(sys, '_MEIPASS', None):
    # PyInstaller 打包后的环境
    if sys._MEIPASS not in sys.path:
        sys.path.insert(0, sys._MEIPASS)


def get_resource_path(relative_path):
    """获取资源文件的正确路径，支持开发和打包后的环境"""
    try:
        # PyInstaller 打包后的路径
        base_path = getattr(sys, '_MEIPASS', None)
        if base_path is None:
            raise AttributeError
    except AttributeError:
        # 开发环境的路径
        base_path = os.path.dirname(os.path.abspath(__file__))
    
    return os.path.join(base_path, relative_path)


def print_banner():
    """打印程序标题"""
    print("=" * 60)
    print("🦅 eBird CLI 追踪器 V2.0")
    print("=" * 60)
    print(f"当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"工作目录: {os.getcwd()}")
    print("=" * 60)


def check_environment():
    """检查运行环境"""
    print("🔍 检查运行环境...")
    
    # 检查数据库文件
    db_file = get_resource_path("ebird_reference.sqlite")
    if not os.path.exists(db_file):
        print(f"❌ 错误: 未找到数据库文件 'ebird_reference.sqlite'")
        print("请确保数据库文件在当前目录中")
        return False
    else:
        print(f"✅ 数据库文件: ebird_reference.sqlite")
    
    # 检查核心程序文件
    required_files = [
        "bird_tracker_unified.py",
        "bird_region_query.py"
    ]
    
    missing_files = []
    for file in required_files:
        file_path = get_resource_path(file)
        if os.path.exists(file_path):
            print(f"✅ 程序文件: {file}")
        else:
            print(f"❌ 缺失文件: {file}")
            missing_files.append(file)
    
    if missing_files:
        print(f"\n❌ 缺失重要文件: {', '.join(missing_files)}")
        return False
    
    print("\n✅ 环境检查通过！")
    return True


def show_main_menu():
    """显示主菜单"""
    print("\n📋 请选择功能:")
    print("1. 🎯 鸟类追踪器 - 支持单一或多物种")
    print("2. 🌍 区域鸟种查询 - 根据区域显示所有鸟种记录")
    print("3. 🔑 API Key管理")
    print("4. 📁 打开输出文件夹")
    print("5. ❓ 使用帮助")
    print("0. 退出程序")
    print("-" * 40)


def run_program(script_name):
    """运行指定的程序"""
    try:
        print(f"\n🚀 启动 {script_name}...")
        print("=" * 40)
        
        # 根据脚本名称直接调用对应的模块
        if script_name == "bird_tracker_unified.py":
            # 导入并运行鸟类追踪器
            import bird_tracker_unified
            bird_tracker_unified.main()
        elif script_name == "bird_region_query.py":
            # 导入并运行区域查询
            import bird_region_query
            bird_region_query.main()
        else:
            print(f"❌ 未知的程序: {script_name}")
            
        print("\n" + "=" * 40)
        print(f"✅ {script_name} 执行完成")
        
    except KeyboardInterrupt:
        print(f"\n⚠️ {script_name} 被用户中断")
    except Exception as e:
        print(f"\n❌ 运行 {script_name} 时出错: {e}")
        import traceback
        traceback.print_exc()
    
    input("\n按回车键返回主菜单...")


def open_output_folder():
    """打开输出文件夹"""
    output_dir = "output"
    try:
        if os.path.exists(output_dir):
            if sys.platform == "darwin":  # macOS
                subprocess.run(["open", output_dir])
            elif sys.platform == "win32":  # Windows
                subprocess.run(["explorer", output_dir])
            else:  # Linux
                subprocess.run(["xdg-open", output_dir])
            print(f"✅ 已打开输出文件夹: {output_dir}")
        else:
            print(f"⚠️ 输出文件夹不存在: {output_dir}")
            print("运行追踪程序后会自动创建该文件夹")
    except Exception as e:
        print(f"❌ 打开文件夹失败: {e}")
    
    input("按回车键返回主菜单...")


def manage_api_key():
    """管理API Key（带智能缓存机制）"""
    import json
    import requests
    
    config_file = "ebird_config.json"
    
    def load_config():
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                print("⚠️ 配置文件损坏，将重新创建。")
        return {}
    
    def save_config(config):
        try:
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
            return True
        except IOError:
            print("❌ 保存配置文件失败！")
            return False
    
    def should_revalidate_api_key(config):
        """判断是否需要重新验证API Key（智能缓存策略）"""
        from datetime import datetime, timedelta
        
        # 如果没有last_validated字段，需要验证
        if 'last_validated' not in config:
            return True
        
        try:
            last_validated = datetime.fromisoformat(config['last_validated'])
            now = datetime.now()
            
            # 如果距离上次验证超过24小时，需要重新验证
            validation_interval = timedelta(hours=24)
            if now - last_validated > validation_interval:
                return True
            
            return False
        except (ValueError, TypeError):
            # 如果时间格式错误，需要重新验证
            return True
    
    def validate_api_key(api_key, force_validate=False):
        """验证API Key是否有效（支持智能缓存）"""
        if not api_key or len(api_key.strip()) < 8:
            return False, "API Key格式不正确（太短）"
        
        # 如果不是强制验证，检查缓存
        if not force_validate:
            config = load_config()
            if not should_revalidate_api_key(config):
                return True, "API Key缓存有效（跳过网络验证）"
        
        # 测试API Key是否有效
        test_url = "https://api.ebird.org/v2/ref/taxonomy/ebird?fmt=json&limit=1"
        headers = {'X-eBirdApiToken': api_key.strip()}
        
        try:
            print("🔍 正在验证API Key...")
            response = requests.get(test_url, headers=headers, timeout=10)
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
    
    config = load_config()
    
    print("\n🔑 API Key 管理")
    print("=" * 30)
    
    if 'api_key' in config:
        print(f"\n当前API Key: {config['api_key'][:4]}...{config['api_key'][-4:]}")
        if 'setup_date' in config:
            print(f"设置时间: {config['setup_date'][:19]}")
        
        print("\n请选择操作:")
        print("1. 查看完整API Key")
        print("2. 更换API Key")
        print("3. 删除API Key")
        print("4. 强制验证API Key（忽略缓存）")
        print("5. 查看API Key申请指南")
        print("0. 返回主菜单")
        
        choice = input("\n请选择: ").strip()
        
        if choice == '1':
            print(f"\n完整API Key: {config['api_key']}")
        elif choice == '2':
            new_key = input("\n请输入新的API Key: ").strip()
            if new_key:
                is_valid, message = validate_api_key(new_key, force_validate=True)
                print(f"\n{message}")
                if is_valid:
                    config['api_key'] = new_key
                    config['setup_date'] = datetime.now().isoformat()
                    config['last_validated'] = datetime.now().isoformat()
                    if save_config(config):
                        print("✅ API Key已更新")
                    else:
                        print("❌ 更新失败")
                else:
                    print("❌ API Key验证失败，未更新")
            else:
                print("❌ API Key不能为空")
        elif choice == '3':
            confirm = input("确认删除API Key? [y/N]: ").lower().strip()
            if confirm in ['y', 'yes']:
                if 'api_key' in config:
                    del config['api_key']
                if 'setup_date' in config:
                    del config['setup_date']
                if 'last_validated' in config:
                    del config['last_validated']
                if save_config(config):
                    print("✅ API Key已删除")
                else:
                    print("❌ 删除失败")
        elif choice == '4':
            if 'api_key' in config:
                is_valid, message = validate_api_key(config['api_key'], force_validate=True)
                print(f"\n{message}")
                if is_valid:
                    config['last_validated'] = datetime.now().isoformat()
                    save_config(config)
            else:
                print("❌ 没有可验证的API Key")
        elif choice == '5':
            show_api_guide()
    else:
        print("\n⚠️ 尚未设置API Key")
        print("\n请选择操作:")
        print("1. 输入API Key")
        print("2. 查看API Key申请指南")
        print("0. 返回主菜单")
        
        choice = input("\n请选择: ").strip()
        
        if choice == '1':
            api_key = input("\n请输入您的eBird API Key: ").strip()
            if api_key:
                is_valid, message = validate_api_key(api_key, force_validate=True)
                print(f"\n{message}")
                if is_valid:
                    config['api_key'] = api_key
                    config['setup_date'] = datetime.now().isoformat()
                    config['last_validated'] = datetime.now().isoformat()
                    if save_config(config):
                        print("✅ API Key已保存")
                    else:
                        print("❌ 保存失败")
                else:
                    print("❌ API Key验证失败，未保存")
            else:
                print("❌ API Key不能为空")
        elif choice == '2':
            show_api_guide()
    
    input("\n按回车键返回主菜单...")


def show_api_guide():
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


def show_help():
    """显示使用帮助"""
    print("\n📖 使用帮助")
    print("=" * 40)
    print("\n🎯 鸟类追踪器:")
    print("   - 支持单一物种深度追踪和多物种情报分析")
    print("   - 智能选择追踪模式，更好的用户体验")
    print("   - 提供观测地点、时间、频率等详细信息")
    print("   - 支持保存搜索配置，适合观鸟路线规划")
    print("   - 生成专业的Markdown格式观鸟报告")
    
    print("\n🌍 区域鸟种查询:")
    print("   - 根据用户输入的区域，显示该区域内所有鸟种的最近观测记录")
    print("   - 支持地名和GPS坐标输入")
    print("   - 生成“鸟类摄影作战简报”格式报告")
    print("   - 按鸟种分类显示观测地点、时间、数量等信息")
    print("   - 适合快速了解某个区域的鸟类分布情况")
    
    print("\n💡 使用提示:")
    print("   - 程序会自动创建output文件夹保存报告")
    print("   - 支持中英文鸟种名称搜索")
    print("   - 需要网络连接获取eBird数据")
    print("   - 首次使用建议先进行环境检查")
    
    print("\n🔄 使用流程:")
    print("   1. 选择追踪模式（单一或多物种）")
    print("   2. 输入鸟种名称（支持中英文模糊搜索）")
    print("   3. 选择时间范围和搜索区域")
    print("   4. 等待程序生成详细报告")
    
    input("\n按回车键返回主菜单...")


def main():
    """主程序"""
    try:
        # 清屏
        os.system('clear' if os.name == 'posix' else 'cls')
        
        # 显示程序标题
        print_banner()
        
        # 检查环境
        if not check_environment():
            print("\n❌ 环境检查失败，程序退出")
            sys.exit(1)
        
        # 主循环
        while True:
            show_main_menu()
            
            try:
                choice = input("请输入选择 (0-5): ").strip()
                
                if choice == '0':
                    print("\n👋 感谢使用 eBird CLI 追踪器！")
                    break
                elif choice == '1':
                    run_program("bird_tracker_unified.py")
                elif choice == '2':
                    run_program("bird_region_query.py")
                elif choice == '3':
                    manage_api_key()
                elif choice == '4':
                    open_output_folder()
                elif choice == '5':
                    show_help()
                else:
                    print("⚠️ 无效选择，请输入 0-5 之间的数字")
                    input("按回车键继续...")
                    
            except KeyboardInterrupt:
                print("\n\n👋 程序被用户中断，退出")
                break
            except EOFError:
                print("\n\n👋 输入结束，程序退出")
                break
            
            # 清屏准备下次循环
            os.system('clear' if os.name == 'posix' else 'cls')
            print_banner()
    
    except Exception as e:
        print(f"\n❌ 程序运行时出现错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()