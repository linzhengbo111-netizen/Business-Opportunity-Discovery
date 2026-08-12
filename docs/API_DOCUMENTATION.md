# FPSO 商机发现系统 — 接口文档

> **写给前端同事和秒搭**：本文档定义了前端可以调用的所有后端数据接口。所有接口由 Supabase PostgREST 自动生成，返回标准 JSON 格式。请严格按本文档的字段名和 URL 格式调用，不要自创字段名。

---

## 1. 服务器信息

| 项目 | 值 |
|------|-----|
| API 基础地址 | `https://zbxogsfnhagcavbvhypk.supabase.co/rest/v1` |
| 前端访问地址 | `https://business-opportunity-discovery.linzhengbo111.workers.dev` |
| 协议 | HTTPS |
| 返回格式 | JSON（需带 `Accept: application/json` 请求头） |
| 认证方式 | 所有请求携带以下两个请求头 |

### 认证请求头（每个请求必须带）

```http
apikey: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpieG9nc2ZuaGFnY2F2YnZoeXBrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODQ1NTEzMzAsImV4cCI6MjEwMDEyNzMzMH0.lyhFL4J6O98pnjsL-oGZWPMvdN_j-xKe6Ol94-45z4Y
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpieG9nc2ZuaGFnY2F2YnZoeXBrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODQ1NTEzMzAsImV4cCI6MjEwMDEyNzMzMH0.lyhFL4J6O98pnjsL-oGZWPMvdN_j-xKe6Ol94-45z4Y
```

> **说明**：本项目使用 Supabase 的 anon key（公开密钥）进行数据读取。RLS 策略为 `USING (true)`，所有数据公开可读。开发和测试阶段无需飞书登录即可调接口。

---

## 2. 数据表：projects（项目表）

### 2.1 完整字段列表（共 24 个字段）

| # | 数据库字段名 | 类型 | 含义 | 可空 | 示例值 |
|---|-------------|------|------|------|--------|
| 1 | `id` | bigint | 主键，自增 | 否 | `1384` |
| 2 | `name` | text | 项目名称 | 否 | `"FPSO Alexandre de Gusmão"` |
| 3 | `country` | text | 国家英文名 | 否 | `"Brazil"` |
| 4 | `flag` | text | 国旗 emoji | 否 | `"🇧🇷"` 或 `""` |
| 5 | `status` | text | 项目状态 | 否 | `"Under Construction"` |
| 6 | `summary` | text | 项目摘要（含技术参数文本） | 否 | `"Operator: PETROBRAS \| Basin: Santos \| WaterDepth: 1890m \| OilCap: 180000 bbl/d"` |
| 7 | `source_name` | text | 数据来源名称 | 否 | `"ANP FPSO CSV"` |
| 8 | `source_url` | text | 数据来源链接 | 否 | `"https://www.gov.br/anp/..."` |
| 9 | `source_date` | text | 数据发布日期 | 否 | `"2026-07-17"` 或 `""` |
| 10 | `stainless_steel` | text | 推荐不锈钢牌号 | 否 | `"Super Duplex 2507, 6Mo, Duplex 2205"` |
| 11 | `application` | text | 不锈钢应用场景 | 否 | `"Gas Compression, Subsea Manifolds, Deepwater Risers"` |
| 12 | `created_at` | timestamptz | 记录创建时间 | 否 | `"2026-08-06T06:26:53"` |
| 13 | `confidence` | text | 数据置信度 | 否 | `"high"` |
| 14 | `water_depth_m` | int | 水深（米） | **是** | `1890` |
| 15 | `oil_capacity_bpd` | int | 原油产能（桶/天） | **是** | `180000` |
| 16 | `gas_capacity_mmcmd` | int | 天然气产能（百万立方米/天） | **是** | `12000` |
| 17 | `hull_type` | text | 船体类型 | **是** | `"Floating Production Storage Offloading - FPSO"` |
| 18 | `field_name` | text | 油田名称 | **是** | `"AnC_MERO / MERO"` |
| 19 | `operator_name` | text | 运营商名称 | **是** | `"PETROBRAS"` |
| 20 | `basin` | text | 沉积盆地 | **是** | `"Santos"` |
| 21 | `recommendation_json` | jsonb | 材质匹配结果（JSON 对象，存储为字符串） | **是** | `{"grades":["Super Duplex 2507"],"confidence":"high"}` |
| 22 | `procurement_chain` | text | 采购链信息 | **是** | `null` |
| 23 | `corrosive_media` | jsonb | 腐蚀介质数据（JSON 对象） | **是** | `null` |
| 24 | `opportunity_score` | jsonb | 商机评分（JSON 对象） | **是** | `null` |

### 2.2 字段可选值范围

