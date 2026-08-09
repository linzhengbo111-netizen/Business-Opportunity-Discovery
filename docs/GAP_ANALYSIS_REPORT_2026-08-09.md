# FPSO 不锈钢商机挖掘系统 — 差距分析报告

**日期**: 2026-08-09
**审计范围**: 完整代码库 + 数据库 Schema + 爬虫管线
**对比基准**: 项目终极目标 v1.0（6 项闭环）
**上次评估**: ~35%（2026-08-09 初版）
**本次评估**: ~50%（重大升级：工厂能力矩阵 + 商机匹配引擎）

---

## 一、总体评估

| 维度 | 上次 | 本次 | 变化 | 评级 |
|------|------|------|------|------|
| 1. 官方项目源锁定 | 65% | 65% | — | C |
| 2. AI 工况分析与材质匹配 | 40% | 65% | +25% | C |
| 3. 工厂能力双向筛选 | 0% | 75% | +75% | B |
| 4. 采购链实体挖掘 | 35% | 35% | — | D |
| 5. 商机清单自动输出 | 30% | 30% | — | D |
| 6. 提前 3-6 个月差异化获客 | 5% | 5% | — | F |
| **整体完成度** | **~35%** | **~50%** | **+15%** | — |

**结论**: 本次升级重点攻克了最大短板——工厂能力矩阵（0%→75%）和材质匹配引擎（40%→65%）。系统现在具备完整的工厂产能数据模型，材质推荐结果会过滤碳钢并标注 in_factory_scope，并新增了产品需求推断和客户类型匹配两个商机模块。剩余最大缺口：采购时间窗预测（5%）、商机清单导出（30%）、H2S/CO2 定量提取（0%填充率）。

---

## 二、逐项差距分析

### 目标 1: 官方项目源锁定

**整体完成度: 65%（未变）**

#### 已完成 ✅

| 功能 | 文件 | 行号 |
|------|------|------|
| ANP 巴西监管数据爬虫（含 PDF 解析） | [crawler/adapters/anp_development_plan.py](crawler/adapters/anp_development_plan.py) | 81-1894 |
| ANP CSV FPSO 数据爬虫 | [crawler/adapters/anp_fpso_csv.py](crawler/adapters/anp_fpso_csv.py) | 1-1354 |
| Guyana EPA 环境监管爬虫 | [crawler/adapters/guyana_epa.py](crawler/adapters/guyana_epa.py) | 1-1728 |
| Guyana Petroleum 管理数据 | [crawler/adapters/guyana_petroleum.py](crawler/adapters/guyana_petroleum.py) | 1-1442 |
| NSTA FDP 英国北海开发计划 | [crawler/adapters/nsta_fdp.py](crawler/adapters/nsta_fdp.py) | 1-1961 |
| Equinor Rosebank 项目页 | [crawler/adapters/equinor_rosebank.py](crawler/adapters/equinor_rosebank.py) | 1-899 |
| SBM Newsroom | [crawler/adapters/sbm_newsroom.py](crawler/adapters/sbm_newsroom.py) | 1-810 |
| MODEC Supply Chain | [crawler/adapters/modec_supplychain.py](crawler/adapters/modec_supplychain.py) | 1-703 |
| Petrobras 供应商页 | [crawler/adapters/petrobras_supplier.py](crawler/adapters/petrobras_supplier.py) | 1-811 |
| 媒体行业新闻爬虫（4 个） | [crawler/adapters/offshore_energy.py](crawler/adapters/offshore_energy.py), oe_digital.py, world_oil.py, splash247.py | 全文件 |
| 多优先级国家提取（FPSO名→运营商→油田→盆地→国家） | [crawler/adapters/media_common.py](crawler/adapters/media_common.py) | 2315-2444 |
| 项目别名跨源归一化（TS + Python 镜像） | [src/data/project_aliases.ts](src/data/project_aliases.ts), [media_common.py:1510-1941](crawler/adapters/media_common.py) | 全文件 |
| 时间过滤（MIN_PUBLICATION_DATE=2023-01-01） | [media_common.py:46](crawler/adapters/media_common.py) | 46 |
| GitHub Actions 定时爬虫（日+周） | [.github/workflows/crawl-daily.yml](.github/workflows/crawl-daily.yml), crawl-weekly.yml | 全文件 |

#### 缺失 / 薄弱 ❌

