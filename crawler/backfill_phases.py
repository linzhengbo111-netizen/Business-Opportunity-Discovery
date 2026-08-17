#!/usr/bin/env python3
"""
Phase backfill — AI lifecycle-phase classification for all projects.

Replaces the legacy 4-value status taxonomy (Under Construction / Planned /
Delivered / Unknown) with 9 standardized phases:
  Concept / Planning / Design / Approval / EPC Award / Procurement /
  Construction / Commissioning / Delivery

For every row in `projects`:
  1. Pull linked candidate_events text (summary + evidence_quote) via
     canonical_project_id.
  2. Call determine_project_phase() — LLM first (DeepSeek, optionally via
     the /api/llm Cloudflare Worker proxy), rule inference as fallback.
  3. Write the phase back to projects.phase. When neither AI nor rules can
     judge, phase stays NULL (待 AI 判断).

Safety:
  - Default is a DRY RUN (prints stats, writes nothing).
  - Before the first write, a local backup of (id, name, status/phase,
    summary) is saved under crawler/data/phase_backfill_backup_*.json —
    independent rollback path alongside the SQL backup table.
  - The projects table must already have the `phase` column (run
    migrations/025_replace_status_with_phase.sql first). Rows whose update
    fails (e.g. pre-migration schema) are counted, never fatal.

Usage:
  python3 crawler/backfill_phases.py                # dry run
  python3 crawler/backfill_phases.py --write        # persist updates
  python3 crawler/backfill_phases.py --limit 10     # demo subset
"""
import argparse
import json
import logging
import os
import sys
from collections import Counter
from datetime import datetime, timezone

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_SCRIPT_DIR)
for _d in (_SCRIPT_DIR, os.path.join(_SCRIPT_DIR, "adapters"), _ROOT_DIR):
    if _d not in sys.path:
        sys.path.insert(0, _d)

from dotenv import load_dotenv
load_dotenv(os.path.join(_ROOT_DIR, ".env"))
from supabase import create_client

from adapters.media_common import normalize_project_name  # noqa: E402
from ai_event_extractor import determine_project_phase  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("phase-backfill")

MAX_EVENTS_TEXT = 4000
PAGE_SIZE = 1000


def _fetch_all_paged(table, select):
    """Fetch every row of a supabase table, paging through .range()."""
    rows = []
    offset = 0
    while True:
        resp = table.select(select).range(offset, offset + PAGE_SIZE - 1) \
            .order("id", desc=False).execute()
        batch = resp.data or []
        rows.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return rows


