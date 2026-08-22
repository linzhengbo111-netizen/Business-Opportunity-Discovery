#!/usr/bin/env python3
"""
FPSO Project Crawler — orchestrator for all 15 adapters (P0/P1/P2).

Delegates scraping to individual adapters in crawler/adapters/:
  Tier 1 线索发现 (media):      offshore_energy, oe_digital, world_oil, splash247
  Tier 2 官方验证 (government):  anp_fpso_csv, anp_development_plan, guyana_epa,
                                 guyana_petroleum, nsta_fdp, equinor_rosebank
  Tier 3 采购链拆解 (contractor): modec_supplychain, sbm_newsroom
  Tier 4 商业入口 (supplier):     petrobras_supplier, petrofac_supplier, equinor_supplier

Also provides promote / backfill / auto-promote modes for the candidate_events
→ projects pipeline.

Usage:
  python crawler/crawl.py                  # run all 15 adapters
  python crawler/crawl.py --promote        # promote accepted candidates to projects
  python crawler/crawl.py --auto-promote   # auto-accept all pending + promote
  python crawler/crawl.py --backfill       # re-extract countries, write to candidate_events
  python crawler/crawl.py --backfill-source-urls  # fix placeholder URLs, write to candidate_events
  python crawler/crawl.py --ai-extract     # AI event extraction on recent 50 articles
  python crawler/crawl.py --ai-backfill    # AI event extraction on recent 500 pending rows

Data Flow (数据流向):
  Crawler → candidate_events → Manual Review → --promote → projects
"""

import os
import re
import sys
import time
import random

# ---- Path hack for imports ---------------------------------------------
# Allow running as: python crawler/crawl.py  (root + crawler/ both on path,
# so `from crawler.opportunity_scorer` and `from adapters.media_common` work).
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_SCRIPT_DIR)
for _d in (_SCRIPT_DIR, _ROOT_DIR):
    if _d not in sys.path:
        sys.path.insert(0, _d)

# S5 Opportunity Scoring Engine
from crawler.opportunity_scorer import score_opportunity
import logging
from datetime import datetime, timezone

from dotenv import load_dotenv
from supabase import create_client

from adapters.media_common import (  # noqa: E402
    normalize_project_name,
    get_display_name,
    extract_country,
    extract_project_info,
    extract_corrosive_media,
    country_to_flag,
)

from enricher import enrich_project, compute_enrichment_diff  # noqa: E402
from notifier import notify_subscribers, normalize_phase  # noqa: E402
from ai_event_extractor import (  # noqa: E402
    run_ai_extraction,
    fetch_pending_reanalyzable,
    log_stats,
    PHASES_SET,
)
from backfill_phases import run_phase_backfill, log_phase_stats  # noqa: E402

# Tier 1 — 线索发现 (media)
from adapters.offshore_energy import run_adapter as run_offshore_energy  # noqa: E402
from adapters.oe_digital import run_adapter as run_oe_digital  # noqa: E402
from adapters.world_oil import run_adapter as run_world_oil  # noqa: E402
from adapters.splash247 import run_adapter as run_splash247  # noqa: E402

# Tier 2 — 官方验证 (government P0)
from adapters.anp_fpso_csv import run_adapter as run_anp_fpso_csv  # noqa: E402
from adapters.anp_development_plan import run_adapter as run_anp_development_plan  # noqa: E402
from adapters.guyana_epa import run_adapter as run_guyana_epa  # noqa: E402
from adapters.guyana_petroleum import run_adapter as run_guyana_petroleum  # noqa: E402
from adapters.nsta_fdp import run_adapter as run_nsta_fdp  # noqa: E402
from adapters.equinor_rosebank import run_adapter as run_equinor_rosebank  # noqa: E402

# Tier 3 — 采购链拆解 (contractor)
from adapters.modec_supplychain import run_adapter as run_modec_supplychain  # noqa: E402
from adapters.sbm_newsroom import run_adapter as run_sbm_newsroom  # noqa: E402

# Tier 4 — 商业入口 (supplier portal)
from adapters.petrobras_supplier import run_adapter as run_petrobras_supplier  # noqa: E402
from adapters.petrofac_supplier import run_adapter as run_petrofac_supplier  # noqa: E402
from adapters.equinor_supplier import run_adapter as run_equinor_supplier  # noqa: E402

# ---- Config -----------------------------------------------------------

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("VITE_SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: SUPABASE_URL and SUPABASE_ANON_KEY must be set in .env")
    sys.exit(1)

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("fpso-crawler")

# ---- Adapter registry (15 adapters across 4 tiers) --------------------

ALL_ADAPTERS = [
    # Tier 1 — 线索发现 (media, daily high-frequency)
    ("Offshore Energy",    run_offshore_energy,    "P1", 1),
    ("OE Digital",         run_oe_digital,         "P1", 1),
    ("World Oil",          run_world_oil,          "P2", 1),
    ("Splash247",          run_splash247,          "P2", 1),
    # Tier 2 — 官方验证 (government P0, weekly-check cadence)
    ("ANP CSV",            run_anp_fpso_csv,       "P0", 2),
    ("ANP Dev Plan",       run_anp_development_plan, "P0", 2),
    ("Guyana EPA",         run_guyana_epa,         "P0", 2),
    ("Guyana Petroleum",   run_guyana_petroleum,   "P0", 2),
    ("NSTA FDP",           run_nsta_fdp,           "P0", 2),
    ("Equinor Rosebank",   run_equinor_rosebank,   "P0", 2),
    # Tier 3 — 采购链拆解 (contractor)
    ("MODEC Supply Chain", run_modec_supplychain,  "P0", 3),
    ("SBM Newsroom",       run_sbm_newsroom,       "P1", 3),
    # Tier 4 — 商业入口 (supplier portals)
    ("Petrobras Supplier", run_petrobras_supplier, "P0", 4),
    ("Petrofac Supplier",  run_petrofac_supplier,  "P1", 4),
    ("Equinor Supplier",   run_equinor_supplier,   "P1", 4),
]


# ========================================================================
# Auto-Classify: rule-based AI pre-screening for candidate_events
# ========================================================================

# Official event types that trigger auto-accept for P0 government sources
OFFICIAL_EVENTS = {
    "EIA_SUBMITTED",
    "DEVELOPMENT_CONSENT_GRANTED",
    "REGULATORY_DATA",
    "FPSO_CONTRACT_AWARDED",
    "DEVELOPMENT_PLAN_SUBMITTED",
    "DEVELOPMENT_PLAN_UPDATED",
    "PERMIT_GRANTED",
    "LICENSE_GRANTED",
    "FIELD_DEVELOPMENT_PLAN",
    "PRODUCTION_START",
    "FIRST_OIL",
    "VENDOR_REGISTRATION_ACTION",
    "PUBLIC_NOTICE",
    "CONTRACT_ANNOUNCEMENT",
}

# Financial/HR keywords that trigger auto-reject for tier-1 (media) sources
MEDIA_REJECT_KEYWORDS = [
    "stock",
    "share price",
    "dividend",
    "earnings",
    "appointment",
    "hiring",
    "quarterly results",
    "ceo ",
    "cfo ",
    "board member",
    "executive director",
    "revenue report",
    "market cap",
    "investor",
    "investment",
    "merger",
    "acquisition",
    "takeover",
    "layoff",
    "lay off",
    "fired",
    "personnel change",
    "management change",
]

