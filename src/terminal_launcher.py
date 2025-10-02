#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
eBird CLI 追踪器终端启动器
点击.app时自动在新终端窗口中运行程序
"""

import os
import sys
import subprocess
import tempfile

def main():
    """启动器主函数"""
    try:
        # 获取应用程序路径
        if getattr(sys, '_MEIPASS', None):
            app_dir = sys._MEIPASS
        else:
            app_dir = os.path.dirname(os.path.abspath(__file__))
        
        # 主程序路径
        main_script = os.path.join(app_dir, 'main.py')
        
        if not os.path.exists(main_script):
            print(f"错误：未找到主程序文件 {main_script}")
            return
        
        # 直接导入并运行主程序，而不是创建子进程
        print("🚀 启动 eBird 追踪器...")
        print(f"📍 工作目录: {os.getcwd()}")
        print("")
        
        # 直接导入主模块并运行
        import main as main_module
        main_module.main()
        
    except Exception as e:
        # 如果启动失败，显示错误对话框
        error_msg = f"eBird 追踪器启动失败: {str(e)}"
        print(error_msg)
        import traceback
        traceback.print_exc()
        try:
            subprocess.run([
                'osascript', '-e',
                f'display dialog "{error_msg}" with title "启动错误" buttons {{"确定"}} default button "确定"'
            ])
        except:
            pass
        input("按回车键退出...")

if __name__ == '__main__':
    main()