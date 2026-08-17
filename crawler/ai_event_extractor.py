#!/usr/bin/env python3
"""
AI Event Extractor — LLM-powered timeline event extraction for candidate_events.

Crawler adapters insert articles with event_type='ARTICLE_MENTION' (rule-engine
default). This module re-analyzes those articles with the LLM API
(LLM_API_URL / LLM_API_KEY / LLM_MODEL from .env, OpenAI Chat Completions
compatible, e.g. DeepSeek) and produces structured timeline events:

  project_name     — FPSO project name, empty when article names no project
  event_type       — one of EVENT_TYPES (see below)
  publication_date — YYYY-MM-DD from the article, empty when unknown
  evidence_quote   — verbatim sentence from the article, never invented
  summary          — one-sentence event summary

Call contract: extract_events_from_article() NEVER raises. On any LLM failure
it returns None and the caller falls back to rule_engine_fallback(), which
mirrors the adapters' existing extract_project_info() logic.

Why: candidate_events rows lacking canonical_project_id (NULL) never show up
in the frontend timeline, which filters by that column. Extracted events get
canonical_project_id filled via normalize_project_name().
"""

import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

# ---- Path hack for adapter imports --------------------------------------
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from adapters.media_common import (  # noqa: E402
    extract_project_info,
    normalize_project_name,
)

load_dotenv()

log = logging.getLogger("fpso-ai-extractor")

LLM_API_URL = os.getenv("LLM_API_URL", "").strip()
LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip()
LLM_MODEL = os.getenv("LLM_MODEL", "").strip()

# ---- Event type taxonomy -------------------------------------------------
# Union of frontend EVENT_TYPE_LABELS (ProjectTimelinePage.tsx), the
# OFFICIAL_EVENTS set in crawl.py, and crawler-specific types.
EVENT_TYPES = [
    "EIA_SUBMITTED",
    "DEVELOPMENT_CONSENT_GRANTED",
    "REGULATORY_DATA",
    "FPSO_CONTRACT_AWARDED",
    "CONTRACT_AWARDED",
    "DEVELOPMENT_PLAN_SUBMITTED",
    "DEVELOPMENT_PLAN_UPDATED",
    "FIELD_DEVELOPMENT_PLAN",
    "PERMIT_GRANTED",
    "LICENSE_GRANTED",
    "FID_CONFIRMED",
    "PRODUCTION_START",
    "FIRST_OIL",
    "DELIVERED",
    "VENDOR_REGISTRATION_ACTION",
    "PUBLIC_NOTICE",
    "CONTRACT_ANNOUNCEMENT",
    "PROCUREMENT_CHAIN",
    "ARTICLE_MENTION",
]
EVENT_TYPES_SET = set(EVENT_TYPES)

# Rows whose event_type is one of these were never analyzed by a human or
# the LLM — safe to re-analyze. Everything else (P0 regulatory events etc.)
# is left untouched by the extractor.
REANALYZABLE_TYPES = {"ARTICLE_MENTION", "", None}

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# ========================================================================
# Project phase taxonomy (replaces the legacy 4-value status system)
# ========================================================================

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

# Optional proxy for LLM calls: POST {LLM_PROXY_URL}/api/llm with the same
# OpenAI Chat Completions body but NO Authorization header (the worker
# keeps the API key server-side). When unset, call_llm() talks to DeepSeek
# directly via LLM_API_URL/LLM_API_KEY, matching the rest of the crawler.
LLM_PROXY_URL = os.getenv("LLM_PROXY_URL", "").strip().rstrip("/")


