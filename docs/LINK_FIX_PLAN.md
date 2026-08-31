# 链接修复计划（LINK FIX PLAN）

> 生成日期：2026-08-31
> 范围：`projects` 与 `candidate_events` 两表中 `source_url` 为空 / 无法定位原文的行
> 状态：**仅诊断与计划，未修改任何数据**

---

## 1. 现状总览（实时 DB 查询结果）

诊断脚本：[crawler/scripts/link_plan_diagnose.py](../crawler/scripts/link_plan_diagnose.py)
原始数据：[crawler/scripts/link_plan_diag.json](../crawler/scripts/link_plan_diag.json)

| 表 | 总行数 | source_url 为空 | 有效文章 | 数据文件 | 通用/搜索页 |
|---|---|---|---|---|---|
| projects | 1213 | **1101 (90.8%)** | 64 | 48 | 0 |
| candidate_events | 2797 | **2533 (90.6%)** | 203 | 61 | 0 |

注：空值为空字符串 `''`（非 NULL）。此前已有两轮修复提交（f711a10、809e224），已修复部分 battle-card 项目，本次统计为修复后余量。

### projects 空值按来源分布（全部）

| source_name | 空 / 总数 | 类型 |
|---|---|---|
| NSTA Field Development Plans | 835 / 849 | 官方注册表 |
| Guyana EPA Oil & Gas Documents | 222 / 229 | 官方文档库 |
| 11 个行业演示来源（各 4 条）| 44 / 44 | 演示项目 |

11 个演示来源：Hydrocarbon Processing、LNG Prime、Chemical Week、World Fertilizer、Sugar Online、Paper Advance、World Nuclear News、Pharmaceutical Technology、ThinkGeoEnergy、Mining.com、Global Water Intelligence。

**projects 表的空值恰好 = 以上三类，无遗漏。**

### candidate_events 空值按来源分布（主要）

| source_name | 空 / 总数 | review_status 构成 |
|---|---|---|
| NSTA Field Development Plans | 1116 / 1127 | accepted 775 / rejected 225 |
| ANP 开发计划 | 786 / 786 | accepted 1 / pending 359 / rejected 426 |
| Guyana EPA Oil & Gas Documents | 517 / 517 | accepted 286 / rejected 230 |
| 11 个演示来源 | 8 × 11 = 88 | 待确认 |
| Equinor Key Information for Suppliers | 10 / 10 | 供应商入口 |
| MODEC Supply Chain | 6 / 6 | 供应商入口 |
| Petrofac Supplier Network | 6 / 6 | 供应商入口 |
| Guyana 石油管理计划 | 3 / 4 | 官方 |
| Petrobras Canal Fornecedor | 1 / 1 | 供应商入口 |

---

## 2. 按来源诊断

### 2.1 Guyana EPA（epaguyana.org）— 可全自动修复 ✅

**结论：最有把握的一类，纯机械修复。**

- 数据来源：`https://epaguyana.org/download-category/oil-gas/`（WordPress Download Manager / WPDM 文档库）。
- DB 行 `summary` 字段带文件元信息，形如 `Category: PERMIT | File: env permit - crude oil lift no 24dny049 ref #20241119- xismf`，文件名与 EPA 网站文件名一致。
- 本地已存最新快照 `crawler/data/guyana_epa/2026-08-28_epa_oil_gas.html`，解析出 **927 个 WPDM 下载链接**，格式：
  ```
  https://epaguyana.org/download/oil-gas/?wpdmdl=7959&ind=...&refresh=...&filename=Hammerhead-Development-...
  ```
- 适配器 [guyana_epa.py](../crawler/adapters/guyana_epa.py) 已有 `clean_wpdm_url()`：剥掉 `refresh`/`ind` 缓存参数，保留 `wpdmdl` + `filename`，得到稳定直链。**无需下载文件本体**（本地 PDF 也已有存档）。

**修复方法（全自动）：**
1. 解析最新快照（或重抓一次），提取全部 `(filename, clean_url)` 映射。
2. 归一化文件名（小写、去引号空格），与 DB 行 summary 里的 `File:` 值做模糊匹配。
3. 匹配上的行 PATCH `source_url = clean_url`（直链）或文档页 URL。
4. 匹配不上的少数行标记待人工。

