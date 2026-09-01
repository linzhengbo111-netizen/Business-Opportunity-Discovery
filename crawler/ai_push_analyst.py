#!/usr/bin/env python3
"""
AI Push Analyst — LLM-personalized push analysis for Feishu notifications.

Replaces the phase-only rule output in notifier.py with per-project AI
judgement. For each project the module feeds the LLM (DeepSeek via
call_llm from ai_event_extractor.py) the full project profile plus the
recent candidate_events timeline text, and asks for:

  procurement_window      — personalized range derived from event evidence
                            ('FID expected Q1 2026' → '2026 Q1-Q2'), never a
                            phase-based template
  recommended_materials   — grades with per-grade reasons tied to technical
                            params (water depth, CO2/H2S, basin) and source text
  recommended_products    — concrete fittings/products with per-item reasons
  action_suggestion       — one concrete next step
  ai_summary              — 2-3 sentence overall judgement

Call contract: analyze_for_push() NEVER raises. On any LLM failure
(no config, HTTP error, malformed/invalid JSON) it falls back to the rule
engine — the same phase-window map and recommendation_json grades the
notifier displayed before — and marks the result source: 'rules'.

Why: phase-based windows output the same range for every project in the
same phase. Projects in the same phase can have months of difference in
their real procurement timing, and the event text (contract award, FID
confirmations, first steel cut) holds the evidence to tell them apart.
"""

import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone

import requests

# ---- Path hack for adapter imports --------------------------------------
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from adapters.media_common import normalize_project_name  # noqa: E402
from ai_event_extractor import call_llm  # noqa: E402
from project_phase import stage_prompt_block  # noqa: E402
from opportunity_scorer import PRODUCIBLE_GRADES  # noqa: E402

# Optional proxy for LLM calls: POST {LLM_PROXY_URL}/api/llm with the same
# OpenAI Chat Completions body but NO Authorization header (the worker keeps
# the API key server-side). Used by GitHub Actions, where LLM_API_KEY is not
# available as a secret. When unset, call_llm() talks to DeepSeek directly.
LLM_PROXY_URL = os.getenv("LLM_PROXY_URL", "").strip().rstrip("/")

log = logging.getLogger("fpso-ai-push-analyst")

# ---- Material grade normalization (mirrors material_matcher.ts) ---------

# Alias → canonical grade name. Keys are normalized (lowercase, all
# spaces/punctuation stripped), so "UNS S31254", "254 SMO" and "AL-6XN"
# all resolve to the canonical "6Mo (UNS S31254)".
MATERIAL_GRADE_ALIASES = {
    # 6Mo super austenitic family — canonical UNS is S31254 (254 SMO)
    "6mo": "6Mo (UNS S31254)",
    "6mounss31254": "6Mo (UNS S31254)",
    "s31254": "6Mo (UNS S31254)",
    "unss31254": "6Mo (UNS S31254)",
    "254smo": "6Mo (UNS S31254)",
    "uns254smo": "6Mo (UNS S31254)",
    "n08367": "6Mo (UNS S31254)",
    "unsn08367": "6Mo (UNS S31254)",
    "al6xn": "6Mo (UNS S31254)",
    "al6xnalloy": "6Mo (UNS S31254)",
    # Duplex 2205
    "2205": "Duplex 2205",
    "duplex2205": "Duplex 2205",
    "s31803": "Duplex 2205",
    "unss31803": "Duplex 2205",
    "s32205": "Duplex 2205",
    "unss32205": "Duplex 2205",
    "22cr": "Duplex 2205",
    # Super Duplex 2507
    "2507": "Super Duplex 2507",
    "superduplex2507": "Super Duplex 2507",
    "s32750": "Super Duplex 2507",
    "unss32750": "Super Duplex 2507",
    "25cr": "Super Duplex 2507",
    # Lean duplex
    "2304": "Lean Duplex 2304",
    "s32304": "Lean Duplex 2304",
    "unss32304": "Lean Duplex 2304",
    "2101": "Lean Duplex 2101",
    "s32101": "Lean Duplex 2101",
    "zeron100": "Zeron 100",
    # Austenitic
    "s31603": "316L",
    "unss31603": "316L",
    "s30403": "304L",
    "unss30403": "304L",
    "n08904": "904L",
    "unss08904": "904L",
    # Surface-finish qualifiers on producible grades
    "316lep": "316L",
    "316lelectropolished": "316L",
    # Application qualifiers on producible grades
    "superduplex2507seawater": "Super Duplex 2507",
    # Nickel alloys
    "alloy625": "Inconel 625",
    "inconel625": "Inconel 625",
    "n06625": "Inconel 625",
    "unsn06625": "Inconel 625",
    "alloy825": "Incoloy 825",
    "inconel825": "Incoloy 825",
    "incoloy825": "Incoloy 825",
    "n08825": "Incoloy 825",
    "unsn08825": "Incoloy 825",
    "alloyc276": "Hastelloy C276",
    "c276": "Hastelloy C276",
    "hastelloyc276": "Hastelloy C276",
    "n10276": "Hastelloy C276",
    "alloyc22": "Hastelloy C22",
    "c22": "Hastelloy C22",
    "hastelloyc22": "Hastelloy C22",
    "n06022": "Hastelloy C22",
    "alloy20": "Alloy 20",
    "n08020": "Alloy 20",
    "monel400": "Monel 400",
    "n04400": "Monel 400",
    "monelk500": "Monel K500",
    "k500": "Monel K500",
    "n05500": "Monel K500",
    "incoloy800": "Incoloy 800",
    "incoloy800h": "Incoloy 800H",
    "incoloy800ht": "Incoloy 800HT",
}