# Map candidate_events source_name → source_registry source_name for fuzzy matching.
# Adapters write English display names; source_registry uses mixed Chinese/English.
SOURCE_NAME_ALIASES = {
    "NSTA Field Development Plans": "NSTA 开发计划",
    "Guyana EPA Oil & Gas Documents": "Guyana EPA",
    "Guyana Petroleum Management": "Guyana 石油管理计划",
    "Petrobras Supplier Registration": "Petrobras 供应商注册",
    "Equinor Supplier Information": "Equinor 供应商信息",
    "Petrofac Supplier Network": "Petrofac 供应商网络",
    "MODEC Supply Chain News": "MODEC Supply Chain",
    "SBM Offshore Newsroom": "SBM Offshore Newsroom",
    "Equinor Rosebank Public Notices": "Equinor Rosebank 公告",
}

# Noise patterns: candidate names that are clearly NOT FPSO projects.
# Person names (First Last format), pure admin permits, etc.
NOISE_NAME_PATTERNS = [
    # Person name pattern: two capitalized words that look like a human name
    # (matched via heuristics in the classify loop)
]

# summary must contain at least one of these to pass Rule B (FPSO relevance check)
FPSO_RELEVANCE_KEYWORDS = [
    "fpso", "offshore", "oil", "gas", "petroleum", "subsea",
    "upstream", "lng", "flng", "platform", "drilling", "deepwater",
    "field development", "production", "exploration",
]


def _lookup_source(source_name, sources):
    """Resolve candidate_events source_name to source_registry entry.

    Tries exact match first, then SOURCE_NAME_ALIASES, then substring match.
    Returns (matched_name, source_info_dict).
    """
    # 1) Exact match
    if source_name in sources:
        return source_name, sources[source_name]

    # 2) Alias lookup (fixes NSTA / Guyana EPA name mismatch)
    aliased = SOURCE_NAME_ALIASES.get(source_name, "")
    if aliased and aliased in sources:
        return aliased, sources[aliased]

    # 3) Substring match: candidate name contains registry name or vice versa
    for reg_name, info in sources.items():
        if reg_name in source_name or source_name in reg_name:
            return reg_name, info

    return source_name, {}


def _is_noise(project_name_raw, summary, source_name, event_type):
    """Return (is_noise: bool, reason: str)."""
    pn = (project_name_raw or "").strip()
    s = (summary or "").lower()
    et = (event_type or "").strip()

    # Person name heuristic: title-case "First Last" with <=3 words,
    # no FPSO/oil/gas/offshore keywords anywhere.
    words = pn.split()
    has_oil_kw = any(kw in s for kw in FPSO_RELEVANCE_KEYWORDS)
    if (2 <= len(words) <= 3
            and all(w and w[0].isupper() and w[1:].islower() for w in words if len(w) > 1)
            and not has_oil_kw
            and "fpso" not in pn.lower()
            and "permit" not in pn.lower()):
        return True, f"Person name pattern: '{pn}'"

    # Environmental permit without FPSO relevance
    if ("environmental permit" in pn.lower()
            or "environmental permit" in s
            or et == "PERMIT_GRANTED"):
        if not has_oil_kw:
            return True, f"Non-FPSO permit: '{pn[:60]}'"

    # Generic noise patterns
    if et == "PERMIT_GRANTED" and not has_oil_kw:
        return True, f"PERMIT_GRANTED without FPSO keywords"

    return False, ""


def auto_classify(supabase):
    """
    Rule-based auto-classification of pending candidate_events.

    Runs AFTER all adapters finish crawling. No external API calls.

    Rule A (auto_accepted): source priority='P0' (any event_type).
        Reasoning: government sources are authoritative; accept all P0 data.

    Rule B (auto_rejected): tier-1 media source whose summary does NOT
        contain FPSO-relevant keywords (fpso/offshore/oil/gas/etc.).
        Reasoning: media articles without these terms are not FPSO signal.

    Rule C (auto_rejected): project_name_raw looks like a person name,
        or is a non-FPSO environmental permit.

    Rule D (pending): everything else — needs human review.
    """
    log.info("=" * 54)
    log.info("AUTO-CLASSIFY MODE: rule-based AI pre-screening")
    log.info("=" * 54)

    candidate_table = supabase.table("candidate_events")
    source_table = supabase.table("source_registry")

    # Fetch ALL pending candidates (handle pagination via large limit).
    # Supabase default page size is 1000; use range queries for >1000 rows.
    all_candidates = []
    offset = 0
    while True:
        resp = candidate_table.select("*") \
            .eq("review_status", "pending") \
            .order("id") \
            .range(offset, offset + 999) \
            .execute()
        batch = resp.data or []
        if not batch:
            break
        all_candidates.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000

    if not all_candidates:
        log.info("No pending events to auto-classify.")
        return {"auto_accepted": 0, "auto_rejected": 0, "pending": 0,
                "noise_rejected": 0}

    candidates = all_candidates
    log.info("Pending candidates to classify: %d", len(candidates))

    # Fetch source_registry for priority / tier lookup
    src_resp = source_table.select("*").execute()
    sources = {}
    for s in (src_resp.data or []):
        sources[s.get("source_name", "")] = s

    auto_accepted = 0
    auto_rejected = 0
    noise_rejected = 0
    still_pending = 0

    for c in candidates:
        source_name = c.get("source_name", "")
        matched_name, source_info = _lookup_source(source_name, sources)
        priority = source_info.get("priority", "")
        tier = source_info.get("tier", 1)
        event_type = c.get("event_type", "") or ""
        summary = (c.get("summary", "") or "").lower()
        project_name_raw = c.get("project_name_raw", "") or ""
        evidence = c.get("evidence_quote", "") or ""
        cid = c.get("id")

        if not cid:
            still_pending += 1
            continue

        classified = False

        # ---- Rule C: noise filter (run first to catch before accept) ----
        # DB constraint allows only pending/accepted/rejected — use 'rejected'.
        is_noise, noise_reason = _is_noise(project_name_raw, summary,
                                           source_name, event_type)
        if is_noise:
            trail = f"\n[Auto-rejected: Noise — {noise_reason}]"
            new_evidence = (evidence + trail) if evidence else trail.strip()
            try:
                candidate_table.update({
                    "review_status": "rejected",
                    "evidence_quote": new_evidence,
                }).eq("id", cid).execute()
                noise_rejected += 1
                classified = True
                log.debug("  NOISE_REJECTED: %s | %s",
                          project_name_raw[:40], noise_reason[:60])
            except Exception as exc:
                log.warning("  Noise reject update error (id=%s): %s", cid, exc)

        # ---- Rule A: P0 source → auto-accept (relaxed: any event_type) ----
        # DB constraint allows only pending/accepted/rejected — use 'accepted'.
        if not classified and priority == "P0":
            trail = "\n[Auto-accepted: Government source (P0)]"
            new_evidence = (evidence + trail) if evidence else trail.strip()
            try:
                candidate_table.update({
                    "review_status": "accepted",
                    "evidence_quote": new_evidence,
                }).eq("id", cid).execute()
                auto_accepted += 1
                classified = True
                log.debug("  AUTO_ACCEPTED: %s | %s | P0 | matched_as=%s",
                          project_name_raw[:40], source_name, matched_name)
            except Exception as exc:
                log.warning("  Auto-accept update error (id=%s): %s", cid, exc)

        # ---- Rule E: publication_date before 2023-01-01 → auto-reject ----
        # Historical news (pre-2023) is noise for stainless-steel opportunity discovery.
        if not classified:
            pub_date = (c.get("publication_date", "") or "").strip()
            if pub_date and pub_date < "2023-01-01":
                trail = f"\n[Auto-rejected: Historical data (pub_date={pub_date} < 2023-01-01)]"
                new_evidence = (evidence + trail) if evidence else trail.strip()
                try:
                    candidate_table.update({
                        "review_status": "rejected",
                        "evidence_quote": new_evidence,
                    }).eq("id", cid).execute()
                    auto_rejected += 1
                    classified = True
                    log.debug("  AUTO_REJECTED (old): %s | %s | pub_date=%s",
                              project_name_raw[:40], source_name, pub_date)
                except Exception as exc:
                    log.warning("  Old-date reject update error (id=%s): %s", cid, exc)

        # ---- Rule B: media tier-1 without FPSO relevance → auto-reject ----
        if not classified and tier == 1:
            has_fpso_kw = any(kw in summary for kw in FPSO_RELEVANCE_KEYWORDS)
            has_fpso_kw = has_fpso_kw or "fpso" in project_name_raw.lower()
            if not has_fpso_kw:
                trail = "\n[Auto-rejected: Media source without FPSO-relevant keywords]"
                new_evidence = (evidence + trail) if evidence else trail.strip()
                try:
                    candidate_table.update({
                        "review_status": "rejected",
                        "evidence_quote": new_evidence,
                    }).eq("id", cid).execute()
                    auto_rejected += 1
                    classified = True
                    log.debug("  AUTO_REJECTED: %s | %s | no FPSO keywords",
                              project_name_raw[:40], source_name)
                except Exception as exc:
                    log.warning("  Auto-reject update error (id=%s): %s", cid, exc)

        # ---- Rule D: keep pending ----
        if not classified:
            still_pending += 1

    log.info("Auto-classify complete: %d auto_accepted, %d auto_rejected "
             "(%d noise), %d pending",
             auto_accepted, auto_rejected, noise_rejected, still_pending)
    return {"auto_accepted": auto_accepted, "auto_rejected": auto_rejected,
            "noise_rejected": noise_rejected, "pending": still_pending}


