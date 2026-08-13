# FPSO 项目商机挖掘系统 — 项目概览

## 项目名称与定位

**Business Opportunity Discovery — Stainless Steel Opportunity Tracking in Global FPSO Projects**

全球 FPSO（浮式生产储卸油装置）项目商业情报系统。从公开信息中自动发现、验证、评分全球 FPSO 建造/改装/维修项目，分析不锈钢材料需求，生成销售战报，帮助不锈钢供应链团队快速锁定商机。

---

## 技术栈

| 层级 | 技术 |
|------|------|
| **前端** | React 18, TypeScript, Vite (Rolldown), Tailwind CSS, shadcn/ui (Radix), Recharts |
| **后端/爬虫** | Python 3, requests, BeautifulSoup, DuckDuckGo Search |
| **数据库** | Supabase (PostgreSQL), 含 real-time subscriptions |
| **认证** | Feishu (Lark) OAuth OIDC |
| **部署** | Cloudflare Workers (API proxy), Vercel (前端) |
| **工具链** | Biome (lint/format), tsc/native-preview, pnpm, Wrangler |

---

## 7层商业情报全链路架构 (S1–S7)

```
S1 CRAWL → S2 ENRICH → S3 REVIEW → S4 PROMOTE → S5 SCORE → S6 BATTLECARD → S7 FOLLOW-UP
```

| 层级 | 名称 | 说明 | 核心文件 |
|------|------|------|----------|
| **S1** | 线索发现与爬取 | 15个适配器分4个层级（媒体线索/政府验证/采购链拆解/供应商入口）自动爬取全球 FPSO 公开信息 | `crawler/crawl.py`, `crawler/adapters/*.py` |
| **S2** | 信息自动扩充 | 基于已提取关键词，DuckDuckGo 搜索 + 已知数据源直查，补充技术规格。零推断原则 | `crawler/enricher.py` |
| **S3** | 人工审核 | 候选事件 → 人工确认/拒绝 → 提升为正式项目。支持批量操作 | `src/pages/ReviewPage.tsx`, `migrations/004_cleanup_candidate_events.sql` |
| **S4** | 项目入库 | 候选事件提升为 projects 表记录，分配 canonical_project_id，自动提取国家/技术规格 | `crawler/crawl.py --promote`, `migrations/005_add_canonical_project_id.sql` |
| **S5** | 商机评分引擎 | 5维度量化评分（采购概率/工厂匹配/可达性/项目价值/信息置信度），每维0-20，总分0-100。A/B/C/D 四级 | `src/lib/opportunity_scorer.ts`, `crawler/opportunity_scorer.py` |
| **S6** | 销售战报生成 | 将评分转化为一页纸销售战报：为什么追、推什么产品、联系谁、何时行动、下一步 | `src/lib/battle_card.ts`, `src/lib/material_matcher.ts` |
| **S7** | 销售跟进闭环 | 销售反馈 → 回写评分调整。订阅通知（Feishu 推送）。实时项目状态更新 | `src/hooks/useFollowUp.ts`, `crawler/notifier.py`, `migrations/021_create_follow_ups.sql` |

---

## 核心文件目录说明

```
app-d534qwn7c9vl/
├── src/                          # 前端 React 应用
│   ├── pages/                    # 页面组件
│   │   ├── DashboardPage.tsx     # 主仪表板（项目地图+列表）
│   │   ├── ReviewPage.tsx        # 候选事件审核页 (S3)
│   │   ├── DatabasePage.tsx      # 项目数据库浏览
│   │   ├── ProjectTimelinePage.tsx # 项目时间线
│   │   ├── IndustryBreakdownPage.tsx # 行业细分分析
│   │   ├── SettingsPage.tsx      # 用户订阅设置
│   │   └── AuthCallbackPage.tsx  # Feishu OAuth 回调
│   ├── lib/                      # 核心业务逻辑 (S5, S6)
│   │   ├── opportunity_scorer.ts # 5维商机评分引擎
│   │   ├── battle_card.ts        # 销售战报生成器
│   │   ├── material_matcher.ts   # 不锈钢材料匹配引擎
│   │   ├── rule_optimizer.ts     # 规则优化器
│   │   └── export_opportunities.ts # 商机导出
│   ├── hooks/                    # React Hooks
│   │   ├── useFollowUp.ts        # 销售跟进 (S7)
│   │   ├── useSubscription.ts    # 用户订阅管理
│   │   └── useProjectRealtime.ts # 实时项目更新
│   ├── components/ui/            # shadcn/ui 组件库 (~50个组件)
│   ├── contexts/AuthContext.tsx  # 认证上下文 (Feishu OAuth)
│   ├── db/supabase.ts            # Supabase 客户端
│   ├── data/                     # 项目数据与工厂产能配置
│   └── types/                    # TypeScript 类型定义
│
├── crawler/                      # Python 爬虫与数据处理
│   ├── crawl.py                  # 爬虫主调度器 (S1)
│   ├── enricher.py               # 信息扩充引擎 (S2)
│   ├── opportunity_scorer.py     # 评分引擎 Python 版 (S5)
│   ├── notifier.py               # Feishu 推送通知 (S7)
│   ├── backfill_urls.py          # URL 回填脚本
│   ├── adapters/                 # 15个爬虫适配器
│   │   ├── offshore_energy.py    # Tier 1: 媒体线索
│   │   ├── oe_digital.py
│   │   ├── world_oil.py
│   │   ├── splash247.py
│   │   ├── anp_fpso_csv.py       # Tier 2: 政府验证
│   │   ├── anp_development_plan.py
│   │   ├── guyana_epa.py
│   │   ├── guyana_petroleum.py
│   │   ├── nsta_fdp.py
│   │   ├── equinor_rosebank.py
│   │   ├── modec_supplychain.py  # Tier 3: 采购链
│   │   ├── sbm_newsroom.py
│   │   ├── petrobras_supplier.py # Tier 4: 供应商入口
│   │   ├── petrofac_supplier.py
│   │   ├── equinor_supplier.py
│   │   └── media_common.py       # 公共媒体解析工具
│   └── scripts/                  # 诊断与回填工具
│       ├── diagnose_unmatched.py
│       └── backfill_pdf_parse.py
│
├── migrations/                   # 数据库迁移 (21个)
│   ├── create_candidate_events.sql
│   ├── 002_create_source_registry.sql
│   ├── 005_add_canonical_project_id.sql
│   ├── 010_add_confidence.sql
│   ├── 011_add_procurement.sql
│   ├── 013_add_technical_specs.sql
│   ├── 017_create_user_subscriptions.sql
│   ├── 020_add_opportunity_score.sql
│   ├── 021_create_follow_ups.sql
│   └── ...
│
├── docs/                         # 文档
│   ├── prd.md                    # 产品需求文档
│   ├── DESIGN.md                 # 设计规范
│   ├── AUDIT_REPORT_*.md         # 代码审计报告
│   └── GAP_ANALYSIS_REPORT_*.md  # 差距分析报告
│
├── api-worker.js                 # Cloudflare Worker (Feishu OIDC proxy)
├── seed-projects.sql             # 种子数据
├── vercel.json                   # Vercel 部署配置
└── package.json                  # 前端依赖 (React/Vite/shadcn)
```

