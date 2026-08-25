#!/usr/bin/env python3
"""
Project phase taxonomy + stage term definitions — Python side.

MIRROR OF src/lib/project_phase.ts. Both files hold the same 10 stage
definitions and render the SAME prompt block, so the crawler's AI phase
classification and the website's AI analysis never disagree about what a
phase means.

Parity is enforced by scripts/check_stage_parity.sh, which renders
stage_prompt_block() here and stagePromptBlock() in the TS file and diffs
them byte-for-byte. Change one side, change the other.

Consumers:
  ai_event_extractor.determine_project_phase  — assigns the phase
  ai_push_analyst.analyze_for_push            — reads the phase
  crawl.py                                    — promotes candidates
"""

# Standardized lifecycle phases. Order = lifecycle order; when several
# phases match a project, the latest phase in this order wins.
PROJECT_PHASES = [
    "Concept",        # 业主/政府首次提出初步构想
    "Planning",       # 整体建设方案初步规划
    "Design",         # 工程细节方案设计
    "Approval",       # 正式通过审批确认落地
    "EPC Award",      # 确定总承包商
    "Procurement",    # EPC 启动物资采购
    "Construction",   # 现场正式开工
    "Commissioning",  # 完工后调试
    "Delivery",       # 正式交付投入运营
]

PHASES_SET = set(PROJECT_PHASES)
PHASE_ORDER = {p: i for i, p in enumerate(PROJECT_PHASES)}

#: Display value for projects whose phase cannot be judged.
PHASE_UNKNOWN = "Unknown"

#: All filterable phase labels, including Unknown (10 options).
PHASE_OPTIONS = [*PROJECT_PHASES, PHASE_UNKNOWN]


# ========================================================================
# Stage definitions — single source of truth for AI phase matching
# ========================================================================

#: The 10 standardized stages, in lifecycle order, Unknown last.
#: Keys mirror the StageDefinition interface in src/lib/project_phase.ts:
#:   phase / zh / definition / characteristics / keywords / business
STAGE_DEFINITIONS = [
    {
        "phase": "Concept",
        "zh": "概念",
        "definition":
            "项目首次被提出，通常出现在政府规划、企业战略公告、媒体报道中，尚未形成具体建设计划。",
        "characteristics":
            "只有意向性表述，无预算、无选址、无时间表；信息多来自政府规划文件、企业战略公告或媒体报道。",
        "keywords": [
            "concept",
            "proposed",
            "under consideration",
            "feasibility study",
            "early stage",
        ],
        "business": "无采购动作，仅作长期线索储备，不投入销售资源。",
    },
    {
        "phase": "Planning",
        "zh": "规划",
        "definition":
            "项目进入正式规划阶段，明确了建设目标、大致规模、选址或开发方案，但尚未进入工程细节设计。",
        "characteristics":
            "已有建设目标与大致规模（产能/投资额），可能已定选址，但无工程图纸与设备清单；常伴随可研报告、总体规划、环评启动。",
        "keywords": [
            "planning",
            "master plan",
            "pre-FEED",
            "environmental impact assessment",
            "site selection",
        ],
        "business": "仍无采购动作，可开始建立业主与设计院关系，争取进入合格供应商视野。",
    },
    {
        "phase": "Design",
        "zh": "设计",
        "definition":
            "项目进入具体工程设计阶段，确定技术方案、工艺流程、设备选型和主要技术参数。",
        "characteristics":
            "出现 FEED / 详细设计承包商、工艺流程、设备选型与技术规格书；材质等级与管道等级在此阶段被写死。",
        "keywords": [
            "FEED",
            "detailed design",
            "engineering design",
            "technical specification",
            "design phase",
        ],
        "business":
            "材质与规格在此阶段写入技术规格书，是进入合格供应商名录（AVL）并影响选材的关键窗口。",
    },
    {
        "phase": "Approval",
        "zh": "审批",
        "definition":
            "项目通过政府审批、环境许可、投资决策或内部批准，正式确认推进。",
        "characteristics":
            "出现明确的批文、许可证、环境许可或 FID（最终投资决策）通过；项目从「可能做」变为「确定做」。",
        "keywords": [
            "approval",
            "permit",
            "consent",
            "FID",
            "final investment decision",
            "environmental permit",
        ],
        "business": "项目落地确定性大幅提升，应锁定 EPC 竞标方名单，提前布局。",
    },
    {
        "phase": "EPC Award",
        "zh": "总包授标",
        "definition": "项目业主与总承包商（EPC）签订合同，明确工程总包方。",
        "characteristics":
            "出现总包合同签订、中标方名称、合同金额与工期；采购主体从业主转移到 EPC 承包商。",
        "keywords": [
            "EPC award",
            "contract awarded",
            "contract signing",
            "EPC contractor selected",
        ],
        "business": "采购主体确定，销售对象从业主转为 EPC 总包商，需立即建立联系。",
    },
    {
        "phase": "Procurement",
        "zh": "采购",
        "definition":
            "EPC 承包商或业主启动设备和材料采购流程，包括询价、招标、评标和下单。",
        "characteristics":
            "出现询价（RFQ）、招标、评标、订单（PO）、长周期设备定标等具体采购动作。",
        "keywords": [
            "procurement",
            "tendering",
            "RFQ",
            "purchase order",
            "equipment supply",
        ],
        "business": "核心商机窗口——询价、招标、下单都在此阶段发生，此时必须已在供应商名录内。",
    },
    {
        "phase": "Construction",
        "zh": "施工",
        "definition":
            "项目进入现场施工阶段，设备安装、管道铺设、模块建造等实际工程开始。",
        "characteristics":
            "出现开工、首钢切割、模块建造、设备安装、管道铺设等现场施工动作。",
        "keywords": [
            "construction",
            "installation",
            "first steel cut",
            "construction started",
            "building phase",
        ],
        "business": "主体长周期物资已定标，剩余机会为补充料、变更料与现场急件。",
    },
    {
        "phase": "Commissioning",
        "zh": "调试",
        "definition":
            "项目主体完工后进行设备调试、系统联调、试运行，验证是否达到设计性能。",
        "characteristics":
            "出现调试、联调、试运行、性能测试、机械竣工等验证性动作。",
        "keywords": [
            "commissioning",
            "pre-commissioning",
            "start-up",
            "trial run",
            "performance test",
        ],
        "business": "新增采购极少，机会集中在调试期更换件与备件。",
    },
    {
        "phase": "Delivery",
        "zh": "交付",
        "definition": "项目正式交付给业主，进入生产或运营阶段。",
        "characteristics":
            "出现交付、首油/首气、商业运营、移交业主等标志性节点。",
        "keywords": [
            "delivery",
            "first oil",
            "first gas",
            "commercial operation",
            "handed over",
        ],
        "business":
            "新建采购结束，转为售后备件与运维（MRO）机会，或作为同业主下一个项目的参考案例。",
    },
    {
        "phase": PHASE_UNKNOWN,
        "zh": "未知",
        "definition": "原文信息不足，无法判断项目处于哪个阶段。",
        "characteristics":
            "原文只提及项目名称或泛泛描述，没有任何生命周期动作词。",
        "keywords": [],
        "business": "需补充信息后再判断，不作为销售优先级依据。",
    },
]