# ========================================================================
# Promote: accepted candidates → projects
# ========================================================================


def _derive_phase(candidate, source_info):
    """Derive project lifecycle phase for candidate_events rows that lack a
    'phase' column value.

    Uses source priority and event_type as signals:
      P0 + PRODUCTION_START / FIRST_OIL       → Delivery
      P0 + FPSO_CONTRACT_AWARDED              → EPC Award
      P0 + EIA_SUBMITTED / consent / permits  → Approval
      P0 + DEVELOPMENT_PLAN_*                 → Planning
      P0 + VENDOR_REGISTRATION_ACTION         → Procurement
      P0 (other)                              → Construction
      P1/P2                                   → Planning

    Returns a phase string suitable for the projects table.
    """
    priority = source_info.get("priority", "")
    event_type = (candidate.get("event_type", "") or "").strip()

    plan_stage = {"DEVELOPMENT_PLAN_SUBMITTED", "DEVELOPMENT_PLAN_UPDATED",
                  "FIELD_DEVELOPMENT_PLAN"}
    approval_stage = {"DEVELOPMENT_CONSENT_GRANTED", "PERMIT_GRANTED",
                      "LICENSE_GRANTED", "EIA_SUBMITTED",
                      "REGULATORY_DATA", "PUBLIC_NOTICE"}
    award_stage = {"FPSO_CONTRACT_AWARDED", "CONTRACT_ANNOUNCEMENT"}
    procurement_stage = {"VENDOR_REGISTRATION_ACTION"}
    late_stage = {"PRODUCTION_START", "FIRST_OIL", "DELIVERED"}

    if priority == "P0":
        if event_type in late_stage:
            return "Delivery"
        if event_type in plan_stage:
            return "Planning"
        if event_type in approval_stage:
            return "Approval"
        if event_type in award_stage:
            return "EPC Award"
        if event_type in procurement_stage:
            return "Procurement"
        return "Construction"
    return "Planning"


_LEGACY_STATUS_TO_PHASE = {
    "delivered": "Delivery",
    "completed": "Delivery",
    "under construction": "Construction",
    "planned": "Planning",
}


def _phase_of_candidate(c):
    """Read a phase from a candidate row, tolerating the legacy 'status'
    key and old status values."""
    raw = c.get("phase") or c.get("status")
    if not raw:
        return None
    stripped = str(raw).strip()
    if stripped in PHASES_SET:
        return stripped
    return _LEGACY_STATUS_TO_PHASE.get(stripped.lower())