---

## 已完成功能清单

- [x] 全球 FPSO 项目仪表板（地图 + 列表 + 国家筛选）
- [x] 15个爬虫适配器，覆盖4层数据源（媒体/政府/承包商/供应商）
- [x] 候选事件审核系统（批量确认/拒绝/提升）
- [x] 5维商机评分引擎（采购概率/工厂匹配/可达性/项目价值/信息置信度）
- [x] 不锈钢材料匹配引擎（技术规格 → 钢种推荐 → 工厂产能校验）
- [x] 销售战报生成器（一键生成一页纸作战卡）
- [x] 销售跟进闭环（S7：反馈 → 回写评分）
- [x] Feishu OAuth 登录认证
- [x] 用户订阅系统（按国家/项目类型订阅，Feishu 推送通知）
- [x] 项目信息自动扩充（DuckDuckGo 搜索 + 多源交叉验证）
- [x] Cloudflare Worker API 代理（Feishu OIDC token 交换）
- [x] 数据库迁移体系（21个迁移脚本）
- [x] 项目时间线视图
- [x] 行业细分分析页
- [x] 暗色数据终端风格 UI

---

## 希望 AI 工程师重点审查的方向

### 1. 爬虫适配器可靠性
`crawler/adapters/` 下15个适配器的错误处理、重试逻辑、HTML 解析鲁棒性。上游网站结构变化时适配器是否会静默失败。

### 2. 评分引擎合理性
`src/lib/opportunity_scorer.ts` 和 `crawler/opportunity_scorer.py` — 两端评分逻辑是否真正一致，评分权重和阈值是否合理，边界条件处理（空值、极端值）。

### 3. 数据库 Schema 设计
`migrations/` 目录下的表结构设计 — candidate_events → projects 数据流是否完整，索引是否覆盖高频查询，source_registry 优先级逻辑是否正确。

### 4. 信息扩充可信度
`crawler/enricher.py` 的零推断原则执行是否严格，多源交叉验证逻辑，搜索结果相关性过滤。

### 5. 前后端评分一致性
TypeScript (`src/lib/opportunity_scorer.ts`) 和 Python (`crawler/opportunity_scorer.py`) 两套评分实现是否行为一致 — 同样的项目数据是否产生相同分数。

### 6. 安全与认证
Feishu OAuth 流程完整性（`src/contexts/AuthContext.tsx`, `api-worker.js`），Supabase RLS 策略是否充分，API 端点鉴权覆盖。

---

## 如何重建运行环境

### 前置要求
- Node.js ≥ 20, npm ≥ 10
- Python ≥ 3.10
- Supabase 项目（本地或云端）

### 步骤

```bash
# 1. 解压代码包
unzip fpso-project-for-review.zip
cd app-d534qwn7c9vl

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入真实的 Supabase URL/Key 和 Lark App ID/Secret

# 3. 安装前端依赖
npm install

# 4. 安装 Python 爬虫依赖
cd crawler
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cd ..

# 5. 启动前端开发服务器
npm run dev -- --host 127.0.0.1

# 6. (可选) 运行爬虫
cd crawler
python crawl.py
```

### 数据库初始化
1. 在 Supabase 中创建项目
2. 按 `migrations/` 目录下的文件顺序执行 SQL
3. 可选：运行 `seed-projects.sql` 导入种子数据

---

## 关键环境变量说明

| 变量 | 用途 |
|------|------|
| `VITE_SUPABASE_URL` | Supabase 项目 URL |
| `VITE_SUPABASE_ANON_KEY` | Supabase 匿名密钥（前端使用） |
| `VITE_LARK_APP_ID` | Feishu 应用 ID（前端 OAuth） |
| `LARK_APP_ID` | Feishu 应用 ID（爬虫端 API 调用） |
| `LARK_APP_SECRET` | Feishu 应用密钥（爬虫端 API 调用） |
| `SUPABASE_SERVICE_KEY` | Supabase service_role 密钥（后端使用，可选） |
