# 🦅 TuiBird Tracker Web 界面使用指南

## 🎉 恭喜！Web 界面已成功搭建

TuiBird Tracker 现在拥有了现代化的 Web 界面，提供更直观、更友好的用户体验。

---

## 🚀 快速启动

### 方法 1：使用启动脚本（推荐）

```bash
./start_web.sh
```

### 方法 2：直接运行

```bash
python3 src/web_app.py
```

启动后，在浏览器中访问：**http://127.0.0.1:5000**

---

## 📋 功能特点

### ✨ 已实现的功能

1. **主页** (`/`)
   - 精美的欢迎页面
   - 核心功能介绍
   - 快速开始指南
   - 使用统计展示

2. **设置页面** (`/settings`)
   - API Key 配置管理
   - 在线验证 API Key
   - 申请指南链接
   - 版本信息查看

3. **历史报告** (`/reports`)
   - 查看所有历史生成的报告
   - 在线预览 Markdown 报告
   - 下载报告文件
   - 按日期分组显示

4. **响应式设计**
   - 支持桌面和移动设备
   - 流畅的动画效果
   - 现代化的 UI 设计

### 🚧 待实现的功能（下一步）

1. **物种追踪页面** (`/tracker`)
   - 单物种追踪界面
   - 多物种追踪界面
   - 实时搜索建议
   - 参数配置面板

2. **区域查询页面** (`/region`)
   - GPS 坐标输入
   - 地点名称搜索
   - 参数设置界面
   - 结果展示

3. **地图可视化**
   - Leaflet.js 集成
   - 观测点标记
   - 热点聚合
   - 路线规划

4. **实时查询进度**
   - WebSocket 实时更新
   - 进度条显示
   - 任务状态管理

---

## 🎨 界面预览

### 配色方案
- **主色调**: 森林绿 `#2D5016` （观鸟主题）
- **辅助色**: 天空蓝 `#4A90E2`
- **强调色**: 鸟橙色 `#FF8C42`
- **背景色**: 浅米色 `#F5F5DC`

### 页面结构
```
导航栏
  ├── 主页
  ├── 物种追踪
  ├── 区域查询
  ├── 历史报告
  └── 设置

主要内容区

页脚
```

---

## 🛠️ 技术栈

### 后端
- **Flask 3.0.0** - Web 框架
- **Python 3.8+** - 编程语言

### 前端
- **HTML5 + CSS3** - 页面结构和样式
- **Vanilla JavaScript** - 交互逻辑
- **Bootstrap Icons** - 图标库
- **Marked.js** - Markdown 渲染

### 已有模块复用
- `config.py` - 配置管理
- `database.py` - 数据库操作
- `api_client.py` - eBird API 客户端
- `utils.py` - 工具函数

---

## 📁 项目结构

```
TuiBird_Tracker_MenuBar/
├── src/
│   ├── web_app.py          # Flask 主应用
│   ├── templates/          # HTML 模板
│   │   ├── base.html       # 基础模板
│   │   ├── index.html      # 主页
│   │   ├── settings.html   # 设置页
│   │   └── reports.html    # 报告列表
│   ├── static/
│   │   ├── css/
│   │   │   └── style.css   # 全局样式
│   │   ├── js/
│   │   │   └── app.js      # 前端脚本
│   │   └── img/            # 图片资源
│   └── [现有Python模块]
├── start_web.sh            # 启动脚本
├── requirements.txt        # Python 依赖
└── WEB_README.md          # 本文档
```

---

## 🔧 开发说明

### 添加新页面

1. 在 `src/templates/` 创建 HTML 模板
2. 在 `src/web_app.py` 添加路由
3. 在导航栏中添加链接

示例：
```python
@app.route('/new_page')
def new_page():
    return render_template('new_page.html', version=VERSION)
```

### API 端点

所有 API 端点都以 `/api/` 开头，返回 JSON 格式数据：

- `POST /api/search_species` - 搜索鸟种
- `POST /api/track` - 执行追踪任务
- `POST /api/region_query` - 区域查询
- `GET/POST/DELETE /api/config/api_key` - API Key 管理
- `GET /api/report/<path>` - 获取报告内容

---

## 🎯 下一步计划

### Phase 1: 完善现有页面（1天）
- [ ] 创建物种追踪页面 UI
- [ ] 创建区域查询页面 UI
- [ ] 实现搜索建议功能
- [ ] 添加表单验证

### Phase 2: 对接后端逻辑（1天）
- [ ] 重构现有追踪代码以支持 API 调用
- [ ] 实现异步任务处理
- [ ] 添加任务状态查询
- [ ] 完善错误处理

### Phase 3: 地图可视化（1天）
- [ ] 集成 Leaflet.js
- [ ] 显示观测点标记
- [ ] 实现热点聚合
- [ ] 添加路线规划功能

### Phase 4: 高级功能（可选）
- [ ] 用户系统和认证
- [ ] 数据导出（CSV/Excel）
- [ ] 图表和统计分析
- [ ] WebSocket 实时更新
- [ ] 系统托盘集成

---

## 💡 使用建议

1. **首次使用**
   - 访问设置页面配置 API Key
   - 查看主页了解功能
   - 访问历史报告查看示例

2. **日常使用**
   - 直接从主页快速进入追踪或查询
   - 历史报告页面管理所有生成的报告
   - 设置页面随时查看和更换 API Key

3. **浏览器推荐**
   - Chrome / Safari / Firefox 最新版本
   - 启用 JavaScript
   - 推荐使用桌面浏览器以获得最佳体验

---

## 🐛 已知问题

1. **SSL 警告**
   - 由于 OpenSSL 版本问题，可能会看到 urllib3 警告
   - 不影响功能使用，可以忽略

2. **开发服务器**
   - 当前使用 Flask 开发服务器
   - 生产环境建议使用 Gunicorn 或 uWSGI

---

## 📞 反馈与支持

遇到问题或有建议？
- GitHub Issues: [项目地址]
- Email: [联系邮箱]

---

## 📜 更新日志

### V4.0.1 (2025-10-01)
- ✅ 初始化 Web 界面
- ✅ 实现主页、设置、报告页面
- ✅ 添加响应式设计
- ✅ 集成现有后端模块
- ✅ 创建启动脚本

---

**享受使用 TuiBird Tracker Web 界面！** 🦅✨