def promote_accepted_candidates(supabase):
    """
    Move candidate_events rows with review_status IN ('accepted','auto_accepted')
    into projects table.

    Normalization + merge logic:
    1. For each accepted candidate, call normalize_project_name() to resolve
       the canonical project ID. If matched, use the canonical display name.
    2. Group candidates by their effective project name (canonical display name
       if matched, otherwise the raw project_name_raw as-is).
    3. For groups with multiple candidates, merge evidence_quote and summary
       fields — concatenate distinct info rather than creating duplicates.
    4. Upsert into projects table: match by 'name' column, update existing,
       insert new.

    Phase is derived from source priority + event_type since candidate_events
    has no native 'status' column (see _derive_phase).
    """
    log.info("=" * 54)
    log.info("PROMOTE MODE: moving accepted/auto_accepted candidates to projects")
    log.info("=" * 54)

    candidate_table = supabase.table("candidate_events")
    project_table = supabase.table("projects")
    source_table = supabase.table("source_registry")

    # Fetch source_registry for status derivation
    src_resp = source_table.select("*").execute()
    sources = {}
    for s in (src_resp.data or []):
        sources[s.get("source_name", "")] = s

    # Fetch ALL accepted candidates (handle pagination).
    # Note: DB constraint only allows pending/accepted/rejected.
    # Auto-classified records are stored as 'accepted' with trail markers.
    all_candidates = []
    for status_filter in ["accepted"]:
        offset = 0
        while True:
            resp = candidate_table.select("*") \
                .eq("review_status", status_filter) \
                .order("id") \
                .range(offset, offset + 999) \
                .execute()
            batch = resp.data or []
            if not batch:
                break
            all_candidates.extend(batch)
            if len(batch) < 1000:
                break
            offset += 1000

    if not all_candidates:
        log.info("No accepted/auto_accepted candidates to promote.")
        return 0, 0

    candidates = all_candidates
    log.info("Accepted + auto_accepted candidates: %d", len(candidates))

    # ---- Step 1: normalize and group candidates --------
    groups = {}       # group_key → [candidates]
    group_names = {}  # group_key → effective project name
    normalization_log = []

    for c in candidates:
        raw_name = c.get("project_name_raw", "")
        canonical_id = normalize_project_name(raw_name)

        if canonical_id:
            display_name = get_display_name(canonical_id)
            effective_name = display_name
            group_key = ("canonical", canonical_id)
            normalization_log.append((raw_name, canonical_id, display_name))
        else:
            effective_name = raw_name
            group_key = ("raw", raw_name)
            normalization_log.append((raw_name, None, raw_name))

        if group_key not in groups:
            groups[group_key] = []
            group_names[group_key] = effective_name
        groups[group_key].append(c)

    # Report normalization results
    matched = sum(1 for _, cid, _ in normalization_log if cid)
    log.info("Normalized: %d/%d → canonical IDs", matched, len(normalization_log))
    for raw, cid, display in normalization_log:
        if cid:
            log.info("  %s → [%s] %s", raw[:50], cid, display[:50])
        else:
            log.info("  %s → (no match, kept as-is)", raw[:50])

    # ---- Step 1b: write canonical_project_id back to candidate_events ----
    for c in candidates:
        raw_name = c.get("project_name_raw", "")
        canonical_id = normalize_project_name(raw_name)
        cid = c.get("id")
        if cid and canonical_id:
            try:
                candidate_table.update({
                    "canonical_project_id": canonical_id,
                }).eq("id", cid).execute()
            except Exception:
                log.debug("  Could not update canonical_project_id for id=%s",
                          cid, exc_info=True)

    # ---- Step 2: merge groups and upsert ----
    new = 0
    updated = 0

    for group_key, group in groups.items():
        effective_name = group_names[group_key]
        try:
            if len(group) == 1:
                c = group[0]
                merged_summary = c.get("summary", "")
                merged_source_name = c.get("source_name", "")
                merged_source_url = c.get("source_url", "")
                merged_source_date = c.get("source_date", "")
                merged_country = c.get("country", "")
                merged_flag = c.get("flag", "")
                # Derive phase: candidate_events may carry a phase column
                # (post-migration) or only event_type signals.
                merged_phase = _phase_of_candidate(c)
                if not merged_phase:
                    src_name = c.get("source_name", "")
                    matched_name, src_info = _lookup_source(src_name, sources)
                    merged_phase = _derive_phase(c, src_info)
            else:
                # Multiple candidates for the same project — merge
                summaries = [c.get("summary", "") for c in group if c.get("summary")]
                merged_summary = max(summaries, key=len) if summaries else ""

                seen_summaries = {merged_summary}
                for c in group:
                    s = c.get("summary", "")
                    if s and s not in seen_summaries and len(s) > 20:
                        if s not in merged_summary:
                            merged_summary += " | " + s
                            seen_summaries.add(s)

                # Source: use most recent date
                dated = sorted(
                    [c for c in group if c.get("source_date")],
                    key=lambda x: x.get("source_date", ""),
                    reverse=True,
                )
                best = dated[0] if dated else group[0]
                merged_source_name = best.get("source_name", "")
                merged_source_url = best.get("source_url", "")
                merged_source_date = best.get("source_date", "")

                # Country: most common value
                countries = [c.get("country", "") for c in group if c.get("country")]
                if countries:
                    merged_country = max(set(countries), key=countries.count)
                else:
                    merged_country = ""

                # Phase: derive from best candidate (most recent source_date)
                merged_phase = _phase_of_candidate(best)
                if not merged_phase:
                    src_name = best.get("source_name", "")
                    matched_name, src_info = _lookup_source(src_name, sources)
                    merged_phase = _derive_phase(best, src_info)
                merged_flag = best.get("flag", "")

                log.info("  Merging %d candidates → %s", len(group), effective_name[:60])

            project_data = {
                "name": effective_name,
                "country": merged_country,
                "flag": merged_flag,
                "phase": merged_phase,
                "summary": merged_summary[:2000],
                "source_name": merged_source_name,
                "source_url": merged_source_url,
                "source_date": merged_source_date,
                "stainless_steel": group[0].get("stainless_steel", ""),
                "application": group[0].get("application", ""),
                "procurement_chain": group[0].get("procurement_chain", ""),
                "water_depth_m": group[0].get("water_depth_m"),
                "oil_capacity_bpd": group[0].get("oil_capacity_bpd"),
                "gas_capacity_mmcmd": group[0].get("gas_capacity_mmcmd"),
                "hull_type": group[0].get("hull_type", ""),
                "field_name": group[0].get("field_name", ""),
                "operator_name": group[0].get("operator_name", ""),
                "basin": group[0].get("basin", ""),
            }

            # ---- Skip Delivered projects with old dates (pre-2023 noise) ----
            existing = project_table.select("id, phase").eq("name", effective_name).execute()
            existing_phase = ""
            if existing.data:
                existing_phase = existing.data[0].get("phase", "") or existing.data[0].get("status", "")
            # Skip if already Delivered in projects table and candidate date is old
            if existing_phase == "Delivery" and merged_source_date < "2023-01-01":
                log.info("  SKIP (Delivered + old date): %s | %s",
                         effective_name[:60], merged_source_date)
                continue

            if existing.data:
                project_table.update(project_data).eq("name", effective_name).execute()
                updated += 1
                log.info("  UPDATED: %s", effective_name[:60])
            else:
                project_table.insert(project_data).execute()
                new += 1
                log.info("  NEW: %s", effective_name[:60])

        except Exception:
            log.warning("  Promote error: %s", effective_name[:60], exc_info=True)

    log.info("Promote complete: %d new, %d updated (from %d candidates in %d groups)",
             new, updated, len(candidates), len(groups))
    return new, updated


# ========================================================================
# Backfill: re-extract countries for Unknown entries
# ========================================================================


def backfill_unknown_countries(supabase):
    """Query projects with empty/null country, re-extract from name+summary,
    and insert corrected records into candidate_events (not projects directly).
    Use --promote to move accepted candidates to projects after review."""
    log.info("=" * 54)
    log.info("BACKFILL MODE: re-extracting countries for Unknown entries")
    log.info("=" * 54)

    project_table = supabase.table("projects")
    candidate_table = supabase.table("candidate_events")

    resp = project_table.select("*").execute()
    if not resp.data:
        log.info("No projects in database.")
        return

    projects = resp.data
    log.info("Total projects in DB: %d", len(projects))

    unknown = [
        p for p in projects
        if not p.get("country") or p.get("country", "").strip() == ""
    ]

    log.info("Projects with missing country: %d", len(unknown))

    if not unknown:
        log.info("No unknown countries to backfill.")
        return

    inserted = 0
    for p in unknown:
        name = p.get("name", "")
        summary = p.get("summary", "")
        country = extract_country(name, summary)

        if country:
            log.info("  %s → %s", name[:60], country)
        else:
            log.info("  %s → still unknown", name[:60])
            continue

        try:
            candidate_table.insert({
                "project_name_raw": name,
                "country": country,
                "summary": summary[:500] if summary else "",
                "source_name": "(backfill-country)",
                "source_url": p.get("source_url", ""),
                "review_status": "accepted",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "event_type": "BACKFILL_COUNTRY",
                "evidence_quote": "",
                "publication_date": p.get("source_date", ""),
            }).execute()
            inserted += 1
        except Exception:
            log.warning("  Backfill insert error: %s", name[:60], exc_info=True)

    log.info("Backfill complete: %d candidate_events inserted.", inserted)


