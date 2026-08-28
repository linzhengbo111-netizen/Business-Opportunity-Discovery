#!/usr/bin/env python3
"""
AI EPC Extractor — LLM-powered semantic extraction of procurement-chain
roles (EPC contractor, shipyard, owner/operator) for a project.

The rule engine (adapters.media_common.extract_procurement) misses ~47% of
real EPC mentions because it only matches a fixed entity dictionary inside a
160-char role window. This module replaces it as the PRIMARY extractor in
promote / auto-ingest: the LLM (DeepSeek via ai_event_extractor.call_llm)
reads the project profile + its linked candidate_events and returns
structured roles. The rule engine stays as the fallback when the LLM fails.

Safety (no hallucinated data):
  - Every company name is grounded verbatim (case-insensitive) in the source
    text before it is accepted; ungrounded names are dropped.
  - News outlets (Reuters, Bloomberg, ...) are never procurement entities;
    if the LLM returns one it lands in news_media, not in a role field.
  - When the source text carries no role evidence, fields stay null — the
    LLM is told explicitly never to fill from its own knowledge.

Call contract: extract_epc_with_ai() NEVER raises — returns None on any
LLM/config failure so the caller falls back to the rule engine.
"""

import json
import logging
import re
import sys
import os

# ---- Path hack (mirrors backfill_procurement_chains.py) -----------------
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_SCRIPT_DIR)
for _d in (_SCRIPT_DIR, os.path.join(_SCRIPT_DIR, "adapters"), _ROOT_DIR):
    if _d not in sys.path:
        sys.path.insert(0, _d)

from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(_ROOT_DIR, ".env"))

from adapters.media_common import (  # noqa: E402
    extract_procurement,
    is_news_media_name,
    normalize_project_name,
    sanitize_chain,
)
from ai_event_extractor import call_llm  # noqa: E402

log = logging.getLogger("ai-epc-extractor")

MAX_EVENTS = 20
MAX_SOURCE_CHARS = 8000

SYSTEM_PROMPT = (
    "You are a supply-chain analyst extracting companies from news snippets "
    "about one industrial project (FPSO, power plant, pulp mill, chemical "
    "plant, ...). Identify the companies holding these ROLES:\n"
    "- epc_contractor (EPC 总包商): the text says 'EPC contract awarded to "
    "X', 'X won EPC contract', 'engineering by X', 'built by X', 'X to "
    "build', or similar — X builds/engineers the project.\n"
    "- shipyard (船厂): the text says 'shipyard X', 'X shipyard', "
    "'constructed at X yard', or similar — X builds the hull/vessel.\n"
    "- owner_operator (业主/运营商): the text says 'operated by X', "
    "'operator X', 'field operator X', or similar — X owns/operates the "
    "asset.\n"
    "- news_media (新闻媒体): NEWS OUTLETS ONLY — the publishing outlets "
    "named in the text, e.g. Reuters, Bloomberg, Offshore Energy, "
    "OEDigital, World Oil, Splash247, Upstream, Rigzone, LNG Prime, "
    "Hydrocarbon Processing, Paper Advance, Sugar Online, Chemical Week, "
    "World Fertilizer, Pharmaceutical Technology, World Nuclear News, "
    "ThinkGeoEnergy, Mining.com, Global Water Intelligence. An outlet "
    "publishes other companies' news; it is never a project stakeholder. "
    "NEVER a procurement entity, NEVER a contact.\n"
    "RULES:\n"
    "1. Extract ONLY company names that appear verbatim in the snippets. "
    "Never invent, infer, complete, or translate a company name.\n"
    "2. A company without a role signal above does not qualify — return "
    "null for that role.\n"
    "3. Classify the snippet publisher '[source: X]' as news_media ONLY "
    "when X is an outlet-style publisher like the list above. COMPANY "
    "press releases (e.g. 'SBM Offshore', 'MODEC', 'Petrobras Agencia', "
    "'Equinor') are NOT outlets: never put them in news_media; they may "
    "be role entities when the text supports a role.\n"
    "4. If the snippets carry no evidence for a role, that field must be "
    "null. Do not fill from your own knowledge, do not guess.\n"
    "5. evidence must quote the source snippets WORD-FOR-WORD (one or two "
    "short verbatim sentences per role, separated by ' | '). Never "
    "paraphrase. If there is no evidence, evidence must be ''.\n"
    "6. confidence: 'high' when every extracted name is backed by a verbatim "
    "quote, 'medium' when at least one is, 'low' otherwise.\n"
    "7. Return JSON with this exact shape:\n"
    '{"epc_contractor": "Exact Name"|null, '
    '"shipyard": "Exact Name"|null, '
    '"owner_operator": "Exact Name"|null, '
    '"news_media": ["Outlet", ...], '
    '"confidence": "high"|"medium"|"low", '
    '"evidence": "verbatim quote(s) or empty", '
    '"reasoning": "one short sentence"}\n'
)