def _phase_prompt(project, events_text):
    """Build the phase-classification prompt for one project."""
    lines = [
        "Classify the lifecycle phase of one FPSO/oil & gas project.",
        "Phases (in lifecycle order): " + " → ".join(PROJECT_PHASES) + ".",
        "",
        "Project data:",
        f"- Name: {project.get('name') or '(unknown)'}",
        f"- Country: {project.get('country') or '(unknown)'}",
        f"- Summary: {project.get('summary') or '(none)'}",
        f"- Procurement chain: {project.get('procurement_chain') or '(none)'}",
    ]
    for key, label in (("operator_name", "Operator"),
                       ("field_name", "Field"),
                       ("basin", "Basin")):
        val = project.get(key)
        if val:
            lines.append(f"- {label}: {val}")
    lines.append("")
    if events_text.strip():
        lines.append("Linked timeline events (evidence):")
        lines.append(events_text[:4000])
    else:
        lines.append("Linked timeline events: (none)")
    lines += [
        "",
        "Return a JSON object with this exact shape:",
        '{"phase": "<one of the 9 phases above>", "reasoning": "<one short sentence>"}',
        "",
        "Rules:",
        "1. phase: exactly one of Concept / Planning / Design / Approval / "
        "EPC Award / Procurement / Construction / Commissioning / Delivery.",
        "2. If evidence supports several phases, return the LATEST phase in "
        "the lifecycle order (e.g. award + procurement → Procurement).",
        "3. A Consent Date / Production Start older than 10 years means the "
        "field is already producing or abandoned → Delivery (or Commissioning "
        "if commissioning data exists). A consent date alone is ONLY Approval "
        "when it is recent (within ~10 years) or no production data exists.",
        "4. Use ONLY facts present in the data above. Never invent events.",
        "5. If nothing supports any phase, return an empty string for phase: "
        '{"phase": "", "reasoning": "insufficient data"}.',
    ]
    return "\n".join(lines)


def _call_llm_via_proxy(messages, temperature=0.2, max_tokens=300):
    """Call the deployed Cloudflare Worker /api/llm proxy (no auth header
    needed client-side). Returns assistant text, or None on any failure.
    Never raises."""
    if not LLM_PROXY_URL:
        return None
    body = {
        "model": LLM_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    try:
        resp = requests.post(f"{LLM_PROXY_URL}/api/llm", json=body, timeout=90)
        if resp.status_code != 200:
            log.warning("Phase proxy HTTP %s: %s",
                        resp.status_code, resp.text[:200])
            return None
        data = resp.json()
        content = (data.get("choices") or [{}])[0] \
            .get("message", {}).get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
    except requests.exceptions.RequestException as exc:
        log.warning("Phase proxy request failed: %s", exc)
    except (json.JSONDecodeError, ValueError) as exc:
        log.warning("Phase proxy response parse error: %s", exc)
    return None


# ========================================================================
# LLM call — never raises, returns None on any failure
# ========================================================================


def _llm_configured():
    return bool(LLM_API_URL and LLM_API_KEY)


def call_llm(messages, temperature=0.2, max_tokens=900):
    """Call the OpenAI Chat Completions compatible endpoint (DeepSeek).

    Returns assistant text, or None on any failure (network, HTTP error,
    malformed response, missing config). Never raises.
    """
    if not _llm_configured():
        log.warning("LLM not configured (LLM_API_URL/LLM_API_KEY empty) — "
                    "rule-engine fallback will be used.")
        return None

    body = {
        "model": LLM_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    if not LLM_MODEL:
        body.pop("model")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LLM_API_KEY}",
    }

    for attempt in (1, 2):
        try:
            resp = requests.post(LLM_API_URL, json=body, headers=headers,
                                 timeout=90)
            if resp.status_code != 200:
                log.warning("LLM HTTP %s (attempt %d): %s",
                            resp.status_code, attempt, resp.text[:200])
                if attempt == 1:
                    time.sleep(2)
                    continue
                return None
            data = resp.json()
            content = (data.get("choices") or [{}])[0] \
                .get("message", {}).get("content")
            if isinstance(content, str) and content.strip():
                return content.strip()
            log.warning("LLM response missing choices[0].message.content "
                        "(attempt %d)", attempt)
        except requests.exceptions.RequestException as exc:
            log.warning("LLM request failed (attempt %d): %s", attempt, exc)
        except (json.JSONDecodeError, ValueError) as exc:
            log.warning("LLM response parse error (attempt %d): %s", attempt, exc)
        if attempt == 1:
            time.sleep(2)
    return None


# ========================================================================
# Phase determination — AI + rule fallback
# ========================================================================

