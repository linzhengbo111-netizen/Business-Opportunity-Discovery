# 决赛演示项目精选（2026-08-13）

从 Supabase `projects` 表精选的 FPSO 演示项目。数据快照日期：2026-08-13。

## 筛选结论

严格按全部条件（industry=FPSO + 水深/不锈钢/采购链非空 + grade A/B + 时间线≥3条）查询：**满足全部条件的项目为 0 个**。

原因（数据库事实）：
- `projects` 表**没有 `industry` 列**，也没有 `grade` 列 —— FPSO 判定改用 `hull_type = 'Floating Production Storage Offloading - FPSO'` 或名称含 "FPSO"；评分与等级由生产代码 `scoreOpportunity()` 本地计算（`opportunity_score` 列全部为 NULL，系统不落库评分）。
- `procurement_chain` 列**全表 1167 行为空**。仅 `candidate_events` 表有 212 条新闻类事件携带采购链片段（均为文章标题类事件，非真实项目行）。
- 100 个 FPSO 项目行中：57 个缺水深、56 个缺不锈钢、63 个缺采购链。

按"最接近"规则（缺失字段最少、评分最高）选出 3 个：**全部只缺 `procurement_chain` 一个字段**，其余条件全部满足。

---

## 主讲项目：FPSO ALMIRANTE TAMANDARE（Búzios 8）

| 字段 | 值 |
|---|---|
| 名称 | FPSO ALMIRANTE TAMANDARE |
| 国家 | Brazil（巴西，Santos 盆地 Búzios 油田群） |
| 状态 | Under Construction（在建） |
| 水深 | 1,985 m |
| 产能 | 原油 270,000 bpd / 天然气 12,000 MMcmd |
| 推荐不锈钢牌号 | Super Duplex 2507、6Mo (UNS S31254)、Duplex 2205、Inconel 625（全部在工厂可生产范围内） |
| 推荐应用 | Gas Compression、Subsea Manifolds、Deepwater Risers、Heat Exchangers、Process Piping、Produced Water Treatment |
| 采购链实体 | ⚠️ DB 缺失（NULL）。DB 已知运营商：PETRÓLEO BRASILEIRO S.A. - PETROBRAS |
| 机会评分 / 等级 | **89 / A** |
| 时间线事件 | **5 条**（REGULATORY_DATA，来源 ANP FPSO CSV，2025 年） |
| 详情页 URL | https://business-opportunity-discovery.linzhengbo111.workers.dev/database?project=FPSO%20ALMIRANTE%20TAMANDARE |

**推荐理由**：评分最高的在建项目（89 分 A 级），巴西盐下超深水（1985m），产量 27 万桶/天为巴西最大 FPSO 之一，双相钢/6Mo 需求典型、演示"水深→材料推荐"逻辑最有说服力。

---

## 备选项目 1：FPSO BACALHAU（Equinor）

| 字段 | 值 |
|---|---|
| 名称 | FPSO BACALHAU |
| 国家 | Brazil（巴西，Santos 盆地 Bacalhau 油田） |
| 状态 | Under Construction（在建） |
| 水深 | 2,100 m |
| 产能 | 原油 220,000 bpd / 天然气 15,000 MMcmd |
| 推荐不锈钢牌号 | Super Duplex 2507、6Mo (UNS S31254)、Inconel 625、Duplex 2205（全部在工厂可生产范围内） |
| 推荐应用 | Deepwater Risers、Gas Compression、Heat Exchangers、Subsea Manifolds、Cargo Oil Tanks、Flare Systems |
| 采购链实体 | ⚠️ DB 缺失（NULL）。DB 已知运营商：EQUINOR BRASIL ENERGIA LTDA. |
| 机会评分 / 等级 | **88 / A** |
| 时间线事件 | **5 条**（REGULATORY_DATA，来源 ANP FPSO CSV，2025 年） |
| 详情页 URL | https://business-opportunity-discovery.linzhengbo111.workers.dev/database?project=FPSO%20BACALHAU |

**备选理由**：水深 2100m 为三项目中最深，Equinor 国际作业者背景与主讲项目（Petrobras）形成对比，适合演示不同作业者场景。

---

## 备选项目 2：FPSO SEPETIBA（Sépia）

| 字段 | 值 |
|---|---|
| 名称 | FPSO SEPETIBA |
| 国家 | Brazil（巴西，Santos 盆地） |
| 状态 | Under Construction（在建） |
| 水深 | 2,000 m |
| 产能 | 原油 225,100 bpd / 天然气 15,000 MMcmd |
| 推荐不锈钢牌号 | Super Duplex 2507、6Mo (UNS S31254)、Duplex 2205、Inconel 625（全部在工厂可生产范围内） |
| 推荐应用 | Gas Compression、Subsea Manifolds、Deepwater Risers、Heat Exchangers、Process Piping、Produced Water Treatment |
| 采购链实体 | ⚠️ DB 缺失（NULL）。DB 已知运营商：PETRÓLEO BRASILEIRO S.A. - PETROBRAS |
| 机会评分 / 等级 | **88 / A** |
| 时间线事件 | **5 条**（REGULATORY_DATA，来源 ANP FPSO CSV，2023 年） |
| 详情页 URL | https://business-opportunity-discovery.linzhengbo111.workers.dev/database?project=FPSO%20SEPETIBA |

**备选理由**：与主讲项目同为 Petrobras 盐下项目、指标接近，可作为主讲项目的对照样本；时间线事件年份（2023）更早，适合演示时间跨度。

---

## 缺失字段汇总

| 项目 | 缺失字段 | 影响 |
|---|---|---|
| FPSO ALMIRANTE TAMANDARE | `procurement_chain`（全表该列均 NULL） | 作战卡"联系谁"退化为运营商兜底 |
| FPSO BACALHAU | `procurement_chain` | 同上 |
| FPSO SEPETIBA | `procurement_chain` | 同上 |

其余条件（FPSO 判定、水深、不锈钢牌号、grade A/B、时间线≥3 条）全部满足。

## 其他说明

- 评分与等级由生产代码 `src/lib/opportunity_scorer.ts` 的 `scoreOpportunity()` 本地计算（与线上页面一致）；`projects.opportunity_score` 列在库中全部为 NULL，不作为筛选依据。
- 时间线事件来自 `candidate_events`（`canonical_project_id` 或 `project_name_raw` 匹配），三项目各 5 条，事件类型均为 REGULATORY_DATA（ANP 巴西监管数据源）；事件类型多样性有限，演示时可结合"查看完整时间线"页面说明数据源结构。
- 采购链数据全表缺失是数据采集侧问题：`candidate_events` 中仅 212 条新闻类事件携带采购链片段。若决赛需展示采购链，建议演示前手工补齐 3 个项目的 `procurement_chain`（例如 Tamandaré 公开信息为 Petrobras → SBM Offshore(EPC)；Bacalhau 为 Equinor → MODEC/TechnipFMC；Sepetiba 为 Petrobras → MODEC），或直接演示系统在链缺失时的运营商兜底逻辑。
