# FPSO 商机挖掘系统状态审计（2026-08-23）

审计方式：逐项读代码 + 对线上 Supabase（projects 1168 行、candidate_events 2703 行）跑脚本复现各页面的真实过滤/排序管线 + 检查线上 Cloudflare Workers 部署。只诊断，未改任何代码。

---

## 1. 商机看板排序 — 结论：排序代码正确，但默认视图下置顶项目根本不显示（问题未解决）

### 代码现状（src/pages/DashboardPage.tsx:732-786）

过滤链：country → industry → confidence → phase（置顶豁免）→ search/maturity → 排序。
排序：`sortPriorityFirst` 置顶按 `PRIORITY_PROJECT_NAMES` 顺序排最前，其余按 `scoreOpportunity().totalScore` 降序，同分名称升序，异常 -1 沉底。每个项目只评分一次（Map 缓存）。

### 真实默认视图（复现线上管线，未加任何筛选改动）

页面默认值（DashboardPage.tsx:571-579）：
- `selectedConfidence = "High & Medium"` — **low 置信度项目被默认排除**
- `selectedPhases` = 全部 10 个阶段、`showAllProjects = true`

结果：
```
默认视图共显示 308 / 1168 个项目
置顶项目可见数: 0 / 3
默认前 10:
  #1  Belinda                66  Approval  high
  #2  Payara (FPSO Prosperity) 66  Approval  high
  #3  Rosebank (FPSO Rosebank) 66  Approval  high
  #4  Victory                66  Approval  high
  #5  Tartaruga Verde        65  Approval  high
  #6  ABIGAIL                55  Approval  high   ← UK 噪音
  #7  AFFLECK REDEVELOPMENT  55  Approval  high   ← UK 噪音
  #8  AFFLECK Redevelopment FDPA 55  Approval  high ← UK 噪音
  #9  ALLIGIN                55  Approval  high   ← UK 噪音
  #10 ALLIGN                 55  Approval  high   ← UK 噪音
```

### 根因

三个置顶项目都是 Delivery 阶段。commit 7ec2633 把 Delivery/Commissioning 的置信度强制压成 low。置信度筛选在阶段筛选**之前**执行，而置顶豁免只写在阶段筛选之后（DashboardPage.tsx:749-758），只救"被阶段筛选排除"的项目，救不了"被置信度筛选排除"的项目。排序逻辑再对也轮不到它们——它们根本不在列表里。

所以"用户反馈前三个不是置顶项目"**至今仍真实存在**：用户打开默认页面看到的是 Belinda/Payara/Rosebank，置信度切到 All 才看得到三个置顶。之前诊断归因为"并行部署覆盖"，那是历史原因之一，但代码层的置信度筛选缺陷一直都在。

### 若用户手动切 confidence = All

三个置顶 59/59/58 排前三 ✓；其余按评分降序：Belinda 66 … ABIGAIL #16、AFFLECK×2 #17-18；纯噪音 WREN/YARE/YORK/YORK FDP ADDENDUM/YTHAN（24 分）在 #1164-1168 沉底 ✓。评分降序排序本身工作正常。

### 线上部署核对

- 线上 active version `1d67a144-bb6c-4668-ab9e-c61df14479a8`（2026-08-22T16:48Z，Source "Unknown (version_upload)"，非我们最近一次提交的部署）
- 线上 JS `assets/index-B9De2OFF.js` 含 `PRIORITY_PROJECT_NAMES`、`FPSO ALMIRANTE TAMANDARE`、`评分 ≥ 55`、`待挖掘项目`、`localeCompare` 等全部功能标记；与本地 build（index-BmDS7qGB.js）diff 仅 minifier 变量名差异，内容等价。**线上 = 当前代码**。
- 风险：同一 Cloudflare 账号存在并行部署者，本次审计时线上又被 version_upload 覆盖过。路演前需约定"谁部署"。

---