# Keyword → phase rules used when the AI cannot judge. Mirrors the
# legacy STATUS_PATTERNS but finer-grained, one keyword set per phase.
# Rule 2 (phase from rules): the latest phase in lifecycle order wins.
_RULE_PHASE_KEYWORDS = {
    "Delivery": [
        "first oil", "first gas", "production start", "started production",
        "commenced production", "on stream", "onstream", "in operation",
        "operational", "delivered", "delivery", "sailaway", "sail away",
        "achieved first oil", "producing",
    ],
    "Commissioning": [
        "commissioning", "commissioned", "start-up", "startup",
        "hook-up", "hook up", "mechanical completion",
    ],
    "Construction": [
        "under construction", "construction", "being built", "building",
        "fabrication", "steel cut", "first steel", "keel laying",
        "hull launch", "topsides", "integration", "outfitting", "dry dock",
        "conversion", "yard",
    ],
    "Procurement": [
        "procurement", "purchasing", "purchase", "tender", "bid",
        "invitation to tender", "rfq", "request for quotation",
        "long-lead", "long lead", "materials order", "equipment order",
        "supply contract", "vendor registration",
    ],
    "EPC Award": [
        "epc contract", "epc award", "epcc", "contract awarded",
        "awarded contract", "fpso contract", "contract award",
        "letter of intent", "loi", "won contract", "secured contract",
        "agreement signed", "epcic",
    ],
    "Approval": [
        "approved", "approval", "final investment decision", "fid",
        "sanctioned", "sanction", "development consent", "consent granted",
        "permit granted", "license granted", "regulatory approval",
        "eia approved", "environmental approval", "环评", "批复", "核准",
    ],
    "Design": [
        "feed", "front-end engineering", "front end engineering",
        "detailed design", "engineering design", "pre-feed", "prefeed",
    ],
    "Planning": [
        "planned", "planning", "proposed", "development plan",
        "field development plan", "master plan", "pre-feasibility",
        "feasibility", "study", "eia", "environmental impact",
        "environmental assessment", "环评", "概念设计", "规划",
    ],
    "Concept": [
        "concept", "conceptual", "preliminary", "early-stage",
        "initial proposal", "under study", "envisaged", "mooted",
    ],
}


def infer_phase_from_rules(project, events_text=""):
    """Rule-based phase inference from project fields + event text.

    Scans combined text for per-phase keyword sets and returns the latest
    lifecycle phase with a match, or None when nothing matches.
    """
    text = " ".join(str(project.get(k) or "") for k in (
        "name", "summary", "procurement_chain", "application"))
    text = f"{text} {events_text}".lower()

    hits = []
    for phase, keywords in _RULE_PHASE_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            hits.append(phase)
    if not hits:
        return None
    return max(hits, key=lambda p: PHASE_ORDER[p])


def _stale_consent_delivery_override(project):
    """Deterministic date rule: a Consent Date / Production Start older
    than 10 years means the field is producing or abandoned — no new-build
    procurement. Overrides any AI phase of Approval/earlier with Delivery.
    Returns "Delivery" when the rule fires, else None."""
    summary = str(project.get("summary") or "")
    this_year = datetime.now(timezone.utc).year
    m = re.search(r"consent date:\s*(\d{4})", summary, re.IGNORECASE)
    if not m:
        m = re.search(r"production start:\s*(\d{4})", summary, re.IGNORECASE)
    if m and this_year - int(m.group(1)) > 10:
        return "Delivery"
    return None


def determine_project_phase(project, events_text=""):
    """Classify a project into one of the 9 lifecycle phases via the LLM
    (DeepSeek, through the /api/llm proxy when LLM_PROXY_URL is set).

    Args:
        project: dict with snake_case project fields (name, summary,
                 procurement_chain, ...).
        events_text: concatenated text of linked candidate_events
                     (summaries + evidence quotes).

    Returns (phase, reasoning, source) where source is "ai" or "rules";
    phase is None when neither can judge. Never raises.
    """
    # Fast path: decades-old consent date with no redevelopment signal —
    # deterministic Delivery, no LLM call needed.
    override = _stale_consent_delivery_override(project)
    if override and not re.search(
            r"replacement|redevelopment|refurbishment|new build|construction|"
            r"conversion|life extension|revital", events_text, re.IGNORECASE):
        return override, "stale consent date override", "rules"

    if _llm_configured() or LLM_PROXY_URL:
        prompt = _phase_prompt(project, events_text)
        messages = [
            {"role": "system",
             "content": "You are an oil & gas FPSO industry analyst. "
                        "Classify project lifecycle phases from facts only. "
                        "Never invent events."},
            {"role": "user", "content": prompt},
        ]
        reply = None
        if LLM_PROXY_URL:
            reply = _call_llm_via_proxy(messages)
        if reply is None and _llm_configured():
            reply = call_llm(messages, max_tokens=300)
        if reply is not None:
            obj = _extract_json_object(reply)
            if obj:
                phase = str(obj.get("phase") or "").strip()
                reasoning = str(obj.get("reasoning") or "").strip()[:300]
                if phase in PHASES_SET:
                    # Date-based sanity override: decades-old consent dates
                    # cannot be Approval — the field is producing/abandoned.
                    override = _stale_consent_delivery_override(project)
                    if override and PHASE_ORDER[phase] < PHASE_ORDER[override]:
                        return override, "stale consent date override", "rules"
                    return phase, reasoning, "ai"
                # LLM answered nothing usable — fall through to rules
                log.info("AI phase reply had no valid phase: %r", phase)

    phase = infer_phase_from_rules(project, events_text)
    if phase:
        override = _stale_consent_delivery_override(project)
        if override and PHASE_ORDER[phase] < PHASE_ORDER[override]:
            return override, "stale consent date override", "rules"
        return phase, "rule inference", "rules"
    return None, "", "none"


