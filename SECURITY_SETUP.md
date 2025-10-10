# 安全配置指南

## ⚠️ 重要提醒

本项目已从 Git 历史中移除敏感配置文件。如果你是新用户或需要重新配置,请按照以下步骤操作:

## 🔐 首次设置

### 1. 创建本地配置文件

复制示例文件并填入真实配置:

```bash
# 复制环境变量配置
cp .env.example .env

# 复制 eBird 配置
cp ebird_config.json.example ebird_config.json
```

### 2. 配置 API Key

#### 获取 eBird API Key:
1. 访问 https://ebird.org/api/keygen
2. 登录 eBird 账户
3. 填写申请表单
4. 获取 API Key 并记录

#### 配置文件填写:

**编辑 `.env` 文件**:
```bash
# 匿名用户共享的 API Key (可选,用于演示)
ANONYMOUS_API_KEY=your_ebird_api_key

# Flask 密钥 (必须生成随机值)
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")

# 数据库文件路径
DB_FILE=ebird_reference.sqlite

# Flask 配置
FLASK_ENV=production
FLASK_DEBUG=0
```

**编辑 `ebird_config.json` 文件**:
```json
{
    "api_key": "your_ebird_api_key_here"
}
```

### 3. 生成安全密钥

**自动生成 SECRET_KEY**:
```bash
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))" >> .env
```

### 4. 验证配置

```bash
# 检查环境变量
cat .env

# 确保敏感文件不在 Git 中
git status --ignored | grep -E "(ebird_config\.json|\.env$)"
```

## 🚨 安全检查清单

- [ ] `.env` 文件已创建且包含真实的 SECRET_KEY
- [ ] `ebird_config.json` 已创建且包含真实的 API Key
- [ ] 这些文件已被 `.gitignore` 忽略
- [ ] 从未提交过真实的密钥到 Git
- [ ] 生产环境的 `DEBUG=False`

## 🔄 如果密钥泄露

如果你的 API Key 或 SECRET_KEY 意外泄露:

1. **立即撤销旧的 API Key**:
   - 访问 eBird API 管理页面
   - 撤销旧密钥并生成新密钥

2. **更新本地配置**:
   ```bash
   # 重新生成 SECRET_KEY
   python3 -c "import secrets; print(secrets.token_hex(32))"

   # 更新 .env 和 ebird_config.json
   ```

3. **清理 Git 历史** (如果已提交):
   ```bash
   # 警告: 这会重写 Git 历史!
   git filter-branch --force --index-filter \
     "git rm --cached --ignore-unmatch .env ebird_config.json" \
     --prune-empty --tag-name-filter cat -- --all

   # 强制推送 (谨慎操作)
   git push origin --force --all
   ```

## 📝 开发 vs 生产环境

**开发环境** (`.env`):
```bash
FLASK_ENV=development
FLASK_DEBUG=1
DEBUG=True
```

**生产环境** (`.env`):
```bash
FLASK_ENV=production
FLASK_DEBUG=0
DEBUG=False
```

## 🛡️ 最佳实践

1. **永远不要提交**:
   - `.env`
   - `ebird_config.json`
   - `rate_limit.json`
   - 任何包含真实密钥的文件

2. **使用环境变量**:
   - 生产环境优先使用系统环境变量
   - 不要在代码中硬编码密钥

3. **定期轮换密钥**:
   - 每 3-6 个月更换一次 API Key
   - 每次部署前更换 SECRET_KEY

4. **最小权限原则**:
   - 只给必要的人员访问权限
   - 开发环境和生产环境使用不同的密钥

## 📚 相关文档

- [eBird API 文档](https://documenter.getpostman.com/view/664302/S1ENwy59)
- [Flask 安全配置](https://flask.palletsprojects.com/en/latest/config/)
- [环境变量最佳实践](https://12factor.net/config)
