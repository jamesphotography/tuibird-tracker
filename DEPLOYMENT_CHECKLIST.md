# 🚀 Render.com 部署检查清单

## ✅ 部署前准备

- [ ] **eBird API Key 已获取**
  - 访问: https://ebird.org/api/keygen
  - 保存好你的 API Key

- [ ] **GitHub 仓库已创建**
  - 仓库名建议: `tuibird-tracker`
  - 可见性: Public 或 Private（都支持）

- [ ] **本地文件已准备**
  - [x] `requirements.txt` ✓
  - [x] `render.yaml` ✓
  - [x] `.gitignore` ✓
  - [x] `ebird_reference.sqlite` (需要检查)
  - [x] `src/web_app.py` (已适配生产环境) ✓

## 📦 Git 推送步骤

```bash
# 1. 初始化 Git（如果还没有）
git init

# 2. 添加所有文件
git add .

# 3. 提交
git commit -m "Ready for Render deployment"

# 4. 添加远程仓库
git remote add origin https://github.com/你的用户名/tuibird-tracker.git

# 5. 推送到 GitHub
git branch -M main
git push -u origin main
```

## 🌐 Render 部署步骤

### 1. 注册/登录 Render
- [ ] 访问 https://render.com/
- [ ] 使用 GitHub 账号登录

### 2. 创建 Web Service
- [ ] 点击 "New +" → "Web Service"
- [ ] 选择 GitHub 仓库: `tuibird-tracker`
- [ ] Render 自动检测到 `render.yaml`

### 3. 配置环境变量
- [ ] 在 "Environment" 标签添加:
  ```
  Key: EBIRD_API_KEY
  Value: 你的_eBird_API_Key
  ```
- [ ] 点击 "Save Changes"

### 4. 启动部署
- [ ] 点击 "Create Web Service"
- [ ] 等待构建（5-10 分钟）
- [ ] 记录你的应用 URL

## 🧪 部署后测试

- [ ] **访问首页**
  - URL: `https://你的应用名.onrender.com`
  - 预期: 首页正常显示

- [ ] **测试 API Key**
  - 访问: `/settings`
  - 检查 API Key 是否已配置

- [ ] **测试物种搜索**
  - 访问: `/tracker`
  - 搜索: "七彩文鸟"
  - 预期: 返回搜索结果

- [ ] **测试报告生成**
  - 选择物种 → 开始追踪
  - 预期: 生成报告并可预览

- [ ] **测试区域查询**
  - 访问: `/region`
  - 输入坐标: `-12.4634, 130.8456`
  - 预期: 返回区域观测数据

- [ ] **测试历史记录**
  - 访问: `/reports`
  - 预期: 显示已生成的报告

## ⚠️ 常见问题排查

### 问题 1: 数据库太大无法推送
```bash
# 检查数据库大小
ls -lh ebird_reference.sqlite

# 如果超过 100MB，使用 Git LFS
git lfs install
git lfs track "*.sqlite"
git add .gitattributes
git commit -m "Add Git LFS for database"
git push
```

### 问题 2: 构建失败
- [ ] 检查 Render Logs
- [ ] 确认 `requirements.txt` 格式正确
- [ ] 确认 Python 版本兼容 (3.9+)

### 问题 3: API 无响应
- [ ] 确认 `EBIRD_API_KEY` 环境变量已设置
- [ ] 检查 API Key 是否有效
- [ ] 查看 Render Runtime Logs

### 问题 4: 冷启动太慢
这是正常现象（免费计划限制）：
- 首次访问: ~30 秒
- 15 分钟无活动会休眠
- 使用 UptimeRobot 定时 ping 可保持活跃

## 📊 监控和维护

- [ ] **设置 UptimeRobot 监控**（可选）
  - 访问: https://uptimerobot.com/
  - 创建 HTTP 监控
  - 间隔: 14 分钟
  - 目的: 防止休眠

- [ ] **查看 Render Logs**
  - Dashboard → 你的服务 → "Logs"
  - 实时查看应用日志

- [ ] **监控磁盘使用**
  - Dashboard → 你的服务 → "Metrics"
  - 免费计划: 1GB 存储

## 🎉 部署完成

恭喜！你的 TuiBird Tracker 已成功部署到云端！

**你的应用 URL:**
```
https://你的应用名.onrender.com
```

**分享给朋友:**
- 直接发送 URL
- 无需安装，浏览器访问即可使用
- 所有功能完整可用

---

**遇到问题？**
- 查看 `README_DEPLOY.md` 详细文档
- 访问 Render 文档: https://render.com/docs
- 提交 Issue 到你的 GitHub 仓库