# ========================================================================
# Prompt building
# ========================================================================


def _build_prompt(article):
    title = (article.get("title") or "").strip()
    summary = (article.get("summary") or "").strip()
    pub_date = (article.get("publication_date") or "").strip()
    source = (article.get("source_name") or "").strip()

    lines = [
        "Article:",
        f"Title: {title}",
        f"Summary: {summary}",
        f"Publication date: {pub_date or '(unknown)'}",
        f"Source: {source}",
        "",
        "Extract ALL FPSO project events explicitly mentioned in this "
        "article. Return a JSON object with this exact shape:",
        '{"events": [{"project_name": "", "event_type": "", '
        '"publication_date": "", "evidence_quote": "", "summary": ""}]}',
        "",
        "Rules:",
        "1. project_name: the FPSO project name explicitly mentioned in the "
        "article (e.g. \"FPSO Bacalhau\", \"Johan Castberg\", "
        "\"FPSO Prosperity\"). Empty string if the article names no "
        "specific project. Do NOT guess or infer project names.",
        f"2. event_type: exactly one of {json.dumps(EVENT_TYPES)}. "
        "Classify the article's main FPSO activity concretely: contract "
        "awards and construction orders are CONTRACT_AWARDED or "
        "FPSO_CONTRACT_AWARDED, first oil / first gas / production start "
        "are FIRST_OIL or PRODUCTION_START, unit delivery is DELIVERED, "
        "etc. Use \"ARTICLE_MENTION\" ONLY when the article mentions an "
        "FPSO without any concrete project activity.",
        "3. publication_date: YYYY-MM-DD from the article only. Empty "
        "string when the article gives no date. Do NOT use today's date.",
        "4. evidence_quote: copy a sentence character-for-character from "
        "the Title or Summary above. Never invent, paraphrase, translate, "
        "or begin with \"The article...\". Empty string if nothing "
        "supports it.",
        "5. summary: one sentence summarizing the event in English, max "
        "50 words. Use the verbatim evidence_quote when possible.",
        "6. If the article mentions no FPSO project events at all, return "
        '{"events": []}.',
    ]
    return "\n".join(lines)


# ========================================================================
# Response parsing / validation
# ========================================================================


def _extract_json_object(text):
    """Pull the first {...} JSON object out of an LLM reply (tolerates
    markdown fences and stray prose)."""
    if not text:
        return None
    # Strip ```json ... ``` fences
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    start = text.find("{")
    if start < 0:
        return None
    # Walk brackets to find the balanced outermost object
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(text[start:i + 1])
                    return obj if isinstance(obj, dict) else None
                except (json.JSONDecodeError, ValueError):
                    return None
    return None


def _validate_event(raw):
    """Coerce one LLM event dict into a clean, DB-safe dict. Returns None
    when the dict has no usable content at all."""
    if not isinstance(raw, dict):
        return None

    project_name = str(raw.get("project_name") or "").strip()[:120]

    event_type = str(raw.get("event_type") or "").strip().upper()
    if event_type not in EVENT_TYPES_SET:
        event_type = "ARTICLE_MENTION"

    pub_date = str(raw.get("publication_date") or "").strip()
    pub_date = pub_date if DATE_RE.match(pub_date) else ""

    evidence = str(raw.get("evidence_quote") or "").strip()[:500]
    summary = str(raw.get("summary") or "").strip()[:500]

    # ARTICLE_MENTION with no project and no summary carries zero signal
    if not project_name and not summary and event_type == "ARTICLE_MENTION":
        return None

    return {
        "project_name": project_name,
        "event_type": event_type,
        "publication_date": pub_date,
        "evidence_quote": evidence,
        "summary": summary,
    }