def _norm(text):
    """Whitespace-normalized lowercase for verbatim grounding checks."""
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def ground(entity_name, source_text):
    """Entity must appear verbatim (case-insensitive) in source text."""
    name = _norm(entity_name)
    if len(name) < 3:
        return False
    return name in _norm(source_text)


def build_source_text(events):
    """Concatenate event snippets into the LLM source text.

    Each event contributes its summary + evidence_quote; the source_name is
    attached so the LLM can tell publisher outlets from real companies.
    """
    parts = []
    for e in events or []:
        source = (e.get("source_name") or "").strip()
        header = f"[source: {source}]" if source else ""
        body = " ".join([
            (e.get("summary") or "").strip(),
            (e.get("evidence_quote") or "").strip(),
        ]).strip()
        if header or body:
            parts.append(f"{header} {body}".strip())
    return "\n".join(parts)[:MAX_SOURCE_CHARS]


def _parse_llm_json(raw):
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None


def extract_epc_with_ai(project, events):
    """LLM extraction of EPC/shipyard/owner-operator roles for one project.

    Args:
        project: dict with name, country, industry, procurement_chain
            (industry/procurement_chain may be absent).
        events: list of candidate_events rows (summary, evidence_quote,
            event_type, source_name), any order.

    Returns:
        dict with epc_contractor / shipyard / owner_operator (str|None),
        news_media (list[str]), confidence ('high'|'medium'|'low'),
        evidence (str), reasoning (str). All names grounded verbatim in the
        source text. Returns None when the LLM call or JSON parsing fails
        (caller falls back to the rule engine). Never raises.
    """
    events = (events or [])[:MAX_EVENTS]
    source = build_source_text(events)
    if not source.strip():
        return {
            "epc_contractor": None, "shipyard": None, "owner_operator": None,
            "news_media": [], "confidence": "low",
            "evidence": "", "reasoning": "no source text",
        }

    project_info = (
        f"- Name: {project.get('name') or '(unknown)'}\n"
        f"- Country: {project.get('country') or '(unknown)'}\n"
        f"- Industry: {project.get('industry') or '(unknown)'}\n"
        f"- Existing procurement chain: "
        f"{project.get('procurement_chain') or '(none)'}"
    )
    user = f"Project:\n{project_info}\n\nSnippets:\n{source}"

    raw = call_llm(
        [{"role": "system", "content": SYSTEM_PROMPT},
         {"role": "user", "content": user}],
        temperature=0.1, max_tokens=600,
    )
    if not raw:
        return None

    parsed = _parse_llm_json(raw)
    if not isinstance(parsed, dict):
        log.warning("EPC LLM bad JSON for %r: %.120s",
                    (project.get("name") or "?")[:40], raw)
        return None

    result = {
        "epc_contractor": None,
        "shipyard": None,
        "owner_operator": None,
        "news_media": [],
        "confidence": "low",
        "evidence": "",
        "reasoning": "",
    }

    # Ground every role name verbatim; news outlets are diverted to
    # news_media instead of any role field.
    for field in ("epc_contractor", "shipyard", "owner_operator"):
        name = (parsed.get(field) or "").strip()
        if not name:
            continue
        if is_news_media_name(name):
            result["news_media"].append(name)
            log.info("EPC LLM put news outlet in %s for %r — diverted: %s",
                     field, (project.get("name") or "?")[:40], name)
            continue
        if not ground(name, source):
            log.info("EPC LLM name not grounded for %r (%s): %s — dropped",
                     (project.get("name") or "?")[:40], field, name)
            continue
        result[field] = name

    # evidence must quote the source text verbatim — drop paraphrases.
    evidence = (parsed.get("evidence") or "").strip()
    evidence_ok = []
    if evidence:
        for quote in evidence.split("|"):
            quote = quote.strip().strip('"').strip()
            if len(quote) >= 10 and ground(quote, source):
                evidence_ok.append(quote)
    result["evidence"] = " | ".join(evidence_ok)

    # news_media from the LLM are only kept when they appear in the source
    # AND hit the authoritative outlet blacklist. The LLM sometimes
    # mislabels company press-release sources (e.g. 'SBM Offshore') as
    # media — those are dropped here and do not affect the role fields.
    for media in (parsed.get("news_media") or []):
        m = (media or "").strip()
        if (m and is_news_media_name(m) and ground(m, source)
                and m not in result["news_media"]):
            result["news_media"].append(m)

    result["reasoning"] = (parsed.get("reasoning") or "").strip()[:400]

    has_role = any(result[f] for f in
                   ("epc_contractor", "shipyard", "owner_operator"))
    if has_role and result["evidence"]:
        result["confidence"] = "high"
    elif has_role:
        result["confidence"] = "medium"
    else:
        result["confidence"] = "low"

    return result


