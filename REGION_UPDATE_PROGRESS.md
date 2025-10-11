# 区域搜索功能更新进度报告

**更新时间**: 2025-10-11
**状态**: 🚧 进行中

---

## ✅ 已完成的工作

### 1. eBird 区域数据库集成

#### 数据库表结构
创建了两个新表来存储 eBird 区域数据：

**`ebird_countries` 表**:
- `country_code`: 国家代码 (如: CN, US, AU)
- `country_name_en`: 英文名称
- `country_name_zh`: 中文名称
- `has_regions`: 是否有下级区域
- `regions_count`: 区域数量

**`ebird_regions` 表**:
- `region_code`: 区域代码 (如: CN-11, US-CA, AU-NSW)
- `region_name_en`: 英文名称
- `region_name_zh`: 中文名称
- `country_id`: 所属国家ID
- `country_code`: 所属国家代码

#### 数据导入
✅ 成功从 `ebird_regions.json` 导入:
- **253** 个国家
- **3,693** 个区域
- **200** 个国家有下级区域

#### 区域最多的国家 (Top 10):
1. 🇸🇮 斯洛文尼亚 - 193 个区域
2. 🇱🇻 拉脱维亚 - 119 个区域
3. 🇷🇺 俄罗斯 - 83 个区域
4. 🇵🇭 菲律宾 - 82 个区域
5. 🇹🇷 土耳其 - 81 个区域
6. 🇲🇰 北马其顿 - 80 个区域
7. 🇵🇷 波多黎各 - 78 个区域
8. 🇹🇭 泰国 - 77 个区域
9. 🇦🇿 阿塞拜疆 - 71 个区域
10. 🇲🇹 马耳他 - 68 个区域

### 2. API 端点开发

#### 新增端点

**`/api/ebird/countries` (GET)**
- 功能: 获取所有 eBird 国家列表
- 返回: 253 个国家的完整信息
- 排序: 按英文名称排序

**示例响应**:
```json
{
  "success": true,
  "total": 253,
  "countries": [
    {
      "code": "CN",
      "name_en": "China",
      "name_zh": "中国",
      "has_regions": true,
      "regions_count": 34
    },
    ...
  ]
}
```

**`/api/ebird/regions/<country_code>` (GET)**
- 功能: 获取指定国家的所有区域
- 参数: `country_code` (如: CN, US, AU)
- 返回: 该国所有区域列表

**示例响应**:
```json
{
  "success": true,
  "country_code": "CN",
  "total": 34,
  "regions": [
    {
      "code": "CN-11",
      "name_en": "Beijing",
      "name_zh": null
    },
    {
      "code": "CN-31",
      "name_en": "Shanghai",
      "name_zh": null
    },
    ...
  ]
}
```

### 3. 特有种页面跳转逻辑

✅ 修改了 `endemic.html` 的 `startTracking()` 函数：

**传递的数据**:
```javascript
{
  birds: ["七彩文鸟", "棕扇尾莺", ...],  // 选中的鸟种列表
  country: "印度尼西亚",                  // 国家中文名
  countryEn: "Indonesia",                // 国家英文名
  countryCode: "ID",                     // 国家代码 ⭐ 新增
  fromEndemic: true                      // 来源标记 ⭐ 新增
}
```

**存储方式**: 通过 `localStorage.setItem('endemicTrackingData', ...)` 传递

---

## 🚧 待完成的工作

### 4. 修改追踪页面 (tracker.html)

**需要实现的功能**:

#### A. 区域选择改造 (先选国家，再选区域)

**当前状态** (第 130-156 行):
```html
<div id="regionModeParams">
    <select id="regionCode">
        <option value="AU">澳大利亚全境</option>
        <option value="AU-NT">北领地 (NT)</option>
        <!-- 硬编码的澳大利亚区域 -->
    </select>
</div>
```

**目标状态**:
```html
<div id="regionModeParams">
    <div class="form-group">
        <label>选择国家</label>
        <select id="countrySelect" onchange="loadRegions()">
            <option value="">-- 请选择国家 --</option>
            <!-- 动态加载 253 个国家 -->
        </select>
    </div>

    <div class="form-group" id="regionSelectGroup" style="display: none;">
        <label>选择区域</label>
        <select id="regionCode">
            <option value="">-- 请先选择国家 --</option>
            <!-- 根据选中国家动态加载区域 -->
        </select>
    </div>
</div>
```

#### B. 自动选择逻辑

当从特有种页面跳转过来时 (`endemicData.fromEndemic === true`):

1. **自动切换到区域搜索模式**
   ```javascript
   document.getElementById('searchMode').value = 'region';
   toggleSearchMode();
   ```

2. **自动选择国家**
   ```javascript
   if (endemicData.countryCode) {
       document.getElementById('countrySelect').value = endemicData.countryCode;
       await loadRegions(endemicData.countryCode);
   }
   ```

3. **提示用户选择区域**
   ```javascript
   showNotification(`已选择国家: ${endemicData.country}，请选择具体区域后开始追踪`, 'info');
   ```

#### C. JavaScript 函数需求

**新增函数**:
```javascript
// 页面加载时获取所有国家
async function loadCountries() {
    const data = await apiRequest('/api/ebird/countries');
    const select = document.getElementById('countrySelect');

    data.countries.forEach(country => {
        const displayName = country.name_zh || country.name_en;
        const option = `<option value="${country.code}">${displayName} (${country.code})</option>`;
        select.innerHTML += option;
    });
}

// 根据国家加载区域
async function loadRegions(countryCode) {
    if (!countryCode) {
        document.getElementById('regionSelectGroup').style.display = 'none';
        return;
    }

    const data = await apiRequest(`/api/ebird/regions/${countryCode}`);
    const select = document.getElementById('regionCode');

    select.innerHTML = '<option value="">-- 请选择区域 --</option>';

    // 添加"全境"选项
    select.innerHTML += `<option value="${countryCode}">该国全境</option>`;

    // 添加各区域
    data.regions.forEach(region => {
        const displayName = region.name_zh || region.name_en;
        const option = `<option value="${region.code}">${displayName}</option>`;
        select.innerHTML += option;
    });

    document.getElementById('regionSelectGroup').style.display = 'block';
}
```