def parse_events_from_llm(text):
    """Parse + validate the LLM JSON reply. Returns list of clean event
    dicts, possibly empty. Never raises."""
    obj = _extract_json_object(text)
    if obj is None:
        log.warning("LLM reply has no JSON object; treating as no events")
        return []
    events_raw = obj.get("events")
    if not isinstance(events_raw, list):
        return []
    events = []
    for raw in events_raw[:5]:  # hard cap: 5 events per article
        ev = _validate_event(raw)
        if ev:
            events.append(ev)
    return events


# ========================================================================
# Rule-engine fallback (mirrors adapters' extraction)
# ========================================================================


_RULE_LATE_KEYWORDS = {
    "PRODUCTION_START": ["first oil", "production start", "started production",
                         "commenced production", "achieved first oil"],
    "FIRST_OIL": ["first oil", "achieved first oil"],
    "DELIVERED": ["delivered", "sailaway", "sail away", "delivery",
                  "completed", "commissioned"],
}


def rule_engine_fallback(article):
    """Re-run the existing rule engine on the article (extract_project_info +
    status keyword mapping). Returns a single event dict, never raises.

    This is what adapters already do at crawl time; it upgrades rows where
    the LLM is unavailable and gives better project names for ARTICLE_MENTION
    rows whose project_name_raw fell back to the article title.
    """
    title = (article.get("title") or "").strip()
    summary = (article.get("summary") or "").strip()
    pub_date = (article.get("publication_date") or "").strip()
    if pub_date and not DATE_RE.match(pub_date):
        pub_date = ""

    project_name, _country, _phase = extract_project_info(title, summary)

    text_lower = f"{title} {summary}".lower()
    event_type = "ARTICLE_MENTION"
    for et, keywords in _RULE_LATE_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            event_type = et
            break

    return {
        "project_name": (project_name or "").strip()[:120],
        "event_type": event_type,
        "publication_date": pub_date,
        "evidence_quote": (summary or title)[:500],
        "summary": (summary or title)[:500],
    }


# ========================================================================
# Post-processing guards (LLM output cannot be trusted on its own)
# ========================================================================

_WS_RE = re.compile(r"\s+")


def _norm_ws(text):
    return _WS_RE.sub(" ", (text or "").strip()).lower()


def _quote_is_verbatim(quote, article):
    """True when the quote is a character-for-character substring of the
    article title or summary (whitespace-normalized). Short quotes are
    rejected: a 5-word overlap is noise, not evidence."""
    q = _norm_ws(quote)
    if len(q) < 20:
        return False
    for field in ("title", "summary"):
        if q in _norm_ws(article.get(field) or ""):
            return True
    return False


# Keyword → event type for upgrading lazy "ARTICLE_MENTION" replies. Only
# fires when the article text itself contains the keyword, mirroring the
# adapters' rule engine — never inventing an event the text does not state.
_UPGRADE_KEYWORDS = {
    "FPSO_CONTRACT_AWARDED": [
        "fpso contract", "fpso contracts", "fpso construction",
        "construction starts", "construction order", "hull construction",
    ],
    "CONTRACT_AWARDED": [
        "awarded", "contract", "order", "deal", "secured", "agreement",
        "feed", "taps", "purchase", "buy", "acquire",
    ],
    "FIRST_OIL": ["first oil", "first production"],
    "PRODUCTION_START": [
        "production start", "started production", "commenced production",
        "gas injection", "starts operating", "started operating",
        "start-up", "startup",
    ],
    "DELIVERED": [
        "delivered", "sailaway", "sail away", "delivery", "commissioned",
    ],
    "CONTRACT_ANNOUNCEMENT": ["announced", "extension"],
}


def _upgrade_event_type(article):
    """Upgrade ARTICLE_MENTION to a concrete type when the article text
    clearly states one. Returns the new type, or ARTICLE_MENTION when no
    keyword matches."""
    text = f"{article.get('title') or ''} {article.get('summary') or ''}".lower()
    for event_type, keywords in _UPGRADE_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return event_type
    return "ARTICLE_MENTION"