# ========================================================================
# Backfill: fix placeholder source URLs
# ========================================================================


def backfill_source_urls(supabase):
    """Search source sites for real article URLs and write to candidate_events."""
    log.info("=" * 54)
    log.info("BACKFILL-SOURCE-URLS MODE")
    log.info("=" * 54)
    log.info("This mode searches source sites for real article URLs.")
    log.info("Run the media adapters to populate candidate_events with article URLs.")
    log.info("backfill_source_urls not yet implemented for the new adapter architecture.")


# ========================================================================
# Auto-promote: auto-accept all pending + promote
# ========================================================================


def auto_promote_candidates(supabase):
    """Auto-accept all pending candidate_events, then promote to projects."""
    log.info("=" * 54)
    log.info("AUTO-PROMOTE MODE")
    log.info("=" * 54)

    candidate_table = supabase.table("candidate_events")

    # Count pending
    resp = candidate_table.select("*", count="exact").eq("review_status", "pending").execute()
    pending_count = resp.count if hasattr(resp, 'count') else len(resp.data or [])
    log.info("Pending candidates: %d", pending_count)

    if pending_count == 0:
        log.info("No pending candidates to auto-promote.")
        return 0, 0

    # Auto-accept all pending
    log.info("Auto-accepting all pending...")
    try:
        candidate_table.update({"review_status": "accepted"}) \
            .eq("review_status", "pending") \
            .execute()
        log.info("Auto-accepted %d candidates.", pending_count)
    except Exception:
        log.error("Failed to auto-accept candidates.", exc_info=True)
        return 0, 0

    # Promote
    return promote_accepted_candidates(supabase)


# ========================================================================
# Backfill canonical_project_id for existing candidate_events
# ========================================================================


def backfill_canonical_ids(supabase):
    """Backfill canonical_project_id for all candidate_events where it is NULL.

    Runs normalize_project_name() against project_name_raw and updates the
    canonical_project_id column. This is necessary for the frontend timeline
    views which filter candidate_events by canonical_project_id.
    """
    log.info("=" * 54)
    log.info("BACKFILL-CANONICAL-IDS: filling NULL canonical_project_id values")
    log.info("=" * 54)

    candidate_table = supabase.table("candidate_events")

    # Count total NULL rows
    count_resp = candidate_table.select("id", count="exact") \
        .is_("canonical_project_id", "null") \
        .execute()
    total_null = count_resp.count if hasattr(count_resp, 'count') else len(count_resp.data or [])
    log.info("Rows with NULL canonical_project_id: %d", total_null)

    if total_null == 0:
        log.info("Nothing to backfill.")
        return {"total": 0, "filled": 0, "unmatched": 0}

    # Fetch all NULL rows (paginated). Skip rejected rows: auto_classify
    # marks noise (old dates, person names, junk ANP pages) as 'rejected',
    # and those must never show up on a project timeline.
    all_null = []
    offset = 0
    while True:
        resp = candidate_table.select("id, project_name_raw, review_status") \
            .is_("canonical_project_id", "null") \
            .order("id") \
            .range(offset, offset + 999) \
            .execute()
        batch = resp.data or []
        if not batch:
            break
        all_null.extend(b for b in batch if b.get("review_status") != "rejected")
        if len(batch) < 1000:
            break
        offset += 1000

    filled = 0
    unmatched = 0

    for row in all_null:
        cid = row.get("id")
        raw_name = row.get("project_name_raw", "")
        canonical_id = normalize_project_name(raw_name)

        if cid and canonical_id:
            try:
                candidate_table.update({
                    "canonical_project_id": canonical_id,
                }).eq("id", cid).execute()
                filled += 1
                if filled % 50 == 0:
                    log.info("  Backfill progress: %d/%d filled", filled, len(all_null))
            except Exception:
                log.debug("  Backfill update error for id=%s", cid, exc_info=True)
                unmatched += 1
        else:
            unmatched += 1
            if raw_name:
                log.debug("  No match: '%s' (id=%s)", raw_name[:60], cid)

    log.info("Backfill complete: %d filled, %d unmatched (total %d)",
             filled, unmatched, len(all_null))
    return {"total": len(all_null), "filled": filled, "unmatched": unmatched}


# ========================================================================
# Crawl mode: run all 15 adapters
# ========================================================================


# ========================================================================
# Auto-Ingest: accepted candidates → projects (with confidence mapping)
# ========================================================================


def _confidence_from_priority(priority, event_type=""):
    """Map source priority + event_type to confidence label.

    P0 sources → 'high'
    P1 sources → 'medium' (bump to 'high' for official event types)
    P2 sources → 'low'  (bump to 'medium' for official event types)
    """
    et = (event_type or "").strip()
    is_official = et in OFFICIAL_EVENTS if et else False

    if priority == "P0":
        return "high"
    elif priority == "P1":
        return "high" if is_official else "medium"
    elif priority == "P2":
        return "medium" if is_official else "low"
    else:
        return "medium"


def _summary_hits_reject_keywords(summary, project_name_raw):
    """Check if a media (tier=1) candidate matches financial/HR noise keywords."""
    text = ((summary or "") + " " + (project_name_raw or "")).lower()
    return any(kw in text for kw in MEDIA_REJECT_KEYWORDS)


def _merge_corrosive_media(group):
    """Merge corrosive_media dicts from multiple candidates in a group.

    Boolean fields: OR logic (True if any candidate has it).
    details string: concatenate distinct snippets from all candidates.
    Returns JSON-serializable dict, or None if no candidate has any hits.
    """
    import json
    merged = {"h2s": False, "co2": False, "sour_service": False, "chloride": False}
    all_details = []

    for c in group:
        raw = c.get("corrosive_media")
        if not raw:
            continue
        # May be a JSON string or a dict
        if isinstance(raw, str):
            try:
                cm = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue
        elif isinstance(raw, dict):
            cm = raw
        else:
            continue

        if cm.get("h2s"):
            merged["h2s"] = True
        if cm.get("co2"):
            merged["co2"] = True
        if cm.get("sour_service"):
            merged["sour_service"] = True
        if cm.get("chloride"):
            merged["chloride"] = True
        if cm.get("details"):
            all_details.append(cm["details"])

    merged["details"] = " | ".join(all_details) if all_details else ""

    # Only return if at least one corrosive indicator is present
    if any([merged["h2s"], merged["co2"], merged["sour_service"], merged["chloride"]]):
        return json.dumps(merged)
    return None


