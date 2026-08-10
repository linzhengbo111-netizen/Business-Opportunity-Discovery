# FPSO 项目信息源使用手册 — 差距分析报告 (Latest)

> **审计日期**: 2026-08-10
> **审计范围**: 完整代码库 + Supabase 数据库 + 15 适配器 + 6 前端页面 + 2 定时任务
> **对比基准**: 《FPSO项目可用信息源使用手册》V1.0 (2026-07-22)
> **上次报告**: [AUDIT_REPORT_2026-08-07.md](AUDIT_REPORT_2026-08-07.md), [GAP_ANALYSIS_REPORT_2026-08-09.md](GAP_ANALYSIS_REPORT_2026-08-09.md)

---

## 一、整体完成度

| 模块 | 完成度 | 权重 | 加权 |
|------|--------|------|------|
| 来源适配器覆盖 | 94% (15/16 适配器) | 15% | 14.1% |
| 数据流架构 | 60% (缺 project_evidence, opportunity_analysis) | 15% | 9.0% |
| 数据库 Schema 与填充 | 72% (字段齐全但技术字段填充率 <5%) | 15% | 10.8% |
| 合规与审计 | 87% (13/15 适配器通过快照差异) | 10% | 8.7% |
| 前端展示与审核 | 40% (缺审核闭环, 缺 AI 四分类) | 15% | 6.0% |
| 定时任务 | 50% (频率未分层, daily 跑全部) | 10% | 5.0% |
| 项目归一化 | 80% (别名覆盖好, 缺交叉验证) | 10% | 8.0% |
| 商机匹配引擎 | 65% (material_matcher 完整, 缺采购窗预测) | 10% | 6.5% |

### **整体完成度: 68%** (较上次 AUDIT_REPORT_2026-08-07 的 74% 下降 6 个百分点 — 因审计粒度细化)

> 注: 上次报告 74% 仅覆盖来源/数据流/Schema/合规/前端/定时/归一化七个维度。本次增加了商机匹配引擎维度，且对前端和定时任务的评分更加严格，故表面数字略低。实际绝对进度: **多项 P0 修复已落地** (见第九节)。

---

## 二、各模块完成度矩阵

### 2.1 来源适配器 — 94%

| 手册来源 | 优先级 | Tier | 适配器 | 行数 | 状态 |
|----------|--------|------|--------|------|------|
| ANP 开发计划 (HTML+PDF) | P0 | 2 | anp_development_plan.py | 1898 | ✅ 完整 |
| ANP FPSO CSV | P0 | 2 | anp_fpso_csv.py | 1354 | ✅ 完整 |
| Guyana EPA | P0 | 2 | guyana_epa.py | 1728 | ✅ 完整 |
| Guyana 石油管理计划 | P0 | 2 | guyana_petroleum.py | 1442 | ✅ 完整 |
| NSTA FDP | P0 | 2 | nsta_fdp.py | 1961 | ✅ 完整 |
| Equinor Rosebank | P0 | 2 | equinor_rosebank.py | 899 | ✅ 完整 |
| Petrobras 供应商注册 | P0 | 4 | petrobras_supplier.py | 811 | ✅ 完整 |
| MODEC Supply Chain | P0 | 3 | modec_supplychain.py | 703 | ✅ 完整 |
| ExxonMobil Guyana 环境 | P1 | 2 | **无** | — | ❌ 未实现 |
| SBM Offshore Newsroom | P1 | 3 | sbm_newsroom.py | 810 | ✅ 完整 |
| Equinor 供应商信息 | P1 | 4 | equinor_supplier.py | 700 | ✅ 完整 |
| Petrofac 供应商网络 | P1 | 4 | petrofac_supplier.py | 754 | ✅ 完整 |
| Offshore Energy | P1 | 1 | offshore_energy.py | 242 | ✅ 完整 |
| OE Digital | P1 | 1 | oe_digital.py | 243 | ✅ 完整 |
| World Oil | P2 | 1 | world_oil.py | 244 | ✅ 完整 |
| Splash247 | P2 | 1 | splash247.py | 242 | ✅ 完整 |

**source_registry**: 16 条记录，tier/priority 与手册完全一致。ExxonMobil Guyana 已注册但无适配器。

### 2.2 数据库 Schema — 72%

| 表 | 手册要求 | 实际 | 行数 | 状态 |
|----|----------|------|------|------|
| source_registry | ✅ | ✅ | 16 | ✅ |
| source_documents | ✅ | ✅ | 2308 | ✅ |
| candidate_events | ✅ | ✅ | 4897 | ✅ |
| **project_evidence** | ✅ | ❌ | — | ❌ P0 |
| projects | ✅ | ✅ | 1167 | ✅ |
| **opportunity_analysis** | ✅ | ❌ | — | ❌ P1 |
| snapshot_registry | — | ✅ | 21 | ⚠️ 仅部分适配器使用 |
| user_subscriptions | — | ⚠️ | 迁移存在，表未创建 | ⚠️ P2 |

