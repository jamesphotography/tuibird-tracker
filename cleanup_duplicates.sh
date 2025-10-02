#!/bin/bash
# 清理重复文件脚本
# 使用前请仔细检查，确保不会删除重要文件

echo "🧹 TuiBird Tracker 项目清理脚本"
echo "================================"
echo ""
echo "⚠️  警告：此脚本将删除根目录下的重复文件"
echo "建议先备份项目，或使用 git 进行版本控制"
echo ""

# 检查是否在正确的目录
if [ ! -f "ebird_reference.sqlite" ]; then
    echo "❌ 错误：请在项目根目录运行此脚本"
    exit 1
fi

# 询问用户确认
read -p "是否继续? [y/N]: " confirm
if [[ ! $confirm =~ ^[Yy]$ ]]; then
    echo "取消清理操作"
    exit 0
fi

echo ""
echo "开始清理..."
echo ""

# 创建备份目录
backup_dir="backup_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$backup_dir"
echo "✅ 创建备份目录: $backup_dir"

# 需要删除的重复文件列表（根目录下的文件）
files_to_backup=(
    "bird_region_query.py"
    "bird_tracker.py"
    "bird_tracker_unified.py"
    "main.py"
    "simple_final.py"
)

# 备份并删除
for file in "${files_to_backup[@]}"; do
    if [ -f "$file" ]; then
        echo "📦 备份: $file -> $backup_dir/"
        cp "$file" "$backup_dir/"
        echo "🗑️  删除: $file"
        rm "$file"
    else
        echo "⏭️  跳过: $file (文件不存在)"
    fi
done

# 清理旧的launcher文件（可选）
launcher_files=(
    "src/app_launcher.py"
    "src/simple_launcher.py"
    "src/terminal_launcher.py"
)

echo ""
echo "📋 以下launcher文件可能不再需要："
for file in "${launcher_files[@]}"; do
    if [ -f "$file" ]; then
        echo "  - $file"
    fi
done

read -p "是否也删除这些文件? [y/N]: " confirm_launcher
if [[ $confirm_launcher =~ ^[Yy]$ ]]; then
    for file in "${launcher_files[@]}"; do
        if [ -f "$file" ]; then
            cp "$file" "$backup_dir/"
            rm "$file"
            echo "🗑️  删除: $file"
        fi
    done
fi

# 清理 __pycache__
echo ""
echo "🧹 清理 Python 缓存文件..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find . -type f -name "*.pyc" -delete 2>/dev/null
echo "✅ 缓存文件已清理"

# 清理重复的配置文件
if [ -f "config/ebird_config.json" ] && [ -f "ebird_config.json" ]; then
    echo ""
    echo "⚠️  发现重复的配置文件:"
    echo "  - config/ebird_config.json"
    echo "  - ebird_config.json"
    read -p "保留根目录的配置文件，删除config目录下的? [y/N]: " confirm_config
    if [[ $confirm_config =~ ^[Yy]$ ]]; then
        cp "config/ebird_config.json" "$backup_dir/"
        rm "config/ebird_config.json"
        echo "🗑️  删除: config/ebird_config.json"
    fi
fi

echo ""
echo "================================"
echo "✅ 清理完成！"
echo ""
echo "📦 备份文件保存在: $backup_dir/"
echo "💡 如需恢复，请从备份目录复制文件"
echo ""
echo "📁 当前项目结构："
ls -lh src/*.py | awk '{printf "  %-30s %s\n", $9, $5}'
echo ""
echo "✨ 核心模块："
echo "  - src/config.py          (配置管理)"
echo "  - src/utils.py           (工具函数)"
echo "  - src/database.py        (数据库操作)"
echo "  - src/api_client.py      (API客户端)"
echo "  - src/bird_tracker_unified.py"
echo "  - src/bird_region_query.py"
echo "  - src/main.py            (主菜单)"
echo ""
