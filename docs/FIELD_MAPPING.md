# FPSO 商机发现系统 — 字段映射表

> **写给前端同事和秒搭**：本文档定义了 API 返回的每个字段在前端 UI 中的展示方式。你可以自由设计页面的视觉风格，但以下字段→UI 区域的映射关系请保持一致。

---

## 1. 字段→UI 位置映射总览

### 1.1 项目卡片（主视图）

```
┌─────────────────────────────────────────┐
│ [status 标签]          [confidence 图标] │  ← 顶部状态行
│                                         │
│  name                                   │  ← 项目名称（标题）
│  🇧🇷 country                            │  ← 国旗 + 国家
│                                         │
│  summary (1-2行截断)                    │  ← 摘要文字
│                                         │
│  [不锈钢牌号标签] [应用场景标签]          │  ← 材质信息区
│                                         │
│  ⚙ water_depth_m | oil_capacity_bpd    │  ← 技术参数简要
│                                         │
│  📎 source_name (可点击链接)             │  ← 来源信息
└─────────────────────────────────────────┘
```

### 1.2 项目详情弹窗 / 展开区

```
┌──────────────────────────────────────────┐
│  基本信息                                 │
│  ├─ name                                 │
│  ├─ country + flag                       │
│  ├─ status (彩色标签)                     │
│  ├─ summary (完整展开)                    │
│  └─ confidence (进度条或星级)             │
│                                          │
│  技术参数                                 │
│  ├─ 水深：water_depth_m M                  │
│  ├─ 原油产能：oil_capacity_bpd bbl/d      │
│  ├─ 天然气产能：gas_capacity_mmcmd MMcmd   │
│  ├─ 船体类型：hull_type                   │
│  ├─ 油田：field_name                      │
│  ├─ 运营商：operator_name                  │
│  └─ 盆地：basin                           │
│                                          │
│  不锈钢材质推荐                            │
│  ├─ 牌号标签 (从 stainless_steel 拆分)     │
│  ├─ 应用场景 (从 application 拆分)         │
│  └─ 详细匹配结果 (recommendation_json)     │
│                                          │
│  腐蚀介质 (corrosive_media)               │
│  ├─ H₂S / CO₂ / 氯化物 / 酸性服务         │
│                                          │
│  采购信息                                 │
│  └─ procurement_chain                    │
│                                          │
│  商机评分 (opportunity_score)             │
│  ├─ 总分 + 等级 (A/B/C/D)                │
│  └─ 5 维雷达图 / 柱状图                   │
│                                          │
│  来源信息                                 │
│  └─ source_name + source_url + source_date│
└──────────────────────────────────────────┘
```

---

## 2. 每个字段的详细展示规范

### 2.1 基础信息区

| 字段 | 展示位置 | 展示形式 | 空值处理 |
|------|---------|---------|---------|
| `name` | 卡片标题 / 详情页大标题 | 文字，加粗，字体稍大 | 不可为空 |
| `country` | 卡片副标题 | 国旗 emoji（`flag` 字段）+ 国家英文名 | 不可为空 |
| `flag` | country 旁边 | emoji 直接渲染 | 为空时不显示 emoji，只显示国家名 |
| `status` | 卡片右上角标签 | 彩色圆点 + 文字标签 | 不可为空 |
| `summary` | 卡片中部 | 1-2 行截断（超出显示 ...），详情页完整展开 | 不可为空 |

### 2.2 状态标签

| 状态值 | 颜色 | 含义 |
|--------|------|------|
| `Under Construction` | 蓝色 `#3B82F6` | 在建中，当前可介入 |
| `Planned` | 黄色 `#F59E0B` | 规划中，需提前布局 |
| `Delivered` | 绿色 `#10B981` | 已交付，可做后续维保 |
| `Unknown` | 灰色 `#6B7280` | 状态不明 |

### 2.3 置信度标识

| 值 | 颜色 | 图标建议 |
|----|------|---------|
| `high` | 绿色 `#10B981` | 🟢 或实心盾牌 |
| `medium` | 黄色 `#F59E0B` | 🟡 或半满盾牌 |
| `low` | 灰色 `#9CA3AF` | ⚪ 或空心盾牌 |

### 2.4 技术参数区

| 字段 | 展示形式 | 单位 | 空值展示 | 备注 |
|------|---------|------|---------|------|
| `water_depth_m` | 数字 | 米 (m) | "--" | 深海 >1500m 可特别标注 |
| `oil_capacity_bpd` | 数字（千分位） | 桶/天 (bbl/d) | "--" | >150,000 可标注为大型 |
| `gas_capacity_mmcmd` | 数字 | Mm³/d | "--" | 百万立方米/天 |
| `hull_type` | 文字标签 | -- | 不渲染 | 如 "FPSO", "FLNG", "FSO" |
| `field_name` | 文字 | -- | 不渲染 | |
| `operator_name` | 文字 | -- | 不渲染 | 运营商名称 |
| `basin` | 文字标签 | -- | 不渲染 | 如 "Santos", "North Sea" |

### 2.5 材质信息区

| 字段 | 展示形式 | 说明 |
|------|---------|------|
| `stainless_steel` | 逗号分隔 → 多个小标签 | 如 "Super Duplex 2507, Duplex 2205" → 两个独立标签 |
| `application` | 逗号分隔 → 列表或标签组 | 如 "Gas Compression, Subsea Manifolds" |
| `recommendation_json` | 结构化卡片/表格 | JSON 解析后展示 grades[] / applications[] / confidence / reasoning |