**candidate_events 字段填充热力图:**

| 字段 | 填充率 | 备注 |
|------|--------|------|
| event_type | 100% | 12 种事件类型 |
| project_name_raw | 100% | |
| publication_date | ~95% | 供应商适配器有时缺失 |
| fetched_at | 100% | |
| source_url | 100% | |
| evidence_quote | 100% | 所有适配器均填充 |
| review_status | 100% | pending:510, accepted:416, rejected:74 |
| canonical_project_id | ~80% | backfill 后 |
| confidence | 100% | medium 为主 (934), high:7, low:59 |
| corrosive_media | 20% (984条) | 填充了 JSON 但布尔值全为 false |
| stainless_steel | 0.04% (2条) | 几乎为零 |
| application | 0.3% (16条) | 几乎为零 |

**projects 技术字段填充率:**

| 字段 | 填充数/总数 | 比例 |
|------|-------------|------|
| water_depth_m | 43/1167 | **3%** |
| oil_capacity_bpd | 44/1167 | **3%** |
| gas_capacity_mmcmd | 44/1167 | **3%** |
| hull_type | 44/1167 | **3%** |
| field_name | 44/1167 | **3%** |
| operator_name | 44/1167 | **3%** |
| basin | 44/1167 | **3%** |
| stainless_steel | 1167/1167 | 100% |
| application | 1167/1167 | 100% |
| corrosive_media | 0/1167 | **0%** |
| recommendation_json | 44/1167 | 3% |
| procurement_chain | 0/1167 | **0%** |

**核心发现**: 技术规格字段 (水深、产能、船型等) 仅 44 条 (~3%) 项目有数据，全部来自 ANP CSV 适配器。其余 1123 条项目无任何技术规格，导致材质匹配引擎无法触发规则。corrosive_media 在 candidate_events 中有 984 条记录但布尔值全为 false，promote 后 projects 中为 0%。

### 2.3 前端页面 — 40%

| 页面 | 路由 | 数据源 | 功能 | 手册对齐 | 状态 |
|------|------|--------|------|----------|------|
| DashboardPage | / | projects + candidate_events | 全球地图 + 图表 + 项目卡片 + 详情弹窗 + 时间线 + CSV 导出 | ⚠️ 部分 | 缺审核入口 |
| DatabasePage | /database | projects | 表格视图 + 筛选 + 行展开详情 | ⚠️ 部分 | 缺审核入口 |
| ReviewPage | /review | projects (非 candidate_events!) | 书签关注/忽略 | ❌ 严重 | 读错表 |
| ProjectTimelinePage | /project-timeline | candidate_events | 项目时间线 + 证据引用 | ✅ 良好 | |
| IndustryBreakdownPage | /industry-breakdown | 静态图片 | 海水淡化 3D 工艺可视化 | — | 非手册范围 |
| SettingsPage | /settings | user_subscriptions | 订阅管理 + Feishu OAuth | ⚠️ 部分 | 表未创建 |

**ReviewPage 核心问题 (自上次报告未修复)**:
- 第 7 行注释: "不再显示 Accept/Reject/Promote 按钮 — 数据已自动入库"
- 从 projects 表读取，不是 candidate_events
- 无 review_status 筛选/展示
- 无 evidence_quote 展示
- 无人工审核→promote 流程
- 唯一操作: 书签 (localStorage)

**前端缺失的手册要求功能:**
- review_status 展示: ❌ 无页面展示 pending/accepted/rejected
- AI 四分类展示 (已证实事实/AI推断/工厂规则/待确认): ❌ 仅显示 confidence high/medium/low
- evidence_quote 突出展示: ⚠️ 仅 Dashboard 时间线 (后 200 条)
- 项目详情 evidence 面板: ❌ 无
- 人工审核界面: ❌ ReviewPage 读错表

### 2.4 定时任务 — 50%

| Workflow | Cron | 运行内容 | 手册建议 | 问题 |
|----------|------|----------|----------|------|
| crawl-daily.yml | `0 0 * * *` (每天) | 15 适配器 + auto_classify + auto_ingest + backfill | 媒体:每天, 政府:每周, ANP CSV:每月 | 全部每天运行 |
| crawl-weekly.yml | `0 0 * * 1` (每周一) | 11 政府/企业适配器 (不含媒体 4 个) | 与 daily 重叠 | daily 已覆盖 weekly 全部 |

**具体问题:**
1. ANP CSV 每天运行 — 手册建议每月，每天拉取产生大量重复
2. 政府来源每天运行 — 手册建议每周，对 gov.br/epa.org.gy 不必要负载
3. daily 和 weekly 功能重叠 — daily 覆盖了 weekly 所有适配器
4. auto_ingest 在每次 daily crawl 后自动执行 — 候选事件不经人工审核直接入库
5. 无 monthly workflow — ANP CSV 应独立月度运行

