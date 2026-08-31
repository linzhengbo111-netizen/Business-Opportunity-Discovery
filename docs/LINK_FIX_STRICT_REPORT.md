# 链接修复严格报告（LINK FIX STRICT REPORT）

> 日期：2026-08-31
> 范围：`projects.source_url` 全量修复（Guyana EPA 222 + NSTA 835 + 演示 44），`candidate_events` 已接受行同步修复
> 标准：只使用真实存在的链接；全部经 HTTP 200 验证；无原文可定位的保持为空

---

## 1. 最终统计

### projects（1213 行，修复前 1101 空）

| 链接类型 | 数量 | 说明 |
|---|---|---|
| **原文** | 401 | 具体文章/官方 PDF/项目页（Guyana 229 + 演示 29 + NSTA 新闻 52 + 既有 91） |
| **数据文件** | 797 | NSTA 官方数据集 XLSX 直链 |
| **待补充**（空） | 15 | 演示项目中无可靠原文的 15 个 |

### 按来源明细

| 来源 | 总数 | 原文 | 数据文件 | 待补充 |
|---|---|---|---|---|
| Guyana EPA Oil & Gas Documents | 229 | **229** | 0 | 0 |
| NSTA Field Development Plans | 849 | **52**（含 44 个高价值项目新闻） | **797** | 0 |
| 11 个演示来源 | 44 | **29** | 0 | **15** |

### candidate_events（2797 行）

- Guyana EPA：accepted 286 行全部补上 WPDM 官方文件直链（HTTP 200 验证）。
- NSTA / ANP / 演示来源的 rejected 行按计划不修；ANP pending 359 行不影响 projects 展示，延后。
- 剩余空 2246 行 = rejected 725 + ANP pending/rejected 785 + 演示/供应商候选行等。

---

## 2. 各来源执行明细

### 2.1 Guyana EPA — 100% 原文，全自动

- 解析本地快照 `crawler/data/guyana_epa/2026-08-28_epa_oil_gas.html`，提取 790 个唯一 WPDM 文件直链（`/download/oil-gas/?wpdmdl=...&filename=...`，已剥离缓存参数）。
- 按文件名与 DB 行 `summary` 中 `File:` 值归一化匹配：**508 行全部命中（229 projects + 286 accepted candidates），0 未匹配**。
- 254 个唯一 URL 全部 HTTP 200 验证通过，0 丢弃。
- 备份：`crawler/scripts/guyana_link_fix_backup.json`；脚本：`crawler/scripts/guyana_link_fix.py`。

### 2.2 NSTA — 分层修复

**层 A（全量 834 行）：** 指向 NSTA 官方数据集真实直链
`https://www.nstauthority.co.uk/media/n5xe0ayq/offshore-field-consents-as-at-march-2026.xlsx`（curl 验证 HTTP 200）。前端显示「数据文件」徽章，不伪装成原文。备份：`crawler/scripts/nsta_bulk_backup.json`。

**层 B（50 个高价值项目，opportunity_score 55）：**
- 2 个并行研究代理逐条搜索 + 验证（操作方新闻稿优先，其次行业媒体），产出 82 个候选链接。
- 主流程独立 curl 复验：**73 个通过 200 落库；9 个被丢弃**（3 个 rigzone 对 curl 返回 202 机器人拦截、其余为代理未找到的字段）。
- 最终 50 个高价值项目中：**44 个有新闻原文，6 个保留数据集直链（严格标准，未凑数）**。
- 备份：`crawler/scripts/nsta_news_backup.json`；脚本：`crawler/scripts/nsta_news_apply.py`。

### 2.3 演示项目 — 29/44 有真实原文，15 待补充

- 3 个研究代理逐条搜索 + WebFetch 验证，主流程独立 curl 复验全部 HTTP 200 后落库。
- **29 个**匹配到真实新闻/官方公告（如 Ontario SMR → OPG Darlington 报道、Dukovany-II → WNN KHNP 报道、Ain Sokhna → Indorama 官方新闻稿）。
- **15 个保持为空**：无可靠原文（如 "Hokkaido Genkai-2" 名称自相矛盾且对应机组已退役；"Global Water Intelligence" 4 个无匹配）。严格标准下不强行指向来源网站首页。

### 2.4 前端徽章

- 新增 `src/lib/source_link.ts`（URL → 原文 / 数据文件 / null）+ `src/components/common/SourceLinkBadge.tsx`。
- 接入 3 处渲染：Dashboard 项目卡 Row 6、项目详情弹窗「采购链与来源」、时间线事件来源链接。
- 判定：URL 路径以 `.pdf/.doc/.docx/.xls/.xlsx/.csv/.zip` 结尾 → 「数据文件」；其他有效 URL → 「原文」；空 → 「待补充」。
- 无需 DB 加列：链接类型从 URL 确定性推导，避免 DDL 依赖（本环境无 DDL 通道）。
- 顺带修复 4 处既有 TS 报错（DashboardPage specs cells `string | undefined` → `?? null`）。tsgo + biome + vite build 全部通过。

---

## 3. 验证方式

1. **Guyana**：254 个唯一直链逐一 HTTP 200（HEAD→GET 回退）。
2. **NSTA 数据集**：XLSX 直链 + 数据页 curl 200。
3. **NSTA 新闻 73 条**：研究代理 WebFetch 验证 + 主流程 curl 独立复验，双重确认。
4. **演示 29 条**：同样双重验证。
5. 修复后全表复扫（见第 1 节统计）：projects 空值从 1101 → **15**。

---

## 4. 遗留说明

1. **NSTA 高价值 6 个**（West Brae、Catcher、Magnus、Foinaven FDPA、Wytch Farm FDPA、Storr x1）：无可验证公开原文（付费墙/无对应报道），保留数据集直链——符合「绝不把数据集链接伪装成项目新闻」原则，但显示为数据文件。
2. **candidate_events 剩余空值**：主要为 rejected 行（按计划不修）与 ANP pending 359（不影响 projects 展示，建议后续重跑 anp 适配器时补）。
3. **NSTA XLSX 直链为季度滚动文件**（`as-at-march-2026`），NSTA 更新文件后旧链接可能失效；页面 URL `https://www.nstauthority.co.uk/data-and-insights/data/themes/fields/` 更稳定，可作后续迁移备选。

---

## 5. 产物清单

| 文件 | 用途 |
|---|---|
| `crawler/scripts/guyana_link_fix.py` | Guyana 修复脚本（可重跑） |
| `crawler/scripts/guyana_link_fix_backup.json` | Guyana 508 行修复备份 |
| `crawler/scripts/nsta_bulk_backup.json` | NSTA 834 行批量备份 |
| `crawler/scripts/nsta_news_apply.py` | NSTA 新闻链接应用脚本（可重跑） |
| `crawler/scripts/nsta_news_backup.json` | NSTA 新闻 73 行备份 |
| `src/lib/source_link.ts` | 链接类型判定 |
| `src/components/common/SourceLinkBadge.tsx` | 原文/数据文件/待补充徽章 |
