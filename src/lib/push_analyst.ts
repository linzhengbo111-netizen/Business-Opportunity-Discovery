/**
 * Push Analyst — AI-personalized project analysis for the website UI.
 * =====================================================================
 *
 * TypeScript mirror of crawler/ai_push_analyst.py (analyze_for_push), so the
 * website shows the SAME AI analysis the Feishu push card shows: the LLM
 * receives the full project profile plus the recent candidate_events
 * timeline text and returns a personalized procurement window, recommended
 * materials and products with per-item reasons, an action suggestion and an
 * AI summary.
 *
 * Contract: analyzePush() NEVER throws. On any LLM failure (worker not
 * configured, HTTP error, malformed/invalid JSON) it falls back to the rule
 * engine — the same phase-window map and recommendation_json grades the
 * pages displayed before — with source: 'rules' and the same reason strings
 * the Python fallback uses. Results are cached per project name so one LLM
 * call serves every component showing that project.
 */

import type { Project } from "@/data/projects";
import { normalizeProjectName } from "@/data/project_aliases";
import { supabase } from "@/db/supabase";
import { callLLM, isLLMConfigured, type ChatMessage } from "@/lib/llm_client";
import { parseRecommendation } from "@/lib/material_matcher";
import { scoreOpportunity } from "@/lib/opportunity_scorer";
import { stagePromptBlock } from "@/lib/project_phase";

// ---------------------------------------------------------------------------
// Types — same shape as analyze_for_push()'s output
// ---------------------------------------------------------------------------

export type PushSource = "ai" | "rules";

export interface PushProcurementWindow {
  range: string;
  confidence: "high" | "medium" | "low";
  reasoning: string;
}

export interface PushMaterial {
  grade: string;
  reason: string;
}

export interface PushProduct {
  product: string;
  reason: string;
}

export interface PushAnalysis {
  source: PushSource;
  procurement_window: PushProcurementWindow;
  recommended_materials: PushMaterial[];
  recommended_products: PushProduct[];
  action_suggestion: string;
  ai_summary: string;
}

// ---------------------------------------------------------------------------
// Rule-engine fallback (mirrors _rules_fallback in ai_push_analyst.py)
// ---------------------------------------------------------------------------

/** Phase → procurement window estimate. Mirrors the Python _PHASE_WINDOW map. */
const PHASE_WINDOW: Record<string, string> = {
  procurement: "0-3 个月",
  "epc award": "2-4 个月",
  construction: "3-6 个月",
  approval: "6-12 个月",
  design: "12-18 个月",
  planning: "12 个月以上",
  concept: "12 个月以上",
  commissioning: "时间未定",
  delivery: "时间未定",
};

const MAX_MATERIALS = 6;
const MAX_PRODUCTS = 6;

function contractAwardDate(events?: PushEvent[]): string {
  for (const ev of events ?? []) {
    if ((ev.event_type ?? "").trim().toUpperCase() === "FPSO_CONTRACT_AWARDED") {
      const d = (ev.publication_date ?? "").trim();
      if (d) return d.slice(0, 10);
    }
  }
  return "";
}

function addMonths(d: Date, n: number): Date {
  return new Date(d.getFullYear(), d.getMonth() + n, d.getDate());
}