def rule_chain_fallback(events):
    """Rule-engine fallback: stored per-event chains + extract_procurement.

    Returns a sanitized comma-separated chain string ('' when nothing).
    """
    names = []
    source_text = build_source_text(events)

    def add(part):
        if (len(part) >= 3 and not is_news_media_name(part)
                and part.lower() not in [n.lower() for n in names]):
            names.append(part)

    for e in events or []:
        for part in re.split(r"[,;]", e.get("procurement_chain") or ""):
            add(part.strip())
    if source_text:
        for part in re.split(r"[,;]", extract_procurement(source_text)):
            add(part.strip())
    return sanitize_chain(", ".join(names))


def sort_events_newest(events):
    def key(e):
        return (e.get("publication_date") or e.get("source_date")
                or e.get("fetched_at") or "")
    return sorted(events or [], key=key, reverse=True)


def fetch_linked_events(supabase, project_name, limit=MAX_EVENTS):
    """Fetch recent candidate_events linked to a project via canonical ID.

    Returns [] on any failure — never raises.
    """
    cid = normalize_project_name(project_name or "")
    if not cid or supabase is None:
        return []
    try:
        resp = supabase.table("candidate_events") \
            .select("summary,evidence_quote,event_type,publication_date,"
                    "source_name,procurement_chain") \
            .eq("canonical_project_id", cid) \
            .order("publication_date", desc=True) \
            .limit(limit).execute()
        return resp.data or []
    except Exception as exc:
        log.warning("linked events fetch error for %r: %s",
                    (project_name or "?")[:40], exc)
        return []


def extract_epc_chain(project, events, supabase=None, use_ai=True):
    """Primary entry for promote / auto-ingest.

    AI extraction first, rule engine as fallback (use_ai=False forces the
    rule engine — used by --skip-ai-epc). Returns:
    {
      "procurement_chain": str,   # EPC contractor + shipyard, comma-separated
      "owner_operator": str|None, # written to projects.operator_name when empty
      "source": "ai"|"rules",
      "confidence": "high"|"medium"|"low",
      "evidence": str,
      "reasoning": str,
    }
    Never raises.
    """
    linked = fetch_linked_events(supabase, project.get("name"))
    # Prefer DB-linked events (they include previously promoted rows); the
    # in-flight group events are added for brand-new projects not yet in DB.
    seen = set()
    merged = []
    for e in sort_events_newest(linked + list(events or [])):
        key = ((e.get("summary") or "").strip()[:80],
               (e.get("publication_date") or e.get("source_date") or ""),
               (e.get("source_name") or "").strip())
        if key in seen:
            continue
        seen.add(key)
        merged.append(e)
    event_list = merged[:MAX_EVENTS]

    ai = extract_epc_with_ai(project, event_list) if use_ai else None
    # Chain roles only decide success — an owner/operator alone is NOT a
    # procurement-chain entity, so the chain falls back to the rule engine
    # while the owner still surfaces via the owner_operator field.
    if ai and any(ai.get(f) for f in ("epc_contractor", "shipyard")):
        chain = sanitize_chain(", ".join(
            ai.get(f) for f in ("epc_contractor", "shipyard") if ai.get(f)))
        log.info("EPC AI extraction for %r: chain=%r owner=%r conf=%s "
                 "evidence=%.120r",
                 (project.get("name") or "?")[:40], chain,
                 ai.get("owner_operator"), ai.get("confidence"),
                 ai.get("evidence"))
        return {
            "procurement_chain": chain,
            "owner_operator": ai.get("owner_operator"),
            "source": "ai",
            "confidence": ai.get("confidence") or "medium",
            "evidence": ai.get("evidence") or "",
            "reasoning": ai.get("reasoning") or "",
        }

    chain = rule_chain_fallback(event_list)
    # An AI owner/operator is still surfaced even when the chain roles
    # came from the rule engine.
    owner = (ai or {}).get("owner_operator") if ai else None
    if ai:
        log.info("EPC AI found no chain role for %r (reason: %s, "
                 "owner=%r) — rules chain: %r",
                 (project.get("name") or "?")[:40],
                 ai.get("reasoning") or "no role evidence", owner, chain)
    else:
        log.info("EPC AI unavailable for %r — rules: %r",
                 (project.get("name") or "?")[:40], chain)
    return {
        "procurement_chain": chain,
        "owner_operator": owner,
        "source": "rules",
        "confidence": "low",
        "evidence": "",
        "reasoning": "",
    }