### 2.5 数据流合规 — 60%

手册要求路径:
```
source_registry → source_documents → candidate_events
→ project_evidence → projects → opportunity_analysis
```

实际路径:
```
source_registry → source_documents → candidate_events
→ (auto_classify → auto_ingest) → projects
```

| 步骤 | 状态 |
|------|------|
| source_registry | ✅ 16 条完整 |
| source_documents | ✅ 2308 条 |
| candidate_events | ✅ 4897 条 |
| **project_evidence** | ❌ 表不存在 |
| projects | ✅ 1167 条 (但直接来自 candidate_events，无中间验证) |
| **opportunity_analysis** | ❌ 表不存在 |

---

## 三、按 P0/P1/P2 分级的剩余缺口清单

### P0 — 阻塞性 (4 项)

| # | 缺口 | 手册引用 | 当前状态 | 影响 |
|---|------|----------|----------|------|
| **P0-1** | 候选事件人工审核流程缺失 | §十 review_status, §十一 商机升级门槛 | ReviewPage 读 projects 表, 无 Accept/Reject/Promote。auto_ingest 每日自动绕过审核 | **核心设计原则失效** |
| **P0-2** | auto_ingest 每日自动执行 | §十一 7 项升级门槛 | crawl-daily.yml 末尾执行 auto_ingest_to_projects | 候选事件不经审核直接入库 |
| **P0-3** | AI 输出未使用手册四分类 | §十二 "AI输出必须区分四类" | 仅 confidence high/medium/low。前端无 review_status 展示 | 用户无法区分事实/推断/规则/待确认 |
| **P0-4** | project_evidence 中间表缺失 | §八 推荐入库路径 | 表不存在。promote 直接从 candidate_events → projects | 缺少证据链审计 |

### P1 — 重要 (8 项)

| # | 缺口 | 手册引用 | 当前状态 |
|---|------|----------|----------|
| **P1-1** | ExxonMobil Guyana 适配器缺失 | §六 P1 来源 | source_registry 已注册, 无适配器文件 |
| **P1-2** | 多源交叉验证未实现 | §十一 "至少有一个监管机构、业主或合同方的一手来源" | promote 仅按 name upsert, 不验证多源 |
| **P1-3** | opportunity_analysis 表缺失 | §八 推荐入库路径 | 表不存在 |
| **P1-4** | 技术字段填充率 <5% | §十 技术规格字段 | 仅 44/1167 项目有技术规格 |
| **P1-5** | corrosive_media 不传递到 projects | §十 | candidate_events 984 条有 JSON 但布尔值全 false, promote 后 projects 0% |
| **P1-6** | TECHNICAL_SPEC 事件类型缺失 | §六 Petrobras 技术 PDF 单独分类 | OFFICIAL_EVENTS 中无此类型 |
| **P1-7** | 快照差异未覆盖全部适配器 | §九 | Equinor Rosebank, SBM, Media(4), Supplier(3) 缺失 |
| **P1-8** | 定时任务频率未按手册分层 | §四 各来源推荐频率 | ANP CSV 每天跑 (应每月), 政府源每天跑 (应每周) |

### P2 — 优化 (6 项)

| # | 缺口 | 手册引用 | 当前状态 |
|---|------|----------|----------|
| **P2-1** | 解析器 test fixture 缺失 | §九 "为解析逻辑保存本地fixture并编写测试" | 无 |
| **P2-2** | 工厂能力矩阵未与 promote 集成 | §十一 "能够与工厂能力矩阵完成规则匹配" | material_matcher.ts 存在但 promote 时不调用 |
| **P2-3** | 失败告警缺失 | §十二 "保留失败告警和人工复核机制" | 各适配器 continue-on-error: true 但无告警 |
| **P2-4** | OE Digital 搜索页结构变化风险 | §七 | 无解析结果数量异常监控 |
| **P2-5** | NSTA FDP 过度采集 | §四 建议每周 | 521 DEVELOPMENT_CONSENT_GRANTED 事件, 疑似重复 |
| **P2-6** | user_subscriptions 表未创建 | 迁移 017 | 迁移文件存在但未在 Supabase 执行 |

---

## 四、事件类型覆盖

### 手册要求 vs 实际实现