| 缺口 | 优先级 | 说明 |
|------|--------|------|
| **无 Petrobras 官方项目页爬虫** | P0 | 有供应商页但没有 Petrobras FPSO 项目列表页（Búzios, Mero, Marlim 等）的专用爬虫 |
| **无 ExxonMobil Guyana 项目页爬虫** | P0 | Stabroek Block 是全球最大 FPSO 新区，缺 Exxon 官方发布页 |
| **无 Suriname/ Angola/ Nigeria 监管源** | P1 | 只有媒体关键词匹配，缺乏官方监管数据源（如 ANPG Angola, NUPRC Nigeria） |
| **已完成项目过滤仅靠日期** | P1 | 缺少项目生命周期状态自动判定逻辑（delivered/completed vs active） |
| **无 SBM/MODEC 在建项目列表页爬虫** | P1 | 只有新闻页，没有项目状态跟踪页 |

#### 实现建议

**P0: 新建 `crawler/adapters/exxon_stabroek.py`**
- URL: `https://corporate.exxonmobil.com/locations/guyana`
- 提取: 每个 FPSO 项目名、FID 状态、预计投产日期、产能
- 参考 guyana_epa.py 的架构

**P0: 新建 `crawler/adapters/petrobras_projects.py`**
- URL: ANP + Petrobras 投资者关系页
- 提取: Búzios, Mero, Marlim 等在建 FPSO 的技术参数

---

### 目标 2: AI 工况分析与材质匹配

**整体完成度: 40% → 65%（+25%）**

#### 本次升级 🆕

| 功能 | 文件 | 说明 |
|------|------|------|
| 碳钢自动过滤 | [src/lib/material_matcher.ts](src/lib/material_matcher.ts) | `matchMaterials()` 在排序后过滤所有碳钢/排除材质牌号 |
| in_factory_scope 标注 | [src/lib/material_matcher.ts](src/lib/material_matcher.ts) | 每个推荐牌号附带 `in_factory_scope` 布尔标签 |
| can_manufacture() 函数 | [src/lib/material_matcher.ts](src/lib/material_matcher.ts) | 传入任意材质牌号，返回是否在工厂产能内（双重检查: producible & not excluded） |
| infer_product_needs() 函数 | [src/lib/material_matcher.ts](src/lib/material_matcher.ts) | 根据设备描述关键词推断所需产品类型（14 条映射规则），标记"AI推断" |
| match_customer_type() 函数 | [src/lib/material_matcher.ts](src/lib/material_matcher.ts) | 根据项目文本匹配 4 类目标客户 + 4 类排除客户，返回布尔 + 标签 |
| GradeRecommendation 类型 | [src/lib/material_matcher.ts](src/lib/material_matcher.ts) | 替代旧 `string[]`，包含 `{grade, in_factory_scope}` |
| 工厂过滤标注 UI | [src/pages/DashboardPage.tsx](src/pages/DashboardPage.tsx) | 可生产牌号蓝色标注，不可生产牌号红色删除线 + "(not producible)" |
| parseRecommendation() 兼容升级 | [src/lib/material_matcher.ts](src/lib/material_matcher.ts) | 同时兼容旧格式 `string[]` 和新格式 `GradeRecommendation[]` |

#### 已完成 ✅

| 功能 | 文件 | 行号 |
|------|------|------|
| 18 条规则引擎（水深/产能/船型/H2S/CO2/盆地/运营商） | [src/lib/material_matcher.ts](src/lib/material_matcher.ts) | 149-367 |
| 6 种不锈钢牌号定义（316L → Inconel 625） | [src/lib/material_matcher.ts](src/lib/material_matcher.ts) | 51-131 |
| 3 级置信度（high/medium/low） | [src/lib/material_matcher.ts](src/lib/material_matcher.ts) | 444-451 |
| 文章文本→技术规格提取（水深/产能/船型/运营商/盆地/油田） | [crawler/adapters/media_common.py](crawler/adapters/media_common.py) | 2100-2298 |
| ANP PDF 文本关键词提取（材料+腐蚀介质+技术参数） | [crawler/adapters/anp_development_plan.py](crawler/adapters/anp_development_plan.py) | 493-697 |
| 技术规格 DB 字段（7 个） | [migrations/013_add_technical_specs.sql](migrations/013_add_technical_specs.sql) | 26-66 |
| 技术规格回填（ANP 数据 → projects） | [migrations/015_backfill_tech_specs.sql](migrations/015_backfill_tech_specs.sql) | 全文件 |
| recommendation_json 存储与展示 | [migrations/013:72-83](migrations/013_add_technical_specs.sql), [DashboardPage.tsx:1124-1363](src/pages/DashboardPage.tsx) | — |
| `matchMaterials()` 引擎 + `specsFromRow()` DB 桥接 | [src/lib/material_matcher.ts](src/lib/material_matcher.ts) | 392-515 |

