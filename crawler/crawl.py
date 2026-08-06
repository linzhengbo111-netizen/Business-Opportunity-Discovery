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

Data Flow (数据流向):
  Crawler → candidate_events → Manual Review → --promote → projects
"""

import os
import re
import sys
import time
import random
import logging
from datetime import datetime, timezone

from dotenv import load_dotenv
from supabase import create_client

# ---- Path hack for adapter imports --------------------------------------
# Allow running as: python crawler/crawl.py  (crawler/ adapters/ are siblings)
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from adapters.media_common import (  # noqa: E402
    normalize_project_name,
    get_display_name,
    extract_country,
    extract_project_info,
    country_to_flag,
)

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
# Promote: accepted candidates → projects
# ========================================================================


def promote_accepted_candidates(supabase):
    """
    Move candidate_events rows with review_status='accepted' into projects table.

    Normalization + merge logic:
    1. For each accepted candidate, call normalize_project_name() to resolve
       the canonical project ID. If matched, use the canonical display name.
    2. Group candidates by their effective project name (canonical display name
       if matched, otherwise the raw project_name_raw as-is).
    3. For groups with multiple candidates, merge evidence_quote and summary
       fields — concatenate distinct info rather than creating duplicates.
    4. Upsert into projects table: match by 'name' column, update existing,
       insert new.

    This is the ONLY path by which data enters the projects table.
    """
    log.info("=" * 54)
    log.info("PROMOTE MODE: moving accepted candidates to projects")
    log.info("=" * 54)

    candidate_table = supabase.table("candidate_events")
    project_table = supabase.table("projects")

    resp = candidate_table.select("*").eq("review_status", "accepted").execute()
    if not resp.data:
        log.info("No accepted candidates to promote.")
        return 0, 0

    candidates = resp.data
    log.info("Accepted candidates: %d", len(candidates))

    # ---- Step 1: normalize and group candidates --------
    # Group by canonical_project_id when available (P0-4.1 fix).
    # Candidates that normalized to the same canonical ID are merged;
    # candidates that failed normalization are grouped by raw name only
    # and never merged with matched candidates (separate key namespace).
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
                merged_status = c.get("status", "Unknown")
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

                # Status: prioritize Delivered > Under Construction > Planned > Unknown
                statuses = [c.get("status", "Unknown") for c in group]
                status_priority = {"Delivered": 0, "Under Construction": 1, "Planned": 2, "Unknown": 3}
                merged_status = min(statuses, key=lambda s: status_priority.get(s, 99))
                merged_flag = best.get("flag", "")

                log.info("  Merging %d candidates → %s", len(group), effective_name[:60])

            project_data = {
                "name": effective_name,
                "country": merged_country,
                "flag": merged_flag,
                "status": merged_status,
                "summary": merged_summary[:2000],
                "source_name": merged_source_name,
                "source_url": merged_source_url,
                "source_date": merged_source_date,
                "stainless_steel": group[0].get("stainless_steel", ""),
                "application": group[0].get("application", ""),
            }

            existing = project_table.select("id").eq("name", effective_name).execute()
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

    log.info("Promote complete: %d new, %d updated (from %d accepted candidates in %d groups)",
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
# Crawl mode: run all 15 adapters
# ========================================================================


def run_all_adapters(dry_run=False, local_only=False):
    """Run all 15 adapters sequentially with polite delays. Continue-on-error."""
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
    args = parser.parse_args()

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

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
        run_all_adapters(dry_run=True)
        return

    if args.local_only:
        run_all_adapters(local_only=True)
        return

    # Normal crawl mode (default when no flag specified)
    run_all_adapters()


if __name__ == "__main__":
    main()