| 手册事件类型 | 适配器 | OFFICIAL_EVENTS | 状态 |
|-------------|--------|-----------------|------|
| ARTICLE_MENTION | media_common.py | ✅ | ✅ |
| DEVELOPMENT_PLAN_SUBMITTED | anp_development_plan.py | ✅ | ✅ |
| DEVELOPMENT_PLAN_UPDATED | anp_development_plan.py | ✅ | ✅ |
| EIA_SUBMITTED | guyana_epa.py, guyana_petroleum.py | ✅ | ✅ |
| PERMIT_GRANTED | guyana_epa.py, guyana_petroleum.py | ✅ | ✅ |
| PUBLIC_NOTICE | guyana_epa.py | ✅ | ✅ |
| PROJECT_SUMMARY | guyana_petroleum.py | ❌ 不在 OFFICIAL_EVENTS | ⚠️ |
| DEVELOPMENT_CONSENT_GRANTED | nsta_fdp.py | ✅ | ✅ |
| SUPPLY_CHAIN_PLAN | nsta_fdp.py | ❌ 不在 OFFICIAL_EVENTS | ⚠️ |
| FPSO_CONTRACT_AWARDED | equinor_rosebank.py, sbm_newsroom.py | ✅ | ✅ |
| FEED_AWARDED | sbm_newsroom.py (规划) | ❌ 不在 OFFICIAL_EVENTS | ⚠️ |
| FABRICATION_MILESTONE | sbm_newsroom.py (规划) | ❌ 不在 OFFICIAL_EVENTS | ⚠️ |
| VENDOR_REGISTRATION_ACTION | petrobras_supplier.py, equinor_supplier.py | ✅ | ✅ |
| VENDOR_ONBOARDING | equinor_supplier.py | ❌ 不在 OFFICIAL_EVENTS | ⚠️ |
| PROCUREMENT_CHAIN | modec_supplychain.py | ❌ 不在 OFFICIAL_EVENTS | ⚠️ |
| PROCUREMENT_PORTAL | petrofac_supplier.py | ❌ 不在 OFFICIAL_EVENTS | ⚠️ |
| **TECHNICAL_SPEC** | — | ❌ 未定义 | ❌ P1 |

### 实际事件分布 (candidate_events, top 12)

| 事件类型 | 数量 | 占比 |
|----------|------|------|
| DEVELOPMENT_CONSENT_GRANTED | 420 | 42% |
| ARTICLE_MENTION | 317 | 32% |
| DEVELOPMENT_PLAN_SUBMITTED | 115 | 12% |
| REGULATORY_DATA | 114 | 11% |
| VENDOR_ONBOARDING | 9 | 1% |
| FPSO_CONTRACT_AWARDED | 7 | <1% |
| PROCUREMENT_CHAIN | 6 | <1% |
| PROCUREMENT_PORTAL | 6 | <1% |
| PERMIT_GRANTED | 3 | <1% |
| PROJECT_ANNOUNCEMENT | 1 | <1% |
| VENDOR_REGISTRATION_ACTION | 1 | <1% |
| EIA_SUBMITTED | 1 | <1% |

**问题**: NSTA FDP 的 DEVELOPMENT_CONSENT_GRANTED 占 42%，严重偏斜。Guyana EPA 的 EIA_SUBMITTED 仅 1 条。事件分布不均衡。

---

## 五、数据库实际状态

### 5.1 来源分布 (candidate_events)

| 来源 | 事件数 | 占比 |
|------|--------|------|
| NSTA FDP | 521 | ~53% |
| Offshore Energy | 165 | ~17% |
| Splash247 | 152 | ~16% |
| ANP Dev Plan | 63 | ~6% |
| ANP CSV | 60 | ~6% |
| Equinor Supplier | 9 | <1% |
| SBM Newsroom | 7 | <1% |
| MODEC | 6 | <1% |
| Petrofac | 6 | <1% |
| Guyana Petroleum | 5 | <1% |
| Guyana EPA | 4 | <1% |
| Equinor Rosebank | 1 | <1% |
| Petrobras | 1 | <1% |
| OE Digital | 0 | **0%** |
| World Oil | 0 | **0%** |

### 5.2 项目置信度分布

| 置信度 | 数量 | 占比 |
|--------|------|------|
| high | 861 | 86% |
| low | 116 | 12% |
| medium | 23 | 2% |

**问题**: 86% high confidence 来自 P0 来源自动分配，不代表实际验证质量。

### 5.3 项目状态分布

| 状态 | 数量 |
|------|------|
| Under Construction | 746 |
| Planned | 254 |
| Delivered | 0 |

### 5.4 国家分布 (projects, top 5)

| 国家 | 数量 | 占比 |
|------|------|------|
| UK | 684 | 69% |
| Guyana | 232 | 23% |
| Brazil | 52 | 5% |
| China | 6 | <1% |
| Malaysia | 5 | <1% |

**问题**: UK 占 69%，来自 NSTA FDP 过度采集。巴西仅 52 条 (5%)，与巴西作为全球最大 FPSO 市场地位不匹配。

---

## 六、前端页面功能审计