#### 缺失 / 薄弱 ❌

| 缺口 | 优先级 | 说明 |
|------|--------|------|
| **H2S/CO2 仅有布尔标记，无定量提取** | P0 | Python 爬虫不提取 hasH2S/hasCO2 字段。TypeScript 定义中 hasH2S/hasCO2 为 boolean，但 crawler 从不写入这两个字段 |
| **hasHighTemp/hasHighPressure 永不为 true** | P0 | TS 类型定义了但 Python 无任何提取逻辑 |
| **infer_product_needs() 未集成到前端** | P1 | 函数已定义，但 DashboardPage 和 OpportunityList 尚未调用和展示 |
| **match_customer_type() 未集成到前端** | P1 | 函数已定义，但未在项目卡片或 Modal 中展示客户类型匹配结果 |
| **材料匹配未在爬虫端运行** | P1 | `matchMaterials()` 只在 DashboardPage 显示时前端运行，未在入库时自动计算并写入 `recommendation_json` |
| **无温度/压力具体数值提取** | P2 | ANP PDF 中有设计温度/压力数据，但未提取为结构化字段 |

#### 实现建议

**P0: `crawler/adapters/media_common.py` 新增 H2S/CO2 提取函数**

```python
def extract_h2s_from_article(text: str) -> Optional[bool]:
    """Detect H2S / sour service mentions in article text."""
    patterns = [
        r"\bH2S\b", r"hydrogen\s+sulfi[dt]e", r"sour\s+(?:gas|service|environment)",
        r"NACE\s*MR\s*0175", r"ISO\s*15156",
    ]
    for pat in patterns:
        if re.search(pat, text, re.IGNORECASE):
            return True
    return None

def extract_co2_from_article(text: str) -> Optional[bool]:
    """Detect CO2 / carbon dioxide corrosion mentions."""
    patterns = [
        r"\bCO2\b", r"carbon\s+dioxide", r"carbonic\s+acid",
        r"CO2\s+corrosion", r"CO2\s+content", r"sweet\s+corrosion",
    ]
    for pat in patterns:
        if re.search(pat, text, re.IGNORECASE):
            return True
    return None
```

**P0: 在 `extract_tech_specs_from_article()` 中加入 H2S/CO2 返回**

修改 [media_common.py:2275-2298](crawler/adapters/media_common.py) 的返回字典，增加 `has_h2s` 和 `has_co2` 布尔字段。

**P1: 前端集成 infer_product_needs() 和 match_customer_type()**

在 DashboardPage 项目卡片或 Modal 中展示推断的产品需求和客户类型匹配结果。

**P1: 爬虫端自动运行材料匹配**

在 `promote_accepted_candidates()` 函数（或新建触发器中），对每个入库 project 运行 `matchMaterials()` 并将结果写入 `recommendation_json`。

---

### 目标 3: 工厂能力双向筛选

**整体完成度: 0% → 75%（+75%）🆕 重大突破**

#### 本次升级 🆕

