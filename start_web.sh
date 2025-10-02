#!/bin/bash
# TuiBird Tracker Web App 启动脚本

echo "=========================================="
echo "🦅 TuiBird Tracker Web 界面启动脚本"
echo "=========================================="

# 检查 Python 版本
if ! command -v python3 &> /dev/null; then
    echo "❌ 错误: 未找到 Python 3"
    echo "请先安装 Python 3.8 或更高版本"
    exit 1
fi

# 检查 Flask 是否安装
if ! python3 -c "import flask" &> /dev/null; then
    echo "⚠️  Flask 未安装，正在安装依赖..."
    pip3 install -r requirements.txt
fi

echo ""
echo "✅ 环境检查通过"
echo ""
echo "🚀 启动 Web 服务器..."
echo "📍 访问地址: http://127.0.0.1:5001"
echo "🔑 按 Ctrl+C 停止服务器"
echo "💡 注意：使用 5001 端口，避免与 macOS AirPlay 冲突"
echo ""

# 启动 Flask 应用
python3 src/web_app.py
