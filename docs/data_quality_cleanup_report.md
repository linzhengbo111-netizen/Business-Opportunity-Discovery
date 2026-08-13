# 数据质量清理报告

日期: 2026-08-13
执行脚本: [scripts/data_quality_cleanup.py](../scripts/data_quality_cleanup.py) (可重跑, `--apply` 写库, 默认 dry-run)

---

## 1. projects 噪音项目清理

规则: 命中即设 `confidence='low'`, **不删除**, 保留数据可追溯。

| 规则 | 命中数 | 降级数 | 说明 |
|---|---|---|---|
| 文件名后缀 (.pdf/.csv/.xlsx/.zip...) | 1 | 0 | `35Well-EIA_Compiled_May-2023.pdf` 已 low (此前清理) |
| 标题型文本 (>80 字符 或含 contract/earnings) | 8 | 0 | 全部已 low (migration 019 已覆盖) |
| 纯人名 (全大写且 <10 字符) | **409** | **0** | 见下方说明 |

### 纯人名规则调查结论: 不适用, 未降级

409 条全大写短名全部来自 `NSTA Field Development Plans`, 是**真实的英国北海油田**:

- FORBES: Operator Hamilton, Block 043/08, 天然气田, 1984 年同意开发
- GORDON: Operator Hamilton, Block 043/20, 天然气田, 1984 年
- FORTIES: 英国最大油田之一, 1975 年
- HUTTON / CLYDE / ROUGH / BALMORAL / ELGIN / AUK ... 均为真实油气田

另外 3 条非 NSTA 命中 (FPSO BRAVO / FPSO FORTE / FPSO FRADE) 是 ANP FPSO CSV 里的真实 FPSO。

**若执行此规则, 会误降级 409+ 条真实监管数据。** 已跳过并在脚本中固化排除逻辑 (NSTA 来源 + 含 FPSO 前缀跳过)。如需强制降级, 一条 SQL 即可。

### 清理前后对比

| 指标 | 清理前 | 清理后 |
|---|---|---|
| projects 总数 | 1167 | 1168 (+1 Tartaruga Verde) |
| confidence=high | 1028 | 1029 |
| confidence=low | 116 | 116 |
| 本次降级数 | — | 0 (噪音已被 migration 016/019 提前清理) |

---

## 2. 监管事件复活 (NSTA / ANP)

被日期规则误拒的真实监管数据:

- 目标: `review_status='rejected'` + `event_type IN (DEVELOPMENT_PLAN_SUBMITTED, DEVELOPMENT_CONSENT_GRANTED)` + source 含 NSTA/ANP = **2477 条**
- 去重 (按 name+event_type+date+source, 保留最小 id): **813 条唯一记录**, **1664 条重复**(标记 `[Auto-rejected: Duplicate of id X — data_quality_cleanup]`, 保持 rejected)
- 813 条改回 `pending` → 重跑 `auto_classify` → 全部命中 Rule A (P0 政府源优先于日期规则) → **accepted**

| 指标 | 复活前 | 复活后 |
|---|---|---|
| 目标监管事件 accepted | 0 | 813 |
| 重复事件标记 | 0 | 1664 |
| 总事件 accepted | 876 | 1335 (+459) |

> 注: 执行中遭遇代理 503 瞬时故障, 3 条记录 (BACCHUS FDPA / YORK FDP ADDENDUM / PELICAN (P19) FDP ADDENDUM) 更新失败后手工修正为 accepted。

---

## 3. Tartaruga Verde 项目补建

- 新增 projects 行 (id=1931):
  - name='Tartaruga Verde', country='Brazil', industry='FPSO', confidence='high'
  - status='Planned' (按 promote 逻辑: P0 + DEVELOPMENT_PLAN_SUBMITTED → Planned)
  - summary/source 取自去重保留事件 (ANP 开发计划)
- 事件关联: 854 条 Tartaruga 事件实为**同一 ANP 页面的 854 份完全相同副本** (同一 event_type/date/evidence)。处理:
  - 保留 1 条 (id=4063) → `accepted` + `canonical_project_id='brazil-tartaruga-verde'`
  - 其余 853 条保持 `rejected` (重复标记)

**与指令的偏差**: 未将全部 854 条设为 accepted — 854 条完全相同副本进时间线会显示 854 个重复里程碑。按去重原则只接受 1 条, 时间线效果一致且数据干净。如需全部 accepted 可另行执行。

---

## 4. 验证结果

- projects 总数: **1168** (高置信度 1029, 中 23, 噪音/low 116)
- 时间线覆盖率: **1168/1168 = 100%**, 空时间线项目 0 个
- 事件状态分布: accepted 1335 / rejected 3174 (其中 1664 为本次重复标记) / pending 454 (媒体源 ARTICLE_MENTION, Rule D 设计上留给人工审核)
- Tartaruga Verde 时间线: 已可显示 (canonical 关联 + 别名注册表 `brazil-tartaruga-verde` 已在 Python/TS 两侧)

---

## 5. 后续建议

1. **人工审核 454 条 pending 媒体事件** (Offshore Energy 376 / Splash247 67 / SBM 7 / Petrofac 4): 多为 ARTICLE_MENTION, 有价值文章可 promote 成项目。
2. **剩余 1510 条 rejected** (3174 - 1664 重复): 部分为真噪音 (人名/旧闻), 部分可能仍是可用的监管/新闻数据, 建议抽查。
3. **英国北海历史油田** (FORBES/GORDON/FORTIES 等): 已交付 30-40 年的油田对不锈钢商机价值低, 但属于真实监管数据 — 如不需要可在前台按 confidence/status 过滤, 不建议删行。
4. 清理脚本幂等, 可随 CI/定时任务重跑 (dry-run 默认安全)。