#: Lookup by canonical phase label.
STAGE_DEFINITION_BY_PHASE = {d["phase"]: d for d in STAGE_DEFINITIONS}

#: Instructions that govern how the AI applies STAGE_DEFINITIONS.
STAGE_MATCHING_RULES = [
    "多个阶段同时出现时，取生命周期排序中最靠后的阶段（例如原文同时出现 contract awarded 与 procurement，取 Procurement）。",
    "优先依据原文明确出现的关键词判断，而不是笼统语境或行业常识推测。",
    "原文信息不足以支撑任何阶段时，阶段设为 Unknown（或 NULL），不要猜测。",
    "不得编造原文不存在的阶段证据；不追求 100% 准确，宁可返回 Unknown 也不要臆断。",
]


def render_stage_definitions() -> str:
    """Render the stage definitions as prompt text.

    MUST stay byte-identical to renderStageDefinitions() in
    src/lib/project_phase.ts.
    """
    lines = ["【项目阶段术语定义（10 个标准阶段，按生命周期排序）】"]
    for i, d in enumerate(STAGE_DEFINITIONS):
        kws = " | ".join(d["keywords"]) if d["keywords"] else "(无)"
        lines.append(f"{i + 1}. {d['phase']}（{d['zh']}）")
        lines.append(f"   定义: {d['definition']}")
        lines.append(f"   典型特征: {d['characteristics']}")
        lines.append(f"   关键词: {kws}")
        lines.append(f"   业务含义: {d['business']}")
    return "\n".join(lines)


def render_stage_matching_rules() -> str:
    """Render the matching rules as prompt text.

    MUST stay byte-identical to renderStageMatchingRules() in
    src/lib/project_phase.ts.
    """
    lines = ["【阶段匹配规则】"]
    for i, rule in enumerate(STAGE_MATCHING_RULES):
        lines.append(f"{i + 1}. {rule}")
    return "\n".join(lines)


def stage_prompt_block() -> str:
    """Full prompt block (definitions + rules) injected into every AI
    prompt that reads or assigns a project phase.

    MUST stay byte-identical to stagePromptBlock() in
    src/lib/project_phase.ts.
    """
    return f"{render_stage_definitions()}\n\n{render_stage_matching_rules()}"


if __name__ == "__main__":
    print(stage_prompt_block())