def _postprocess_events(events, article):
    """Enforce data-quality invariants the LLM cannot be trusted with:
    verbatim-only evidence quotes, and concrete event types for articles
    whose text clearly supports one (upgrades lazy ARTICLE_MENTION)."""
    cleaned = []
    for ev in events:
        quote = ev.get("evidence_quote") or ""
        if quote and not _quote_is_verbatim(quote, article):
            ev["evidence_quote"] = ""
        if ev["event_type"] == "ARTICLE_MENTION":
            ev["event_type"] = _upgrade_event_type(article)
        cleaned.append(ev)
    return cleaned


# ========================================================================
# Article payload helpers
# ========================================================================

# Trail markers appended by auto_classify — not article content, strip them.
_AUTO_TRAIL = re.compile(r"\n\[Auto-(?:accepted|rejected):[^\]]*\]")


def article_from_row(row):
    """Build the {title, summary, publication_date, source_name} input dict
    expected by the prompt from a candidate_events row.

    Adapters store the article title in evidence_quote (and often the same
    text in project_name_raw as a fallback), so title = evidence_quote.
    """
    evidence = (row.get("evidence_quote") or "").strip()
    evidence = _AUTO_TRAIL.sub("", evidence).strip()
    title = evidence or (row.get("project_name_raw") or "").strip()

    return {
        "title": title,
        "summary": (row.get("summary") or "").strip(),
        "publication_date": (row.get("publication_date") or "").strip(),
        "source_name": (row.get("source_name") or "").strip(),
        "source_url": (row.get("source_url") or "").strip(),
    }


def _already_exists(table, project_name, event_type, summary, exclude_id=None):
    """Dedup check mirroring insert_candidate_events(): same
    (project_name_raw, event_type, summary) already present?"""
    try:
        q = table.select("id") \
            .eq("project_name_raw", project_name) \
            .eq("event_type", event_type) \
            .eq("summary", summary)
        if exclude_id is not None:
            q = q.neq("id", exclude_id)
        resp = q.limit(1).execute()
        return bool(resp.data)
    except Exception:
        return False


# ========================================================================
# Main pipeline
# ========================================================================