_PRODUCIBLE_SET = set(PRODUCIBLE_GRADES)


def normalize_material_grade(grade) -> str | None:
    """Normalize a grade name to the canonical factory-catalog name.

    Known aliases/UNS numbers map to the canonical name; exact catalog
    names pass through; anything else returns None (callers drop it).
    """
    raw = (grade or "").strip()
    if not raw:
        return None
    key = re.sub(r"[\s,()\-/.]+", "", raw.lower())
    canonical = MATERIAL_GRADE_ALIASES.get(key)
    if canonical:
        return canonical
    if raw in _PRODUCIBLE_SET:
        return raw
    return None


def canonical_grade_list() -> list[str]:
    """Factory grade whitelist in canonical names (deduped), for prompts."""
    seen: list[str] = []
    for g in PRODUCIBLE_GRADES:
        canon = normalize_material_grade(g) or g
        if canon not in seen:
            seen.append(canon)
    return seen


# ---- Rule-engine fallback (mirrors notifier.py's pre-AI output) ---------

# Phase → procurement window estimate. Mirrors the TS engine's
# estimateProcurementWindow (src/lib/material_matcher.ts) phase rules.
_PHASE_WINDOW = {
    "procurement": "0-3 个月",
    "epc award": "2-4 个月",
    "construction": "3-6 个月",
    "approval": "6-12 个月",
    "design": "12-18 个月",
    "planning": "12 个月以上",
    "concept": "12 个月以上",
    "commissioning": "时间未定",
    "delivery": "时间未定",
}

_LEGACY_PHASE = {
    "delivered": "Delivery",
    "completed": "Delivery",
    "under construction": "Construction",
    "planned": "Planning",
}

_CONFIDENCE_LABELS = {"high": "高", "medium": "中", "low": "低"}

MAX_MATERIALS = 6
MAX_PRODUCTS = 6


def _normalize_phase(phase: str) -> str:
    """Normalize a phase/status value to the canonical 9-phase taxonomy."""
    raw = (phase or "").strip()
    if not raw:
        return ""
    return _LEGACY_PHASE.get(raw.lower(), raw)


def _contract_award_date(events: list[dict] | None) -> str:
    """First FPSO_CONTRACT_AWARDED publication_date, or ''."""
    for ev in events or []:
        if (ev.get("event_type") or "").strip().upper() == "FPSO_CONTRACT_AWARDED":
            d = (ev.get("publication_date") or "").strip()
            if d:
                return d[:10]
    return ""