### DashboardPage (`/`)
- 全球地图 + 国家点: ✅
- 饼图 (国家/状态/行业): ✅
- 柱状图 (材质推荐): ✅
- 项目卡片 (含 corrosive_media tags): ✅
- 详情弹窗 (Overview + Material Match + Timeline tabs): ✅
- CSV 导出: ✅
- 实时订阅 (useProjectRealtime): ✅
- 侧边栏筛选: ✅
- **缺失**: 无 review_status 筛选, 无 evidence_quote 面板, 无审核入口

### DatabasePage (`/database`)
- 表格视图 + 分页: ✅
- 国家/行业/置信度筛选: ✅
- 行点击展开详情: ✅
- 材质推荐 + corrosive_media: ✅
- **缺失**: 无 review_status 列, 无 evidence_quote, 无审核入口

### ReviewPage (`/review`) — **严重缺陷**
- 数据源: projects (错误 — 应为 candidate_events)
- 功能: 仅书签 (localStorage)
- **缺失**: Accept/Reject/Promote 按钮, review_status 筛选, evidence_quote 展示, 审核工作流

### ProjectTimelinePage (`/project-timeline`)
- 项目搜索/选择: ✅
- 垂直时间线: ✅
- 事件详情展开 (evidence_quote + source_url): ✅
- 较好的手册对齐度

### IndustryBreakdownPage (`/industry-breakdown`)
- 海水淡化 3D Canvas 可视化: ✅
- 管道材质色卡: ✅
- 非手册范围，属于产品展示

### SettingsPage (`/settings`)
- Feishu OAuth: ✅
- 行业/国家订阅: ✅
- 项目关注: ✅
- **问题**: user_subscriptions 表未在 Supabase 创建 (迁移 017 未执行)

---

## 七、适配器合规审计

### 7.1 合规检查清单

| 合规要求 | ANP CSV | ANP Dev | Guyana EPA | Guyana Pet | NSTA FDP | Eq Rosebank | Media(4) | Supplier(3) | SBM |
|----------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| robots.txt 声明 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 请求延迟 5-10s | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 保存原始 HTML | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 保存原始 PDF | N/A | ✅ | ✅ | N/A | ✅ | N/A | N/A | N/A | N/A |
| 文件哈希 SHA256 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| publication_date vs fetched_at | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 不绕过登录 | N/A | N/A | N/A | N/A | N/A | N/A | N/A | ✅ | N/A |
| source_documents 写入 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| snapshot_registry 写入 | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ⚠️ | ❌ |
| 快照差异对比 | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |

**快照差异缺失**: Equinor Rosebank, SBM, 4 个 Media, 3 个 Supplier = 9/15 适配器 (60%)

### 7.2 适配器代码量

| 适配器 | 行数 | 复杂度 |
|--------|------|--------|
| media_common.py | 3001 | 共享模块 |
| nsta_fdp.py | 1961 | 高 |
| anp_development_plan.py | 1898 | 高 (含 PDF 解析) |
| guyana_epa.py | 1728 | 高 |
| guyana_petroleum.py | 1442 | 高 |
| anp_fpso_csv.py | 1354 | 高 (含 CSV diff) |
| equinor_rosebank.py | 899 | 中 |
| petrobras_supplier.py | 811 | 中 |
| sbm_newsroom.py | 810 | 中 |
| petrofac_supplier.py | 754 | 中 |
| modec_supplychain.py | 703 | 中 |
| equinor_supplier.py | 700 | 中 |
| world_oil.py | 244 | 低 (共享逻辑) |
| oe_digital.py | 243 | 低 (共享逻辑) |
| offshore_energy.py | 242 | 低 (共享逻辑) |
| splash247.py | 242 | 低 (共享逻辑) |
| **总计** | **17,038** | |

---

## 八、每个缺口的修复建议和预计工作量

### P0 修复路线图

#### P0-1: 重构 ReviewPage 为 candidate_events 审核界面
**工作量**: ~16h
**方案**:
1. 修改 ReviewPage 数据源: `supabase.from("candidate_events")` 替代 `supabase.from("projects")`
2. 增加 review_status 筛选栏 (pending/accepted/rejected/all)
3. 每个事件卡片增加 Accept / Reject 按钮
4. Accept 时记录审核人和审核时间
5. 增加 "Promote Selected" 批量操作按钮
6. 展示 evidence_quote + source_url (可折叠)
7. 增加四分类标签 (confirmed_fact/ai_inference/rule_result/pending_review)

#### P0-2: 移除 daily workflow 中的 auto_ingest
**工作量**: ~1h
**方案**:
1. 从 crawl-daily.yml 删除 `--auto-ingest` 步骤
2. 在 crawl-weekly.yml 中保留 (或改为手动触发)
3. 在 DashboardPage 增加 "待审核 (N)" 徽标，引导用户前往 ReviewPage