| 字段 | 可选值 |
|------|--------|
| `status` | `Under Construction`, `Planned`, `Delivered`, `Unknown` |
| `confidence` | `high`, `medium`, `low` |
| `country` | `Brazil`, `Guyana`, `Angola`, `Nigeria`, `Australia`, `Norway`, `UK`, `Ghana`, `Indonesia`, `China`, `Malaysia`, `Israel`, `Suriname` 等（动态增长） |

### 2.3 可空字段处理

以下字段**可能为 null 或空字符串**，前端必须做空值判断：

`flag`, `source_date`, `stainless_steel`, `application`, `water_depth_m`, `oil_capacity_bpd`, `gas_capacity_mmcmd`, `hull_type`, `field_name`, `operator_name`, `basin`, `recommendation_json`, `procurement_chain`, `corrosive_media`, `opportunity_score`

空值展示建议：
- 数字类型 → 显示 "--" 或 "暂无数据"
- 文本类型 → 显示 "暂无" 或不渲染该区域
- JSON 类型 → 不渲染相关模块

---

## 3. 接口列表

所有接口以 `https://zbxogsfnhagcavbvhypk.supabase.co/rest/v1` 为前缀。为节约篇幅，下方只写路径。

### 3.1 获取项目列表（分页 + 排序）

**用途**：Dashboard 首页展示项目卡片列表。

```http
GET /projects?select=*&limit=20&offset=0&order=created_at.desc
```

**Query 参数**：

| 参数 | 必填 | 说明 | 示例 |
|------|------|------|------|
| `select` | 是 | 选择字段，`*` 表示全部 | `*` 或 `name,country,status` |
| `limit` | 否 | 每页条数 | `20` |
| `offset` | 否 | 偏移量（分页） | `0`（第一页），`20`（第二页） |
| `order` | 否 | 排序字段和方向 | `created_at.desc`（最新在前） |

**返回**：JSON 数组。响应头 `content-range` 包含分页信息，格式 `0-19/150`（第 0-19 条，共 150 条）。

**curl 示例**：
```bash
curl "https://zbxogsfnhagcavbvhypk.supabase.co/rest/v1/projects?select=*&limit=3" \
  -H "apikey: <anon_key>" \
  -H "Authorization: Bearer <anon_key>" \
  -H "Accept: application/json"
```

---

### 3.2 按国家筛选

**用途**：侧边栏筛选器选择国家后过滤项目。

```http
GET /projects?select=*&country=eq.Brazil
```

**Query 参数**：`country=eq.{国家名}`，国家名需 URL 编码（如 `Côte d'Ivoire` → `C%C3%B4te%20d%27Ivoire`）。

**返回示例**：
```json
[
  {
    "id": 1384,
    "name": "FPSO Alexandre de Gusmão",
    "country": "Brazil",
    "status": "Under Construction",
    "confidence": "high",
    "water_depth_m": 1890,
    "oil_capacity_bpd": 180000
  }
]
```

---

### 3.3 按状态筛选

**用途**：筛选特定状态的项目。

```http
GET /projects?select=*&status=eq.Under Construction
```

可选值：`Under Construction`（空格需保留）, `Planned`, `Delivered`, `Unknown`

---

### 3.4 按置信度筛选

**用途**：筛选高/中/低置信度项目。

```http
GET /projects?select=*&confidence=eq.high
```

可选值：`high`, `medium`, `low`

---

### 3.5 组合筛选 + 分页

**用途**：同时按多个条件筛选。

```http
GET /projects?select=*&country=eq.Brazil&status=eq.Under Construction&confidence=eq.high&limit=20&offset=0
```

多个条件用 `&` 连接，逻辑为 AND。

---

### 3.6 模糊搜索项目名

**用途**：顶部搜索框输入关键词搜索项目。

```http
GET /projects?select=*&name=ilike.*FPSO*
```

`ilike` 不区分大小写。`*` 是 PostgREST 通配符，表示任意字符。

---

### 3.7 获取不重复的国家列表

**用途**：筛选侧边栏获取所有国家选项。

```http
GET /projects?select=country&order=country.asc
```

**返回**：JSON 数组，可能含重复值，**前端需要自行去重**。

```json
[{"country": "Angola"}, {"country": "Angola"}, {"country": "Australia"}, ...]
```

前端去重：`[...new Set(data.map(d => d.country))]`

---

### 3.8 获取不重复的状态列表

**用途**：筛选侧边栏获取所有状态选项。

```http
GET /projects?select=status&order=status.asc
```

**返回**：JSON 数组，前端自行去重。

---

### 3.9 获取单个项目详情

**用途**：项目详情弹窗、战报卡生成。

```http
GET /projects?select=*&id=eq.1384
```

**返回**：包含所有 24 个字段的单个 JSON 对象。

---

### 3.10 获取候选事件（审核页面）

**用途**：审核页面展示爬虫抓回的待审核事件。

```http
GET /candidate_events?select=*&review_status=eq.pending&limit=20&offset=0&order=created_at.desc
```