| 功能 | 文件 | 说明 |
|------|------|------|
| PRODUCT_TYPES 枚举（10 种产品） | [src/data/factory_capabilities.ts](src/data/factory_capabilities.ts) | SEAMLESS_PIPE 到 STEEL_WIRE，含中英文标签 |
| PRODUCIBLE_MATERIALS（3 大类 37 个牌号） | [src/data/factory_capabilities.ts](src/data/factory_capabilities.ts) | 不锈钢 15 个 + 双相钢 6 个 + 镍基合金 14 个 |
| EXCLUDED_MATERIALS（碳钢 18 个牌号） | [src/data/factory_capabilities.ts](src/data/factory_capabilities.ts) | A106/A53/API 5L/A333/A335/SA516 等完整碳钢排除清单 |
| TARGET_CUSTOMER_KEYWORDS（4 类 × ~10 关键词） | [src/data/factory_capabilities.ts](src/data/factory_capabilities.ts) | 换热器制造商/不锈钢管分销商/水处理方案商/海上钻井平台方案商 |
| EXCLUDED_CUSTOMER_KEYWORDS（4 类 × ~8 关键词） | [src/data/factory_capabilities.ts](src/data/factory_capabilities.ts) | 小型贸易公司/库存商/个人转售/小批量批发 |
| FACTORY_CAPABILITIES 详细产能记录（43 条） | [src/data/factory_capabilities.ts](src/data/factory_capabilities.ts) | 每条含 grade / canProduce / maxSize / schedule / productTypes / notes |
| isGradeProducible() / isGradeExcluded() | [src/data/factory_capabilities.ts](src/data/factory_capabilities.ts) | O(1) Set 查找 + 子串匹配 |
| PRODUCIBLE_GRADE_SET / EXCLUDED_GRADE_SET | [src/data/factory_capabilities.ts](src/data/factory_capabilities.ts) | 预构建 Set 供快速查询 |

#### 缺失 ❌

| 缺口 | 优先级 | 说明 |
|------|--------|------|
| **工厂能力管理后台** | P2 | 当前能力数据是硬编码常量。以后需要 Supabase 管理后台或配置文件热更新 |
| **产能实时同步** | P2 | 工厂新增/淘汰产品线时需手动更新代码 |
| **maxSize/schedule 未用于匹配过滤** | P1 | 当前只过滤材质牌号，未按尺寸/壁厚进一步过滤（如项目需要 20" Sch 160 但工厂最多 16"） |

#### 实现建议

**P1: matchMaterials() 增加尺寸过滤**

```typescript
export function filterBySize(
  grades: GradeRecommendation[],
  requiredSize: string,
): GradeRecommendation[] {
  // Parse "24 inch" → numeric, compare against required
  // Filter out grades where maxSize < requiredSize
}
```

**P2: 新建 Supabase 表 `factory_capabilities`**

```sql
CREATE TABLE factory_capabilities (
  id SERIAL PRIMARY KEY,
  grade TEXT NOT NULL,
  can_produce BOOLEAN NOT NULL DEFAULT true,
  max_size_inch NUMERIC,
  schedule TEXT,
  product_types TEXT[],
  notes TEXT,
  updated_at TIMESTAMPTZ DEFAULT now()
);
```

用 Supabase 管理后台替代硬编码常量，支持非开发人员更新产能数据。

---

### 目标 4: 采购链实体挖掘

**整体完成度: 35%（未变）**

#### 已完成 ✅

| 功能 | 文件 | 行号 |
|------|------|------|
| PROCUREMENT_ENTITIES 字典（70+ 实体，3 分类） | [media_common.py](crawler/adapters/media_common.py) | 1978-2044 |
| `extract_procurement()` 函数 | [media_common.py](crawler/adapters/media_common.py) | 2047-2079 |
| procurement_chain 字段（逗号分隔） | DB + [media_common.py:2802](crawler/adapters/media_common.py) | — |
| Dashboard 展示采购链标签 | [DashboardPage.tsx](src/pages/DashboardPage.tsx) | 1045-1057 |
| 项目详情 Modal 展示采购链 | [DashboardPage.tsx](src/pages/DashboardPage.tsx) | 1263-1274 |

#### 缺失 ❌

| 缺口 | 优先级 | 说明 |
|------|--------|------|
| **无实体官网 URL/联系方式** | P0 | 只知道实体名，没有 URL 或联系入口 |
| **无结构化实体表** | P1 | 当前是逗号分隔字符串，无法做实体级分析 |
| **无实体-项目关系模型** | P1 | 无法回答 "SBM Offshore 出现在哪些项目中" |
| **无实体角色分类展示** | P2 | 前端不区分 Contractor / EPC / Equipment Supplier |
| **无关键设备商专项挖掘** | P2 | 当前只提取名称，不提取具体设备类型（压缩机/热交换器等） |

#### 实现建议

**P0: 新建 `src/data/procurement_entities.ts` 包含 URL 映射**

```typescript
export const PROCUREMENT_ENTITIES_WITH_URLS: Record<string, { type: string; url: string }> = {
  "SBM Offshore": { type: "Contractor/Shipyard", url: "https://www.sbmoffshore.com" },
  "MODEC": { type: "Contractor/Shipyard", url: "https://www.modec.com" },
  "TechnipFMC": { type: "Topsides EPC", url: "https://www.technipfmc.com" },
  // ... 70+ entries
};
```