#### P0-3: 实现 AI 输出四分类
**工作量**: ~8h
**方案**:
1. candidate_events 和 projects 表增加 `output_category` 字段:
   - `confirmed_fact`: 来自 P0 + 至少 2 个来源交叉验证
   - `ai_inference`: 来自 AI 文本提取但未交叉验证
   - `rule_result`: 来自 material_matcher 规则匹配
   - `pending_review`: 来自 P1/P2 来源且未审核
2. 前端用四色标签展示
3. crawl.py auto_classify 中增加分类逻辑

#### P0-4: 创建 project_evidence 表
**工作量**: ~4h
**方案**:
1. 创建迁移 020:
```sql
CREATE TABLE project_evidence (
  id SERIAL PRIMARY KEY,
  canonical_project_id TEXT,
  candidate_event_id INT REFERENCES candidate_events(id),
  source_name TEXT,
  evidence_type TEXT, -- REGULATORY / OPERATOR / CONTRACTOR / SUPPLIER
  evidence_quote TEXT,
  source_url TEXT,
  publication_date TEXT,
  verified_by TEXT,
  verified_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```
2. promote 时先写入 project_evidence，再合并到 projects
3. 前端增加证据链视图

### P1 修复路线图

#### P1-1: 创建 ExxonMobil Guyana 适配器
**工作量**: ~8h
**方案**:
- URL: `https://corporate.exxonmobil.com/locations/guyana`
- 参考 equinor_rosebank.py 架构
- 提取: Stabroek Block FPSO 项目名, FID 状态, 预计投产, 产能
- 事件类型: PROJECT_ANNOUNCEMENT, FID_CONFIRMED, PRODUCTION_START

#### P1-2: 实现多源交叉验证
**工作量**: ~8h
**方案**:
1. promote 前检查: 同一 canonical_project_id 是否至少有 1 个 Tier-2 来源
2. 对 Tier-1 来源事件: 搜索已有的 Tier-2/Tier-3 证据 → 存在则提升置信度
3. 对无 Tier-2 验证的项目: 标记为 "unverified" → 不进入商机推荐

#### P1-3: 创建 opportunity_analysis 表
**工作量**: ~4h
**方案**:
1. 创建迁移:
```sql
CREATE TABLE opportunity_analysis (
  id SERIAL PRIMARY KEY,
  project_name TEXT,
  canonical_project_id TEXT,
  opportunity_score INT, -- 0-100
  procurement_window TEXT, -- 预估采购窗口
  recommended_grades JSONB,
  factory_match BOOLEAN,
  customer_type TEXT,
  next_action TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```
2. 满足 §十一 升级门槛后自动生成商机记录

#### P1-4: 提升技术字段填充率
**工作量**: ~12h
**方案**:
1. 运行 enricher.py 对全部 1167 个项目扩充技术规格
2. ANP CSV 数据回填到更多巴西项目 (目前仅 44 条)
3. 增加 Guyana EPA/NSTA 文档中的技术规格提取
4. 手动整理 20+ 已知 FPSO 的技术规格作为种子数据

#### P1-5: 修复 corrosive_media 传递
**工作量**: ~2h
**方案**:
1. 检查 extract_corrosive_media() 为何提取了 JSON 但布尔值全为 false
2. 修复 media_common.py 中的正则/关键词匹配
3. 增加对 H2S/CO2 浓度的定量提取 (如 "500 ppm H2S")

#### P1-6: 增加 TECHNICAL_SPEC 事件类型
**工作量**: ~2h
**方案**:
1. crawl.py OFFICIAL_EVENTS 增加 "TECHNICAL_SPEC"
2. petrobras_supplier.py 对技术 PDF 使用该类型
3. DashboardPage EVENT_TYPE_LABELS 增加中文标签

#### P1-7: 为缺失适配器增加快照差异对比
**工作量**: ~8h
**方案**:
1. Equinor Rosebank: 增加 HTML snapshot + diff
2. SBM Newsroom: 增加文章指纹 + diff
3. Media(4): 在 media_common.py 增加 diff_articles()
4. Supplier(3): 增加 content hash + change detection

#### P1-8: 拆分定时任务频率
**工作量**: ~4h
**方案**:
1. crawl-daily.yml: 仅 4 个媒体适配器 (Tier 1)
2. crawl-weekly.yml: 政府 + 企业适配器 (Tier 2/3/4)
3. crawl-monthly.yml (新建): ANP CSV 适配器
4. 移除 daily 和 weekly 之间的重叠

### P2 修复路线图

#### P2-1: 解析器 test fixture
**工作量**: ~16h
- 每个适配器保存 2-3 个 HTML/PDF fixture
- 编写 pytest 验证提取逻辑
- CI 集成

#### P2-2: 工厂能力矩阵集成 promote
**工作量**: ~4h
- promote 时调用 matchMaterials()
- 将 recommendation_json 写入 projects

