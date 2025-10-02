# TuiBird Tracker - Render.com 部署指南

## 📋 部署前准备

### 1. 获取 eBird API Key
1. 访问 https://ebird.org/api/keygen
2. 注册/登录 eBird 账号
3. 申请 API Key（通常立即批准）
4. 保存好你的 API Key

### 2. 准备 GitHub 仓库
```bash
# 初始化 Git（如果还没有）
git init

# 添加所有文件
git add .

# 提交
git commit -m "Initial commit for Render deployment"

# 创建 GitHub 仓库（在 GitHub 网站上）
# 然后关联远程仓库
git remote add origin https://github.com/你的用户名/tuibird-tracker.git
git branch -M main
git push -u origin main
```

## 🚀 Render.com 部署步骤

### 步骤 1: 注册 Render 账号
1. 访问 https://render.com/
2. 使用 GitHub 账号登录（推荐）

### 步骤 2: 创建新 Web Service
1. 点击 "New +" → "Web Service"
2. 连接你的 GitHub 仓库（TuiBird_Tracker_MenuBar）
3. Render 会自动检测到 `render.yaml` 配置

### 步骤 3: 配置环境变量
在 Render Dashboard 中：
1. 找到 "Environment" 标签
2. 添加环境变量：
   ```
   Key: EBIRD_API_KEY
   Value: 你的eBird API Key
   ```
3. 点击 "Save Changes"

### 步骤 4: 部署
1. 点击 "Create Web Service"
2. 等待构建完成（首次约 5-10 分钟）
3. 部署成功后会得到一个 URL，例如：
   ```
   https://tuibird-tracker.onrender.com
   ```

## ⚙️ 配置说明

### render.yaml 配置详解

```yaml
services:
  - type: web
    name: tuibird-tracker          # 服务名称
    runtime: python                # Python 运行时
    region: oregon                 # 服务器位置（oregon 或 singapore）
    plan: free                     # 免费计划
    buildCommand: pip install -r requirements.txt
    startCommand: gunicorn --bind 0.0.0.0:$PORT --workers 2 --timeout 120 src.web_app:app
    envVars:
      - key: PYTHON_VERSION
        value: 3.9.18
      - key: EBIRD_API_KEY
        sync: false                # 需要手动在 Dashboard 设置
    disk:
      name: tuibird-data           # 持久化存储
      mountPath: /opt/render/project/src/output
      sizeGB: 1                    # 1GB 存储空间
```

### 免费计划限制
- ✅ **750 小时/月**（足够全天候运行）
- ✅ **512MB RAM**
- ✅ **1GB 持久化存储**（保存报告）
- ⚠️ **15 分钟无访问会自动休眠**
- ⚠️ **冷启动时间约 30 秒**
- ✅ **100GB 月流量**

## 🔧 代码调整（已包含）

无需修改代码！项目已配置好生产环境支持。

### 自动适配的配置：
1. **端口绑定**：自动使用 Render 的 `$PORT` 环境变量
2. **API Key 读取**：从环境变量 `EBIRD_API_KEY` 读取
3. **数据库路径**：自动使用相对路径
4. **输出目录**：使用持久化磁盘挂载点

## 📊 访问和使用

### 首次访问
```
https://你的应用名.onrender.com
```

### 配置 API Key（如果部署时没设置）
1. 访问 `/settings` 页面
2. 输入你的 eBird API Key
3. 点击保存

### 注意事项
- ⏰ **首次访问可能需要等待 30 秒**（冷启动）
- 🔄 **15 分钟无访问会休眠，下次访问会重新唤醒**
- 💾 **报告会自动保存到持久化存储**
- 🌍 **建议选择 `singapore` 区域**（距离澳洲更近）

## 🔍 故障排查

### 问题 1: 构建失败
```bash
# 检查 requirements.txt 是否正确
# 确保所有依赖版本兼容
```

### 问题 2: 启动失败
```bash
# 检查 Render Logs
# 确认 EBIRD_API_KEY 环境变量已设置
```

### 问题 3: 数据库找不到
```bash
# 确保 ebird_reference.sqlite 在仓库中
# 检查文件大小是否超过 100MB（Git 限制）
```

**解决方案（数据库太大）：**
```bash
# 使用 Git LFS（Large File Storage）
git lfs install
git lfs track "*.sqlite"
git add .gitattributes
git commit -m "Add Git LFS for SQLite"
git push
```

### 问题 4: 报告不保存
```bash
# 确认 render.yaml 中的 disk 配置正确
# 检查挂载路径是否匹配代码中的输出路径
```

## 🔄 更新部署

每次推送到 GitHub，Render 会自动重新部署：

```bash
git add .
git commit -m "Update features"
git push origin main
```

Render 会自动：
1. 检测到新提交
2. 重新构建应用
3. 零停机时间滚动更新

## 🌐 自定义域名（可选）

免费计划支持自定义域名：

1. 在 Render Dashboard 中点击 "Settings"
2. 找到 "Custom Domains"
3. 添加你的域名（如 `tuibird.yourdomain.com`）
4. 在你的 DNS 提供商添加 CNAME 记录：
   ```
   CNAME tuibird 你的应用名.onrender.com
   ```

## 💡 性能优化建议

1. **启用 Render 的 "Keep Alive" 监控**
   - 使用 UptimeRobot 或 Cron-Job.org
   - 每 14 分钟 ping 一次你的应用
   - 防止休眠

2. **减少冷启动时间**
   - 优化 `gunicorn` workers 数量
   - 预加载数据库索引

3. **缓存策略**
   - 使用 Flask-Caching
   - 缓存常见查询结果

## 📞 支持

- **Render 文档**: https://render.com/docs
- **GitHub Issues**: https://github.com/你的用户名/tuibird-tracker/issues
- **eBird API 文档**: https://documenter.getpostman.com/view/664302/S1ENwy59

## 📝 许可证

本项目使用 MIT 许可证。

---

**部署完成后，记得在 Render Dashboard 中设置环境变量 `EBIRD_API_KEY`！**

祝你使用愉快！ 🦅🔍
