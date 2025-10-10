#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
eBird CLI 追踪器 macOS .app 启动器
直接在当前进程中运行主程序，避免依赖库问题
"""

import os
import sys
import subprocess

def main():
    """主启动函数"""
    try:
        print("🚀 启动 eBird 追踪器...")
        print(f"📍 工作目录: {os.getcwd()}")
        print("")

        # 直接导入并运行主程序模块
        # 这样可以确保所有依赖库都在同一个进程中
        import main as main_module

        # 检查是否有main函数
        if hasattr(main_module, 'main'):
            main_module.main()
        else:
            # 如果没有main函数，尝试直接运行模块
            # 注意：避免使用exec()，这是不安全的做法
            raise ImportError("main.py 缺少 main() 函数入口")
        
    except ImportError as e:
        error_msg = f"模块导入错误: {str(e)}"
        print(f"❌ {error_msg}")
        try:
            subprocess.run([
                'osascript', '-e',
                f'display dialog "{error_msg}" with title "eBird 追踪器错误" buttons {{"确定"}} default button "确定"'
            ])
        except:
            pass
    except Exception as e:
        error_msg = f"启动错误: {str(e)}"
        print(f"❌ {error_msg}")
        import traceback
        traceback.print_exc()
        try:
            subprocess.run([
                'osascript', '-e',
                f'display dialog "{error_msg}" with title "eBird 追踪器错误" buttons {{"确定"}} default button "确定"'
            ])
        except:
            pass

if __name__ == '__main__':
    main()