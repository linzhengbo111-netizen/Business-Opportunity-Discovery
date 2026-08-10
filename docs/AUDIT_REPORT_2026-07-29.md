# FPSO 项目系统审计报告

**审计日期**: 2026-07-29
**审计依据**: 《FPSO项目可用信息源使用手册》V1.0 (2026-07-22)
**审计范围**: 全项目 (src/, crawler/, migrations/, .github/workflows/, 数据库表结构, 前端页面)

---

## 整体完成度: ~72%

| 维度 | 完成度 |
|------|--------|
| 来源适配器覆盖 (P0) | 100% (8/8) |
| 来源适配器覆盖 (P1+P2) | 78% (7/9) |
| 四层数据流 | 90% |
| 项目归一化 | 60% (Python 完整, TypeScript 前端缺失) |
| 快照差异对比 | 45% (5/11 适配器有 diff) |
| CI/CD 频率匹配 | 70% |
| 前端合规展示 | 40% |
| 合规 (安全/凭据) | 100% |

---

## 1. 项目结构总览

| 目录 | 关键文件数 | 状态 |
|------|-----------|------|
| `src/pages/` | 4 页面 (Dashboard, Database, Review, Settings) | Review 有缺陷 |
| `src/data/` | project_aliases.ts, projects.ts | 正常 |
| `crawler/adapters/` | 11 适配器 | 正常 |
| `crawler/crawl.py` | 通用媒体爬虫 (3090行) | 有缺陷 |
| `migrations/` | 8 迁移脚本 | 正常 |
| `.github/workflows/` | 2 活动 workflow + 1 .bak | 频率不匹配 |

---

## 2. 四层架构数据流

手册要求: 线索发现(1) → 官方验证(2) → 采购链拆解(3) → 商业入口(4)

### source_registry 层级分配 (已修正)

迁移 `004_fix_source_registry_priority.sql` 修正了 8 处不匹配。当前状态与手册一致。

**source_registry 覆盖完整性: 16/16 已登记**

| 手册来源 | 适配器 | 状态 |
|----------|--------|------|
| ANP CSV (P0) | anp_fpso_csv.py | ✅ |
| ANP 开发计划 (P0) | anp_development_plan.py | ✅ |
| Guyana EPA (P0) | guyana_epa.py | ✅ |
| Guyana 石油管理计划 (P0) | guyana_petroleum.py | ✅ |
| NSTA (P0) | nsta_fdp.py | ✅ |
| Equinor Rosebank (P0) | equinor_rosebank.py | ✅ |
| Petrobras 供应商 (P0) | petrobras_supplier.py | ✅ |
| MODEC Supply Chain (P0) | modec_supplychain.py | ✅ |
| ExxonMobil Guyana (P1) | **无适配器** | ❌ |
| SBM Offshore (P1) | sbm_newsroom.py | ✅ |
| Equinor 供应商 (P1) | equinor_supplier.py | ✅ |
| Petrofac 供应商 (P1) | petrofac_supplier.py | ✅ |
| Offshore Energy (P1) | crawl.py (通用) | ⚠️ 无独立适配器 |
| OE Digital (P1) | crawl.py (通用) | ⚠️ 无独立适配器 |
| World Oil (P2) | crawl.py (通用) | ⚠️ 无独立适配器 |
| Splash247 (P2) | crawl.py (通用) | ⚠️ 无独立适配器 |

---

## 3. candidate_events 表结构

所有手册要求字段均已存在（经 003/005 迁移补充）:

| 手册字段 | 表列名 | 状态 |
|----------|--------|------|
| event_type | event_type | ✅ |
| project_name_raw | project_name_raw | ✅ |
| canonical_project_id | canonical_project_id | ✅ |
| publication_date | publication_date | ✅ |
| fetched_at | fetched_at | ✅ |
| source_url | source_url | ✅ |
| evidence_quote | evidence_quote | ✅ |
| review_status | review_status | ✅ |

### 适配器写入 event_type 覆盖

共 25 种 event_type，主要类型:

| event_type | 适配器 |
|-----------|--------|
| ARTICLE_MENTION | crawl.py |
| REGULATORY_DATA | ANP CSV, ANP Plans, EPA, Petroleum, NSTA |
| EIA_SUBMITTED | EPA |
| PERMIT_GRANTED | EPA, Petroleum |
| DEVELOPMENT_PLAN_SUBMITTED | ANP Plans, NSTA |
| DEVELOPMENT_CONSENT_GRANTED | NSTA |
| PROJECT_ANNOUNCEMENT / FID_CONFIRMED / CONTRACT_AWARDED | Equinor Rosebank |
| FEED_AWARDED / FPSO_CONTRACT_AWARDED | SBM Newsroom |
| VENDOR_REGISTRATION_ACTION | Petrobras Supplier |
| VENDOR_ONBOARDING | Equinor Supplier |
| PROCUREMENT_CHAIN | MODEC |
| PROCUREMENT_PORTAL | Petrofac |

