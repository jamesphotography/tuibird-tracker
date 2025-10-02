#!/bin/bash

# TuiBird Tracker - Render.com 部署脚本

echo "🦅 TuiBird Tracker - Render 部署助手"
echo "===================================="
echo ""

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 步骤 1: 检查 Git 是否初始化
if [ ! -d .git ]; then
    echo -e "${YELLOW}⚠️  检测到未初始化 Git 仓库${NC}"
    read -p "是否初始化 Git 仓库? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        git init
        echo -e "${GREEN}✓ Git 仓库初始化成功${NC}"
    else
        echo -e "${RED}✗ 已取消部署${NC}"
        exit 1
    fi
fi

# 步骤 2: 检查 Git LFS
echo ""
echo "📦 检查 Git LFS..."
if ! command -v git-lfs &> /dev/null; then
    echo -e "${YELLOW}⚠️  Git LFS 未安装${NC}"
    echo ""
    echo "请先安装 Git LFS:"
    echo "  macOS:   brew install git-lfs"
    echo "  Linux:   sudo apt-get install git-lfs"
    echo "  Windows: 访问 https://git-lfs.github.com/"
    echo ""
    read -p "已安装 Git LFS? 按任意键继续... " -n 1 -r
    echo
fi

git lfs install
echo -e "${GREEN}✓ Git LFS 已配置${NC}"

# 步骤 3: 检查必要文件
echo ""
echo "📋 检查必要文件..."

files=("requirements.txt" "render.yaml" ".gitignore" ".gitattributes" "ebird_reference.sqlite")
missing_files=()

for file in "${files[@]}"; do
    if [ -f "$file" ]; then
        echo -e "${GREEN}✓${NC} $file"
    else
        echo -e "${RED}✗${NC} $file (缺失)"
        missing_files+=("$file")
    fi
done

if [ ${#missing_files[@]} -ne 0 ]; then
    echo -e "${RED}错误: 缺少必要文件，请先完成配置${NC}"
    exit 1
fi

# 步骤 4: 添加文件到 Git
echo ""
echo "📝 添加文件到 Git..."
git add .
echo -e "${GREEN}✓ 文件已添加${NC}"

# 步骤 5: 提交
echo ""
read -p "📝 输入提交信息 (默认: Ready for Render deployment): " commit_msg
commit_msg=${commit_msg:-"Ready for Render deployment"}

git commit -m "$commit_msg"
echo -e "${GREEN}✓ 提交成功${NC}"

# 步骤 6: 询问远程仓库
echo ""
echo "🌐 配置远程仓库"
echo ""
git remote -v

if [ -z "$(git remote)" ]; then
    echo -e "${YELLOW}⚠️  未检测到远程仓库${NC}"
    echo ""
    read -p "输入 GitHub 仓库 URL (例如: https://github.com/username/tuibird-tracker.git): " repo_url

    if [ ! -z "$repo_url" ]; then
        git remote add origin "$repo_url"
        echo -e "${GREEN}✓ 远程仓库已添加${NC}"
    else
        echo -e "${RED}✗ 未提供仓库 URL${NC}"
        exit 1
    fi
fi

# 步骤 7: 推送到 GitHub
echo ""
echo "🚀 推送到 GitHub..."
git branch -M main
git push -u origin main

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ 推送成功！${NC}"
else
    echo -e "${RED}✗ 推送失败，请检查网络和仓库权限${NC}"
    exit 1
fi

# 步骤 8: 显示后续步骤
echo ""
echo "===================================="
echo -e "${GREEN}🎉 本地准备完成！${NC}"
echo "===================================="
echo ""
echo "📝 接下来的步骤:"
echo ""
echo "1. 访问 https://render.com/"
echo "2. 使用 GitHub 登录"
echo "3. 点击 'New +' → 'Web Service'"
echo "4. 选择你的仓库: tuibird-tracker"
echo "5. Render 会自动检测到 render.yaml"
echo "6. 在 'Environment' 标签添加:"
echo "   Key: EBIRD_API_KEY"
echo "   Value: 你的_eBird_API_Key"
echo "7. 点击 'Create Web Service'"
echo "8. 等待部署完成（5-10分钟）"
echo ""
echo "📖 详细说明请查看: README_DEPLOY.md"
echo "📋 部署检查清单: DEPLOYMENT_CHECKLIST.md"
echo ""
echo "祝你部署顺利！ 🦅🔍"