预计工作量：**30–60 分钟**（含脚本 + 验证）。预计覆盖率：projects 222 条 ≈ 90%+，candidates accepted 286 条 ≈ 90%+。

### 2.2 NSTA（nstauthority.co.uk）— 无逐字段页面，需分层处理 ⚠️

**关键发现：NSTA 网站没有逐字段的文档页面。**

- 835 个空 URL 的项目是历史 FDP 批准注册表行（Operator/Block/Type/Consent Date，最早的 1976 年），原始数据来自 XLSX 数据集。
- 验证 `https://www.nstauthority.co.uk/data-and-insights/data/themes/fields/`：只提供 **4 个 XLSX 下载**（offshore-field-consents、FDP addenda、field start-ups、fields in production），无逐字段详情页；逐字段数据在 ArcGIS Hub 开放数据门户（`opendata-nstauthority.opendata.arcgis.com`，JS 渲染，需进一步探测是否有稳定单条 URL 模式）。
- 个别 FDP 文档本体（如 Guidance、SET 模板）已有直链，仅 14 条非空。
- 非空的 3 条（Belinda / Victory / Rosebank）用的是新闻链接（offshore-mag、ogj、equinor）——即注册表行本身在 NSTA 网站没有公开原文，只有"数据集 + 新闻报道"两种可定位方式。

**修复方法（分层）：**

| 层 | 对象 | 方案 | 自动化 |
|---|---|---|---|
| A | 全部 835 条 | `source_url` 统一指向 NSTA 数据集直链（`/media/n5xe0ayq/offshore-field-consents-as-at-march-2026.xlsx` 或其数据页） | 全自动，1 条 SQL / 批量 PATCH |
| B | battle-card 展示的高价值项目（约 30–50 个，如 Rosebank、Cambo、Jackdaw 等知名油田） | 半自动：项目名 + 新闻搜索（offshore-mag / ogj / upstream / oedigital），逐条验证后写入 | 半自动，每条 2–4 分钟 |
| C | 其余（占多数的小型/历史油田） | 接受数据集 URL（层 A），不再逐条找新闻 | — |

**风险与限制：** 大部分 1970–2000 年代的 FDP 注册表行没有公开原文，层 B 只覆盖高价值子集。逐条找新闻不现实（835 条 × 验证）。ArcGIS 门户逐字段 URL 探测留作后续增强（若发现稳定模式，可升级为全量自动）。

预计工作量：层 A **10 分钟**；层 B **1–2 小时**（分多轮执行）；层 C 随层 A 完成。

### 2.3 11 个行业演示来源 — 半自动，每条需人工验证 ⚠️

- 44 个项目（11 来源 × 4）全空，项目名是演示数据（如 "Hokkaido Genkai-2 Restart Works"、"Poland Baltic AP1000 Nuclear Plant"），summary 里有运营商/机组/投产年份等参数。
- 多数有真实新闻原型可映射：Ontario SMR BWRX-300 → OPG Darlington 真实报道；Poland AP1000 → 真实选址报道；Czech Dukovany-II → 真实招标报道；LNG 项目 → LNG Prime 相关报道。**但演示项目名与真实事件并非一一对应，每条链接都要打开验证内容相关性。**
- candidates 同来源另有 8 × 11 = 88 条空值（多为 rejected/pending 演示行，可延后或同批处理）。

**修复方法（半自动）：**
1. 按来源 + 关键词（运营商、机组、年份）WebSearch，取候选文章 2–3 条。
2. 逐条打开验证（标题、运营商、容量参数对上），写入 `source_url`。
3. 验证不上的保留空值，标注。

预计工作量：**1–1.5 小时**（44 条 ÷ 每条约 2 分钟验证）。可拆成 11 个小批次执行。

### 2.4 ANP 开发计划 — 可自动化，但优先级低 ⚠️

- 786 条 candidates 全空，但 review_status：accepted 仅 1、pending 359、rejected 426。**projects 表无 ANP 空值**（projects 里 ANP 来源已有 URL）。
- 行内带 `Field / Category / Published / SHA256` 元信息，来自 gov.br 开发计划页面；适配器 [anp_development_plan.py](../crawler/adapters/anp_development_plan.py) 已实现按字段名 + 文件哈希匹配文件直链。
- gov.br 站点 SSL 兼容性差（适配器自带 curl fallback），重跑有一定不稳定性。