**P1: 新建迁移 `018_create_entities.sql`**

```sql
CREATE TABLE IF NOT EXISTS procurement_entities (
  id SERIAL PRIMARY KEY,
  entity_name TEXT NOT NULL UNIQUE,
  entity_type TEXT NOT NULL,
  website_url TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS project_entities (
  project_id INTEGER REFERENCES projects(id),
  entity_id INTEGER REFERENCES procurement_entities(id),
  source_name TEXT,
  PRIMARY KEY (project_id, entity_id)
);
```

---

### 目标 5: 商机清单自动输出

**整体完成度: 30%（未变）**

#### 已完成 ✅

| 功能 | 文件 | 行号 |
|------|------|------|
| DashboardPage 含完整筛选器 | [DashboardPage.tsx](src/pages/DashboardPage.tsx) | 310-1495 |
| FilterSidebar（国家/行业/置信度/状态） | [FilterSidebar](src/components/dashboard/FilterSidebar.tsx) | — |
| 项目详情 Modal（技术规格+材质匹配+采购链） | [DashboardPage.tsx](src/pages/DashboardPage.tsx) | 1112-1491 |
| 国家分布饼图 + 状态柱状图 | [DashboardPage.tsx](src/pages/DashboardPage.tsx) | 809-908 |
| 世界地图光点 | [DashboardPage.tsx](src/pages/DashboardPage.tsx) | 767-806 |
| 用户关注/订阅按钮 | [DashboardPage.tsx](src/pages/DashboardPage.tsx) | 1212-1228 |

#### 缺失 ❌

| 缺口 | 优先级 |
|------|--------|
| 无 CSV/Excel/PDF 导出功能 | P0 |
| 无 "商机清单" 专用页面（销售视角） | P0 |
| 无商机评分/排序（优先级 = 工厂能力匹配 × 采购时间窗紧迫度 × 项目规模） | P1 |
| 无实体联系入口（官网链接） | P1 |
| 无按需订阅推送（"巴西有新项目时通知我"） | P2 |

#### 实现建议

**P0: 新建 `src/components/dashboard/ExportButton.tsx`**

```typescript
function exportToCSV(projects: Project[]): void {
  const headers = ["Project", "Country", "Status", "Operator", "Water Depth (m)",
    "Oil Cap (bpd)", "Gas Cap (MMcmd)", "Hull Type", "Stainless Steel",
    "Application", "Procurement Chain", "Confidence", "Source", "Source Date"];
  const rows = projects.map(p => [
    p.name, p.country, p.status, p.operatorName ?? "",
    p.waterDepthM ?? "", p.oilCapacityBpd ?? "", p.gasCapacityMmcmd ?? "",
    p.hullType ?? "", p.stainlessSteel, p.application, p.procurementChain,
    p.confidence, p.source.name, p.source.date,
  ]);
  const csv = [headers, ...rows].map(r => r.map(c => `"${String(c).replace(/"/g, '""')}"`).join(",")).join("\n");
  const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = `fpso_opportunities_${new Date().toISOString().slice(0,10)}.csv`;
  a.click(); URL.revokeObjectURL(url);
}
```

**P0: 新建 `src/pages/OpportunityListPage.tsx`**

销售视角页面，每个卡片包含：项目名、业主、总包方、预计采购时间、所需材质、工厂能力匹配标注（绿色可做/红色不可做）、联系方式/官网入口。

---

### 目标 6: 提前 3-6 个月差异化获客

**整体完成度: 5%（未变）**

#### 已完成 ✅

| 功能 | 文件 | 行号 |
|------|------|------|
| 项目阶段进度条（规划/FEED/在建/投产） | [DashboardPage.tsx](src/pages/DashboardPage.tsx) | 185-209, 1060-1077 |
| 里程碑预览标签 | [DashboardPage.tsx](src/pages/DashboardPage.tsx) | 58-77, 1080-1093 |
| 项目时间线 Modal | [DashboardPage.tsx](src/pages/DashboardPage.tsx) | 1395-1486 |
| 用户订阅表（基础设施） | [migrations/017_create_user_subscriptions.sql](migrations/017_create_user_subscriptions.sql) | 全文件 |

#### 缺失 ❌

| 缺口 | 优先级 | 说明 |
|------|--------|------|
| **无采购时间窗推算模型** | P0 | 不能估算 "该FPSO什么时候开始采购不锈钢管件" |
| **无 lead time 计算** | P0 | 不能根据项目阶段推算提前接触客户的最佳时间 |
| **无 "即将进入采购期" 预警** | P0 | 当前系统是被动的数据展示，不是主动商机提醒 |
| **无采购时间线 UI** | P1 | 前端没有 "预计Q3 2026开始采购" 这样的标注 |
| 用户订阅系统缺触发逻辑 | P1 | 有表但无通知发送服务（notifier.py 存在但未与时间窗联动） |

#### 实现建议

**P0: 新建 `src/lib/procurement_timeline.ts`**

```typescript
/**
 * FPSO 项目阶段 → 不锈钢管件采购时间窗推算
 *
 * 行业经验:
 *   - FID 后 3-6 个月: 长周期设备采购（压缩机、热交换器）
 *   - FID 后 6-12 个月: 大宗管道/管件采购
 *   - 船体下水后 2-4 个月: 第二批管件/法兰采购
 *   - 投产前 3-6 个月: 备品备件采购
 */