**review_status 可选值**：`pending`（待审核）, `accepted`（已通过）, `auto_accepted`（自动通过）, `rejected`（已拒绝）, `archived`（已归档）

---

### 3.11 获取用户订阅

**用途**：设置页面展示用户订阅偏好。

```http
GET /user_subscriptions?select=*
```

**返回字段**：`id`, `user_open_id`, `subscribed_industries` (TEXT[]), `subscribed_countries` (TEXT[]), `followed_project_ids` (TEXT[]), `webhook_url`, `created_at`, `updated_at`

---

### 3.12 获取跟进记录

**用途**：展示某个项目的销售跟进状态。

```http
GET /follow_ups?select=*
```

**返回字段**：`id`, `project_id`, `user_open_id`, `status`, `notes`, `corrections` (JSONB), `created_at`, `updated_at`

**status 可选值**：`contacted`（已联系）, `valid`（有效商机）, `inquiry`（已询价）, `invalid`（无效）, `closed`（已关闭）

---

## 4. PostgREST 查询语法速查表

| 功能 | 语法 | 示例 |
|------|------|------|
| 精确匹配 | `?column=eq.value` | `?country=eq.Brazil` |
| 模糊搜索 | `?column=ilike.*关键词*` | `?name=ilike.*FPSO*` |
| 多条件 (AND) | `?a=eq.1&b=eq.2` | `?country=eq.Brazil&status=eq.Planned` |
| 选择指定列 | `?select=col1,col2,col3` | `?select=name,country,status` |
| 分页 | `?limit=N&offset=M` | `?limit=20&offset=0` |
| 升序排序 | `?order=column.asc` | `?order=created_at.asc` |
| 降序排序 | `?order=column.desc` | `?order=created_at.desc` |
| NULL 值排最后 | `?order=column.asc.nullslast` | `?order=water_depth_m.asc.nullslast` |
| 范围查询 | `?col=gte.MIN&col=lte.MAX` | `?water_depth_m=gte.500&water_depth_m=lte.2000` |

---

## 5. 前端调用代码模板（TypeScript / JavaScript）

### 5.1 使用 fetch（推荐，无框架依赖）

```typescript
const API_BASE = "https://zbxogsfnhagcavbvhypk.supabase.co/rest/v1";
const ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."; // 完整 key

async function getProjects(country?: string, limit = 20, offset = 0) {
  let url = `${API_BASE}/projects?select=*&limit=${limit}&offset=${offset}&order=created_at.desc`;
  if (country) url += `&country=eq.${encodeURIComponent(country)}`;

  const res = await fetch(url, {
    headers: {
      apikey: ANON_KEY,
      Authorization: `Bearer ${ANON_KEY}`,
      Accept: "application/json",
    },
  });
  if (!res.ok) throw new Error(`API Error: ${res.status}`);
  return res.json();
}
```

### 5.2 使用 Supabase JS SDK（如果秒搭输出的是 React 项目）

```typescript
import { createClient } from "@supabase/supabase-js";

const supabase = createClient(
  "https://zbxogsfnhagcavbvhypk.supabase.co",
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
);

// 获取项目列表
const { data, error } = await supabase
  .from("projects")
  .select("*")
  .eq("country", "Brazil")
  .order("created_at", { ascending: false })
  .limit(20);
```

---

## 6. 错误处理

| HTTP 状态码 | 含义 | 返回格式 |
|------------|------|---------|
| 200 | 成功 | JSON 数组或对象 |
| 400 | 请求参数错误 | `{"message":"..."}` |
| 401 | 认证失败（anon key 缺失或无效） | `{"message":"..."}` |
| 404 | 接口路径错误 | `{"message":"..."}` |
| 406 | 缺少 `Accept: application/json` 请求头 | 空响应 |

**前端统一错误处理**：
```typescript
async function apiFetch(path: string) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { apikey: ANON_KEY, Authorization: `Bearer ${ANON_KEY}`, Accept: "application/json" },
  });
  if (!res.ok) {
    console.error(`API Error ${res.status}: ${await res.text()}`);
    return []; // 返回空数组，不崩页面
  }
  return res.json();
}
```

---

## 7. 重要注意事项

1. **字段名严格一致**：API 返回 snake_case（如 `water_depth_m`），前端代码中必须使用相同字段名。不要自己改名为 camelCase，除非你主动在代码中做映射。
2. **空值处理**：约 15 个字段可能为 null。每个使用字段的地方都要做空值判断。
3. **分页**：响应头 `content-range` 格式为 `start-end/total`，解析后可获得总条数。
4. **URL 编码**：国家名含特殊字符（如 `Côte d'Ivoire`）时需 `encodeURIComponent()`。
5. **CRUD 操作**：本文档只列了 GET 读取接口。POST/PATCH/DELETE 写操作需要更严格权限，不在本文档范围。