def auto_ingest_to_projects(supabase, skip_enrich=False):
    """After auto_classify, upsert all accepted/auto_accepted candidates
    directly into projects table with AI confidence labels.

    - Maps confidence from source priority + event_type.
    - Skips media (tier=1) candidates that match REJECT_KEYWORDS.
    - Normalizes project names and merges duplicates.
    - Enriches projects by searching public web sources for missing tech specs
      (set skip_enrich=True to disable).
    """
    log.info("=" * 54)
    log.info("AUTO-INGEST: moving accepted candidates → projects")
    log.info("=" * 54)

    candidate_table = supabase.table("candidate_events")
    project_table = supabase.table("projects")
    source_table = supabase.table("source_registry")

    # Fetch source_registry for priority / tier / confidence lookup
    src_resp = source_table.select("*").execute()
    sources = {}
    for s in (src_resp.data or []):
        sources[s.get("source_name", "")] = s

    # Fetch ALL accepted candidates (paginated)
    all_candidates = []
    for status_filter in ["accepted"]:
        offset = 0
        while True:
            resp = candidate_table.select("*") \
                .eq("review_status", status_filter) \
                .order("id") \
                .range(offset, offset + 999) \
                .execute()
            batch = resp.data or []
            if not batch:
                break
            all_candidates.extend(batch)
            if len(batch) < 1000:
                break
            offset += 1000

    if not all_candidates:
        log.info("No accepted candidates to ingest.")
        return 0, 0, 0

    candidates = all_candidates
    log.info("Accepted candidates fetched: %d", len(candidates))

    # ---- Filter: skip media tier-1 with REJECT_KEYWORDS ----
    skipped_reject_kw = 0
    kept = []
    for c in candidates:
        source_name = c.get("source_name", "")
        matched_name, source_info = _lookup_source(source_name, sources)
        tier = source_info.get("tier", 1)
        summary = c.get("summary", "") or ""
        project_name_raw = c.get("project_name_raw", "") or ""

        if tier == 1 and _summary_hits_reject_keywords(summary, project_name_raw):
            skipped_reject_kw += 1
            log.debug("  SKIP (reject keyword): %s | %s",
                      project_name_raw[:50], source_name)
            # Mark as rejected in candidate_events so it won't be retried
            try:
                cid = c.get("id")
                if cid:
                    candidate_table.update({
                        "review_status": "rejected",
                    }).eq("id", cid).execute()
            except Exception:
                pass
            continue
        kept.append(c)

    if skipped_reject_kw:
        log.info("Skipped %d media candidates with financial/HR keywords.",
                 skipped_reject_kw)
    log.info("Candidates to ingest: %d", len(kept))

    if not kept:
        return 0, 0, skipped_reject_kw

    # ---- Group by canonical project name ----
    groups = {}       # group_key → [candidates]
    group_names = {}  # group_key → effective project name

    for c in kept:
        raw_name = c.get("project_name_raw", "")
        canonical_id = normalize_project_name(raw_name)

        if canonical_id:
            display_name = get_display_name(canonical_id)
            effective_name = display_name
            group_key = ("canonical", canonical_id)
        else:
            effective_name = raw_name
            group_key = ("raw", raw_name)

        if group_key not in groups:
            groups[group_key] = []
            group_names[group_key] = effective_name
        groups[group_key].append(c)

    # ---- Step 1b: write canonical_project_id back to candidate_events ----
    # Timeline queries on the frontend filter by canonical_project_id.
    # Without this backfill, newly ingested events have NULL canonical_project_id
    # and won't appear in any timeline view.
    for c in kept:
        raw_name = c.get("project_name_raw", "")
        canonical_id = normalize_project_name(raw_name)
        cid = c.get("id")
        if cid and canonical_id:
            try:
                candidate_table.update({
                    "canonical_project_id": canonical_id,
                }).eq("id", cid).execute()
            except Exception:
                log.debug("  Could not update canonical_project_id for id=%s",
                          cid, exc_info=True)

    # ---- Upsert each group into projects ----
    new_count = 0
    updated_count = 0
    notified_projects = []  # track new/updated projects for notification

    for group_key, group in groups.items():
        effective_name = group_names[group_key]
        try:
            # Merge logic
            if len(group) == 1:
                c = group[0]
                merged_summary = c.get("summary", "")
                merged_source_name = c.get("source_name", "")
                merged_source_url = c.get("source_url", "")
                merged_source_date = c.get("source_date", "")
                merged_country = c.get("country", "")
                merged_flag = c.get("flag", "")

                src_name = c.get("source_name", "")
                matched_name, src_info = _lookup_source(src_name, sources)
                priority = src_info.get("priority", "")
                event_type = c.get("event_type", "") or ""
                merged_phase = _derive_phase(c, src_info)
                confidence = _confidence_from_priority(priority, event_type)
            else:
                summaries = [c.get("summary", "") for c in group if c.get("summary")]
                merged_summary = max(summaries, key=len) if summaries else ""
                seen_summaries = {merged_summary}
                for c in group:
                    s = c.get("summary", "")
                    if s and s not in seen_summaries and len(s) > 20:
                        if s not in merged_summary:
                            merged_summary += " | " + s
                            seen_summaries.add(s)

                dated = sorted(
                    [c for c in group if c.get("source_date")],
                    key=lambda x: x.get("source_date", ""),
                    reverse=True,
                )
                best = dated[0] if dated else group[0]
                merged_source_name = best.get("source_name", "")
                merged_source_url = best.get("source_url", "")
                merged_source_date = best.get("source_date", "")

                countries = [c.get("country", "") for c in group if c.get("country")]
                if countries:
                    merged_country = max(set(countries), key=countries.count)
                else:
                    merged_country = ""

                merged_flag = best.get("flag", "")

                src_name = best.get("source_name", "")
                matched_name, src_info = _lookup_source(src_name, sources)
                priority = src_info.get("priority", "")
                event_type = best.get("event_type", "") or ""
                merged_phase = _derive_phase(best, src_info)
                confidence = _confidence_from_priority(priority, event_type)

                log.info("  Merging %d candidates → %s", len(group), effective_name[:60])

            project_data = {
                "name": effective_name,
                "country": merged_country,
                "flag": merged_flag,
                "phase": merged_phase,
                "summary": merged_summary[:2000],
                "source_name": merged_source_name,
                "source_url": merged_source_url,
                "source_date": merged_source_date,
                "stainless_steel": group[0].get("stainless_steel", ""),
                "application": group[0].get("application", ""),
                "procurement_chain": group[0].get("procurement_chain", ""),
                "water_depth_m": group[0].get("water_depth_m"),
                "oil_capacity_bpd": group[0].get("oil_capacity_bpd"),
                "gas_capacity_mmcmd": group[0].get("gas_capacity_mmcmd"),
                "hull_type": group[0].get("hull_type", ""),
                "field_name": group[0].get("field_name", ""),
                "operator_name": group[0].get("operator_name", ""),
                "basin": group[0].get("basin", ""),
                "confidence": confidence,
            }

            # ---- Merge corrosive_media from all candidates in group ----
            corrosive_merged = _merge_corrosive_media(group)
            if corrosive_merged:
                project_data["corrosive_media"] = corrosive_merged

            # ---- Skip Delivered projects with old dates (pre-2023 noise) ----
            existing = project_table.select("id, phase").eq("name", effective_name).execute()
            existing_phase = ""
            if existing.data:
                existing_phase = existing.data[0].get("phase", "") or existing.data[0].get("status", "")
            if existing_phase == "Delivery" and merged_source_date < "2023-01-01":
                log.info("  SKIP (Delivered + old date): %s | %s",
                         effective_name[:60], merged_source_date)
                continue

            # ---- Confidence guard: Delivery/Commissioning stay 'low' ----
            # Migration 016 downgraded delivered projects, but later auto-ingest
            # runs from P0 sources overwrote confidence back to 'high'. A
            # delivered/commissioning vessel is built — no procurement
            # opportunity — so P0 sources must NOT override the downgrade.
            if merged_phase in ("Delivery", "Commissioning") \
                    or existing_phase in ("Delivery", "Commissioning"):
                if confidence != "low":
                    log.info("  Confidence guard: forcing low for %s (phase=%s)",
                             effective_name[:60], merged_phase or existing_phase)
                    confidence = "low"
                    project_data["confidence"] = "low"
                # Never regress a terminal phase from a newer, weaker candidate.
                if existing_phase in ("Delivery", "Commissioning") \
                        and project_data.get("phase") not in ("Delivery", "Commissioning"):
                    log.info("  Phase guard: keeping %s (candidate suggested %s)",
                             existing_phase, project_data.get("phase"))
                    project_data["phase"] = existing_phase

            # ---- Enrich: search public sources for missing technical specs ----
            # Only runs when project has searchable keywords (name, operator, field, etc.)
            # and is missing at least one tech-spec field. Best-effort: errors are logged
            # but never block the ingest.
            if not skip_enrich and (not existing.data or existing_phase != "Delivery"):
                try:
                    has_keywords = any([
                        project_data.get("operator_name"),
                        project_data.get("field_name"),
                        project_data.get("basin"),
                    ])
                    missing_fields = any(
                        not project_data.get(f) or project_data.get(f) == ""
                        for f in ["water_depth_m", "oil_capacity_bpd",
                                  "gas_capacity_mmcmd", "hull_type",
                                  "field_name", "operator_name", "basin"]
                    )
                    if has_keywords and missing_fields:
                        log.info("  Enriching: %s", effective_name[:60])
                        enrichment = enrich_project(project_data, max_search_results=3, max_page_fetch=2)
                        diff = compute_enrichment_diff(project_data, enrichment.get("enriched", {}))
                        if diff:
                            project_data.update(diff)
                            log.info("  Enriched %d fields: %s", len(diff),
                                     ", ".join(f"{k}={v}" for k, v in diff.items()))
                        else:
                            log.debug("  Enrichment: no new fields found")
                except Exception:
                    log.debug("  Enrichment failed for %s", effective_name[:60], exc_info=True)

            # ---- S5 Opportunity Scoring ----
            try:
                opportunity_score = score_opportunity(project_data)
                project_data["opportunity_score"] = opportunity_score
                log.info("  Scored: total=%d grade=%s",
                         opportunity_score["totalScore"],
                         opportunity_score["grade"])
            except Exception:
                log.debug("  Scoring failed for %s", effective_name[:60], exc_info=True)

            if existing.data:
                # Push only when the phase actually changed. Summary/tech-spec
                # updates must NOT re-trigger a push for the same project.
                new_phase = normalize_phase(project_data.get("phase") or "")
                phase_changed = normalize_phase(existing_phase) != new_phase
                project_table.update(project_data).eq("name", effective_name).execute()
                updated_count += 1
                if phase_changed:
                    notified_projects.append(project_data)
                    log.info("  UPDATED (phase change %s → %s, notify): %s",
                             normalize_phase(existing_phase) or "-", new_phase or "-",
                             effective_name[:60])
                else:
                    log.info("  UPDATED (no phase change, no notify): %s",
                             effective_name[:60])
            else:
                project_table.insert(project_data).execute()
                new_count += 1
                notified_projects.append(project_data)
                log.info("  NEW: %s (confidence=%s)", effective_name[:60], confidence)

        except Exception:
            log.warning("  Ingest error: %s", effective_name[:60], exc_info=True)

    log.info("Auto-ingest complete: %d new, %d updated, %d skipped (from %d candidates in %d groups)",
             new_count, updated_count, skipped_reject_kw, len(kept), len(groups))

    # ---- Notify subscribers about new/updated projects ----
    if notified_projects:
        try:
            notifier_result = notify_subscribers(supabase, notified_projects)
            log.info("Notifier: %s", notifier_result)
        except Exception:
            log.warning("Notifier failed", exc_info=True)

    return new_count, updated_count, skipped_reject_kw


