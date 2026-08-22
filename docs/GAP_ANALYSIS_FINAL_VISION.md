# 差距分析:现状 vs 最终产品愿景(终版)

日期:2026-08-23(02:30 版,覆盖同日 00:30 版)
方法:7 路并行代码侦察 + Supabase 实时数据验证(projects 1168 行 / candidate_events 2703 行全量拉取)+ 三页过滤管线复现
基准愿景:用户自由选国家 → 爬官方在建项目 → AI 判使用环境 → 工厂筛选 → 挖 EPC/采购方 → 输出完整商机清单 → 提前 3-6 个月锁定

---

## 0. 结论摘要

| 结论 | 数据 |
|---|---|
| 距最终愿景 | 约 35%(六个闭环中无一项完整闭环) |
| P0 必须修复 | 7 项 |
| P1 应该修复 | 7 项 |
| P2 建议优化 | 6 项 |
| 核心矛盾 | 引擎齐全但数据枯竭:AI/工厂/时机三套分析引擎已建,输入数据填充率 0-4%;"提前 3-6 个月"机制存在但无一条证据链可对评委证明 |

与 00:30 版相比本版已核实的进展(commits 7ec2633 → 89e1c10):

1. **历史交付项目压制已修复**:[crawl.py:1216-1227](crawler/crawl.py#L1216-L1227) 新增置信度守卫(Delivery/Commissioning 强制 low,P0 源不可覆盖),配合 migration 026。DB 实证:low 860 (74%)、high 293。00:30 版的 P0-2"降级被 auto_ingest 覆盖"已不成立。
2. **置顶项目默认视图不可见已修复**:89e1c10 置信度筛选豁免置顶项目。复现:默认视图前三 = 三个置顶。
3. 战报卡门槛放宽(event+phase,评分 ≥ 55)、看板按机会评分降序。

新发现的本版核心问题:唯一基于真实日期的采购窗规则(`FPSO_CONTRACT_AWARDED` +2-4 月)是**死代码**——所有调用方都只传单参数,时间线事件从未传入。详见 §2.4。

---

## 1. DB 实证(2026-08-23 02:00 全量重查)

### projects 表(n=1168)

| 维度 | 分布 |
|---|---|
| 国家 | UK 850 (73%)、Guyana 232 (20%)、Brazil 54 (4.6%)、其他 ≤6 |
| 阶段 | Delivery 828 (71%)、Approval 284 (24%)、Planning 4、Concept 4、'EPC Award' 4、Construction 4、Design 2、Procurement 2、Commissioning 1、Unknown 35 |
| 置信度 | low 860 (74%)、high 293 (25%)、medium 15(026 迁移生效后) |
| water_depth_m | 43 (3.7%) |
| oil_capacity_bpd | 45 (3.9%) |
| gas_capacity_mmcmd | 44 (3.8%) |
| hull_type / basin | 44 (3.8%) |
| corrosive_media | **0 (0%)** |
| recommendation_json | 44 (3.8%) |
| procurement_chain | 27 (2.3%) |
| industry | 4 (0.3%) |
| opportunity_score | 1168 (100%) |
| **活跃阶段(非 Delivery/Commissioning)且含任一技术参数的项目** | **1 个** |

### candidate_events 表(n=2703)

| 维度 | 分布 |
|---|---|
| 审核 | accepted 1221 (45%)、rejected 979 (36%)、pending 503 (19% 积压) |
| canonical_project_id | **1818 行 (67%) 为 NULL**——不参与任何页面时间线/门控 |
| 事件类型 | 监管类为主:DEVELOPMENT_PLAN_SUBMITTED 1130、PERMIT_GRANTED 488、DEVELOPMENT_CONSENT_GRANTED 477;商业信号稀缺:FPSO_CONTRACT_AWARDED 27、CONTRACT_AWARDED 15、FIRST_OIL 3 |

### 其他表

- source_registry:16 行,全 is_active=true,但 `is_active`/`crawl_frequency`/`last_crawled_at` **运行时零消费方**(仅 verify_source_registry.py 读取)
- follow_ups:**0 行**(反馈闭环从未启用)
- user_subscriptions:1 行,且是空行(无 country/关键词)

---

## 2. 七维度差距分析

### 2.1 官方项目源覆盖(愿景第 1 点)

**现状**

- 15 个 adapter 硬编码注册于 [crawl.py:115-135](crawler/crawl.py#L115-L135)。**官方政府源仅 3 国**:Brazil(ANP CSV :122 + ANP Dev Plan :123)、Guyana(EPA :124 + Petroleum :125)、UK(NSTA FDP :126)。Equinor Rosebank :127 是作业方官网,非政府源。其余:4 个全球媒体源(Tier 1,全部只搜 `?s=FPSO`:offshore_energy.py:68 / oe_digital.py:68-69 / world_oil.py:68-70 / splash247.py:68)+ 3 个承包商源 + 3 个供应商门户。
- **缺失主要 FPSO 市场**:Angola、Nigeria、Senegal/Mauritania、Malaysia、Indonesia、Suriname、US Gulf of Mexico、Norway、Australia。媒体源靠 [media_common.py:65-84](crawler/adapters/media_common.py#L65-L84) COUNTRY_LIST(~85 国)可打这些国家标签,但无该国官方源。
- **媒体源无分页**:[media_common.py:2875-2883](crawler/adapters/media_common.py#L2875-L2883) `fetch_search_page` 单次 GET 无 page 参数;全仓无 `page=`/`paged=` 循环,每源永远只抓搜索结果第一页。
- **行业面单一**:爬虫全部按 `FPSO` 关键词检索。愿景中的化工、海水淡化、市政管道在爬虫侧**零数据源零关键词**——前端行业筛选([DatabasePage.tsx:122-128](src/pages/DatabasePage.tsx#L122-L128))背后没有数据。

**差距**

1. **用户不能自由选择目标国家**。crawl.py 共 17 个 CLI flag([crawl.py:1422-1523](crawler/crawl.py#L1422-L1523)),无 `--country`/`--sources`;运行循环 :1331 无条件跑全部 15 adapter;两个 workflow 的 `workflow_dispatch` 均无 inputs;worker 只有 `/api/llm`、`/api/feishu/token` 两个端点(api-worker.js:16,22,70),无 `/api/crawl`。前端国家下拉只是展示过滤([DashboardPage.tsx:570,734-735](src/pages/DashboardPage.tsx#L570))。
2. 历史项目排除:本版已修复(见 §0),默认视图 "High & Medium" 过滤器挡掉全部 828 个 Delivery。残余问题是 284 个 Approval 项目里混着 UK 噪音数据(ABIGAIL、AFFLECK 等 55 分进默认视图 #6-8),属数据质量问题非阶段问题。三个置顶项目为演示刻意豁免(Delivery 置顶)。
3. 官方源国家 3/前十大 FPSO 市场,数据偏斜:UK 73%、NSTA 42% 事件。

**改进建议**

- **P0**:按国家按需爬取:api-worker.js 加 `POST /api/crawl`(传 country/source,用 GitHub `workflow_dispatch` 带 inputs 触发 crawl-daily.yml);crawl.py 加 `--country`/`--sources` 过滤 ALL_ADAPTERS;SettingsPage 加"目标国家"选择器。
- **P1**:补 3-4 个高价值官方源 adapter(优先级:Angola ANPG、Nigeria NUPRC、Malaysia PETRONAS、Norway NPD)。模板:媒体型 offshore_energy.py 仅 242 行;政府 PDF 型 nsta_fdp.py 1975 行(成本高一个量级)。
- **P1**:媒体 adapter 加分页(media_common.py fetch_search_page 加 page 参数循环 + 去重)。
- **P2**:化工/海水淡化行业扩展需新关键词配置 + 全新数据源,建议 FPSO 打透后再评估。

### 2.2 AI 分析能力(愿景第 2 点)

**现状**

- 三套 AI 路径:
  1. `ai_analyst.ts`:规则引擎 + LLM 包装,输入含 water_depth_m/oil_capacity_bpd/gas_capacity_mmcmd/corrosive_media/basin([ai_analyst.ts:127-147](src/lib/ai_analyst.ts#L127-L147)),输出 `{products, grades, reasoning}`——reasoning 是整段 blob,无逐项依据([ai_analyst.ts:56-60](src/lib/ai_analyst.ts#L56-L60))。
  2. `push_analyst.ts` / `ai_push_analyst.py`:飞书推送分析,提示词强制个性化——时间窗必须引用事件原文具体线索(FID/开工/授标推导),材质绑定水深/产能/介质腐蚀性/盆地,逐项 reason 必须引用原文([push_analyst.ts:241-260](src/lib/push_analyst.ts#L241-L260))。此路径个性化质量最好,但只服务飞书卡片。
  3. `ai_event_extractor.py`:只从文章提取项目名/事件类型/日期/逐字 evidence_quote/summary([ai_event_extractor.py:417-458](crawler/ai_event_extractor.py#L417-L458)),**不提取水深/介质/产能/H2S/酸性**——技术参数依赖 media_common 规则抽取器,是链路断点。
- 产品覆盖:[material_matcher.ts:618-774](src/lib/material_matcher.ts#L618-L774) inferProductNeeds 覆盖无缝管/焊管/无缝管件/锻制管件/法兰/盘管 7 类,自动补法兰(:752-771)。缺 WELDED_TUBE、CAST_FITTINGS。三种产品类型齐。
- 模型:deepseek-chat(api-worker.js:44,worker 代理 /api/llm),温度 0.2。

**差距(对照愿景第 2 点)**

1. **输入枯竭——个性化判断在数据层面不成立**:96% 项目无水深/产能,corrosive_media 0%,**活跃阶段项目里有技术参数的仅 1 个**。引擎在,原料没有。
2. **可追溯性断裂**:AI 输出全部不落库——TS 侧内存 Map 缓存([push_analyst.ts:396-400](src/lib/push_analyst.ts#L396-L400))、ai_analyst 结果只存 React state、Python 侧只进飞书卡片 payload([ai_push_analyst.py:461-466](crawler/ai_push_analyst.py#L461-L466))。全仓无 ai_analysis 表/列。评委点开任何项目都无法回看"AI 为什么这么判"。
3. 置信度是行级单一值(high/medium/low,来源优先或规则命中数),无逐字段置信度(水深、介质等各自置信度只存在于运行时)。
4. 爬虫侧 Python 分析无重试(前端有 30s 冷却重试,两端口径不一致)。

**改进建议**

- **P0**:扩展 ai_event_extractor.py 提示词,从原文提取 water_depth_m/oil_capacity_bpd/h2s/co2/sour/hull_type(逐字段带 evidence_quote + confidence),对全量 2703 事件重跑回填。这是恢复 AI 个性化分析的根因修复。同时对活跃阶段 339 个项目跑针对性 backfill(backfill_tech_params.py)。
- **P0**:新 migration `027_add_ai_analysis.sql`(026 已被 delivery 修复占用):projects 加 `ai_analysis JSONB`,schema 为 procurement_window/recommended_materials/recommended_products/action/summary,每项带 evidence_quote 与 confidence;push_analyst 成功路径写库,notifier 与前端读库。
- **P1**:ai_analyst.ts 输出改为逐项 `{product, grade, reason, evidence}` 结构,与 push_analyst 对齐;界面 Reasoning 展开显示引用原文。
- **P2**:逐字段置信度存 technical_specs JSONB。

### 2.3 工厂匹配(愿景第 3 点)

**现状**

- 能力矩阵较完整:[factory_capabilities.ts](src/data/factory_capabilities.ts) 10 类产品(:17-28)、35 个可产牌号(:57-108)、18 个碳钢排除牌号(:111-135)、36 条牌号记录含 maxSize("24 inch")与 schedule(:321-611)。
- 匹配引擎:matchMaterials 排除过滤([material_matcher.ts:510-519](src/lib/material_matcher.ts#L510-L519)),每个推荐牌号打 `in_factory_scope`(:530)。
- 评分:[opportunity_scorer.ts:218-278](src/lib/opportunity_scorer.ts#L218-L278) 工厂维度 0-20 分,zero-grades 分支存在(:236-239)但见下——实质不触发。

**差距(对照愿景第 3 点)**

1. **"只筛选工厂能做的项目"未真正实现——致命兜底**:全部牌号被排除时强制回退 `["316L", "Duplex 2205"]`([material_matcher.ts:524-525](src/lib/material_matcher.ts#L524-L525),同对也见于 DEFAULT_RESULT :446-457)。"工厂做不了"的状态永远不可达,scoreFactoryMatch 的 zero 分支因此永不触发。`canManufacture()`(:604-606)定义存在但**全仓零调用方**。
2. **唯一的能力门槛过滤在 CSV 导出**:[export_opportunities.ts:104-105](src/lib/export_opportunities.ts#L104-L105) `projects.filter(hasProducibleGrade)`。列表页/看板无此过滤。
3. **匹配结果不可见**:工厂匹配只是评分明细一行,藏在折叠 `<details>`([DashboardPage.tsx:1813](src/pages/DashboardPage.tsx#L1813)、[DatabasePage.tsx:918](src/pages/DatabasePage.tsx#L918));列表无"仅看可做"开关;战报卡仅在 ≥3 可产牌号时显示文字徽章([battle_card.ts:109-111](src/lib/battle_card.ts#L109-L111))。
4. 尺寸/壁厚(maxSize/schedule)零消费方;CAST_FITTINGS 枚举存在但零牌号记录(:24)。
5. 双份真相源:Python 镜像 [opportunity_scorer.py:42-53](crawler/opportunity_scorer.py#L42-L53) 手工复制 35 牌号,漂移风险。

**改进建议**

- **P0**:删除 316L+2205 兜底,改为输出 `{grades: [], in_factory_scope: 0, verdict: "超出工厂能力"}`;zero 分支(opportunity_scorer.ts:236-239)随之真正可达。
- **P0**:DashboardPage/DatabasePage 加"工厂可做"过滤开关 + 徽章(数据源 recommendation_json 或现场 matchMaterials),与 CSV 语义一致。
- **P1**:尺寸评估——项目口径来自应用场景时比对 maxSize/schedule;CAST_FITTINGS 补能力记录或从枚举删除。
- **P2**:牌号清单收敛为单一 JSON 源,TS/Python 共用。

### 2.4 采购链挖掘(愿景第 4 点)

**现状**

- Schema 是**单列逗号分隔文本**([migrations/011_add_procurement.sql:10-11](migrations/011_add_procurement.sql#L10-L11)):无角色、无官网、无注册入口、无证据。
- 发现路径:LLM 从事件文本+网页文章提取实体,提示词明确排除 operator([backfill_procurement_chains.py:46-63](crawler/backfill_procurement_chains.py#L46-L63)),逐字落地校验;但 **LLM 返回的 type(角色)写库时被丢弃**(:175 只取 names、:191-192 逗号连接写 text)。官网/注册链接两脚本均不提取。procurement_urls.json 为手工搜集的 23 项目/59 URL 映射。
- 供应商 adapter:注册链接多埋在 raw_json;仅 petrofac_supplier.py:248-264 结构化提取注册 URL 为事件;MODEC 是唯一直接喂 procurement_chain 列的 adapter。无 tender/RFQ 抓取。
- 填充率:procurement_chain 27/1168 (2.3%)。
- **采购时间:四份并行实现**(material_matcher.ts:1094、push_analyst.ts:62-73、ai_push_analyst.py:58-97、notifier.py:87-132 各一份 PHASE_WINDOW 镜像)。唯一基于真实日期的规则 = `FPSO_CONTRACT_AWARDED` 发布日期 +2-4 月([material_matcher.ts:1104-1126](src/lib/material_matcher.ts#L1104-L1126)),**但所有调用方单参数调用不传事件**(battle_card.ts:210,236 / ai_analyst.ts:323,384 / opportunity_scorer.ts:457 / export_opportunities.ts:158)——该规则是死代码,真实日期从未进入规则引擎。FID/first-oil 日期只作为 LLM 提示词软证据。
- 窗口不落库,每次展示重算。

**差距(对照愿景第 4 点)**

1. 无官网字段、无注册入口结构化字段、无采购方(买方组织)侧发现。
2. "预计采购时间基于原文证据"只在 AI 路径成立,且结果不落库不可回看;规则路径是 phase→固定窗口("非官方公布日期"明示)。
3. 无"即将进入采购窗口"预警机制(全仓 grep `window<=60` 零命中;notifier 唯一触发条件是新增/更新项目匹配订阅)。

**改进建议**

- **P1**:新 migration:projects 加 `procurement_chain_json JSONB`(entities:[{name, role, website, registration_url, evidence}])。backfill 脚本改造:type 不再丢弃、从 LLM 提取官网/注册链接并落地校验;前端采购链区块渲染"名称+角色+官网链接+注册入口"卡片。
- **P1**:采购时间窗落库(`procurement_window JSONB`:range/confidence/reasoning/evidence_quotes/updated_at);**接通死规则**——所有 estimateProcurementWindow 调用方传入项目 accepted 事件,并补 FID/FIRST_OIL 日期锚点;删除三份重复 PHASE_WINDOW,收敛单一实现。
- **P1**:加"进入采购窗口"预警:每日爬取后扫描窗口起点 ≤60 天项目,飞书推"即将采购"卡片(notifier.py 订阅框架已有,加一个 trigger)。

### 2.5 商机清单输出(愿景第 4/5 点)

**现状**

- CSV([export_opportunities.ts:115-135](src/lib/export_opportunities.ts#L115-L135))19 列:项目名/国家/状态/时间窗+置信度/业主(operatorName 空时回退 sourceName——新闻源冒充业主,误导)/EPC(从采购链关键词启发式抽取)/可产牌号(仅名字,无逐牌号依据)/产品/AI 推理说明(仅时间窗)/评分/来源/行动建议。**缺:客户官网、项目情况摘要、逐材质推理依据、技术参数(水深/盆地)**。
- 飞书推送([notifier.py:196-453](crawler/notifier.py#L196-L453)):单项目结构化卡片,含项目定位(油田/运营商/盆地/水深/产能/船型)、时间窗+依据、逐项产品/牌号理由、AI 摘要、下一步、联系路径。**每卡单项目非清单;无客户官网链接(只有新闻 source_url);无评分门槛**。
- UI:无任何页面同时呈现六要素。ReviewPage 映射了 procurementChain/waterDepthM/oilCapacityBpd/hullType/fieldName/operatorName/basin 共 8 个字段但**一个都不渲染**([ReviewPage.tsx:110-117](src/pages/ReviewPage.tsx#L110-L117) 仅映射)。Dashboard 无官网;战报卡无项目摘要。**无"商机清单"专用页面**(routes 仅 8 页,IndustryBreakdownPage/SamplePage 已孤立)。
- 官网字段在 schema 中根本不存在(只有 source_url/source_name;全仓无 website 列)。

**差距(对照愿景第 5 点)**

1. "完整商机清单"不存在——六要素散落 CSV(缺 3)、飞书卡(缺 1)、Dashboard(缺官网),无一处凑齐。
2. CSV 的"业主/运营商"列在 96% 数据下回退为新闻源名,产出误导性清单。

**改进建议**

- **P0**:建"商机清单"页(销售视角表格):项目名/国家/阶段/客户名称(运营商+EPC)/官网/项目摘要/预计采购时间窗+依据/推荐材质(可产)/推荐产品/工厂匹配徽章/来源证据链接/联系行动。数据从 projects + 新 ai_analysis + 新 procurement_chain_json 组装。
- **P0**:CSV 补三列:客户官网、项目情况摘要、逐材质推理依据;operatorName 为空时列"未知"而非新闻源名。

### 2.6 多国扩展能力(愿景第 1 点"自由选择")

**现状**

- 无插件机制:adapter 是约定式模块,无基类无接口——媒体型签名 `run_adapter(dry_run, local_only)` 2 参,政府型 5 参(offshore_energy.py:104 vs nsta_fdp.py:1333);注册靠 [crawl.py:71-91](crawler/crawl.py#L71-L91) 硬编码 import + ALL_ADAPTERS 元组。
- `source_registry` 运行时仅 3 处读取(crawl.py:293,525,1012),全部只为 priority/tier 查表;**is_active/crawl_frequency/last_crawled_at 零消费方**——DB 关源不生效。
- **加一个新国家官方源 = 12-13 处改动**:① 新 adapter 文件(媒体型 ~242 行 / 政府 PDF 型 ~1950 行)② crawl.py import ③ ALL_ADAPTERS 注册 ④ source_registry INSERT 迁移 ⑤ verify_source_registry.py 断言更新(行数 ≥16、每国 ==4、tier 计数、expected_p0 硬编码集)⑥ crawl-weekly.yml 加步骤 ⑦-⑯ media_common.py 十个国家词典(COUNTRY_LIST/COUNTRY_ALIASES/FPSO_COUNTRY 等)⑰ 前端 projects.ts ×3 ⑱ project_aliases.ts。
- 无 UI 源管理:SettingsPage 只有 Profile/订阅/关注项目/跟进记录 4 区块,零 source_registry 引用。

**改进建议**

- **P1**:adapter 注册改造:定义 Adapter 接口(dataclass:name/sources/country_focus/tier/priority/runner),ALL_ADAPTERS 由该结构 + source_registry(is_active)驱动;crawl.py 加 `--source`/`--country`;weekly workflow 改为循环或只保留 daily。
- **P1**:SettingsPage 加"数据源"页:列 source_registry,开关源(is_active 接线)、手动触发单源爬取(workflow_dispatch 带 inputs)。
- **P2**:verify_source_registry.py 改为从 ALL_ADAPTERS 读期望值。

### 2.7 核心优势验证("提前 3-6 个月锁定",愿景第 5 点)

**现状**

- 机制存在:AI 从事件原文(FID/开工/授标)推个性化时间窗 + 规则兜底。前端展示与飞书卡均有窗口+依据。
- 但:**无持久化窗口、无"进入窗口"预警、无历史预测准确率记录**;唯一真实日期规则是死代码(§2.4);rule_optimizer.ts **零调用方**(全仓 grep runOptimization/fetchAndOptimize 仅定义处),`deltaMonths` 硬编码 0([rule_optimizer.ts:137-142](src/lib/rule_optimizer.ts#L137-L142))。follow_ups 表 corrections JSONB 已含 actualProcurementDate 字段且 [FollowUpStatus.tsx:103-104](src/components/dashboard/FollowUpStatus.tsx#L103-L104) 会写入,但表 0 行——闭环从未启动。
- 演示证据链断裂:三个置顶项目 procurement_chain 全 NULL(demo_projects.md:29,49,69),事件全是 REGULATORY_DATA(无授标/FID 日期);67% 事件无 canonical_project_id,时间线对不上项目。
- 演示素材风险:[mock_data_fpso.json](docs/mock_data_fpso.json) 含虚构采购链/腐蚀介质/评分,仅标 "示例" 未标虚构,而 TEAM_COLLABORATION_GUIDE.md:32 称其"6 条真实项目数据"——评委核查即穿帮。
- 活跃阶段项目合计 ~20 个(1.7%),可推窗口的供给本身极薄。

**差距(对照愿景第 5 点)**

1. 系统能"估计"时机,不能"证明"时机:无基线、无预警、无验证闭环。
2. "提前 3-6 个月"在 DB 现状下不可验证:无一条项目同时具备 阶段+商业事件日期+采购链+材质推荐。

**改进建议**

- **P0**(演示阻断):跑 `--backfill-canonical-ids` 修复 67% 事件断链;对三个置顶项目用真实来源手工补齐采购链(SBM Offshore/MODEC 已知,scripts/backfill_demo_projects.py:53-63 已有脚本);mock_data_fpso.json 加"虚构示例"标注并修正 TEAM_COLLABORATION_GUIDE.md 表述。
- **P0**:接通 estimateProcurementWindow 真实日期规则(§2.4 修复),让窗口真正基于原文证据日期。
- **P1**:窗口落库 + 每日扫描"窗口起点 ≤60 天"推送预警;rule_optimizer 接通(join projects.procurement_window,delta 真实计算),月度生成预测准确率报告(docs/ 落档),路演时以数字证明优势。

---

## 3. 差距清单(按优先级)

### P0 必须修复(7 项)

| # | 差距 | 证据 | 修复路径 |
|---|---|---|---|
| P0-1 | 技术参数/腐蚀介质填充崩溃,AI 个性化空转 | DB:corrosive_media 0%、water_depth_m 3.7%、活跃项目含参数仅 1 个;抽取器只提事件不提参数 [ai_event_extractor.py:417-458](crawler/ai_event_extractor.py#L417-L458) | ai_event_extractor.py 提示词加技术参数提取(逐字段 evidence_quote+置信度);全量 2703 事件重跑;活跃 339 项目针对性 backfill |
| P0-2 | AI 输出不落库,不可追溯,评委无法验证 | push_analyst.ts:396-400 仅内存 Map;无 ai_analysis 表;python 结果只进卡片 | migration `027_add_ai_analysis.sql`:projects.ai_analysis JSONB(逐项带 evidence_quote/confidence);push_analyst 写库;UI/notifier 读库 |
| P0-3 | "只筛选工厂能做的项目"被兜底架空,UI 无匹配过滤 | [material_matcher.ts:524-525](src/lib/material_matcher.ts#L524-L525) 回退 316L/2205;canManufacture 零调用;CSV 是唯一门槛 [export_opportunities.ts:104-105](src/lib/export_opportunities.ts#L104-L105) | 删兜底改 verdict "超出工厂能力";DashboardPage/DatabasePage 加"工厂可做"开关+徽章 |
| P0-4 | 完整商机清单不存在;官网字段 schema 缺失 | CSV 19 列缺官网/摘要/材质依据 [export_opportunities.ts:115-135](src/lib/export_opportunities.ts#L115-L135);六要素无页面同屏;全仓无 website 列 | 建"商机清单"页;CSV 补 3 列;operatorName 空不再回退新闻源名;官网来自 P1 结构化采购链 |
| P0-5 | 用户无法选择目标国家触发爬取 | crawl.py 17 个 flag 无 --country;workflow_dispatch 无 inputs;worker 无 /api/crawl;前端国家仅展示过滤 [DashboardPage.tsx:570](src/pages/DashboardPage.tsx#L570) | worker 加 POST /api/crawl + workflow_dispatch inputs;crawl.py 加 --country/--sources;SettingsPage 加目标国家选择器 |
| P0-6 | 唯一真实日期窗口规则是死代码,"提前 3-6 个月"核心证据缺失 | FPSO_CONTRACT_AWARDED +2-4 月规则 [material_matcher.ts:1104-1126](src/lib/material_matcher.ts#L1104-L1126) 无调用方传事件(全部单参调用:battle_card.ts:210,236 等) | 所有调用方传入项目 accepted 事件;补 FID/FIRST_OIL 日期锚点 |
| P0-7 | 演示证据链断裂,评委核查穿帮风险 | 置顶 3 项目 procurement_chain NULL(demo_projects.md:29,49,69);事件全 REGULATORY_DATA;67% 事件无 canonical_project_id;mock 数据被 TEAM_COLLABORATION_GUIDE.md:32 称"真实" | 跑 --backfill-canonical-ids;3 置顶项目真实采购链补齐;mock_data_fpso.json 标虚构;修正协作指南表述 |

### P1 应该修复(7 项)

| # | 差距 | 证据 | 修复路径 |
|---|---|---|---|
| P1-1 | 采购链单列文本,角色/官网/注册入口丢失 | [011_add_procurement.sql:10-11](migrations/011_add_procurement.sql#L10-L11);LLM type 丢弃 [backfill_procurement_chains.py:175,191-192](crawler/backfill_procurement_chains.py#L175) | procurement_chain_json JSONB(role/website/registration_url/evidence)+ backfill 改造;前端卡片渲染 |
| P1-2 | 采购时间窗四份重复实现、不落库、无预警 | PHASE_WINDOW 四副本(material_matcher/push_analyst.ts/ai_push_analyst.py/notifier.py);无 procurement_window 列;notifier 无日期触发 | 收敛单实现 + 落库 + 每日"窗口≤60天"飞书预警 |
| P1-3 | 主要 FPSO 市场无官方源 | ALL_ADAPTERS 仅 3 国官方源 [crawl.py:115-135](crawler/crawl.py#L115-L135) | 优先 Angola ANPG / Nigeria NUPRC / Malaysia PETRONAS / Norway NPD adapter |
| P1-4 | 媒体源无分页,每源只抓首页 | [media_common.py:2875-2883](crawler/adapters/media_common.py#L2875-L2883) 单次 GET 无 page | fetch_search_page 分页循环 + 去重 |
| P1-5 | 源注册需 12-13 处代码改动,is_active 零消费方 | registry 硬编码;SettingsPage 零 source_registry 引用;verify_source_registry.py 硬编码断言 | Adapter 接口化 + is_active 接线 + SettingsPage 源管理页 + verify 期望值自动化 |
| P1-6 | ReviewPage 读 projects 表、无 Accept/Reject;auto_ingest 绕过审核;pending 503 积压 | [ReviewPage.tsx:150](src/pages/ReviewPage.tsx#L150) supabase.from("projects");零 review_status 引用;[crawl-daily.yml:44](.github/workflows/crawl-daily.yml#L44) --auto-ingest | ReviewPage 改读 candidate_events + 审核动作;auto_ingest 仅摄入 accepted |
| P1-7 | 提前 3-6 个月无验证闭环,rule_optimizer 死代码 | follow_ups 0 行;rule_optimizer 零调用方、delta 硬编码 0 [rule_optimizer.ts:137-142](src/lib/rule_optimizer.ts#L137-L142) | 接通 FollowUpStatus→rule_optimizer(actualProcurementDate vs 预测窗口),月度准确率报告 |

### P2 建议优化(6 项)

| # | 差距 | 证据 | 修复路径 |
|---|---|---|---|
| P2-1 | 工厂尺寸/壁厚无数值评估;CAST_FITTINGS 无记录 | maxSize/schedule 零消费方;枚举 :24 零记录 | 口径比对;补记录或删枚举 |
| P2-2 | 牌号清单双源漂移 | [opportunity_scorer.py:42-53](crawler/opportunity_scorer.py#L42-L53) 手工复制 35 牌号 | 单一 JSON 源,两端共享 |
| P2-3 | 置信度行级单一值,非逐字段 | 010 迁移 check high/medium/low | technical_specs 加逐字段置信度 |
| P2-4 | 化工/海水淡化/市政管道行业零数据 | 全部 adapter 只搜 FPSO;前端筛选无数据源 | FPSO 打透后做行业扩展评估(新源+新关键词配置) |
| P2-5 | CI 与本机 Python 版本漂移 | crawl-daily.yml python-version '3.12' vs 本地 3.14 | 锁定版本 |
| P2-6 | 部署竞态:并行部署者覆盖线上版本 | 审计时线上被 version_upload 覆盖(1d67a144) | 路演前锁死部署权;约定唯一部署人 |

---

## 4. 距最终愿景评估

| 愿景要点 | 达成度 | 依据 |
|---|---|---|
| 1. 用户选国家 + 官方在建项目爬取 | **35%** | 历史项目压制已修复(Delivery→low 强制);但官方源仅 3 国、无国家选择触发、媒体无分页、主要市场缺位 |
| 2. AI 按使用环境个性化判材质 | **45%** | 引擎与提示词合格(逐项 reason+原文引用),但 96% 项目无输入参数、活跃项目仅 1 个有参数;输出不落库 |
| 3. 只筛工厂能做的项目 | **40%** | 矩阵较全,但兜底逻辑使"做不了"不可达;UI 无过滤/徽章(仅 CSV 有) |
| 4. 自动找 EPC/采购方+完整清单 | **35%** | 实体挖掘+落地校验机制好,但 2.3% 填充、角色丢弃、无官网/注册入口、无完整清单输出 |
| 5. 提前 3-6 个月锁定(可证明) | **15%** | 估计机制存在,但唯一真实日期规则是死代码、无持久化、无预警、无验证闭环、演示证据链断裂 |
| **综合** | **≈35%** | 六闭环无一完整;根因是数据链路断点(P0-1)+持久化缺失(P0-2)+死规则(P0-6),而非引擎缺失 |

引擎层建设度显著高于数据层:分析/评分/推送引擎已具备,证明产品路径可行;当前瓶颈是抽取-回填-持久化-展示-验证链路的最后一公里。

---

## 5. 改进路线图

### 阶段一:修地基(1-2 周,全部 P0)

1. **P0-1 数据回填**(最大杠杆):ai_event_extractor.py 技术参数提取 → 全量 2703 事件回填 → 目标:water_depth/corrosive_media/procurement_chain 填充率 ≥40%
2. **P0-6 接通死规则**:estimateProcurementWindow 调用方传事件 + FID/first-oil 锚点 → 窗口真正基于原文日期
3. **P0-2 分析落库**:migration 027 + push_analyst 写库 → 可追溯
4. **P0-3 工厂过滤**:删兜底 + UI 开关/徽章
5. **P0-4 商机清单页**:新页面 + CSV 补列(官网依赖 P1-1,先落 schema)
6. **P0-5 按国家爬取**:worker 端点 + crawl.py --country + SettingsPage 选择器
7. **P0-7 演示证据修复**:canonical-id 回填 + 3 置顶项目真实采购链 + mock 数据治理

验收:活跃项目可见且含技术参数、AI 逐项推理可点击看原文、列表可按工厂可做过滤、可导出六要素清单、可指定国家触发爬取、置顶项目证据链完整。

### 阶段二:价值闭环(2-3 周,P1)

1. P1-1/P1-2 结构化采购链 + 时间窗落库 + "窗口≤60天"预警推送
2. P1-3 新国家官方源(Angola/Nigeria 优先,评委认知度高)
3. P1-4 媒体分页
4. P1-6 ReviewPage 审核链路修复(旧账)
5. P1-7 验证闭环:rule_optimizer 接通 + 首份预测准确率报告

验收:每日飞书推送含"窗口≤60天"预警;新增国家数据流入;审核流程走通;准确率报告可出示。

### 阶段三:护城河(3-4 周,P2 + 增量)

1. P1-5 源配置化(P2-2 合并做单一真相源)
2. P2-1 尺寸评估、P2-3 逐字段置信度
3. P2-4 化工/海水淡化行业扩展评估(FPSO 打透后)
4. P2-6 部署治理:锁死部署权,约定唯一部署人

---

## 附:侦察覆盖清单

- 代码:crawler/(16 个 adapter 文件 + 6 回填/分析脚本)、src/lib/(13 分析引擎)、src/pages/(8 页)、src/components/、migrations/(26)、.github/workflows/(3)
- 数据(Supabase 实时全量):projects 1168、candidate_events 2703、source_registry 16、follow_ups 0、user_subscriptions 1
- 页面管线复现:看板默认视图 308 项目、战报 16 卡、时间线 49 有事件/1119 待挖掘(scripts/system_audit.ts 可复跑)
- 文档:prd.md、FIELD_MAPPING.md、SYSTEM_AUDIT_2026-08-23.md、demo_projects.md、mock_data_fpso.json、TEAM_COLLABORATION_GUIDE.md、历史差距分析报告