**修复方法：** 重跑适配器（或定向脚本）重新抓取 gov.br 计划页面，按 Field + SHA256 匹配后回填 URL。仅处理 accepted 1 + pending 359（rejected 不修）。

预计工作量：**30–60 分钟**（含 gov.br 抓取重试）。价值低：不影响任何 projects 展示，只影响审核队列。

### 2.5 供应商入口小批量（Equinor 10 / MODEC 6 / Petrofac 6 / Petrobras 1 / Guyana 石油管理计划 3）

- 均为 candidates 行，来源是供应商门户列表页（非具体文章）。
- 适配器都存在。修复 = 统一指向对应门户列表页 URL（如 Equinor supplier 页），或重跑适配器重抓。

预计工作量：**15 分钟**（批量 PATCH）。优先级低（不影响 projects）。

---

## 3. 修复路线图（按优先级）

| 优先级 | 类别 | 行数（projects） | 方式 | 预计工作量 | 风险 |
|---|---|---|---|---|---|
| **P0** | Guyana EPA | 222 | 全自动（快照解析 + 文件名匹配 + PATCH） | 30–60 分钟 | 低。快照已有，直链模式清晰 |
| **P1** | NSTA 层 A：全量数据集 URL | 835 | 全自动（1 条批量 PATCH） | 10 分钟 | 低。URL 为官方数据集直链 |
| **P1** | NSTA 层 B：高价值项目新闻链接 | ~30–50 | 半自动（搜索 + 逐条验证） | 1–2 小时 | 中。需逐条验证相关性 |
| **P2** | 演示来源 11 × 4 | 44 | 半自动（搜索 + 逐条验证） | 1–1.5 小时 | 中。演示名与真实事件非一一对应 |
| **P3** | ANP candidates（accepted+pending） | 0（仅 candidates 360） | 自动重跑适配器 | 30–60 分钟 | 中。gov.br 不稳定 |
| **P3** | 供应商入口小批量（candidates 26） | 0 | 批量 PATCH 列表页 URL | 15 分钟 | 低 |
| **P3** | 演示来源 candidates 88 | 0 | 随 P2 批次处理或延后 | 0–30 分钟 | 低 |

**总计：约 2.5–4.5 小时**，与预判一致；P0 + P1 层 A 可在第一小时内完成 1057 / 1101 个 projects 的修复。

### 执行顺序建议

1. **P0 Guyana EPA**（先做）——收益最大、最稳、脚本可复用现有 `link_fix_apply.py` 的 PATCH 模式。
2. **P1 NSTA 层 A**（紧随其后）——10 分钟搞定 835 条。
3. **P1 NSTA 层 B + P2 演示**——分多轮半自动执行，每轮一个来源或一批项目，逐条验证。
4. **P3** 视时间决定是否本轮做；不影响前端展示，可延后。

### 执行规范（沿用现有工具链）

- 修改前写备份（沿用 `link_fix_backup.json` 模式：table / id / old_url / new_url 四元组）。
- 用 `crawler/scripts/link_fix_apply.py` 的幂等 PATCH 方式落库（带重试）。
- 每批修复后跑 `crawler/scripts/link_report.py` 复检分类统计。
- 所有写入走 Supabase REST，无 DDL 操作（记忆：本环境无 DDL 通道）。

---

## 4. 遗留问题 / 待确认

1. **NSTA ArcGIS Hub 逐字段 URL**：若 `opendata-nstauthority.opendata.arcgis.com` 存在稳定单条模式（如 `/datasets/<id>`），层 A 可升级为逐字段直链，取代数据集 URL。需一次专项探测。
2. **演示项目性质确认**：44 个演示项目是否需要"真原文"（新闻验证成本高）还是接受演示状态（可批量指向来源网站首页/搜索页）。建议执行 P2 前确认。
3. **candidates rejected 行**（ANP 426、Guyana 230、NSTA 225）：本计划默认不修。如要全量修，工作量 +50%。