function fmtMonth(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function rulesWindow(
  phase: string | null | undefined,
  events?: PushEvent[],
): { range: string; reasoning: string } {
  // Contract-award events win over the phase map — mirrors the TS engine's
  // Rule 1 in estimateProcurementWindow and Python _rules_window.
  const norm = (phase ?? "").trim().toLowerCase();
  const award = contractAwardDate(events);
  if (award) {
    const awardD = new Date(award);
    if (!isNaN(awardD.getTime())) {
      const start = addMonths(awardD, 2);
      const end = addMonths(awardD, 4);
      const rng = `${fmtMonth(start)} ~ ${fmtMonth(end)}`;
      const suffix =
        norm === "delivery" || norm === "commissioning"
          ? "（历史采购窗口，已结束）"
          : "";
      return {
        range: `${rng}${suffix}`,
        reasoning:
          `合同于 ${award} 授予（FPSO_CONTRACT_AWARDED 事件），` +
          `按行业经验，长周期设备采购通常在授标后 2-4 个月启动，` +
          `预计采购窗口为 ${rng}。`,
      };
    }
  }
  if (!norm) return { range: "待补充", reasoning: "" };
  return { range: PHASE_WINDOW[norm] ?? "待补充", reasoning: "" };
}

function rulesGrades(project: Project): string[] {
  const grades: string[] = [];
  const rec = parseRecommendation(project.recommendationJson);
  if (rec) {
    for (const g of rec.grades) {
      const name = (g.grade ?? "").trim();
      if (name && !grades.includes(name)) grades.push(name);
    }
  }
  if (grades.length === 0) {
    for (const g of (project.stainlessSteel ?? "").split(",")) {
      const name = g.trim();
      if (name && !grades.includes(name)) grades.push(name);
    }
  }
  return grades;
}

function rulesProducts(project: Project): string[] {
  const apps: string[] = [];
  const rec = parseRecommendation(project.recommendationJson);
  if (rec) {
    for (const a of rec.applications) {
      const name = a.trim();
      if (name && !apps.includes(name)) apps.push(name);
    }
  }
  if (apps.length === 0) {
    for (const a of (project.application ?? "").split(",")) {
      const name = a.trim();
      if (name && !apps.includes(name)) apps.push(name);
    }
  }
  return apps;
}

/**
 * Rule-engine result — the same values the pages displayed pre-AI.
 * Pass linked candidate_events so delivered projects with a
 * FPSO_CONTRACT_AWARDED event get a dated historical window instead
 * of '时间未定'.
 */
export function rulesFallback(
  project: Project,
  events?: PushEvent[],
): PushAnalysis {
  const { range, reasoning } = rulesWindow(project.phase, events);
  return {
    source: "rules",
    procurement_window: {
      range,
      confidence: reasoning ? "high" : "low",
      reasoning: reasoning || "规则引擎按项目阶段估算，未参考事件原文。",
    },
    recommended_materials: rulesGrades(project)
      .slice(0, MAX_MATERIALS)
      .map((grade) => ({ grade, reason: "规则引擎：按项目阶段与技术参数匹配" })),
    recommended_products: rulesProducts(project)
      .slice(0, MAX_PRODUCTS)
      .map((product) => ({ product, reason: "规则引擎：按项目应用场景匹配" })),
    action_suggestion: scoreOpportunity(project).recommendedAction,
    ai_summary: "",
  };
}

// ---------------------------------------------------------------------------
// Event fetching — same input as the Feishu push (candidate_events)
// ---------------------------------------------------------------------------

export interface PushEvent {
  summary: string;
  evidence_quote: string;
  event_type: string;
  publication_date: string;
}

async function fetchProjectEvents(project: Project): Promise<PushEvent[]> {
  const cid = normalizeProjectName(project.name);
  if (!cid) return [];
  try {
    const { data, error } = await supabase
      .from("candidate_events")
      .select("summary,evidence_quote,event_type,publication_date")
      .eq("canonical_project_id", cid)
      .order("publication_date", { ascending: false })
      .limit(10);
    if (error) return [];
    return (data ?? []) as PushEvent[];
  } catch {
    return [];
  }
}

// ---------------------------------------------------------------------------
// Prompt building — same text as _build_prompt in ai_push_analyst.py
// ---------------------------------------------------------------------------

function buildPrompt(project: Project, events: PushEvent[], today: string): string {
  const lines = [
    "你是一名工业能源项目不锈钢材料销售分析助手。",
    `今天是 ${today}。请基于下方项目数据与该项目的事件报道原文，` +
      "为销售推送做个性化分析。",
    "严格只基于给定信息，不得编造原文不存在的事实；" +
      "信息不足以支持判断时写 '信息不足'。",
    "",
    "【项目数据】",
    `- 项目名称: ${project.name || "(unknown)"}`,
    `- 国家: ${project.country || "(unknown)"}`,
    `- 阶段: ${project.phase || "(unknown)"}`,
  ];
  const facts: Array<[keyof Project, string]> = [
    ["waterDepthM", "水深(m)"],
    ["oilCapacityBpd", "石油产能(bpd)"],
    ["gasCapacityMmcmd", "天然气产能(MMcmd)"],
    ["fieldName", "油田/气田"],
    ["operatorName", "运营商"],
    ["basin", "盆地"],
    ["hullType", "船体类型"],
    ["procurementChain", "采购链/EPC"],
    ["confidence", "数据置信度"],
  ];
  for (const [key, label] of facts) {
    const val = project[key];
    if (val != null && val !== "") {
      lines.push(`- ${label}: ${val}`);
    }
  }
  const summary = (project.summary ?? "").trim();
  if (summary) lines.push(`- 项目简介: ${summary.slice(0, 600)}`);

  lines.push("");
  if (events.length > 0) {
    lines.push(`【事件时间线（最近 ${events.length} 条，按时间倒序）】`);
    for (const ev of events) {
      const date = (ev.publication_date || "日期未知").slice(0, 10);
      const etype = ev.event_type || "ARTICLE_MENTION";
      const summ = (ev.summary || "").trim();
      const quote = (ev.evidence_quote || "").trim();
      let line = `- [${date}] (${etype}) ${summ}`;
      if (quote) line += ` 原文: ${quote.slice(0, 300)}`;
      lines.push(line);
    }
  } else {
    lines.push("【事件时间线】无关联事件。");
  }

  // Canonical stage term definitions — same text the Python
  // ai_push_analyst.py injects (both render from their mirrored
  // project_phase modules).
  lines.push("", stagePromptBlock());

  lines.push(
    "",
    "【输出】只输出一个 JSON 对象，不要输出其他文本，格式如下：",
    JSON.stringify(
      {
        procurement_window: {
          range: "采购时间窗，如 '2026 Q1-Q2' 或 '时间未定'",
          confidence: "high / medium / low",
          reasoning: "时间窗推导依据",
        },
        recommended_materials: [{ grade: "不锈钢牌号", reason: "推荐理由" }],
        recommended_products: [{ product: "管件产品", reason: "推荐理由" }],
        action_suggestion: "下一步行动建议，一句话",
        ai_summary: "整体判断摘要，2-3 句话",
      },
      null,
      2,
    ),
    "",
    "【判断规则】",
    "1. 采购时间窗必须从事件原文的具体线索推导，个性化，不得套统一模板。" +
      "例如：原文 'FID expected Q1 2026' → range 写 '2026 Q1-Q2'（FID 后" +
      "长周期采购通常在 0-3 个月内启动）；原文 'first steel cut in March " +
      "2026' → range 写 '2026 Q3-Q4'（开工后批量采购在 3-6 个月内）；" +
      "原文提到合同授予日期则按授标后 2-4 个月推导。reasoning 必须引用" +
      "具体原文证据。原文没有任何时间线索时 range 写 '时间未定'，" +
      "reasoning 说明为什么无法判断。" +
      "注意：项目阶段为 Delivery/Commissioning（已交付/已投产）且事件时间线" +
      "包含合同授予/FID/投产日期时，采购时间窗应输出该项目的历史采购时间窗，" +
      "例如合同授予 2019-06、投产 2024-01 → range 写 " +
      "'2019-06 ~ 2021-06（历史采购窗口，已结束）'，reasoning 引用具体事件" +
      "日期推导（合同授予后 2-4 个月启动长周期采购、开工后 3-6 个月批量采购），" +
      "不得对已交付项目输出 '时间未定'。",
    "2. 推荐材质必须结合项目技术参数（水深、产能、介质腐蚀性、盆地）与" +
      "原文内容，每个牌号说明为什么（例如：项目水深 2100m、Santos 盐下、" +
      "原文提到高 CO2 环境 → 推荐 Super Duplex 2507，因为深水盐下加高 CO2 " +
      "需要高耐点蚀当量材质）。只推荐 2-5 个最相关的牌号，不得简单堆砌牌号。",
    "3. 推荐产品必须结合项目阶段与设备类型（如 FPSO 上部模块、LNG 冷箱、海水淡化蒸发器等），" +
      "说明该项目为什么需要这些具体管件产品（例如：项目进入 EPC 采购阶段，" +
      "上部模块工艺管线需要大量对焊无缝管件与法兰）。只推荐 2-5 个。",
    "4. confidence 只允许 high / medium / low，反映时间窗证据的强弱。",
    "5. 项目「阶段」字段的含义以【项目阶段术语定义】为准；若原文证据不足，" +
      "不要臆断项目阶段，涉及阶段的内容写 '信息不足'。",
    "6. 所有输出用中文。",
  );
  return lines.join("\n");
}

// ---------------------------------------------------------------------------
// Response parsing & validation — mirrors _extract_json_object /
// _coerce_item_list / _validate_ai_result
// ---------------------------------------------------------------------------

function parseJSONObject(text: string): Record<string, unknown> | null {
  const trimmed = text
    .trim()
    .replace(/^```(?:json)?\s*/i, "")
    .replace(/```\s*$/, "");
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

function coerceItemList(
  value: unknown,
  key: "grade" | "product",
): Array<Record<string, string>> {
  if (!Array.isArray(value)) return [];
  const items: Array<Record<string, string>> = [];
  for (const entry of value) {
    let name = "";
    let reason = "";
    if (entry && typeof entry === "object") {
      const obj = entry as Record<string, unknown>;
      name = String(obj[key] ?? obj.name ?? "").trim();
      reason = String(obj.reason ?? "").trim();
    } else if (typeof entry === "string") {
      name = entry.trim();
    }
    if (!name) continue;
    if (reason && reason.toLowerCase() === "信息不足") {
      reason = "信息不足，原文未提及具体工况";
    }
    items.push({ [key]: name, reason });
  }
  return items;
}

/** Shape-check the LLM object; null means fall back to rules.
 *  Lenient: keep the AI result as long as ANY field carries content —
 *  only an entirely empty object is rejected. */
function validateAIResult(obj: Record<string, unknown>): Omit<PushAnalysis, "source"> | null {
  const pwRaw = obj.procurement_window;
  const pwObj =
    pwRaw && typeof pwRaw === "object" && !Array.isArray(pwRaw)
      ? (pwRaw as Record<string, unknown>)
      : null;

  const range = pwObj ? String(pwObj.range ?? "").trim().slice(0, 120) : "";
  const rawConf = pwObj ? String(pwObj.confidence ?? "").trim().toLowerCase() : "";
  const confidence: PushProcurementWindow["confidence"] =
    rawConf === "high" || rawConf === "low" ? rawConf : "medium";
  const reasoning = pwObj ? String(pwObj.reasoning ?? "").trim().slice(0, 400) : "";

  const materials = coerceItemList(obj.recommended_materials, "grade")
    .slice(0, MAX_MATERIALS) as unknown as PushMaterial[];
  const products = coerceItemList(obj.recommended_products, "product")
    .slice(0, MAX_PRODUCTS) as unknown as PushProduct[];

  const actionSuggestion = String(obj.action_suggestion ?? "").trim().slice(0, 200);
  const aiSummary = String(obj.ai_summary ?? "").trim().slice(0, 600);

  const hasAny =
    range !== "" ||
    reasoning !== "" ||
    aiSummary !== "" ||
    materials.length > 0 ||
    products.length > 0;
  if (!hasAny) return null;

  return {
    procurement_window: { range, confidence, reasoning },
    recommended_materials: materials,
    recommended_products: products,
    action_suggestion: actionSuggestion,
    ai_summary: aiSummary,
  };
}

// ---------------------------------------------------------------------------
// LLM config check (retrying) & main entry
// ---------------------------------------------------------------------------

/** Failed config checks are retried by the next caller after this long. */
const CONFIG_RETRY_MS = 30_000;

let configState: { configured: boolean; checkedAt: number } | null = null;
let configInFlight: Promise<boolean> | null = null;

/**
 * Whether the worker has an LLM key. A successful check is cached for the
 * session; a failed check is NOT permanent — the next caller after
 * CONFIG_RETRY_MS re-checks instead of locking the whole session to rules.
 */
function llmConfigured(): Promise<boolean> {
  if (configInFlight) return configInFlight;
  const now = Date.now();
  if (configState && (configState.configured || now - configState.checkedAt < CONFIG_RETRY_MS)) {
    return Promise.resolve(configState.configured);
  }
  configInFlight = isLLMConfigured()
    .then((ok) => {
      configState = { configured: ok, checkedAt: Date.now() };
      return ok;
    })
    .catch(() => {
      configState = { configured: false, checkedAt: Date.now() };
      return false;
    })
    .finally(() => {
      configInFlight = null;
    });
  return configInFlight;
}

/** Failed analyses block retries for this long (call-storm guard only). */
const FAILURE_COOLDOWN_MS = 30_000;

/** Successful results, cached per project name forever (session-scoped). */
const successCache = new Map<string, PushAnalysis>();
/** In-flight calls, shared so concurrent components make one LLM call. */
const inflightCache = new Map<string, Promise<PushAnalysis>>();
/** Project name -> cooldown expiry (ms). Failures are NOT cached, only delayed. */
const failureCooldown = new Map<string, number>();

/**
 * AI-personalized push analysis for one project, same input and output
 * shape as crawler analyze_for_push(). Never throws.
 *
 * Success is cached per project name permanently. Failures (timeout, HTTP
 * error, malformed/invalid JSON, unconfigured worker) are NOT cached — after
 * a short cooldown the next caller retries the LLM automatically.
 */
export function analyzePush(project: Project): Promise<PushAnalysis> {
  const cached = successCache.get(project.name);
  if (cached) return Promise.resolve(cached);

  const inFlight = inflightCache.get(project.name);
  if (inFlight) return inFlight;

  let failed = false;
  const run = (async (): Promise<PushAnalysis> => {
    // Fetch events before any fallback so the rule path can derive a
    // dated window from FPSO_CONTRACT_AWARDED events.
    const events = await fetchProjectEvents(project);
    const cooldown = failureCooldown.get(project.name);
    if (cooldown && cooldown > Date.now()) {
      return rulesFallback(project, events);
    }
    try {
      if (!(await llmConfigured())) {
        console.warn(`[push] LLM not configured — rules fallback for "${project.name}"`);
        failed = true;
        return rulesFallback(project, events);
      }
      const today = new Date().toISOString().slice(0, 10);
      const messages: ChatMessage[] = [
        {
          role: "system",
          content:
            "你是工业能源项目的不锈钢材料销售分析助手。" +
            "严格只基于用户提供的项目事实与事件原文分析，" +
            "不得编造任何原文不存在的信息。信息不足时写 '信息不足'。" +
            "只输出 JSON。",
        },
        { role: "user", content: buildPrompt(project, events, today) },
      ];
      const content = await callLLM(messages, {
        temperature: 0.2,
        maxTokens: 1400,
        jsonMode: true,
      });
      if (!content) {
        console.warn(`[push] LLM returned no content for "${project.name}" — rules fallback`);
        failed = true;
        return rulesFallback(project, events);
      }
      const obj = parseJSONObject(content);
      if (!obj) {
        console.warn(
          `[push] LLM JSON unparseable for "${project.name}": ${content.slice(0, 120)}`,
        );
        failed = true;
        return rulesFallback(project, events);
      }
      const result = validateAIResult(obj);
      if (!result) {
        console.warn(`[push] LLM result empty/invalid for "${project.name}" — rules fallback`);
        failed = true;
        return rulesFallback(project, events);
      }
      const ai: PushAnalysis = { source: "ai", ...result };
      successCache.set(project.name, ai);
      return ai;
    } catch (err) {
      console.warn(`[push] LLM analysis failed for "${project.name}":`, err);
      failed = true;
      return rulesFallback(project, events);
    } finally {
      inflightCache.delete(project.name);
      if (failed) {
        failureCooldown.set(project.name, Date.now() + FAILURE_COOLDOWN_MS);
      }
    }
  })();

  inflightCache.set(project.name, run);
  return run;
}

/**
 * Rule-engine-only variant for surfaces that skip the LLM (e.g. cards
 * below the fold). Fetches events first so the fallback window derives
 * from FPSO_CONTRACT_AWARDED dates instead of the bare phase map.
 */
export async function analyzePushRules(project: Project): Promise<PushAnalysis> {
  const events = await fetchProjectEvents(project);
  return rulesFallback(project, events);
}
