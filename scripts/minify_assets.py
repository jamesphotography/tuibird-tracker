#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
前端资源压缩工具
自动压缩 CSS 和 JS 文件，减少文件大小，提升加载速度
"""

import rcssmin
import rjsmin
import os
import sys

def get_file_size(file_path):
    """获取文件大小（KB）"""
    return os.path.getsize(file_path) / 1024

def minify_css(input_file, output_file):
    """
    压缩 CSS 文件

    Args:
        input_file: 输入 CSS 文件路径
        output_file: 输出压缩后的 CSS 文件路径
    """
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            css = f.read()

        # 压缩 CSS
        minified = rcssmin.cssmin(css)

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(minified)

        # 计算压缩率
        original_size = len(css) / 1024
        minified_size = len(minified) / 1024
        reduction = (1 - minified_size / original_size) * 100

        print(f"✅ CSS 压缩完成")
        print(f"   输入:  {input_file}")
        print(f"   输出:  {output_file}")
        print(f"   原始:  {original_size:.2f} KB")
        print(f"   压缩:  {minified_size:.2f} KB")
        print(f"   减少:  {reduction:.1f}%")
        print()

        return True

    except Exception as e:
        print(f"❌ CSS 压缩失败: {e}")
        return False

def minify_js(input_file, output_file):
    """
    压缩 JS 文件

    Args:
        input_file: 输入 JS 文件路径
        output_file: 输出压缩后的 JS 文件路径
    """
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            js = f.read()

        # 压缩 JS
        minified = rjsmin.jsmin(js)

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(minified)

        # 计算压缩率
        original_size = len(js) / 1024
        minified_size = len(minified) / 1024
        reduction = (1 - minified_size / original_size) * 100

        print(f"✅ JS 压缩完成")
        print(f"   输入:  {input_file}")
        print(f"   输出:  {output_file}")
        print(f"   原始:  {original_size:.2f} KB")
        print(f"   压缩:  {minified_size:.2f} KB")
        print(f"   减少:  {reduction:.1f}%")
        print()

        return True

    except Exception as e:
        print(f"❌ JS 压缩失败: {e}")
        return False

def main():
    """主函数"""
    print("="*60)
    print("前端资源压缩工具")
    print("="*60)
    print()

    # 获取项目根目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)

    # 定义文件路径
    css_input = os.path.join(project_root, 'src/static/css/style.css')
    css_output = os.path.join(project_root, 'src/static/css/style.min.css')
    js_input = os.path.join(project_root, 'src/static/js/app.js')
    js_output = os.path.join(project_root, 'src/static/js/app.min.js')

    # 检查输入文件是否存在
    if not os.path.exists(css_input):
        print(f"❌ 错误: CSS 文件不存在: {css_input}")
        sys.exit(1)

    if not os.path.exists(js_input):
        print(f"❌ 错误: JS 文件不存在: {js_input}")
        sys.exit(1)

    # 执行压缩
    success_count = 0

    if minify_css(css_input, css_output):
        success_count += 1

    if minify_js(js_input, js_output):
        success_count += 1

    # 总结
    print("="*60)
    if success_count == 2:
        print("🎉 所有文件压缩成功！")
        print()
        print("下一步:")
        print("1. 检查压缩后的文件是否正常")
        print("2. 更新 base.html 以使用压缩版本")
        print("3. 设置 DEBUG=False 环境变量以启用压缩版本")
    else:
        print(f"⚠️  部分文件压缩失败（成功 {success_count}/2）")

    print("="*60)

if __name__ == '__main__':
    main()