## 2. 战报中心 — 结论：16 张卡，前三为置顶，AI 链路可用

### 过滤逻辑（src/pages/BattleCardsPage.tsx:268-293）

1. 有阶段（≠ Unknown）+ 有时间线事件（`hasTimelineData`）
2. 排除 Delivery/Commissioning（置顶豁免）
3. 评分 ≥ 55（置顶豁免）
4. 评分降序，置顶按常量顺序排最前

实际复现：**16 张卡**，前三 = FPSO Almirante Tamandaré 59 / Bacalhau 59 / Cidade de Sepetiba 58 ✓；其后 Belinda 66、Payara 66、Rosebank 66、Victory 66、Tartaruga Verde 65、Guyana 系列 8 张 55 分。无 UK 噪音卡。

### AI 内容完整性

- 摘要卡：推荐产品/材质/时间窗 显示 AI 结果（AI 返回后），请求期间显示琥珀色 "AI 分析中…"（BattleCardsPage.tsx:162-206）
- 完整作战卡弹窗：材质/产品逐条带 reason、时间窗带 reasoning（BattleCard.tsx:239-282, 368-380）
- 线上 `/api/llm/status` = `{"configured":true}`；实测 POST /api/llm 返回合法 chat.completion（model deepseek-v4-flash）✓

### 一处不一致（非致命）

本页 `hasTimelineData` 的事件计数来自 `useTimelineEventCounts`，统计**所有 review_status** 的事件（含 503 条 pending、979 条 rejected）。注释写"有 accepted 时间线事件"，实际比注释宽松。时间线页则只算 accepted。两页"有没有事件"口径不一致。

---

## 3. 项目时间线 — 结论：分组、置顶、默认选中均正常

- 选择器分两组：有 accepted 事件（49 个）/ 待挖掘（1119 个，折叠组，点击展开）（ProjectTimelinePage.tsx:401-418）✓
- 置顶在"有事件"组内按常量顺序排最前（sortPriorityFirst，canonicalId 匹配）✓
- 三个置顶的 accepted 事件数：Tamandaré 4、Bacalhau 4、Sepetiba 4，全部落在"有事件"组 ✓
- 默认选中 = 有事件项目里置顶顺序第一个（Tamandaré），首屏必有时间线（ProjectTimelinePage.tsx:240-248）✓

---

## 4. AI 个性化分析 — 结论：前端链路完整可用，爬虫侧无重试

### 前端（src/lib/push_analyst.ts + src/hooks/usePushAnalysis.ts）

- `analyzePush()` 永不 throw；LLM 未配置/HTTP 失败/JSON 非法 → 规则引擎兜底（source:'rules'，同样的字段结构）
- 失败重试：失败不进缓存，冷却 30s 后下一个调用者自动重试 LLM；配置检查失败同样 30s 后重查（push_analyst.ts:360-400）
- 成功结果按项目名会话级缓存，并发组件共享一次 LLM 调用
- 加载态：`usePushAnalysisState` 暴露 loading，卡片显示 "AI 分析中…"；仅卡片进入视口才触发（IntersectionObserver）
- Prompt 强制个性化：时间窗必须引用事件原文具体线索（FID/开工/授标日期推导），材质结合技术参数给理由，产品结合阶段给理由，Delivery 项目输出历史采购窗口而非"时间未定"（push_analyst.ts:240-254）

### 爬虫（crawler/ai_push_analyst.py）

- `analyze_for_push` 有 `_rules_fallback`，但**无重试循环**：单次调用失败即回落规则。与 TS 侧的"30s 后重试"策略不一致。影响有限（下次爬取轮次会重新触发），但属可以改进项。

---

## 5. 飞书推送链路 — 结论：阶段过滤、卡片信息、链接域名均正确

（crawler/notifier.py）