def _backup_local(projects, write_mode):
    """Dump pre-backfill project rows to a local JSON file (rollback)."""
    if not write_mode:
        return
    data_dir = os.path.join(_SCRIPT_DIR, "data")
    os.makedirs(data_dir, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(data_dir, f"phase_backfill_backup_{stamp}.json")
    payload = [
        {"id": p.get("id"), "name": p.get("name"),
         "status": p.get("status"), "phase": p.get("phase"),
         "summary": p.get("summary")}
        for p in projects
    ]
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    log.info("Local backup written: %s (%d rows)", path, len(payload))


def run_phase_backfill(supabase, write=False, limit=0):
    """Classify phases for all projects and optionally write them back."""
    # Pre-migration the `phase` column does not exist yet — degrade the
    # select so a dry run still works.
    try:
        projects = _fetch_all_paged(
            supabase.table("projects"),
            "id,name,phase,summary,country,procurement_chain,"
            "operator_name,field_name,basin,application")
    except Exception as exc:  # 42703: column projects.phase does not exist
        log.warning("projects.phase unavailable (%s) — selecting legacy "
                    "columns only", str(exc)[:80])
        projects = _fetch_all_paged(
            supabase.table("projects"),
            "id,name,status,summary,country,procurement_chain,"
            "operator_name,field_name,basin,application")
    if limit:
        projects = projects[:limit]
    log.info("Loaded %d projects (write=%s)", len(projects), write)

    _backup_local(projects, write)

    events_table = supabase.table("candidate_events")
    projects_table = supabase.table("projects")

    stats = {
        "total": 0,
        "ai_matched": 0,
        "rules_matched": 0,
        "left_null": 0,
        "write_errors": 0,
        "distribution": Counter(),
        "examples": [],
    }

    for i, p in enumerate(projects):
        cid = normalize_project_name(p.get("name") or "")
        events_text = ""
        if cid:
            try:
                resp = events_table.select(
                    "summary,evidence_quote,event_type,publication_date"
                ).eq("canonical_project_id", cid) \
                 .order("publication_date", desc=True).limit(10).execute()
                parts = []
                for ev in (resp.data or [])[:5]:
                    for field in ("summary", "evidence_quote"):
                        val = (ev.get(field) or "").strip()
                        if val:
                            parts.append(val)
                events_text = " ".join(parts)[:MAX_EVENTS_TEXT]
            except Exception as exc:
                log.warning("  events fetch error for %s: %s",
                            p.get("name", "?")[:40], exc)

        phase, reasoning, source = determine_project_phase(p, events_text)
        stats["total"] += 1
        if phase:
            if source == "ai":
                stats["ai_matched"] += 1
            else:
                stats["rules_matched"] += 1
            stats["distribution"][phase] += 1
        else:
            stats["left_null"] += 1

        if len(stats["examples"]) < 5:
            stats["examples"].append({
                "name": (p.get("name") or "?")[:60],
                "phase": phase,
                "source": source,
                "reasoning": reasoning[:120],
            })

        if write and phase:
            try:
                projects_table.update({"phase": phase}) \
                    .eq("id", p.get("id")).execute()
            except Exception as exc:
                stats["write_errors"] += 1
                if stats["write_errors"] <= 3:
                    log.warning("  update error (id=%s): %s",
                                p.get("id"), exc)

        if (i + 1) % 25 == 0:
            log.info("  Progress: %d/%d | ai=%d rules=%d null=%d",
                     i + 1, len(projects), stats["ai_matched"],
                     stats["rules_matched"], stats["left_null"])

    return stats


def log_phase_stats(stats):
    """Pretty-print backfill stats (shared by script and crawl.py flag)."""
    log.info("=" * 56)
    log.info("PHASE BACKFILL %s",
             "COMPLETE (writes persisted)" if stats.get("_wrote")
             else "DRY RUN (nothing written)")
    log.info("total=%d | ai_matched=%d | rules_matched=%d | "
             "left_null=%d | write_errors=%d",
             stats["total"], stats["ai_matched"], stats["rules_matched"],
             stats["left_null"], stats["write_errors"])
    log.info("-" * 56)
    log.info("Phase distribution:")
    for phase, count in stats["distribution"].most_common():
        bar = "#" * min(60, max(1, int(count / max(1, stats["total"]) * 60)))
        log.info("  %-14s %4d  %s", phase, count, bar)
    if stats["left_null"]:
        log.info("  %-14s %4d  (pending AI judgment)", "NULL", stats["left_null"])
    log.info("-" * 56)
    log.info("Examples:")
    for ex in stats["examples"]:
        log.info("  [%s/%-5s] %-60s %s",
                 ex["phase"] or "NULL", ex["source"],
                 ex["name"], ex["reasoning"])


def main():
    ap = argparse.ArgumentParser(description="AI phase backfill for projects")
    ap.add_argument("--write", action="store_true",
                    help="persist phase updates (default: dry run)")
    ap.add_argument("--limit", type=int, default=0,
                    help="only process the first N projects (0 = all)")
    args = ap.parse_args()

    sb = create_client(os.environ["VITE_SUPABASE_URL"],
                       os.environ["VITE_SUPABASE_ANON_KEY"])
    stats = run_phase_backfill(sb, write=args.write, limit=args.limit)
    stats["_wrote"] = args.write
    log_phase_stats(stats)


if __name__ == "__main__":
    main()
