# 🦅 TuiBird Tracker 项目结构说明

## 📂 目录结构

```
TuiBird_Tracker_MenuBar/
│
├── 📄 主程序文件
│   └── src/main.py                    # 主菜单入口程序
│
├── 🧩 核心模块 (src/)
│   ├── __init__.py                   # 包初始化
│   ├── config.py                     # 配置管理模块 ⭐
│   ├── utils.py                      # 工具函数模块 ⭐
│   ├── database.py                   # 数据库操作模块 ⭐
│   ├── api_client.py                 # API客户端模块 ⭐
│   ├── bird_tracker_unified.py       # 鸟类追踪核心逻辑
│   └── bird_region_query.py          # 区域查询核心逻辑
│
├── 📊 数据文件
│   ├── ebird_reference.sqlite        # 鸟类数据库
│   ├── ebird_config.json            # 用户配置 (API Key等)
│   └── profiles.json                # 搜索档案 (可选)
│
├── 📁 输出目录
│   └── output/
│       └── YYYY-MM-DD/              # 按日期组织的报告
│
└── 📚 文档
    ├── REFACTORING.md               # 重构说明
    ├── PROJECT_STRUCTURE.md         # 本文档
    └── cleanup_duplicates.sh        # 清理脚本
```

## 🔧 核心模块详解

### 1️⃣ config.py - 配置管理模块

**用途：** 统一管理所有配置项、常量和路径

**主要内容：**
```python
# 路径管理
get_resource_path(relative_path)    # 获取资源路径（支持打包）

# 文件路径常量
DB_FILE                             # 数据库文件路径
CONFIG_FILE                         # 配置文件路径
PROFILES_FILE                       # 档案文件路径

# API配置
EBIRD_API_BASE_URL                  # eBird API基础URL
API_TIMEOUT                         # API超时时间
API_VALIDATION_INTERVAL             # API Key验证间隔

# 区域代码
AUSTRALIA_STATES                    # 澳大利亚各州代码列表

# 默认参数
DEFAULT_DAYS_BACK                   # 默认查询天数
DEFAULT_RADIUS_KM                   # 默认搜索半径

# 配置管理器类
ConfigManager                       # 配置文件管理类
  .load()                          # 加载配置
  .save()                          # 保存配置
  .get_api_key()                   # 获取API Key
  .set_api_key(api_key)            # 设置API Key
  .should_revalidate_api_key()     # 检查是否需要重新验证
```

**使用示例：**
```python
from src.config import ConfigManager, DB_FILE

config = ConfigManager()
api_key = config.get_api_key()
```

### 2️⃣ utils.py - 工具函数模块

**用途：** 提供通用的工具函数

**主要功能：**

#### 输入验证
```python
safe_input(prompt, input_type="string",
          min_val=None, max_val=None,
          allow_empty=True, default=None)

# 示例
days = safe_input("输入天数: ", input_type="int",
                 min_val=1, max_val=30, default=14)
```

#### 地理位置处理
```python
get_location_from_ip()                        # IP自动定位
get_coords_from_string(input_str)             # 解析GPS坐标
get_coords_from_placename(placename, geolocator)  # 地名→坐标
get_placename_from_coords(lat, lng, geolocator)   # 坐标→地名
create_geolocator(user_agent)                 # 创建地理编码器
```

#### 数据格式化
```python
format_count(count)                           # 格式化观测数量
create_google_maps_link(lat, lng)            # 生成Google地图链接
create_ebird_checklist_link(sub_id)          # 生成eBird清单链接
```

#### 显示工具
```python
print_banner(title, width=60)                # 打印标题横幅
print_divider(char="-", width=40)           # 打印分隔线
```

### 3️⃣ database.py - 数据库操作模块

**用途：** 统一管理SQLite数据库操作

**主要类：**
```python
class BirdDatabase:
    def __init__(self, db_path)              # 初始化数据库

    # 上下文管理器（自动关闭连接）
    def get_connection()

    # 数据加载（带缓存）
    def load_all_birds()                     # 加载所有鸟种
    def get_code_to_name_map()               # 获取代码→名称映射

    # 搜索功能
    def find_species_by_name(query)          # 模糊搜索鸟种

    # 交互式选择
    def select_species_interactive()         # 选择单个鸟种
    def select_multiple_species_interactive() # 选择多个鸟种
```

**使用示例：**
```python
from src.database import BirdDatabase
from src.config import DB_FILE

db = BirdDatabase(DB_FILE)
birds = db.load_all_birds()
selected = db.select_species_interactive()
```

**优点：**
- ✅ 自动管理数据库连接（使用上下文管理器）
- ✅ 数据缓存机制（避免重复加载）
- ✅ 类型提示（提高代码可读性）

### 4️⃣ api_client.py - API客户端模块

**用途：** 统一管理与eBird API的所有交互

**主要类：**
```python
class EBirdAPIClient:
    def __init__(self, api_key)              # 初始化客户端

    # API Key验证
    def validate_api_key()                   # 验证API Key

    # 观测记录查询
    def get_recent_observations_by_species(  # 按物种查询
        species_code, region_code, days_back)

    def get_recent_observations_by_location( # 按位置查询
        lat, lng, radius, days_back, species_code=None)

    def get_checklist_details(sub_id)        # 获取清单详情

    # 热点相关
    def search_hotspots(query, region_code)  # 搜索热点
    def get_hotspot_observations(            # 获取热点观测
        location_id, days_back)
```