**recommendation_json 解析示例**：
```json
{
  "grades": ["Super Duplex 2507", "6Mo (UNS S31254)", "Duplex 2205"],
  "applications": ["Gas Compression", "Subsea Manifolds", "Deepwater Risers"],
  "confidence": "high",
  "reasoning": "Water depth 1890m >1500m: deepwater conditions recommend Super Duplex 2507..."
}
```

### 2.6 腐蚀介质区

`corrosive_media` 是 JSONB 对象，包含子字段：

| 子字段 | 展示形式 |
|--------|---------|
| `h2s` | "H₂S: {值}"（如 "H₂S: low"） |
| `co2` | "CO₂: {值}" |
| `chloride` | "氯化物: {值}" |
| `sour_service` | 布尔值："酸性服务: 是/否" |
| `details` | 自由文本（如有） |

### 2.7 采购信息区

| 字段 | 展示位置 | 展示形式 |
|------|---------|---------|
| `procurement_chain` | 卡片底部 / 详情页采购区块 | 文字，如 "SBM Offshore (EPC) → Tier 2 suppliers" |

### 2.8 商机评分区

`opportunity_score` 是 JSONB 对象：

```json
{
  "totalScore": 85,
  "grade": "A",
  "dimensions": {
    "procurement": { "score": 18, "reasoning": "..." },
    "factoryMatch": { "score": 17, "reasoning": "..." },
    "reachability": { "score": 16, "reasoning": "..." },
    "value": { "score": 19, "reasoning": "..." },
    "confidence": { "score": 15, "reasoning": "..." }
  },
  "summary": "Premium opportunity",
  "recommendedAction": "Contact within 3 months"
}
```

| 子字段 | 展示位置 | 展示形式 |
|--------|---------|---------|
| `totalScore` + `grade` | 卡片右下角 / 详情页顶部 | 大号数字 (0-100) + 彩色等级标签 |
| `dimensions` 五维 | 详情页 | 雷达图 (Recharts) 或柱状图 + 各维度得分 |
| `summary` | 详情页评分区下方 | 一句话总结 |
| `recommendedAction` | 详情页底部 | 行动建议文字 |

**等级颜色**：
- A (≥80)：绿色
- B (60-79)：蓝色
- C (40-59)：黄色
- D (<40)：灰色

### 2.9 来源信息区

| 字段 | 展示位置 | 展示形式 |
|------|---------|---------|
| `source_name` | 卡片最底部 | 可点击链接 |
| `source_url` | source_name 的链接地址 | 新标签页打开 |
| `source_date` | source_name 旁边 | 灰色小字日期（有则显示，无则隐藏） |

---

## 3. 空值处理总表

以下字段在渲染前必须检查是否为空：

```typescript
// 推荐的空值处理模式
function safe(value: any, fallback: string = "暂无数据") {
  return value ?? fallback;
}

function safeNumber(value: number | null | undefined): string {
  return value != null ? value.toLocaleString() : "--";
}
```

| 字段 | 空值显示 | 备注 |
|------|---------|------|
| `water_depth_m` | `"--"` | 图表的项目可跳过 null 值 |
| `oil_capacity_bpd` | `"--"` | |
| `gas_capacity_mmcmd` | `"--"` | |
| `hull_type` | 不展示该行 | |
| `field_name` | 不展示该行 | |
| `operator_name` | 不展示该行 | |
| `basin` | 不展示该行 | |
| `stainless_steel`（空字符串） | 隐藏材质标签区 | 空字符串和 null 都算空 |
| `application`（空字符串） | 隐藏应用标签区 | |
| `recommendation_json` | 隐藏材质推荐模块 | |
| `procurement_chain` | 不展示该行 | |
| `corrosive_media` | 隐藏腐蚀介质模块 | |
| `opportunity_score` | 显示 "待评分" | 保留区域但提示暂无评分 |
| `source_date`（空字符串） | 不展示日期 | |
| `flag`（空字符串） | 不展示 emoji | 只显示国家文字 |

---

## 4. 页面功能清单

以下是已确定的功能页面。页面视觉设计任你发挥，但每个页面需要包含以下核心数据展示：

| 页面 | 路由 | 核心功能 | 数据来源 |
|------|------|---------|---------|
| Dashboard | `/` | 项目卡片列表 + 筛选侧边栏 + 统计面板 | GET /projects |
| Database | `/database` | 表格视图 + 筛选 + 排序 + 分页 | GET /projects |
| Review | `/review` | 待审核事件列表 + 通过/拒绝操作 | GET /candidate_events |
| Project Timeline | `/project-timeline` | 按时间排列项目 | GET /projects (排序) |
| Industry Breakdown | `/industry-breakdown` | 按分类统计图表 | GET /projects (前端分组统计) |
| Settings | `/settings` | 用户订阅偏好设置 | GET /user_subscriptions |
| Login | `/login` | 飞书 OAuth 登录 | 暂用 anon key 绕过开发 |

---

## 5. 设计自由度

以下方面**完全由你和秒搭自由决定**，没有任何限制：

- 配色方案和整体视觉风格
- 字体、圆角、阴影等细节
- 页面布局（左右分栏、上下排列、T 型布局等）
- 卡片样式和形状
- 交互动效和过渡动画
- 图表样式和配色（柱状图/饼图/雷达图任选）
- 响应式断点和移动端适配方案
- 图标库选择（Lucide / Heroicons / 自定义 SVG）
- 暗黑模式支持（可选加分项）