interface ProcurementWindow {
  earliest: Date;
  latest: Date;
  confidence: "high" | "medium" | "low";
  description: string;
}

const PROJECT_PHASE_OFFSETS: Record<string, { monthsFromFid: [number, number]; items: string[] }> = {
  "FID_CONFIRMED": { monthsFromFid: [0, 0], items: ["Initial inquiry"] },
  "FPSO_CONTRACT_AWARDED": { monthsFromFid: [1, 3], items: ["Long-lead equipment"] },
  "CONSTRUCTION_START": { monthsFromFid: [6, 12], items: ["Bulk piping", "Fittings", "Flanges"] },
  "HULL_LAUNCH": { monthsFromFid: [12, 18], items: ["Second-batch piping", "Valves"] },
  "TOPSIDES_INTEGRATION": { monthsFromFid: [18, 24], items: ["Final fittings", "Spares"] },
  "FIRST_OIL": { monthsFromFid: [24, 30], items: ["MRO spares"] },
};

export function estimateProcurementWindow(
  projectPhase: string,
  fidDate: string | null,
  firstOilDate: string | null,
): ProcurementWindow | null {
  // ... 推算逻辑
}
```

**P0: 在 DashboardPage 项目卡片上显示采购时间窗**

在 [DashboardPage.tsx](src/pages/DashboardPage.tsx) 1007 行附近（技术规格行），新增采购时间窗徽章：

```tsx
{project.estimatedProcurementWindow && (
  <span className="inline-flex items-center gap-1 rounded bg-green-500/10 px-1.5 py-0.5 text-[10px] font-semibold text-green-400">
    <Clock className="h-3 w-3" />
    Procurement: {project.estimatedProcurementWindow}
  </span>
)}
```

**P1: 激活 notifier.py 的采购时间窗通知**

修改 [crawler/notifier.py](crawler/notifier.py)，新增检查逻辑：扫描 projects 表，若项目进入采购时间窗（当前日期在 [earliest-30d, latest] 范围内），向关注该项目的用户发送通知。

---

## 三、数据质量评估

### 3.1 当前数据库字段覆盖率（推测，基于代码分析）

| 字段 | 填充来源 | 估计填充率 | 数据质量 |
|------|---------|-----------|---------|
| `name` | 爬虫提取 | ~95% | 良好（有别名系统归一化） |
| `country` | 多优先级提取 | ~90% | 良好（7 层 fallback） |
| `status` | 关键词匹配 | ~70% | 中等（依赖新闻标题措辞） |
| `water_depth_m` | ANP PDF + 文章提取 | ~20% | 低（ANP 覆盖率好，媒体文章低） |
| `oil_capacity_bpd` | ANP PDF + 文章提取 | ~20% | 同上 |
| `gas_capacity_mmcmd` | ANP PDF + 文章提取 | ~15% | 同上 |
| `hull_type` | 文章提取 | ~10% | 低（很少在新闻中出现） |
| `field_name` | ANP + 文章提取 | ~30% | 中等 |
| `operator_name` | ANP + 文章提取 | ~35% | 中等 |
| `basin` | ANP + 文章提取 | ~30% | 中等 |
| `has_h2s` | **未提取** | 0% | 无数据 |
| `has_co2` | **未提取** | 0% | 无数据 |
| `stainless_steel` | ANP PDF 关键词 | ~15% | 低（仅 ANP 来源） |
| `application` | ANP PDF | ~10% | 低 |
| `procurement_chain` | 文章实体识别 | ~40% | 中等 |
| `recommendation_json` | 前端运行时 | 0% | **从未持久化**（注：v2 引擎已就绪，需爬虫端触发） |

### 3.2 关键数据缺口

1. **H2S/CO2 数据: 0%** — 这是材料选型的核心输入，当前爬虫完全不提取。需要从 ANP PDF、行业报告、技术文章中提取。
2. **水深/产能数据: 15-20%** — ANP 源有结构化数据，但媒体文章提取率低。应优先加强 ANP 源的数据覆盖。
3. **recommendation_json: 0%** — 材料匹配引擎 v2 已就绪（含工厂过滤），但仅在前端运行时计算，从未写入数据库。应在爬虫端或 Supabase Edge Function 中自动计算并持久化。

### 3.3 数据源增强建议

| 优先级 | 动作 | 预期效果 |
|--------|------|---------|
| P0 | 补齐 ANP PDF 未回填的项目（44 条已有迁移，检查是否全部覆盖） | 立即提升技术参数填充率 |
| P0 | 新增 Petrobras、Exxon 项目页爬虫 | 获得 Búzios、Mero、Stabroek 等核心项目的官方技术参数 |
| P1 | 从 Equinor、MODEC 年报/投资者关系 PDF 中提取技术数据 | 获得水深、产能、H2S/CO2 等定量数据 |
| P1 | 集成 Wood Mackenzie 或 Rystad Energy 等付费数据源（远期） | 商业级数据质量 |
| P2 | 从 SPE（Society of Petroleum Engineers）论文中提取工况数据 | 获得巴西 pre-salt 的高 CO2 含量具体数值 |

---

## 四、下一步最优行动清单

按投入产出比排序：

| 排序 | 任务 | 预计工时 | 影响 | 投入产出比 | 状态 |
|------|------|---------|------|-----------|------|
| **1** | **P0: 爬虫新增 H2S/CO2 提取 + article→hasH2S/hasCO2** | 1-2h | 让 18 条规则中的 sour-service 和 co2-corrosion 规则真正生效 | ★★★★★ | 待做 |
| **2** | **P0: 爬虫端入库时自动运行 `matchMaterials()` 并写入 `recommendation_json`** | 2h | recommendation_json 填充率从 0%→80%+，前端展示立即可用 | ★★★★★ | 待做 |
| **3** | **P0: 新建 `src/lib/procurement_timeline.ts` + 阶段→时间窗推算** | 3-4h | 解锁差异化获客核心价值 | ★★★★★ | 待做 |
| **4** | **P0: 新建 `src/pages/OpportunityListPage.tsx` + CSV 导出** | 4-6h | 销售团队直接可用 | ★★★★☆ | 待做 |
| **5** | **P1: 前端集成 `infer_product_needs()` 和 `match_customer_type()`** | 2-3h | 项目卡片展示产品需求和客户类型匹配（函数已就绪） | ★★★★☆ | 待做 |
| **6** | **P1: `procurement_entities` 表 + URL 映射** | 2h | 让采购链实体从"名字"变成"可联系的客户" | ★★★★☆ | 待做 |
| **7** | **P0: 新建 Petrobras + Exxon 项目页爬虫** | 4-6h | 提升核心项目数据覆盖率 | ★★★☆☆ | 待做 |
| **8** | **P1: 激活 notifier.py 采购时间窗通知** | 2-3h | 从被动查询变为主动推送 | ★★★☆☆ | 待做 |
| **9** | **P1: AI 增强 — 用 LLM 分析 ANP PDF 技术文本** | 8-12h | 从关键词匹配跃升至真正 AI 分析 | ★★★☆☆ | 待做 |
| **10** | **P2: 工厂能力管理后台（Supabase 表）** | 4-6h | 运维便利性，非开发人员可更新产能 | ★★☆☆☆ | 待做 |

### 建议实施节奏

**Week 1 (立即)**: 任务 1 + 2 + 5 → 让材料匹配和工厂筛选闭环跑通 + 前端可交互
**Week 2**: 任务 3 + 4 → 让销售团队看到可用的商机清单 + 时间窗
**Week 3**: 任务 6 + 7 → 充实数据源和客户信息
**Week 4**: 任务 8 + 9 → AI 增强和主动推送

---

## 五、附录：模块完成度矩阵（更新后）

| 模块 | 子系统 | 上次 | 本次 | 变化 | 关键文件 |
|------|--------|------|------|------|---------|
| **数据采集** | ANP 巴西监管 | 85% | 85% | — | anp_development_plan.py, anp_fpso_csv.py |
| | Guyana EPA | 80% | 80% | — | guyana_epa.py, guyana_petroleum.py |
| | UK NSTA | 75% | 75% | — | nsta_fdp.py |
| | Equinor | 60% | 60% | — | equinor_rosebank.py, equinor_supplier.py |
| | SBM/MODEC | 50% | 50% | — | sbm_newsroom.py, modec_supplychain.py |
| | Petrobras | 40% | 40% | — | petrobras_supplier.py (仅供应商页) |
| | 行业媒体 | 70% | 70% | — | offshore_energy.py, oe_digital.py, world_oil.py, splash247.py |
| | ExxonMobil | 0% | 0% | — | — (不存在) |
| **数据归一化** | 项目别名系统 | 80% | 80% | — | project_aliases.ts, media_common.py |
| | 国家提取 | 90% | 90% | — | media_common.py: extract_country() |
| | 项目名提取 | 75% | 75% | — | media_common.py: extract_project_info() |
| **技术分析** | 工况参数提取 | 35% | 35% | — | media_common.py: extract_tech_specs_from_article() |
| | H2S/CO2 提取 | 0% | 0% | — | — (不存在) |
| | 材料匹配引擎 | 60% | 80% | **+20%** 🆕 | material_matcher.ts (v2 with factory filter) |
| | 工厂能力数据模型 | 0% | 90% | **+90%** 🆕 | factory_capabilities.ts (全新文件) |
| | 工厂能力筛选逻辑 | 0% | 80% | **+80%** 🆕 | material_matcher.ts (canManufacture + grade filter) |
| | 产品需求推断 | 0% | 70% | **+70%** 🆕 | material_matcher.ts (infer_product_needs) |
| | 客户类型匹配 | 0% | 75% | **+75%** 🆕 | material_matcher.ts (match_customer_type) |
| **采购链** | 实体识别 | 55% | 55% | — | media_common.py: extract_procurement() |
| | 结构化实体表 | 0% | 0% | — | — (不存在) |
| | URL/联系方式 | 0% | 0% | — | — (不存在) |
| **商机输出** | 仪表盘 | 70% | 75% | **+5%** 🆕 | DashboardPage.tsx (factory scope badges) |
| | 导出功能 | 0% | 0% | — | — (不存在) |
| | 商机清单页 | 0% | 0% | — | — (不存在) |
| **采购时间窗** | 阶段推算 | 5% | 5% | — | DashboardPage.tsx (仅进度条) |
| | 时间窗估算 | 0% | 0% | — | — (不存在) |
| | 主动预警 | 0% | 0% | — | — (不存在) |

### 本次升级摘要

| 新增文件 | 行数（估） | 说明 |
|---------|-----------|------|
| [src/data/factory_capabilities.ts](src/data/factory_capabilities.ts) | ~420 | 完整工厂能力矩阵：10 种产品、37 个可生产牌号、18 个碳钢排除牌号、4 类目标客户 + 4 类排除客户关键词、43 条详细产能记录 |

| 修改文件 | 变化 | 说明 |
|---------|------|------|
| [src/lib/material_matcher.ts](src/lib/material_matcher.ts) | +140 行 | 新增 `GradeRecommendation` 类型、碳钢过滤逻辑、`in_factory_scope` 标注、`can_manufacture()`、`infer_product_needs()`（14 条设备→产品映射）、`match_customer_type()`（8 类客户模式匹配） |
| [src/pages/DashboardPage.tsx](src/pages/DashboardPage.tsx) | ~10 行修改 | Modal 中 Grade 展示适配 `GradeRecommendation` 类型，可生产标注蓝色、不可生产红色删除线 |

---

*报告由系统架构审计自动生成。所有行号基于 2026-08-09 代码快照。*
*本次升级: 工厂能力矩阵 (目标3) 0→75%，材质匹配引擎 (目标2) 40→65%，总体 35%→50%。*