---

## 4. 关键缺陷 (按优先级)

### P0-1: ReviewPage.tsx Promote 不调用 normalizeProjectName

**位置**: [src/pages/ReviewPage.tsx:215-270](src/pages/ReviewPage.tsx#L215-L270)

前端 Promote 按钮直接用 `ev.project_name_raw` 作为项目名，不执行项目归一化。Python 端 `promote_accepted_candidates()` 正确实现了归一化+合并，但前端版本完全跳过。

**影响**: 前端 promote 产生重复项目。"Payara" 和 "Payara Development" 会变成两个独立 projects 行。

**修复**: 重构 handlePromote 导入 `normalizeProjectName` / `getDisplayName`，按 canonical ID 分组合并。

**工作量**: 中

---

### P0-2: 前端无 AI 推断 vs 已证实事实区分

**位置**: DashboardPage.tsx, ReviewPage.tsx, 数据库 schema

手册要求: "AI输出必须区分：已证实事实、AI推断、工厂规则结果、待人工确认"

当前状态:
- candidate_events 表无 `evidence_level` 列
- Dashboard 不显示任何置信度/来源权威度标记
- candidate_events 行与 projects 行外观完全相同
- 用户无法区分 P0 监管证据 vs P2 新闻线索

**修复**:
1. candidate_events 添加 `evidence_level` 列 (CONFIRMED_FACT / AI_INFERRED / FACTORY_RULE / PENDING_CONFIRMATION)
2. 适配器根据来源 tier 自动设置 evidence_level (tier 2 = CONFIRMED_FACT, tier 1 = PENDING_CONFIRMATION)
3. Dashboard 显示区分标记

**工作量**: 大

---

### P0-3: ANP CSV 适配器缺 evidence_quote + publication_date

**位置**: [crawler/adapters/anp_fpso_csv.py:815-826](crawler/adapters/anp_fpso_csv.py#L815-L826)

`build_candidate_event()` 返回的字典不含 `evidence_quote` 和 `publication_date`。这是唯一的 P0 适配器有此缺陷。

**修复**: 添加两个缺失字段。evidence_quote 用 "ANP open data: {facility} operated by {operator} in {basin} basin"，publication_date 用 CSV 中的 start_date 字段。

**工作量**: 小

---

### P0-4: crawl.py publication_date 误用 TODAY 回退

**位置**: [crawler/crawl.py:2437](crawler/crawl.py#L2437)

```python
"publication_date": raw_date or TODAY,
```

当无法解析发布日期时填入抓取日期，混淆了两种日期语义。手册要求: "严格区分来源发布日期publication_date和系统抓取时间fetched_at"

**修复**: 改为 `raw_date or ""`，缺日期时留空。

**工作量**: 小

---

### P0-5: 行业媒体无独立适配器

**位置**: crawl.py

4 个媒体来源共用一个通用爬虫，输出单一 `ARTICLE_MENTION` 类型。无法按手册要求区分 P1 (Offshore Energy) vs P2 (World Oil/Splash247) 的处理策略差异。无事件去重，每次全量写入。

**修复**: 可选方案:
1. 为每个媒体来源创建独立适配器（参照现有 P0 适配器模式）
2. 在 crawl.py 中为不同站点输出不同 event_type 和 priority

**工作量**: 中

---

### P0-6: 快照差异对比仅覆盖 5/11 适配器

实现完整 diff 的适配器: ANP CSV, ANP Plans, Guyana EPA, Guyana Petroleum, NSTA FDP

未实现 diff 的适配器: Equinor Rosebank, SBM Newsroom, Equinor Supplier, MODEC, Petrobras, Petrofac

未实现 diff 导致每次运行全量输出 candidate_events，而非仅输出变更。

**修复**: 参照 guyana_epa.py 的 diff_documents() 模式，为其余 P0/P1 适配器添加差异对比。

**工作量**: 大

---

### P1-1: CI/CD 频率不匹配

| 来源 | 手册建议 | 当前设置 | 偏差 |
|------|---------|----------|------|
| ANP CSV | 每月 | 每周一 | ❌ 过于频繁 |
| Equinor Rosebank | 每日 | 每周一 | ⚠️ 延迟 |
| 行业媒体 | 每日 | 每日 | ✅ |

**修复**: 将 ANP CSV 移至独立 monthly workflow（或条件运行），将 Equinor Rosebank 移至 daily workflow。

**工作量**: 小

---

### P1-2: 无 GitHub Actions 失败告警

所有适配器 step 使用 `continue-on-error: true`，静默失败。手册要求 "必须准备解析fixture和失败告警"。

**修复**: 添加 GitHub Actions notification step（Slack webhook 或 email）。

**工作量**: 中

---

### P1-3: DatabasePage 不显示候选事件字段

DatabasePage 仅查询 projects 表，不查询 candidate_events。即使显示 projects，也不展示 evidence_quote 或 review_status。

**修复**: 添加 candidate_events 数据源选项，或至少显示 review_status 和 evidence_quote 列。

**工作量**: 小

---

### P2-1: Dashboard 不显示来源权威度

Dashboard 合并 projects + candidate_events 显示为统一列表，无任何视觉区分标记（除 candidate 行 status 固定为 "Unknown"）。

**修复**: 添加 source tier badge (T1/T2/T3/T4) 或来源权威度指示器。

**工作量**: 中

---

### P2-2: 无 opportunity_analysis 表

手册数据流: `source_registry → source_documents → candidate_events → project_evidence → projects → opportunity_analysis`

当前缺失 project_evidence 和 opportunity_analysis 两层。

**修复**: 创建 opportunity_analysis 表和相关页面，实现商机分析闭环。

**工作量**: 大

---

## 5. 合规检查结果

| 检查项 | 状态 |
|--------|------|
| 无硬编码凭据/密码/Cookie | ✅ |
| 所有适配器使用环境变量读取 Supabase 凭据 | ✅ |
| SHA256 哈希保存原始文件 | ✅ (除 crawl.py 媒体爬虫) |
| publication_date vs fetched_at 区分 | ⚠️ crawl.py 回退逻辑有问题 |
| 无登录绕过/验证码绕过代码 | ✅ |
| Supabase anon key 在客户端 JS 中硬编码回退值 | ⚠️ 设计如此 (anon key) |
| RLS 策略全表开放 (USING true) | ⚠️ 内部分析工具可接受 |

---

## 6. 项目归一化机制

### Python 端 (crawl.py) — 完整

`promote_accepted_candidates()` (line 2522-2684):
1. 对每个 accepted candidate 调用 `normalize_project_name()`
2. 匹配成功则使用 canonical display name
3. 按 effective_name 分组合并
4. 回写 canonical_project_id 到 candidate_events
5. 智能合并: 最长 summary, 最新 source_date, 最多国家

### TypeScript 端 (ReviewPage.tsx) — 不完整

`handlePromote()` (line 200-282):
1. 不调用 normalizeProjectName
2. 直接用 project_name_raw 作为项目名
3. 不做 canonical 分组合并
4. 不回写 canonical_project_id

**结论**: 两条 promote 路径不一致。Python CLI promote 是权威路径，前端 ReviewPage promote 是简化版。应统一。

---

## 7. 接下来优先处理的 5 个任务

1. **修复 ReviewPage.tsx promote 归一化** (P0-1, 工作量: 中)
2. **ANP CSV 适配器补充 evidence_quote + publication_date** (P0-3, 工作量: 小)
3. **添加 evidence_level 字段和前端 AI 推断展示** (P0-2, 工作量: 大)
4. **创建 ExxonMobil Guyana 适配器** (缺失 P1, 工作量: 中)
5. **为 Equinor Rosebank/NSTA 添加 diff 对比** (P0-6 部分, 工作量: 中)

## 8. 正面发现

- 所有 8 个 P0 来源均有适配器，代码质量高
- 巴西双源交叉验证 (ANP CSV + ANP Plans) 设计合理
- Guyana EPA 适配器的事件分类 (EIA_SUBMITTED, PERMIT_GRANTED 等) 精确匹配手册
- source_documents 表 + SHA256 哈希建立完整审计链
- Python/TypeScript 双端 PROJECT_ALIASES 保持一致
- 无安全红线违规 (无硬编码密码、无登录绕过)
- 本地 fixture 数据 (crawler/data/) 完整，支持离线测试

---

## 附录: 手册逐项对照关键条目

| 手册章节 | 要求 | 实现 |
|----------|------|------|
| 一、先看结论 | 网页→候选事件→归一化→验证→审核→正式项目 | ⚠️ 归一化在前端缺失 |
| 二、分层使用 | 4层架构 | ✅ source_registry tier |
| 三、巴西 | ANP+Petrobras/MODEC | ✅ 三个适配器完整 |
| 三、圭亚那 | EPA+ExxonMobil/SBM | ⚠️ 缺 ExxonMobil |
| 三、英国 | NSTA+运营商/EPC | ✅ |
| 八、网页接入 | CSV直接下载/HTML解析/PDF下载 | ✅ |
| 八、合规 | 不自动登录/不绕过验证 | ✅ |
| 九、CC任务模板 | 输出先进入candidate_events | ✅ |
| 九、CC任务模板 | 禁止直接写projects | ✅ |
| 十、候选事件字段 | 8个标准字段 | ✅ 表结构完整 |
| 十一、商机升级门槛 | 7项升级条件 | ❌ 未系统化实现 |
| 附录 | 遵守robots/合理频率/不绕过付费墙 | ✅ |