**修改现有函数** (`loadBirdsByNames`, 第 371-409 行):
```javascript
async function loadBirdsByNames(birdNames, countryName, endemicData) {
    // ... 加载鸟种代码 ...

    // 如果来自特有种页面
    if (endemicData && endemicData.fromEndemic && endemicData.countryCode) {
        // 切换到区域搜索模式
        document.getElementById('searchMode').value = 'region';
        toggleSearchMode();

        // 自动选择国家
        document.getElementById('countrySelect').value = endemicData.countryCode;
        await loadRegions(endemicData.countryCode);

        showNotification(
            `已从${countryName}加载 ${selectedSpeciesList.length} 种鸟，请选择区域后开始追踪`,
            'info'
        );
    }
}
```

**修改 DOMContentLoaded** (第 341-368 行):
```javascript
document.addEventListener('DOMContentLoaded', async function() {
    // 加载国家列表
    await loadCountries();

    // 检查是否有特有种数据
    const endemicData = localStorage.getItem('endemicTrackingData');

    if (endemicData) {
        const data = JSON.parse(endemicData);

        if (data.birds && data.birds.length > 0) {
            if (data.birds.length > 1) {
                selectMode('multi');
            }

            // 传递完整的endemicData
            await loadBirdsByNames(data.birds, data.country, data);
        }

        localStorage.removeItem('endemicTrackingData');
    }
});
```

---

## 📝 实现步骤

### 下一步: 修改 tracker.html

1. **修改 HTML 结构** (第 130-156 行)
   - 删除硬编码的澳大利亚区域选项
   - 添加国家选择下拉框
   - 添加区域选择下拉框（初始隐藏）
   - 添加适当的样式和提示文本

2. **添加 JavaScript 函数** (在 `{% block extra_js %}` 内)
   - `loadCountries()` - 加载国家列表
   - `loadRegions(countryCode)` - 加载指定国家的区域
   - 修改 `loadBirdsByNames()` - 支持自动选择
   - 修改 `DOMContentLoaded` - 初始化国家列表

3. **测试流程**
   - 从特有种页面选择印度尼西亚的鸟种
   - 点击"追踪已选鸟种"
   - 验证跳转到追踪页面后:
     * 自动切换到区域搜索模式 ✓
     * 自动选择印度尼西亚 (ID) ✓
     * 显示印度尼西亚的所有区域 ✓
     * 提示用户选择区域 ✓

---

## 🎯 预期效果

### 用户体验流程

1. **特有种页面**:
   - 用户搜索"印度尼西亚"
   - 浏览 504 种特有鸟类
   - 选择感兴趣的鸟种（如: 爪哇八哥、七彩文鸟）
   - 点击"追踪已选鸟种"

2. **自动跳转到追踪页面**:
   - ✅ 已加载鸟种: 爪哇八哥、七彩文鸟
   - ✅ 搜索模式: 区域搜索
   - ✅ 已选国家: 印度尼西亚 (ID)
   - 🔽 区域选择: 显示印度尼西亚的所有区域

3. **用户操作**:
   - 选择具体区域（如: Java）
   - 选择时间范围（如: 最近 14 天）
   - 点击"开始追踪"
   - 查看观测记录

### 数据优势

- **灵活性**: 支持 253 个国家、3,693 个区域
- **准确性**: 数据来自官方 eBird 数据库
- **可维护性**: 集中存储在 SQLite，易于更新
- **扩展性**: 未来可添加更多国家/区域数据

---

## 🔧 技术细节

### 数据库查询示例

**查询中国的所有区域**:
```sql
SELECT er.region_code, er.region_name_en, er.region_name_zh
FROM ebird_regions er
JOIN ebird_countries ec ON er.country_id = ec.id
WHERE ec.country_code = 'CN'
ORDER BY er.region_code;
```

**结果** (34 个区域):
```
CN-11  Beijing
CN-12  Tianjin
CN-13  Hebei
CN-14  Shanxi
...
CN-65  Xinjiang
```

### API 调用示例

```javascript
// 获取所有国家
const countries = await apiRequest('/api/ebird/countries');
// 返回: { success: true, countries: [...], total: 253 }

// 获取印度尼西亚的区域
const regions = await apiRequest('/api/ebird/regions/ID');
// 返回: { success: true, country_code: "ID", regions: [...], total: 34 }
```

---

## 📊 进度总结

| 任务 | 状态 | 完成度 |
|------|------|--------|
| 数据库表结构设计 | ✅ 完成 | 100% |
| 数据导入 | ✅ 完成 | 100% |
| API 端点开发 | ✅ 完成 | 100% |
| 特有种页面跳转 | ✅ 完成 | 100% |
| 追踪页面改造 | 🚧 待完成 | 0% |
| 自动选择逻辑 | 🚧 待完成 | 0% |
| 测试验证 | 🚧 待完成 | 0% |

**总体进度**: 约 **60%**

---

## 🚀 下一步行动

1. 修改 `tracker.html` 的 HTML 结构
2. 添加必要的 JavaScript 函数
3. 测试完整流程
4. 优化用户体验细节

请准备好后，我会开始修改 tracker.html！