def _add_months(d: datetime, n: int) -> datetime:
    m = d.month - 1 + n
    return d.replace(year=d.year + m // 12, month=m % 12 + 1)


def _rules_window(
    phase: str, events: list[dict] | None = None
) -> tuple[str, str]:
    """(range, reasoning) — contract-award events win over phase guess.

    FPSO_CONTRACT_AWARDED + 2-4 months mirrors the TS engine's Rule 1
    (estimateProcurementWindow in src/lib/material_matcher.ts), so the
    rule fallback never returns '时间未定' for delivered projects that
    have award events.
    """
    norm = _normalize_phase(phase).lower()
    award = _contract_award_date(events)
    if award:
        try:
            award_d = datetime.strptime(award, "%Y-%m-%d")
        except ValueError:
            award_d = None
        if award_d is not None:
            start = _add_months(award_d, 2)
            end = _add_months(award_d, 4)
            rng = f"{start:%Y-%m} ~ {end:%Y-%m}"
            suffix = (
                "（历史采购窗口，已结束）"
                if norm in ("delivery", "commissioning")
                else ""
            )
            reasoning = (
                f"合同于 {award} 授予（FPSO_CONTRACT_AWARDED 事件），"
                f"按行业经验，长周期设备采购通常在授标后 2-4 个月启动，"
                f"预计采购窗口为 {rng}。"
            )
            return f"{rng}{suffix}", reasoning
    if not norm:
        return "待补充", ""
    return _PHASE_WINDOW.get(norm, "待补充"), ""


def _parse_recommendation(project: dict) -> dict:
    """Parse recommendation_json (JSONB may arrive as dict or str)."""
    rec = project.get("recommendation_json")
    if isinstance(rec, str):
        try:
            rec = json.loads(rec)
        except Exception:
            rec = None
    return rec if isinstance(rec, dict) else {}


def _rules_grades(project: dict, rec: dict) -> list[str]:
    """Grades from recommendation_json.grades, fallback stainless_steel."""
    grades: list[str] = []
    for g in rec.get("grades") or []:
        if isinstance(g, dict):
            name = g.get("grade") or g.get("name") or ""
        else:
            name = str(g)
        name = name.strip()
        if name and name not in grades:
            grades.append(name)
    if not grades:
        for g in (project.get("stainless_steel") or "").split(","):
            g = g.strip()
            if g and g not in grades:
                grades.append(g)
    return grades


def _rules_apps(project: dict, rec: dict) -> list[str]:
    """Products from recommendation_json.applications, fallback application."""
    apps: list[str] = []
    for a in rec.get("applications") or []:
        a = str(a).strip()
        if a and a not in apps:
            apps.append(a)
    if not apps:
        for a in (project.get("application") or "").split(","):
            a = a.strip()
            if a and a not in apps:
                apps.append(a)
    return apps


def _rules_action(project: dict) -> str:
    score = project.get("opportunity_score")
    if isinstance(score, str):
        try:
            score = json.loads(score)
        except Exception:
            score = None
    if isinstance(score, dict):
        return (score.get("recommendedAction") or "").strip()
    return ""


def _rules_fallback(
    project: dict, events: list[dict] | None = None
) -> dict:
    """Rule-engine result, same values the notifier displayed pre-AI.

    Contract-award events (FPSO_CONTRACT_AWARDED) override the phase
    window map so delivered projects get a dated historical window
    instead of '时间未定'.
    """
    phase = (project.get("phase") or project.get("status") or "")
    rec = _parse_recommendation(project)
    grades = _rules_grades(project, rec)
    apps = _rules_apps(project, rec)
    window_range, window_reasoning = _rules_window(phase, events)

    return {
        "source": "rules",
        "procurement_window": {
            "range": window_range,
            "confidence": "high" if window_reasoning else "low",
            "reasoning": window_reasoning or "规则引擎按项目阶段估算，未参考事件原文。",
        },
        "recommended_materials": [
            {"grade": g, "reason": "规则引擎：按项目阶段与技术参数匹配"}
            for g in grades[:MAX_MATERIALS]
        ],
        "recommended_products": [
            {"product": a, "reason": "规则引擎：按项目应用场景匹配"}
            for a in apps[:MAX_PRODUCTS]
        ],
        "action_suggestion": _rules_action(project),
        "ai_summary": "",
    }


# ---- Event fetching -------------------------------------------------------


def fetch_project_events(supabase, project: dict, limit: int = 10) -> list[dict]:
    """Fetch recent candidate_events for a project, newest first.

    Rows carry summary, evidence_quote, event_type, publication_date.
    Returns [] on any failure — never raises.
    """
    cid = normalize_project_name(project.get("name") or "")
    if not cid:
        return []
    try:
        resp = supabase.table("candidate_events") \
            .select("summary,evidence_quote,event_type,publication_date") \
            .eq("canonical_project_id", cid) \
            .order("publication_date", desc=True) \
            .limit(limit).execute()
        return resp.data or []
    except Exception as exc:
        log.warning("events fetch error for %s: %s",
                    (project.get("name") or "?")[:40], exc)
        return []


# ---- Prompt building ------------------------------------------------------


def _build_prompt(project: dict, events: list[dict], today: str) -> str:
    lines = [
        "你是一名 FPSO 海上油气项目不锈钢材料销售分析助手。",
        f"今天是 {today}。请基于下方项目数据与该项目的事件报道原文，"
        "为销售推送做个性化分析。",
        "严格只基于给定信息，不得编造原文不存在的事实；"
        "信息不足以支持判断时写 '信息不足'。",
        "",
        "【项目数据】",
        f"- 项目名称: {project.get('name') or '(unknown)'}",
        f"- 国家: {project.get('country') or '(unknown)'}",
        f"- 阶段: {project.get('phase') or project.get('status') or '(unknown)'}",
    ]
    for key, label in (
        ("water_depth_m", "水深(m)"),
        ("oil_capacity_bpd", "石油产能(bpd)"),
        ("gas_capacity_mmcmd", "天然气产能(MMcmd)"),
        ("field_name", "油田/气田"),
        ("operator_name", "运营商"),
        ("basin", "盆地"),
        ("hull_type", "船体类型"),
        ("procurement_chain", "采购链/EPC"),
        ("confidence", "数据置信度"),
    ):
        val = project.get(key)
        if val not in (None, ""):
            lines.append(f"- {label}: {val}")
    summary = (project.get("summary") or "").strip()
    if summary:
        lines.append(f"- 项目简介: {summary[:600]}")

    lines.append("")
    if events:
        lines.append(f"【事件时间线（最近 {len(events)} 条，按时间倒序）】")
        for ev in events:
            date = (ev.get("publication_date") or "日期未知")[:10]
            etype = ev.get("event_type") or "ARTICLE_MENTION"
            summ = (ev.get("summary") or "").strip()
            quote = (ev.get("evidence_quote") or "").strip()
            line = f"- [{date}] ({etype}) {summ}"
            if quote:
                line += f" 原文: {quote[:300]}"
            lines.append(line)
    else:
        lines.append("【事件时间线】无关联事件。")

    # Canonical stage term definitions — same text the TS push_analyst.ts
    # injects (both render from their mirrored project_phase modules).
    lines += [
        "",
        stage_prompt_block(),
    ]

    # Factory-producible grade whitelist — the LLM must copy names verbatim
    # from this list. Mirrors the TS push_analyst.ts block.
    lines += [
        "",
        "【工厂可生产不锈钢牌号清单（规范全名）】",
        "- " + "、".join(canonical_grade_list()),
    ]

    lines += [
        "",
        "【输出】只输出一个 JSON 对象，不要输出其他文本，格式如下：",
        json.dumps({
            "procurement_window": {
                "range": "采购时间窗，如 '2026 Q1-Q2' 或 '时间未定'",
                "confidence": "high / medium / low",
                "reasoning": "时间窗推导依据",
            },
            "recommended_materials": [
                {"grade": "不锈钢牌号", "reason": "推荐理由"}
            ],
            "recommended_products": [
                {"product": "管件产品", "reason": "推荐理由"}
            ],
            "action_suggestion": "下一步行动建议，一句话",
            "ai_summary": "整体判断摘要，2-3 句话",
        }, ensure_ascii=False, indent=2),
        "",
        "【判断规则】",
        "1. 采购时间窗必须从事件原文的具体线索推导，个性化，不得套统一模板。"
        "例如：原文 'FID expected Q1 2026' → range 写 '2026 Q1-Q2'（FID 后"
        "长周期采购通常在 0-3 个月内启动）；原文 'first steel cut in March "
        "2026' → range 写 '2026 Q3-Q4'（开工后批量采购在 3-6 个月内）；"
        "原文提到合同授予日期则按授标后 2-4 个月推导。reasoning 必须引用"
        "具体原文证据。原文没有任何时间线索时 range 写 '时间未定'，"
        "reasoning 说明为什么无法判断。"
        "注意：项目阶段为 Delivery/Commissioning（已交付/已投产）且事件时间线"
        "包含合同授予/FID/投产日期时，采购时间窗应输出该项目的历史采购时间窗，"
        "例如合同授予 2019-06、投产 2024-01 → range 写 "
        "'2019-06 ~ 2021-06（历史采购窗口，已结束）'，reasoning 引用具体事件"
        "日期推导（合同授予后 2-4 个月启动长周期采购、开工后 3-6 个月批量采购），"
        "不得对已交付项目输出 '时间未定'。",
        "2. 推荐材质必须结合项目技术参数（水深、产能、介质腐蚀性、盆地）与"
        "原文内容，每个牌号说明为什么（例如：项目水深 2100m、Santos 盐下、"
        "原文提到高 CO2 环境 → 推荐 Super Duplex 2507，因为深水盐下加高 CO2 "
        "需要高耐点蚀当量材质）。只推荐 2-5 个最相关的牌号，不得简单堆砌牌号。"
        "grade 字段只能从【工厂可生产不锈钢牌号清单】中选择，必须逐字复制"
        "完整规范名，禁止自造变体、简写或改写 UNS 号（如 '6Mo' 只能写"
        "'6Mo (UNS S31254)'，不得写 '6Mo (UNS N08367)'）。"
        "如果项目需要的材质不在清单中，grade 写 '工厂不生产'，不得推荐该牌号。",
        "3. 推荐产品必须结合项目阶段与设备类型（FPSO/FLNG 上部模块等），"
        "说明该项目为什么需要这些具体管件产品（例如：项目进入 EPC 采购阶段，"
        "上部模块工艺管线需要大量对焊无缝管件与法兰）。"
        "必须同时覆盖三大类：管材（无缝管/焊管）、管件（对焊管件、弯头、三通、异径管等）、"
        "法兰（如 WN 对焊法兰）——做项目三类缺一不可；"
        "其余位置可再按项目需要补充（如管座 Stub End、盘管等）。推荐 3-6 个。",
        "4. confidence 只允许 high / medium / low，反映时间窗证据的强弱。",
        "5. 项目「阶段」字段的含义以【项目阶段术语定义】为准；若原文证据不足，"
        "不要臆断项目阶段，涉及阶段的内容写 '信息不足'。",
        "6. 所有输出用中文。",
    ]
    return "\n".join(lines)


# ---- Response parsing & validation ---------------------------------------


def _extract_json_object(text: str) -> dict | None:
    """Parse a JSON object out of LLM text (tolerates fences / prose)."""
    trimmed = text.strip()
    trimmed = re.sub(r"^```(?:json)?\s*", "", trimmed)
    trimmed = re.sub(r"```\s*$", "", trimmed)
    start = trimmed.find("{")
    end = trimmed.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        obj = json.loads(trimmed[start:end + 1])
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _coerce_item_list(value, key: str) -> list[dict]:
    """Normalize [{'grade': ..., 'reason': ...}] style lists; tolerate
    plain strings. Drops empty entries."""
    if not isinstance(value, list):
        return []
    items = []
    for entry in value:
        if isinstance(entry, dict):
            name = str(entry.get(key) or entry.get("name") or "").strip()
            reason = str(entry.get("reason") or "").strip()
        else:
            name = str(entry).strip()
            reason = ""
        if not name:
            continue
        if reason and reason.lower() == "信息不足":
            reason = "信息不足，原文未提及具体工况"
        items.append({key: name, "reason": reason})
    return items


def _validate_ai_result(obj: dict) -> dict | None:
    """Shape-check the LLM object; None means fall back to rules."""
    pw = obj.get("procurement_window")
    if not isinstance(pw, dict):
        return None
    range_ = str(pw.get("range") or "").strip()
    if not range_ or len(range_) > 120:
        return None
    conf = str(pw.get("confidence") or "").strip().lower()
    if conf not in ("high", "medium", "low"):
        conf = "medium"
    reasoning = str(pw.get("reasoning") or "").strip()[:400]

    # Normalize every LLM grade to the canonical factory-catalog name and
    # drop anything unknown (fabricated grades, '工厂不生产' markers).
    materials: list[dict] = []
    seen_grades: set[str] = set()
    for m in _coerce_item_list(obj.get("recommended_materials"), "grade"):
        grade = normalize_material_grade(m.get("grade"))
        if not grade or grade in seen_grades:
            continue
        seen_grades.add(grade)
        materials.append({"grade": grade, "reason": m.get("reason")})
        if len(materials) >= MAX_MATERIALS:
            break
    products = _coerce_item_list(obj.get("recommended_products"), "product")
    if not materials and not products:
        return None

    return {
        "procurement_window": {
            "range": range_,
            "confidence": conf,
            "reasoning": reasoning,
        },
        "recommended_materials": materials,
        "recommended_products": products[:MAX_PRODUCTS],
        "action_suggestion": str(obj.get("action_suggestion") or "").strip()[:200],
        "ai_summary": str(obj.get("ai_summary") or "").strip()[:600],
    }


# ---- LLM call: proxy first (Actions), direct DeepSeek fallback ------------


def _call_llm_via_proxy(messages, max_tokens=1400):
    """Call the deployed Cloudflare Worker /api/llm proxy (no auth header
    needed client-side). Returns assistant text, or None on any failure.
    Never raises."""
    if not LLM_PROXY_URL:
        return None
    body = {
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    try:
        resp = requests.post(f"{LLM_PROXY_URL}/api/llm", json=body, timeout=90)
        if resp.status_code != 200:
            log.warning("AI push proxy HTTP %s: %s",
                        resp.status_code, resp.text[:200])
            return None
        data = resp.json()
        content = (data.get("choices") or [{}])[0] \
            .get("message", {}).get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
    except requests.exceptions.RequestException as exc:
        log.warning("AI push proxy request failed: %s", exc)
    except (json.JSONDecodeError, ValueError) as exc:
        log.warning("AI push proxy response parse error: %s", exc)
    return None


# ---- Main entry -----------------------------------------------------------


def analyze_for_push(project: dict, events: list[dict] | None = None) -> dict:
    """AI-personalized push analysis for one project.

    Args:
        project: project dict from Supabase (name, country, phase,
            water_depth_m, oil_capacity_bpd, gas_capacity_mmcmd, field_name,
            operator_name, basin, hull_type, procurement_chain, confidence,
            summary, recommendation_json, opportunity_score, ...).
        events: linked candidate_events rows (summary, evidence_quote,
            event_type, publication_date), newest first. Use
            fetch_project_events() to get them; [] when none.

    Returns dict with source 'ai' or 'rules' plus procurement_window,
    recommended_materials, recommended_products, action_suggestion,
    ai_summary. Never raises.
    """
    events = events or []
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    prompt = _build_prompt(project, events, today)
    messages = [
        {"role": "system",
         "content": "你是 FPSO 海上油气项目的不锈钢材料销售分析助手。"
                    "严格只基于用户提供的项目事实与事件原文分析，"
                    "不得编造任何原文不存在的信息。信息不足时写 '信息不足'。"
                    "只输出 JSON。"},
        {"role": "user", "content": prompt},
    ]

    started = time.time()
    reply = _call_llm_via_proxy(messages)
    if reply is None:
        reply = call_llm(messages, temperature=0.2, max_tokens=1400)
    if reply is None:
        log.warning("AI push analysis unavailable for %s — using rules",
                    (project.get("name") or "?")[:40])
        return _rules_fallback(project, events)

    obj = _extract_json_object(reply)
    if obj is None:
        log.warning("AI push analysis unparseable JSON for %s — using rules",
                    (project.get("name") or "?")[:40])
        return _rules_fallback(project, events)

    result = _validate_ai_result(obj)
    if result is None:
        log.warning("AI push analysis invalid shape for %s — using rules",
                    (project.get("name") or "?")[:40])
        return _rules_fallback(project, events)

    result["source"] = "ai"
    log.info("AI push analysis OK for %s (%.1fs): window=%s",
             (project.get("name") or "?")[:40],
             time.time() - started,
             result["procurement_window"]["range"])
    return result