#### P2-3: 失败告警
**工作量**: ~4h
- GitHub Actions Slack/Email 通知
- 适配器零输出告警
- 解析结构变化检测

#### P2-4: OE Digital 结构监控
**工作量**: ~2h
- 预期文章数范围检测
- 低于阈值时告警

#### P2-5: NSTA FDP 去重
**工作量**: ~4h
- 实现文件内容哈希去重
- 清理已有的 521 条重复事件

#### P2-6: 执行 user_subscriptions 迁移
**工作量**: ~1h
- 在 Supabase SQL Editor 中执行迁移 017

---

## 九、与上次报告的对比

### 上次报告 (2026-08-07) 摘要

上次报告识别了 9 个 P0、7 个 P1、5 个 P2 缺口，整体完成度 74%。

### 已修复 ✅

| 编号 | 问题 | 修复内容 | 验证 |
|------|------|----------|------|
| P0-6 | promote_accepted_candidates() 不写 confidence | auto_ingest_to_projects 现在调用 `_confidence_from_priority()` | [crawl.py:1098](crawler/crawl.py#L1098) |
| P0-8 | promote 不传递技术规格字段 | auto_ingest_to_projects 现在传递 water_depth_m 等全部 7 个技术字段 | [crawl.py:1149-1155](crawler/crawl.py#L1149-L1155) |
| P0-8b | promote 不传递 confidence | auto_ingest_to_projects 现在写入 confidence 字段 | [crawl.py:1156](crawler/crawl.py#L1156) |
| — | corrosive_media 字段不存在 | 迁移 018 添加了 JSONB 列 | [migrations/018_add_corrosive_media.sql](migrations/018_add_corrosive_media.sql) |
| — | 无信息扩充机制 | enricher.py 创建，auto_ingest 时自动运行 | [crawler/enricher.py](crawler/enricher.py), [crawl.py:1178-1202](crawler/crawl.py#L1178-L1202) |
| — | 无推送通知 | notifier.py 创建，ingest 后通知订阅者 | [crawler/notifier.py](crawler/notifier.py), [crawl.py:1222-1227](crawler/crawl.py#L1222-L1227) |
| — | 噪声数据 | 迁移 019 清理噪声项目 | [migrations/019_cleanup_noise_data.sql](migrations/019_cleanup_noise_data.sql) |
| P0-6 (原) | promote_accepted_candidates 不写 confidence | 但现在 promote_accepted_candidates (老函数) 仍不写 confidence。auto_ingest_to_projects (新函数) 写了 | 两个 promote 路径仍不一致 |

### 仍缺失 ❌

| 编号 (旧) | 编号 (新) | 问题 | 持续天数 |
|-----------|-----------|------|----------|
| P0-1 | P0-1 | ReviewPage 读 projects 不读 candidate_events | 3 天+ |
| P0-2 | P0-2 | auto_ingest 每日自动执行 | 3 天+ |
| P0-3 | P0-3 | AI 输出四分类未实现 | 3 天+ |
| P0-4 | P0-3 (部分) | 前端不显示 review_status | 3 天+ |
| P0-5 | P0-3 (部分) | 前端不突出显示 evidence_quote | 3 天+ |
| P0-7 | P1-8 | ANP CSV 每天运行 | 3 天+ |
| P0-9 | P2-7 | 前端 confidence 默认 "High" | 3 天+ |
| P1-1 | P0-4 | project_evidence 表缺失 | 3 天+ |
| P1-2 | P1-2 | 多源交叉验证缺失 | 3 天+ |
| P1-3 | P1-3 | opportunity_analysis 表缺失 | 3 天+ |
| P1-4 | P1-1 | ExxonMobil Guyana 适配器缺失 | 3 天+ |
| P1-6 | P1-6 | TECHNICAL_SPEC 事件类型缺失 | 3 天+ |
| P1-7 | P1-7 | 快照差异未覆盖全部适配器 | 3 天+ |
| P2-1 | P2-1 | test fixture 缺失 | 3 天+ |
| P2-3 | P2-3 | 失败告警缺失 | 3 天+ |

### 新增发现 🆕

| 编号 | 问题 | 发现方式 |
|------|------|----------|
| P1-4 | 技术字段填充率 <5% (仅 44/1167) | DB 查询 |
| P1-5 | corrosive_media 在 projects 中 0% 填充 | DB 查询 (984 条 candidate_events 有 JSON 但布尔值全 false) |
| P2-5 | NSTA FDP 过度采集 521 条事件 (占 42%) | DB 查询 |
| P2-6 | user_subscriptions 迁移未执行 | DB 查询 (表不存在) |
| — | OE Digital + World Oil 适配器零输出 | DB 查询 (source 分布中无此两来源) |
| — | candidate_events stainless_steel 填充率 0.04% | DB 查询 |
| — | 无 Delivered 状态项目 (所有项目 Under Construction 或 Planned) | DB 查询 |
| — | promote_accepted_candidates() 与 auto_ingest_to_projects() 代码重复 ~70% | 代码审查 |
| — | source_registry 中有 ExxonMobil 注册但无适配器 (已注册未开发) | DB 查询 |

---

## 十、修复优先级路线图

```
第 1 周 (紧急 — 恢复审核闭环):
  P0-2: 移除 daily workflow 中的 auto_ingest              [1h]
  P0-1: 重构 ReviewPage 为 candidate_events 审核界面       [16h]
  P1-8: 拆分 crawl workflows 为 daily/weekly/monthly       [4h]
  P2-6: 执行 user_subscriptions 迁移                        [1h]

第 2 周 (数据质量):
  P0-3: 实现 AI 输出四分类 + 前端展示                       [8h]
  P1-4: 提升技术字段填充率 (enricher + ANP 回填)            [12h]
  P1-5: 修复 corrosive_media 提取与传递                      [2h]
  P2-5: NSTA FDP 去重                                       [4h]

第 3 周 (架构完整性):
  P0-4: 创建 project_evidence 表 + promote 流程更新          [4h]
  P1-1: 创建 ExxonMobil Guyana 适配器                        [8h]
  P1-2: 实现多源交叉验证                                     [8h]
  P1-6: 增加 TECHNICAL_SPEC 事件类型                          [2h]

第 4 周 (合规与优化):
  P1-7: 为缺失适配器增加快照差异 (9 个适配器)                  [8h]
  P1-3: 创建 opportunity_analysis 表                          [4h]
  P2-2: 工厂能力矩阵集成 promote                              [4h]
  P2-3: 失败告警                                              [4h]

后续:
  P2-1: 解析器 test fixture                                  [16h]
  P2-4: OE Digital 结构监控                                   [2h]
```

---

## 十一、数据库健康度

| 指标 | 值 | 评级 |
|------|-----|------|
| 总项目数 | 1167 | ⚠️ 偏多 (UK 占 69%) |
| 有技术规格的项目 | 44 (3%) | ❌ 严重不足 |
| 有商机推荐的项目 | 44 (3%) | ❌ 严重不足 |
| 高置信度项目 | 861 (86%) | ❌ 虚高 (全因 P0 自动标记) |
| 候选事件审核率 | 41% (416 accepted / 1000 sampled) | ⚠️ 低 |
| 来源覆盖均衡度 | NSTA 53% vs Guyana EPA 0.4% | ❌ 严重不均衡 |
| Delivered 项目 | 0 | ⚠️ 缺失已投产项目 |
| 事件类型多样性 | 12 种 / 17 种手册要求 | ⚠️ 71% |

---

## 十二、总结

### 核心成就
- 15/16 适配器实现 (缺 ExxonMobil Guyana)
- 17,038 行适配器代码，覆盖巴西/圭亚那/英国三国全部 P0 来源
- enricher.py + notifier.py 模块交付 (自动扩充 + 飞书推送)
- auto_ingest_to_projects 完整实现 (含 enrich + notify)
- 技术字段传递已修复 (promote 时不再丢失)
- noise data cleanup 迁移已执行
- 材质匹配引擎 (material_matcher.ts) 完整: 18 规则 + 6 牌号 + 工厂能力过滤

### 核心阻塞
1. **人工审核流程完全绕过** — ReviewPage 读错表，无 Accept/Reject/Promote，auto_ingest 每日自动入库
2. **技术字段填充率 <5%** — 材质匹配引擎依赖技术规格输入，当前 96% 项目无规格数据，引擎空转
3. **数据分布严重失衡** — NSTA FDP (UK) 占 53% 事件和 69% 项目，巴西仅 5%
4. **project_evidence 中间表缺失** — 缺少证据链审计，从候选直接到正式项目

### 最应优先处理的 5 个任务
1. **P0-2 + P0-1**: 停止 auto_ingest + 重构 ReviewPage — 恢复人工审核闭环 (17h)
2. **P1-4**: 提升技术字段填充率 — 否则材质匹配引擎无数据可用 (12h)
3. **P0-3**: AI 四分类 — 用户能区分事实/推断/规则/待确认 (8h)
4. **P1-8**: 拆分定时任务频率 — 减少不必要负载，遵守手册建议 (4h)
5. **P1-5**: 修复 corrosive_media 传递 — 支撑材质匹配的 H2S/CO2 规则 (2h)

---

> **审计结论**: 自上次报告以来，系统在数据管道后端取得显著进展 (enricher, notifier, 技术字段传递修复, noise cleanup)。但人工审核闭环仍未恢复，导致手册核心设计原则 "候选事件→人工审核→正式项目" 失效。数据库技术字段填充率 3% 是材质匹配引擎的最大瓶颈。优先恢复审核流程，然后大规模回填技术规格。
