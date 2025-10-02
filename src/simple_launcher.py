#!/usr/bin/env python3
# -*- coding: utf-8 -*-
\"\"\"
eBird CLI 追踪器启动器
直接在终端中运行主程序
\"\"\"

import os
import sys
import subprocess

def main():
    \"\"\"启动主程序\"\"\"
    try:
        # 获取应用程序目录
        if getattr(sys, '_MEIPASS', None):
            app_dir = sys._MEIPASS
        else:
            app_dir = os.path.dirname(os.path.abspath(__file__))
        
        # 主程序路径
        main_script = os.path.join(app_dir, 'main.py')
        
        # 直接在当前终端中运行
        if os.path.exists(main_script):
            # 方法1：直接执行Python脚本
            os.system(f'cd \"{os.path.dirname(app_dir)}\" && python3 \"{main_script}\"')
        else:
            print(\"错误：未找到主程序文件\")
            print(f\"查找路径: {main_script}\")
            input(\"按回车键退出...\")
            
    except Exception as e:
        print(f\"启动错误: {e}\")
        input(\"按回车键退出...\")

if __name__ == '__main__':
    main()