def run_ai_extraction(supabase, rows, update_existing=True, polite_delay=0.3):
    """Run AI extraction over candidate_events rows and write events back.

    For each row:
      1. Skip rows whose event_type is already meaningful (not
         ARTICLE_MENTION/empty) — those were accepted by rules/humans.
      2. Call the LLM. On failure, fall back to rule_engine_fallback().
      3. Update the original row with the first extracted event, filling
         canonical_project_id via normalize_project_name().
      4. Insert any extra events as new pending rows (deduped).

    Returns stats dict:
      processed, ai_success, ai_no_event, ai_failed, updated,
      inserted, canonical_filled, examples (up to 3 sample events)
    """
    stats = {
        "processed": 0,
        "ai_success": 0,       # LLM call returned valid JSON
        "ai_no_event": 0,      # LLM returned {"events": []}
        "ai_failed": 0,        # LLM failure → rule fallback used
        "updated": 0,
        "inserted": 0,
        "canonical_filled": 0,
        "examples": [],
    }

    if not _llm_configured():
        log.warning("LLM not configured — running pure rule-engine fallback.")

    table = supabase.table("candidate_events")
    if not rows:
        return stats

    for i, row in enumerate(rows):
        cid = row.get("id")
        event_type = row.get("event_type") or ""
        if event_type not in REANALYZABLE_TYPES:
            continue
        if not cid:
            continue

        stats["processed"] += 1
        article = article_from_row(row)

        events = None
        if _llm_configured():
            prompt = _build_prompt(article)
            reply = call_llm([
                {"role": "system",
                 "content": "You are an oil & gas FPSO industry analyst. "
                            "Extract structured project events from news "
                            "articles. Only use facts explicitly stated in "
                            "the article."},
                {"role": "user", "content": prompt},
            ])
            if reply is not None:
                events = parse_events_from_llm(reply)
                stats["ai_success"] += 1
                if not events:
                    stats["ai_no_event"] += 1
                else:
                    events = _postprocess_events(events, article)
            else:
                stats["ai_failed"] += 1

        if events is None:
            # LLM unavailable or failed → rule engine fallback
            events = [rule_engine_fallback(article)]
            ai_named_project = False
        else:
            ai_named_project = True

        if not events:
            continue

        # ---- First event updates the original row ----
        first = events[0]
        project_name = first.get("project_name") or row.get("project_name_raw", "")
        if first.get("project_name"):
            project_name = first["project_name"]

        # canonical_project_id only from an AI-explicit project name. Junk
        # rule-engine names like "FPSO from Modec for" would otherwise
        # false-match a canonical project via token overlap.
        canonical_id = None
        if ai_named_project and first.get("project_name"):
            canonical_id = normalize_project_name(first["project_name"])

        if update_existing:
            update_payload = {
                "project_name_raw": project_name,
                "event_type": first["event_type"],
                "evidence_quote": first.get("evidence_quote")
                                  or row.get("evidence_quote", ""),
                "summary": first.get("summary") or row.get("summary", ""),
            }
            if first.get("publication_date"):
                update_payload["publication_date"] = first["publication_date"]
            if canonical_id:
                update_payload["canonical_project_id"] = canonical_id

            try:
                table.update(update_payload).eq("id", cid).execute()
                stats["updated"] += 1
                if canonical_id and not row.get("canonical_project_id"):
                    stats["canonical_filled"] += 1
            except Exception as exc:
                log.warning("  Update error (id=%s): %s", cid, exc)

        # ---- Extra events → new pending rows (deduped) ----
        for ev in events[1:]:
            ev_project = ev.get("project_name") or project_name
            ev_summary = ev.get("summary") or first.get("summary", "")
            if _already_exists(table, ev_project, ev["event_type"],
                               ev_summary, exclude_id=cid):
                continue
            # Same rule as above: canonical id only from an explicit name.
            ev_canonical = normalize_project_name(ev.get("project_name")) \
                if ev.get("project_name") else None
            try:
                table.insert({
                    "project_name_raw": ev_project,
                    "country": row.get("country", ""),
                    "summary": ev_summary,
                    "source_name": row.get("source_name", ""),
                    "source_url": row.get("source_url", ""),
                    "review_status": "pending",
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "event_type": ev["event_type"],
                    "evidence_quote": ev.get("evidence_quote", ""),
                    "publication_date": ev.get("publication_date", ""),
                    "canonical_project_id": ev_canonical,
                    "procurement_chain": row.get("procurement_chain", ""),
                }).execute()
                stats["inserted"] += 1
            except Exception as exc:
                log.warning("  Insert error for extra event (id=%s): %s",
                            cid, exc)

        # ---- Example capture (first 3 meaningful events) ----
        if len(stats["examples"]) < 3 and first.get("event_type") != "ARTICLE_MENTION":
            stats["examples"].append({
                "project": project_name,
                "event_type": first["event_type"],
                "publication_date": first.get("publication_date", ""),
                "summary": (first.get("summary") or "")[:100],
                "source": row.get("source_name", ""),
            })

        if (i + 1) % 20 == 0:
            log.info("  Progress: %d/%d processed, %d updated, %d inserted",
                     i + 1, len(rows), stats["updated"], stats["inserted"])
            time.sleep(polite_delay)

        time.sleep(polite_delay)

    return stats


def fetch_pending_reanalyzable(supabase, limit=500):
    """Fetch the most recent `limit` pending rows whose event_type is
    ARTICLE_MENTION/empty (safe to re-analyze)."""
    table = supabase.table("candidate_events")
    rows = []
    offset = 0
    # Supabase pages at 1000; pull up to 3 pages and filter client-side.
    while offset < 3000:
        resp = table.select("*") \
            .eq("review_status", "pending") \
            .order("id", desc=True) \
            .range(offset, offset + 999) \
            .execute()
        batch = resp.data or []
        if not batch:
            break
        rows.extend(r for r in batch
                    if (r.get("event_type") or "") in REANALYZABLE_TYPES)
        if len(batch) < 1000:
            break
        offset += 1000
        if len(rows) >= limit:
            break
    return rows[:limit]


def log_stats(stats):
    """Pretty-print extraction stats (shared by crawl and backfill modes)."""
    log.info("AI extraction stats: processed=%d | ai_success=%d | "
             "ai_no_event=%d | ai_failed=%d",
             stats["processed"], stats["ai_success"],
             stats["ai_no_event"], stats["ai_failed"])
    log.info("Writes: updated=%d rows, inserted=%d extra events, "
             "canonical_project_id filled=%d",
             stats["updated"], stats["inserted"], stats["canonical_filled"])
    for ex in stats["examples"]:
        log.info("  EXAMPLE: [%s] %s | %s | %s | %s",
                 ex["event_type"], ex["project"][:50],
                 ex["publication_date"] or "no-date",
                 ex["summary"][:80], ex["source"][:30])