def run_all_adapters(dry_run=False, local_only=False, skip_classify=False,
                     skip_ingest=False, skip_enrich=False, anp_download=False,
                     skip_ai_extract=False, ai_extract_limit=50):
    """Run all 15 adapters sequentially with polite delays. Continue-on-error.
    After crawl: auto-classify pending, then auto-ingest into projects,
    then AI event extraction on newly crawled ARTICLE_MENTION rows.
    Use --skip-ingest to skip the projects ingest step.
    Use --skip-enrich to skip public web enrichment during ingest.
    Use --skip-ai-extract to skip the AI event extraction step."""
    log.info("=" * 54)
    log.info("FPSO Project Crawler — %s", TODAY)
    log.info("=" * 54)

    mode_str = "DRY-RUN" if dry_run else ("LOCAL-ONLY" if local_only else "FULL")
    log.info("Mode: %s | Adapters: %d", mode_str, len(ALL_ADAPTERS))

    all_results = []

    for i, (name, runner, priority, tier) in enumerate(ALL_ADAPTERS):
        log.info("=" * 54)
        log.info("[%d/%d] Running %s adapter (P%s / Tier %d)...",
                 i + 1, len(ALL_ADAPTERS), name, priority, tier)
        log.info("=" * 54)

        try:
            if name == "ANP Dev Plan":
                result = runner(dry_run=dry_run, local_only=local_only, skip_download=not anp_download)
            else:
                result = runner(dry_run=dry_run, local_only=local_only)
            all_results.append((name, result))
        except Exception:
            log.error("Adapter %s failed!", name, exc_info=True)
            all_results.append((name, {"error": "Adapter crashed", "total_articles": 0, "inserted": 0}))

        # Polite delay between adapters (except after last)
        if i < len(ALL_ADAPTERS) - 1:
            delay = random.uniform(2, 5)
            log.info("Sleeping %.1fs before next adapter...", delay)
            time.sleep(delay)

    # ---- Summary ----
    log.info("=" * 54)
    log.info("CRAWL SUMMARY")
    log.info("=" * 54)

    total_articles = 0
    total_inserted = 0
    errors = 0

    for name, result in all_results:
        articles = result.get("total_articles", 0)
        inserted = result.get("inserted", 0)
        error = result.get("error")
        if error:
            errors += 1
            status = f"ERROR: {error}"
        else:
            status = f"{articles} articles, {inserted} inserted"
        log.info("  %-20s → %s", name, status)
        total_articles += articles
        total_inserted += inserted

    log.info("  %-20s   %d articles, %d inserted (%d errors)",
             "TOTAL", total_articles, total_inserted, errors)
    log.info("Crawl complete.")

    unrecognized = sum(r.get("unrecognized", 0) for _, r in all_results)
    if unrecognized > 0:
        log.info("Unrecognized countries: %d article(s) — run with --promote after manual review.", unrecognized)

    # ---- Auto-classify newly inserted pending events ----
    if not skip_classify:
        log.info("")
        classify_result = auto_classify(supabase)
        log.info("")

        # ---- Auto-ingest accepted → projects ----
        if not skip_ingest:
            log.info("")
            ingest_result = auto_ingest_to_projects(supabase, skip_enrich=skip_enrich)
            log.info("")

    # ---- AI event extraction for newly crawled articles ----
    # Runs after classify/ingest: analyze the most recent pending
    # ARTICLE_MENTION rows with the LLM and write structured timeline
    # events (with canonical_project_id) back to candidate_events.
    # Falls back to the rule engine when the LLM call fails.
    if not skip_ai_extract:
        log.info("")
        log.info("=" * 54)
        log.info("AI EVENT EXTRACTION: analyzing recent articles")
        log.info("=" * 54)
        rows = fetch_pending_reanalyzable(supabase, limit=ai_extract_limit)
        if rows:
            stats = run_ai_extraction(supabase, rows)
            log_stats(stats)
        else:
            log.info("No recent ARTICLE_MENTION rows to analyze.")
        log.info("")