**辅助函数：**
```python
setup_api_key_interactive(config_manager)    # 交互式设置API Key
get_api_key_with_validation(config_manager)  # 获取并验证API Key
show_api_key_guide()                         # 显示申请指南
```

**使用示例：**
```python
from src.api_client import EBirdAPIClient, get_api_key_with_validation
from src.config import ConfigManager

config = ConfigManager()
api_key = get_api_key_with_validation(config)
client = EBirdAPIClient(api_key)

observations = client.get_recent_observations_by_species(
    species_code="houspa",
    region_code="AU",
    days_back=14
)
```

**特性：**
- ✅ 统一的错误处理
- ✅ 智能缓存验证（24小时内无需重新验证）
- ✅ 灵活的超时控制

## 🔄 模块依赖关系

```
main.py
  ├── config.py          (配置管理)
  ├── api_client.py      (API交互)
  │   └── config.py
  ├── database.py        (数据库操作)
  │   └── config.py
  └── utils.py           (工具函数)

bird_tracker_unified.py
  ├── config.py
  ├── database.py
  ├── api_client.py
  └── utils.py

bird_region_query.py
  ├── config.py
  ├── database.py
  ├── api_client.py
  └── utils.py
```

## 🚀 快速开始

### 运行程序

```bash
# 运行主菜单
python -m src.main

# 或者直接运行
cd src
python main.py
```

### 清理重复文件

```bash
# 运行清理脚本（会先备份）
./cleanup_duplicates.sh
```

## 📝 编码规范

### 导入顺序
```python
# 1. 标准库
import os
import sys
from typing import List, Dict

# 2. 第三方库
import requests
from geopy.geocoders import Nominatim

# 3. 本地模块
from src.config import ConfigManager
from src.database import BirdDatabase
from src.api_client import EBirdAPIClient
from src.utils import safe_input
```

### 类型提示
```python
def find_species_by_name(query: str) -> List[Dict]:
    """搜索鸟种"""
    pass

def get_coords(lat: float, lng: float) -> Tuple[float, float]:
    """获取坐标"""
    pass
```

### 上下文管理器
```python
# 推荐：使用上下文管理器
with db.get_connection() as conn:
    cursor = conn.cursor()
    cursor.execute(query)

# 避免：手动管理连接
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute(query)
conn.close()  # 可能忘记关闭
```

## 🛠️ 常见任务

### 添加新的配置项

**步骤：**
1. 在 `src/config.py` 中定义常量
2. 在 `ConfigManager` 类中添加getter/setter方法

```python
# src/config.py
NEW_SETTING = "default_value"

class ConfigManager:
    def get_new_setting(self):
        return self._config.get('new_setting', NEW_SETTING)

    def set_new_setting(self, value):
        self._config['new_setting'] = value
```

### 添加新的API端点

**步骤：**
1. 在 `src/api_client.py` 的 `EBirdAPIClient` 类中添加方法

```python
# src/api_client.py
class EBirdAPIClient:
    def get_new_data(self, param1, param2):
        """获取新数据"""
        endpoint = f"new/endpoint/{param1}"
        params = {'param2': param2}
        return self._make_request(endpoint, params)
```

### 添加新的工具函数

**步骤：**
1. 在 `src/utils.py` 中添加函数
2. 添加完整的文档字符串和类型提示

```python
# src/utils.py
def new_utility_function(input: str) -> str:
    """
    新的工具函数

    Args:
        input: 输入参数

    Returns:
        处理后的结果
    """
    return input.upper()
```

## 📊 代码统计

```
模块               行数    大小    职责
=====================================
config.py          ~200    5.5K   配置管理
utils.py           ~180    7.0K   工具函数
database.py        ~210    8.8K   数据库操作
api_client.py      ~270   12.0K   API客户端
=====================================
总计              ~860   33.3K   基础设施
```

## ✅ 重构成果

### 消除重复代码
- ❌ 旧：API Key管理代码在3个文件中重复
- ✅ 新：统一在 `api_client.py` 中管理

- ❌ 旧：数据库操作代码在3个文件中重复
- ✅ 新：统一在 `database.py` 中管理

- ❌ 旧：工具函数散落在各个文件中
- ✅ 新：统一在 `utils.py` 中管理

### 提高代码质量
- ✅ 添加类型提示
- ✅ 使用上下文管理器
- ✅ 完善的文档字符串
- ✅ 统一的错误处理

### 改进架构
- ✅ 模块化设计，职责清晰
- ✅ 配置集中管理
- ✅ API调用统一封装
- ✅ 数据库操作抽象化

### 性能优化
- ✅ 数据缓存（鸟种数据、API Key验证）
- ✅ 智能验证（避免频繁API调用）
- ✅ 连接自动管理

## 🔮 未来改进

- [ ] 添加日志记录功能 (`logging`)
- [ ] 添加单元测试 (`pytest`)
- [ ] 异步API请求 (`aiohttp`)
- [ ] 命令行参数支持 (`argparse`)
- [ ] 配置文件验证 (`pydantic`)
- [ ] 进度条显示 (`tqdm`)

## 📧 联系方式

项目：TuiBird Tracker V4.0
作者：TuiBird Tracker Team
