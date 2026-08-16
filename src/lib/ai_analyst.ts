/**
 * AI Analyst (S8) — LLM-powered analysis with rule-engine fallback
 * =================================================================
 *
 * Wraps the rule engines (material_matcher / opportunity_scorer) with
 * LLM-generated analysis. Every function:
 *   1. Runs the corresponding rule engine first (unless a result is passed in).
 *   2. Builds a prompt from project facts + factory capabilities + rule results.
 *   3. Asks the LLM for strict JSON, forbidding fabrication — insufficient
 *      information must be written as "信息不足".
 *   4. Returns `{ source: "ai", data }` on success; on any failure (no API
 *      key, network error, malformed JSON) returns `{ source: "rules", data }`
 *      built from the rule-engine result.
 *
 * callLLM never throws, so the app keeps working without an API key.
 */

import type { Project } from "@/data/projects";
import { callLLM, type ChatMessage } from "@/lib/llm_client";
import {
  matchMaterials,
  parseRecommendation,
  estimateProcurementWindow,
  inferProductNeeds,
  type MaterialMatchResult,
  type TechnicalSpecs,
} from "@/lib/material_matcher";
import { scoreOpportunity, type ScoreResult } from "@/lib/opportunity_scorer";
import {
  PRODUCIBLE_MATERIALS,
  PRODUCT_TYPES,
  PRODUCT_TYPE_LABELS,
} from "@/data/factory_capabilities";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type AISource = "ai" | "rules";

/** Where the data came from. `rules` = rule-engine fallback. */
export interface AIResult<T> {
  source: AISource;
  data: T;
}

/** analyzeProjectScenario output. */
export interface ScenarioAnalysis {
  scenario: string;
  keyPoints: string[];
  risks: string[];
  infoGaps: string[];
}

/** recommendProducts output. */
export interface ProductRecommendation {
  products: string[];
  grades: string[];
  reasoning: string;
}

/** assessOpportunity output. */
export interface OpportunityAssessment {
  verdict: string;
  rationale: string;
}

/** suggestNextActions output. */
export interface NextActionSuggestions {
  actions: string[];
  nextStep: string;
  timing: string;
}

/** Factory capability summary passed into prompts (and to the LLM). */
export interface FactoryCapabilities {
  producibleGrades: string[];
  productTypes: string[];
}

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

const SYSTEM_PROMPT =
  "你是 FPSO 海上油气项目的不锈钢材料销售分析助手。" +
  "严格只基于用户提供的项目事实、工厂能力和规则引擎结果进行分析，不得编造任何数据或事实。" +
  "当信息不足以支持判断时，明确写 '信息不足'。" +
  "只输出 JSON，不要输出任何其他文本。";