- 阶段门：`_EXCLUDED_PHASES = {"delivery", "commissioning"}`，`normalize_phase` 先做 legacy 映射（delivered/completed/under construction/planned）（notifier.py:111-120, 584-594）✓
- 卡片内容：项目定位（油田/运营商/盆地/水深/产能/船型）、简介、国家/阶段/评分/时间窗、AI 时间窗依据、推荐产品与牌号逐条带理由、AI 摘要、下一步行动、联系路径（EPC/承包商/来源链接）— 完整 ✓
- "View Details" 按钮默认指向 `https://business-opportunity-discovery.linzhengbo111.workers.dev/database?project=...`（notifier.py:199, 410），workers.dev 新域名 ✓
- 每条推送 AI 分析缓存按项目只调一次 LLM ✓

---

## 6. 数据质量现状 — 结论：数据规模大但卫生状况差，是路演最大隐患

### projects 表（1168 行）

| 阶段分布 | 行数 | 置信度分布 | 行数 |
|---|---|---|---|
| Delivery | 828 (71%) | low | 860 (74%) |
| Approval | 284 (24%) | high | 293 (25%) |
| Unknown | 35 | medium | 15 |
| Planning/Concept/Design/Construction/Procurement/EPC Award/Commissioning | 各 1-4 | | |

- high 置信度 + 进行中（非 Delivery/Commissioning）：293 个，但名单前部几乎全是 UK 噪音名（ABIGAIL、AFFLECK、ALLIGIN、ALLIGN、ALWYN EAST…）
- UK 项目占 850/1168（73%），其中真实 FPSO（Belinda/Rosebank/Victory 等）只占少数
- 看板（confidence=All 时）噪音位置：ABIGAIL #16、AFFLECK×2 #17-18；默认视图（High & Medium）噪音从 #6 就开始

### candidate_events 表（2703 行）

| review_status | 行数 |
|---|---|
| accepted | 1221 (45%) |
| rejected | 979 (36%) |
| pending | 503 (19%) |

- **1818 行（67%）没有 canonical_project_id** — 这些事件不参与任何页面的时间线/成熟度/作战卡门控，等于白爬
- pending 503 行会拖入看板/战报的"有事件"判定（全状态计数），但时间线页看不到

---

## 7. 最终判断

### 不能宣布"功能完善、可以转向路演准备"。一个必修缺陷 + 两个建议修。

**必须修复（影响路演第一屏）**

1. **商机看板默认视图看不到三个置顶项目**（本次审计发现，之前所有任务都漏了这条）。根因：置顶被强制 low 置信度 + 默认置信度筛选 "High & Medium" + 置信度筛选在置顶豁免之前。修复方向（未实施）：置信度筛选后像阶段豁免一样把置顶项目加回，或默认置信度改 "All"。不改的话，路演打开首页第一屏是 Belinda/Payara/Rosebank + UK 噪音，演示效果直接失败。

**建议修复（不影响演示但影响可信度）**

2. **67% 事件行没有 canonical_project_id**。演示时若评审者追问"数据为什么对不上项目"，这是硬伤。需要跑一遍回填。
3. **并行部署竞态**。审计时线上版本又被第三方 version_upload 覆盖（1d67a144，非我们提交）。路演前必须锁死部署权，否则台上刷新可能加载旧包。

**可以接受、不用再改**

- 排序逻辑本身（置顶常量三页共用、评分降序、噪音沉底）— 正确
- 战报中心 16 张卡、前三置顶、AI 加载态与理由展示 — 达标
- 项目时间线分组/置顶/默认选中 — 达标
- AI 分析链路（永不抛错、冷却重试、规则兜底、个性化 prompt）— 达标
- 飞书推送（阶段过滤、卡片完整性、workers.dev 链接）— 达标

**轻微不一致（可选）**

- 看板/战报"有事件"统计全状态事件，时间线只算 accepted；两处口径不同
- 爬虫 ai_push_analyst.py 无重试（前端有）

审计脚本：scripts/system_audit.ts（可复跑）。