# ========================================================================
# CLI
# ========================================================================


def main():
    import argparse

    parser = argparse.ArgumentParser(description="FPSO Project Crawler")
    parser.add_argument(
        "--promote",
        action="store_true",
        help="Move accepted candidates from candidate_events to projects table.",
    )
    parser.add_argument(
        "--auto-promote",
        action="store_true",
        help="Auto-accept all pending candidates and promote to projects (no manual review).",
    )
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="Re-extract countries for Unknown entries and write to candidate_events.",
    )
    parser.add_argument(
        "--backfill-source-urls",
        action="store_true",
        help="Search source sites for real article URLs and write to candidate_events.",
    )
    parser.add_argument(
        "--crawl",
        action="store_true",
        default=False,
        help="Run normal crawl (default if no other mode specified).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Crawl all adapters without writing to Supabase.",
    )
    parser.add_argument(
        "--local-only",
        action="store_true",
        help="Save files locally only, no Supabase connection.",
    )
    parser.add_argument(
        "--auto-classify",
        action="store_true",
        help="Run auto-classification on all pending candidate_events (standalone).",
    )
    parser.add_argument(
        "--skip-classify",
        action="store_true",
        help="Skip auto-classification after crawl (use when testing).",
    )
    parser.add_argument(
        "--skip-ingest",
        action="store_true",
        help="Skip auto-ingest into projects after auto-classify (keep candidates for manual review).",
    )
    parser.add_argument(
        "--skip-enrich",
        action="store_true",
        help="Skip project enrichment (public web search for missing tech specs) during auto-ingest.",
    )
    parser.add_argument(
        "--anp-download",
        action="store_true",
        help="Enable ANP Dev Plan PDF download (disabled by default for speed).",
    )
    parser.add_argument(
        "--auto-ingest",
        action="store_true",
        help="Run auto-ingest on accepted candidates (standalone, no crawl).",
    )
    parser.add_argument(
        "--backfill-canonical-ids",
        action="store_true",
        help="Backfill NULL canonical_project_id on all candidate_events rows.",
    )
    parser.add_argument(
        "--ai-extract",
        action="store_true",
        help="Run AI event extraction on the most recent pending "
             "ARTICLE_MENTION rows (standalone, no crawl).",
    )
    parser.add_argument(
        "--ai-backfill",
        action="store_true",
        help="Run AI event extraction over the most recent 500 pending "
             "ARTICLE_MENTION rows (historical backfill).",
    )
    parser.add_argument(
        "--ai-limit",
        type=int,
        default=50,
        help="Max rows for --ai-extract (default 50). Ignored by --ai-backfill.",
    )
    parser.add_argument(
        "--skip-ai-extract",
        action="store_true",
        help="Skip the AI event extraction step after crawl.",
    )
    parser.add_argument(
        "--backfill-phases",
        action="store_true",
        help="AI-classify lifecycle phases for all projects and write "
             "projects.phase (requires migration 025 applied).",
    )
    args = parser.parse_args()

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    # Standalone auto-classify (no crawl)
    if args.auto_classify:
        result = auto_classify(supabase)
        log.info("Standalone auto-classify: %s", result)
        return

    # Standalone auto-ingest (no crawl)
    if args.auto_ingest:
        new, updated, skipped = auto_ingest_to_projects(supabase, skip_enrich=args.skip_enrich)
        log.info("Standalone auto-ingest: %d new, %d updated, %d skipped.",
                 new, updated, skipped)
        return

    # Backfill canonical_project_id for existing candidate_events
    if args.backfill_canonical_ids:
        result = backfill_canonical_ids(supabase)
        log.info("Backfill canonical IDs: %s", result)
        return

    # AI event extraction — standalone on recent pending ARTICLE_MENTION rows
    if args.ai_extract:
        log.info("AI EXTRACT MODE: analyzing %d recent articles", args.ai_limit)
        rows = fetch_pending_reanalyzable(supabase, limit=args.ai_limit)
        stats = run_ai_extraction(supabase, rows)
        log_stats(stats)
        return

    # AI event extraction — historical backfill (recent 500 pending rows)
    if args.ai_backfill:
        log.info("AI BACKFILL MODE: analyzing recent 500 pending rows")
        rows = fetch_pending_reanalyzable(supabase, limit=500)
        stats = run_ai_extraction(supabase, rows)
        log_stats(stats)
        return

    # Phase backfill — AI lifecycle classification for all projects
    if args.backfill_phases:
        log.info("PHASE BACKFILL MODE: classifying lifecycle phases "
                 "for all projects")
        stats = run_phase_backfill(supabase, write=True)
        stats["_wrote"] = True
        log_phase_stats(stats)
        return

    # Promote mode
    if args.promote:
        new, updated = promote_accepted_candidates(supabase)
        log.info("Promote complete: %d new, %d updated in projects.", new, updated)
        return

    # Auto-promote mode
    if args.auto_promote:
        new, updated = auto_promote_candidates(supabase)
        log.info("Auto-promote complete: %d new, %d updated in projects.", new, updated)
        return

    # Backfill modes
    if args.backfill_source_urls:
        backfill_source_urls(supabase)
        return

    if args.backfill:
        backfill_unknown_countries(supabase)
        return

    # Dry-run / local-only crawl
    if args.dry_run:
        run_all_adapters(dry_run=True, skip_classify=True)
        return

    if args.local_only:
        run_all_adapters(local_only=True, skip_classify=True)
        return

    # Normal crawl mode (default when no flag specified)
    run_all_adapters(skip_classify=args.skip_classify,
                     skip_ingest=args.skip_ingest,
                     skip_enrich=args.skip_enrich,
                     anp_download=args.anp_download,
                     skip_ai_extract=args.skip_ai_extract,
                     ai_extract_limit=args.ai_limit)


if __name__ == "__main__":
    main()