/** Parse a JSON object out of LLM text (tolerates code fences / prose). */
function parseJSONObject(text: string): Record<string, unknown> | null {
  const trimmed = text.trim().replace(/^```(?:json)?\s*/i, "").replace(/```\s*$/, "");
  const start = trimmed.indexOf("{");
  const end = trimmed.lastIndexOf("}");
  if (start < 0 || end <= start) return null;
  try {
    const parsed = JSON.parse(trimmed.slice(start, end + 1));
    return parsed && typeof parsed === "object" && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
}

/** Send a prompt and get back a parsed JSON object, or null on failure. */
async function askJSON(userPrompt: string): Promise<Record<string, unknown> | null> {
  const messages: ChatMessage[] = [
    { role: "system", content: SYSTEM_PROMPT },
    { role: "user", content: userPrompt },
  ];
  const content = await callLLM(messages, { temperature: 0.2, jsonMode: true });
  return content ? parseJSONObject(content) : null;
}

function toStr(v: unknown): string | null {
  return typeof v === "string" && v.trim() ? v.trim() : null;
}

function toStrArray(v: unknown): string[] | null {
  if (!Array.isArray(v)) return null;
  return v.map((x) => (typeof x === "string" ? x.trim() : "")).filter(Boolean);
}

/** Compact project facts for the prompt — only what the DB actually holds. */
function projectFacts(project: Project): Record<string, unknown> {
  return {
    name: project.name,
    country: project.country,
    phase: project.phase,
    industry: project.industry,
    summary: project.summary,
    application: project.application,
    stainless_steel: project.stainlessSteel,
    procurement_chain: project.procurementChain,
    operator: project.operatorName,
    field: project.fieldName,
    basin: project.basin,
    hull_type: project.hullType,
    water_depth_m: project.waterDepthM,
    oil_capacity_bpd: project.oilCapacityBpd,
    gas_capacity_mmcmd: project.gasCapacityMmcmd,
    corrosive_media: project.corrosiveMedia ?? null,
    confidence: project.confidence,
  };
}

function specsFromProject(project: Project): TechnicalSpecs {
  return {
    waterDepthM: project.waterDepthM,
    oilCapacityBpd: project.oilCapacityBpd,
    gasCapacityMmcmd: project.gasCapacityMmcmd,
    hullType: project.hullType ?? null,
    fieldName: project.fieldName ?? null,
    operatorName: project.operatorName ?? null,
    basin: project.basin ?? null,
    hasH2S: project.corrosiveMedia?.h2s === true,
    hasCO2: project.corrosiveMedia?.co2 === true,
    sourService: project.corrosiveMedia?.sour_service === true,
    corrosiveMediaRaw: project.corrosiveMedia ?? null,
  };
}

/** Rule-engine material match: stored recommendation first, fresh match second. */
function materialRules(project: Project, rulesResult?: MaterialMatchResult): MaterialMatchResult {
  if (rulesResult) return rulesResult;
  const rec = parseRecommendation(project.recommendationJson);
  if (rec) return rec;
  return matchMaterials(specsFromProject(project));
}

/** Factory capability summary from the single source of truth. */
function defaultFactoryCapabilities(): FactoryCapabilities {
  return {
    producibleGrades: PRODUCIBLE_MATERIALS.flatMap((c) => c.grades),
    productTypes: PRODUCT_TYPES.map((t) => PRODUCT_TYPE_LABELS[t]),
  };
}

// ---------------------------------------------------------------------------
// 1. analyzeProjectScenario — scenario-level analysis (material matcher)
// ---------------------------------------------------------------------------

export async function analyzeProjectScenario(
  project: Project,
  rulesResult?: MaterialMatchResult,
): Promise<AIResult<ScenarioAnalysis>> {
  const rules = materialRules(project, rulesResult);

  // Rule-engine fallback content
  const fallback: ScenarioAnalysis = {
    scenario: rules.reasoning,
    keyPoints: [
      ...rules.grades.map((g) =>
        `推荐牌号 ${g.grade}${g.in_factory_scope ? "（工厂可生产）" : "（超出工厂生产能力）"}`),
      ...rules.applications.map((a) => `应用场景：${a}`),
    ],
    risks: [],
    infoGaps:
      rules.confidence === "low" ? ["技术参数不足，规则匹配置信度低"] : [],
  };

  const ai = await askJSON(
    [
      "请分析以下 FPSO 项目的材料需求场景，输出 JSON。",
      "项目数据：",
      JSON.stringify(projectFacts(project), null, 2),
      "规则引擎匹配结果：",
      JSON.stringify(rules, null, 2),
      '输出格式：{"scenario": "场景分析总结（中文，2-4句）", "key_points": ["要点"], "risks": ["风险"], "info_gaps": ["信息缺口，不足处写信息不足"]}',
    ].join("\n"),
  );

  const scenario = toStr(ai?.scenario);
  if (!scenario) return { source: "rules", data: fallback };

  return {
    source: "ai",
    data: {
      scenario,
      keyPoints: toStrArray(ai?.key_points) ?? [],
      risks: toStrArray(ai?.risks) ?? [],
      infoGaps: toStrArray(ai?.info_gaps) ?? [],
    },
  };
}

// ---------------------------------------------------------------------------
// 2. recommendProducts — what to sell (material matcher + product inference)
// ---------------------------------------------------------------------------

export async function recommendProducts(
  project: Project,
  factoryCapabilities?: FactoryCapabilities,
  rulesResult?: MaterialMatchResult,
): Promise<AIResult<ProductRecommendation>> {
  const factory = factoryCapabilities ?? defaultFactoryCapabilities();
  const rules = materialRules(project, rulesResult);

  const descriptionText = [project.name, project.summary, project.application]
    .filter(Boolean)
    .join(" ");
  const productNeeds = inferProductNeeds(descriptionText);

  // Rule-engine fallback content
  const fallback: ProductRecommendation = {
    products: productNeeds.length > 0 ? productNeeds.map((p) => p.label) : rules.applications,
    grades: rules.grades.filter((g) => g.in_factory_scope).map((g) => g.grade),
    reasoning: rules.reasoning,
  };

  const ai = await askJSON(
    [
      "请为该 FPSO 项目推荐工厂可生产的产品和材料牌号，输出 JSON。",
      "项目数据：",
      JSON.stringify(projectFacts(project), null, 2),
      "工厂生产能力：",
      JSON.stringify(factory, null, 2),
      "规则引擎匹配结果：",
      JSON.stringify(rules, null, 2),
      "要求：只推荐工厂能力范围内的产品，不得编造需求。信息不足处写 '信息不足'。",
      '输出格式：{"products": ["产品中文名"], "grades": ["牌号"], "reasoning": "推荐理由（中文）"}',
    ].join("\n"),
  );

  const products = toStrArray(ai?.products);
  const grades = toStrArray(ai?.grades);
  const reasoning = toStr(ai?.reasoning);
  if (!products || !reasoning) return { source: "rules", data: fallback };

  return {
    source: "ai",
    data: { products, grades: grades ?? [], reasoning },
  };
}

// ---------------------------------------------------------------------------
// 3. assessOpportunity — is this opportunity worth pursuing (opportunity scorer)
// ---------------------------------------------------------------------------

export async function assessOpportunity(
  project: Project,
  rulesResult?: ScoreResult,
): Promise<AIResult<OpportunityAssessment>> {
  const rules = rulesResult ?? scoreOpportunity(project);

  const fallback: OpportunityAssessment = {
    verdict: rules.summary,
    rationale: rules.recommendedAction,
  };

  const ai = await askJSON(
    [
      "请评估该 FPSO 项目作为不锈钢材料销售商机的价值，输出 JSON。",
      "项目数据：",
      JSON.stringify(projectFacts(project), null, 2),
      "规则引擎评分结果：",
      JSON.stringify(rules, null, 2),
      "要求：只基于给定事实判断，不得编造。信息不足处写 '信息不足'。",
      '输出格式：{"verdict": "商机判断结论（中文，1-2句）", "rationale": "判断依据（中文）"}',
    ].join("\n"),
  );

  const verdict = toStr(ai?.verdict);
  if (!verdict) return { source: "rules", data: fallback };

  return {
    source: "ai",
    data: { verdict, rationale: toStr(ai?.rationale) ?? "" },
  };
}

// ---------------------------------------------------------------------------
// 4. suggestNextActions — concrete sales moves (opportunity scorer)
// ---------------------------------------------------------------------------

export async function suggestNextActions(
  project: Project,
  rulesResult?: ScoreResult,
): Promise<AIResult<NextActionSuggestions>> {
  const rules = rulesResult ?? scoreOpportunity(project);
  const procWindow = estimateProcurementWindow(project);

  const fallback: NextActionSuggestions = {
    actions: [rules.recommendedAction],
    nextStep: rules.recommendedAction,
    timing: procWindow.window,
  };

  const ai = await askJSON(
    [
      "请为该 FPSO 项目提出下一步销售行动建议，输出 JSON。",
      "项目数据：",
      JSON.stringify(projectFacts(project), null, 2),
      "规则引擎评分结果：",
      JSON.stringify(rules, null, 2),
      "采购时间窗估计：",
      JSON.stringify(procWindow, null, 2),
      "要求：行动建议必须基于给定事实，不得编造联系方式或内部信息。信息不足处写 '信息不足'。",
      '输出格式：{"actions": ["行动项"], "next_step": "最优先的下一步（中文）", "timing": "建议时间窗口（中文，模糊表述）"}',
    ].join("\n"),
  );

  const actions = toStrArray(ai?.actions);
  const nextStep = toStr(ai?.next_step);
  if (!actions || !nextStep) return { source: "rules", data: fallback };

  return {
    source: "ai",
    data: {
      actions,
      nextStep,
      timing: toStr(ai?.timing) ?? fallback.timing,
    },
  };
}

// ---------------------------------------------------------------------------
// 5. generate_outreach_message — sales outreach email draft
// ---------------------------------------------------------------------------

/** generate_outreach_message output. */
export interface OutreachMessage {
  subject: string;
  body: string;
}

/**
 * Generate a cold-outreach email draft (开发信) for a project.
 *
 * Unlike the analysis functions above there is NO rule-engine fallback:
 * the email must be written by the LLM. On any failure (no API key,
 * network error, malformed JSON, missing subject/body) returns null —
 * the caller shows "信息不足，暂无法生成开发信".
 */
export async function generate_outreach_message(
  project: Project,
  factoryCapabilities?: FactoryCapabilities,
  rulesResult?: MaterialMatchResult,
): Promise<OutreachMessage | null> {
  const factory = factoryCapabilities ?? defaultFactoryCapabilities();
  const rules = materialRules(project, rulesResult);
  const procWindow = estimateProcurementWindow(project);

  const descriptionText = [project.name, project.summary, project.application]
    .filter(Boolean)
    .join(" ");
  const productNeeds = inferProductNeeds(descriptionText);
  const recommendedProducts =
    productNeeds.length > 0 ? productNeeds.map((p) => p.label) : rules.applications;

  const ai = await askJSON(
    [
      "请为该 FPSO 项目撰写一封销售开发信（冷邮件）草稿，输出 JSON。",
      "工厂：Jiaxing MT Stainless Steel（嘉兴 MT 不锈钢）。",
      "项目数据：",
      JSON.stringify(projectFacts(project), null, 2),
      "工厂生产能力：",
      JSON.stringify(factory, null, 2),
      "规则引擎匹配结果：",
      JSON.stringify(rules, null, 2),
      "推荐产品：",
      JSON.stringify(recommendedProducts, null, 2),
      "采购时间窗估计：",
      JSON.stringify(procWindow, null, 2),
      "写作要求：",
      "1. 严格只基于给定的项目事实和工厂能力撰写，不得编造任何过往业绩、合作案例、认证资质、客户名单、联系人姓名或产能数据。",
      "2. 语气专业、简洁。正文语言默认英文。问候语全信只写一个：巴西或拉美项目写 'Prezados Senhores,'，其余项目写 'Dear Procurement Team,'。不要写两个问候语。",
      "3. 正文必须包含：(a) 从项目数据中识别到的具体需求——材质牌号、产品类型、工况环境（腐蚀性介质、水深、产量等）；(b) 工厂能提供的对应产品与牌号；(c) 请求进一步沟通或索取技术规格书 / RFQ。",
      "4. 若项目数据中有 procurement_chain（EPC 或采购链，如 SBM Offshore），正文中须明确提到该采购链，说明我们理解该项目由其建造/采购，并针对其供应链提出供货意向。没有 EPC 或采购联系人姓名时不要硬编收件人姓名，用第 2 条的通用称呼。",
      "5. 信息不足时不要编造，宁可写通用表述。",
      "6. 正文为纯文本（段落间用空行分隔），不要 Markdown 格式。",
      '输出格式：{"subject": "邮件主题（英文）", "body": "邮件正文，署名 Jiaxing MT Stainless Steel — Sales Team"}',
    ].join("\n"),
  );

  const subject = toStr(ai?.subject);
  const body = toStr(ai?.body);
  if (!subject || !body) return null;
  return { subject, body };
}
