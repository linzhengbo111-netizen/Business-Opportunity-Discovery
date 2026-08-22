#!/usr/bin/env python3
"""
Backfill technical parameters from accepted events (gap-analysis P0-1).

projects.water_depth_m sits at ~3.7% so the AI material analysis has no
input. This tool enriches projects from their ACCEPTED candidate_events:

  Step 0  Linkage — accepted events with NULL canonical_project_id get it
          re-derived from project_name_raw via the alias registry
          (normalize_project_name). Mechanical, no text generation.
  Step 1  Per-event AI extraction — for every accepted event, one LLM
          call through the (extended) extractor prompt returns the FPSO
          project name plus the 7 tech fields (water_depth_m,
          oil_capacity_bpd, gas_capacity_mmcmd, field_name, operator_name,
          basin, hull_type) from the event text (summary + evidence_quote
          + raw_json snippet). Strict evidence rule: a field is kept only
          when its supporting quote appears verbatim in the input text
          (verified mechanically). Extracted values are written to the
          event row; the AI project name re-derives canonical_project_id
          for events that lack one.
  Step 2  Project roll-up — per canonical project, take the newest
          non-null value per field and write it to the projects row.
          Existing (non-null) project fields are never overwritten.

Priority order: pinned demo projects first (FPSO ALMIRANTE TAMANDARE /
BACALHAU / SEPETIBA), then battle-card-visible projects (known phase, not
Delivery/Commissioning, opportunity_score >= 55), then everything else.

Safety: dry run by default (--write to persist). Before the first write a
backup of the planned project/event updates is saved under
crawler/data/tech_events_backup_*.json.

Usage:
  python3 crawler/backfill_tech_from_events.py              # dry run
  python3 crawler/backfill_tech_from_events.py --write      # persist
  python3 crawler/backfill_tech_from_events.py --limit 50   # first N events
"""
import argparse
import json
import logging
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_SCRIPT_DIR)
for _d in (_SCRIPT_DIR, os.path.join(_SCRIPT_DIR, "adapters"), _ROOT_DIR):
    if _d not in sys.path:
        sys.path.insert(0, _d)

from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(_ROOT_DIR, ".env"))
from supabase import create_client  # noqa: E402

from adapters.media_common import normalize_project_name  # noqa: E402
from ai_event_extractor import (  # noqa: E402
    call_llm, _build_prompt, _postprocess_events, parse_events_from_llm,
)
from backfill_tech_params import _event_text, _fetch_all_paged  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("tech-events-backfill")

TECH_FIELDS = ("water_depth_m", "oil_capacity_bpd", "gas_capacity_mmcmd",
               "field_name", "operator_name", "basin", "hull_type")
PINNED = ("FPSO ALMIRANTE TAMANDARE", "FPSO BACALHAU", "FPSO SEPETIBA")
BATTLE_EXCLUDED_PHASES = {"Delivery", "Commissioning"}
MIN_EVENT_TEXT = 40          # below this, no useful LLM input
POLITE_DELAY = 0.25          # seconds between LLM calls


def pinned_rank(name):
    """Index in PINNED (0-2), or -1 when the project is not pinned."""
    upper = (name or "").upper()
    for i, pinned in enumerate(PINNED):
        if pinned in upper:
            return i
    return -1


def battle_card_eligible(p):
    """Mirror the 战报中心 gate: known phase, not Delivery/Commissioning,
    opportunity_score.totalScore >= 55. (Pinned exemption handled by
    group order.)"""
    phase = p.get("phase")
    if not phase or phase in BATTLE_EXCLUDED_PHASES:
        return False
    score = p.get("opportunity_score")
    if isinstance(score, dict):
        score = score.get("totalScore")
    return (score or 0) >= 55


def group_key(p, n_events):
    """0 = pinned, 1 = battle-card eligible, 2 = rest (incl. unlinked)."""
    if pinned_rank(p.get("name")) >= 0:
        return 0
    if battle_card_eligible(p):
        return 1
    return 2


def main():
    ap = argparse.ArgumentParser(
        description="Backfill tech params from accepted events")
    ap.add_argument("--write", action="store_true",
                    help="persist updates (default: dry run)")
    ap.add_argument("--limit", type=int, default=0,
                    help="only process the first N accepted events")
    ap.add_argument("--skip-link", action="store_true",
                    help="skip step 0 (event linkage)")
    args = ap.parse_args()

    sb = create_client(os.environ["VITE_SUPABASE_URL"],
                       os.environ["VITE_SUPABASE_ANON_KEY"])
    projects_table = sb.table("projects")
    events_table = sb.table("candidate_events")

    log.info("Loading projects + events ...")
    projects = _fetch_all_paged(
        projects_table,
        "id,name,phase,confidence,opportunity_score,"
        "water_depth_m,oil_capacity_bpd,gas_capacity_mmcmd,"
        "field_name,operator_name,basin,hull_type")
    events = _fetch_all_paged(
        events_table,
        "id,review_status,event_type,canonical_project_id,project_name_raw,"
        "publication_date,summary,evidence_quote,raw_json,source_url,"
        "water_depth_m,oil_capacity_bpd,gas_capacity_mmcmd,"
        "field_name,operator_name,basin,hull_type")
    log.info("Loaded %d projects, %d events", len(projects), len(events))

    accepted = [e for e in events if e.get("review_status") == "accepted"]
    log.info("Accepted events: %d (of which %d linked)",
             len(accepted),
             sum(1 for e in accepted if e.get("canonical_project_id")))

    # ---- Baseline stats (before) ----
    def fill_counts(rows):
        return {f: sum(1 for r in rows if r.get(f) not in (None, ""))
                for f in TECH_FIELDS}
    before_projects = fill_counts(projects)
    before_events = fill_counts(accepted)
    log.info("BEFORE projects: %s", before_projects)
    log.info("BEFORE accepted events: %s", before_events)

    # ---- Step 0: linkage ----
    link_count = 0
    if not args.skip_link:
        for ev in accepted:
            if ev.get("canonical_project_id"):
                continue
            cid = normalize_project_name(ev.get("project_name_raw") or "")
            if cid:
                link_count += 1
                ev["_new_canonical"] = cid
        log.info("Step 0 linkage: %d/%d unlinked accepted events re-linkable",
                 link_count,
                 sum(1 for e in accepted if not e.get("canonical_project_id")))

    # ---- Project indexes for group ordering and roll-up ----
    # candidate_events.canonical_project_id is the alias-registry SLUG
    # (e.g. "brazil-bacalhau") while projects.id is the numeric PK —
    # match through normalize_project_name(project.name).
    projects_by_id = {}
    slug_index = {}
    for p in projects:
        projects_by_id[p.get("id")] = p
        slug = normalize_project_name(p.get("name") or "")
        if slug:
            slug_index[slug] = p

    # ---- Order events: pinned projects first, then battle cards, then rest;
    # within a group, newest event first ----
    def event_cid(ev):
        return (ev.get("canonical_project_id") or ev.get("_new_canonical")
                or ev.get("_ai_canonical"))

    def project_for(ev):
        return slug_index.get(event_cid(ev) or "")

    def event_group(ev):
        p = project_for(ev)
        if not p:
            return 2
        return group_key(p, 0)

    def pinned_order(ev):
        p = project_for(ev)
        if not p:
            return 3
        rank = pinned_rank(p.get("name"))
        return rank if rank >= 0 else 3

    accepted.sort(key=lambda ev: (
        event_group(ev),
        pinned_order(ev),
        -(project_for(ev) is not None),
        -(int((ev.get("publication_date") or "").replace("-", "") or 0)),
        -int(ev.get("id") or 0),
    ))
    if args.limit:
        accepted = accepted[:args.limit]
    log.info("Processing %d accepted events", len(accepted))

    # ---- Backup before write ----
    if args.write:
        data_dir = os.path.join(_SCRIPT_DIR, "data")
        os.makedirs(data_dir, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = os.path.join(data_dir, f"tech_events_backup_{stamp}.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({
                "linked_events": [
                    {"id": e.get("id"),
                     "old_canonical": e.get("canonical_project_id"),
                     "new_canonical": e.get("_new_canonical")}
                    for e in accepted if e.get("_new_canonical")
                ],
            }, fh, ensure_ascii=False, indent=2)
        log.info("Backup written: %s", path)

    # ---- Step 0 write: linkage ----
    if args.write and link_count:
        written = 0
        for ev in accepted:
            cid = ev.get("_new_canonical")
            if not cid:
                continue
            try:
                events_table.update({"canonical_project_id": cid}) \
                    .eq("id", ev.get("id")).execute()
                written += 1
            except Exception as exc:
                log.warning("  link write error (event id=%s): %s",
                            ev.get("id"), exc)
        log.info("Step 0 write: %d/%d events linked", written, link_count)

    # ---- Step 1: per-event AI extraction (project name + tech params) ----
    # One LLM call per event through the (extended) extractor prompt:
    # it returns both the FPSO project name and the 7 tech fields with
    # verbatim evidence. Project names feed canonical linkage; tech fields
    # feed the project roll-up.
    stats = Counter()
    stats.update({"events_total": len(accepted), "text_too_short": 0,
                  "llm_failed": 0, "llm_empty": 0, "event_filled": 0,
                  "ai_linked": 0, "event_write_errors": 0})
    field_stats = Counter()
    examples = []
    _SYSTEM = ("You are an oil & gas FPSO industry analyst. Extract "
               "structured project events from news articles. Only use "
               "facts explicitly stated in the article.")

    for i, ev in enumerate(accepted):
        ev_id = ev.get("id")
        text = _event_text([ev])
        if len(text) < MIN_EVENT_TEXT:
            stats["text_too_short"] += 1
            continue
        # Article shape the extractor prompt expects; the raw_json text
        # rides inside summary so verbatim evidence checks can see it.
        article = {
            "title": (ev.get("evidence_quote") or "").strip(),
            "summary": text[:4000],
            "publication_date": (ev.get("publication_date") or "").strip(),
            "source_name": (ev.get("source_name") or "").strip(),
        }
        reply = call_llm([{"role": "system", "content": _SYSTEM},
                          {"role": "user",
                           "content": _build_prompt(article)}],
                         max_tokens=900)
        if not reply:
            stats["llm_failed"] += 1
            continue
        events = _postprocess_events(parse_events_from_llm(reply), article)
        if not events:
            stats["llm_empty"] += 1
            continue

        first = events[0]
        values = first.get("tech_params") or {}
        stats["event_filled"] += 1
        for f in values:
            field_stats[f] += 1
        ev["_tech"] = values
        if len(examples) < 10:
            examples.append(((ev.get("project_name_raw") or "?")[:45],
                             {f: v for f, v in values.items()}))

        # Linkage: prefer an AI-explicit project name, fall back to the
        # raw name. Never overwrite an existing canonical id.
        cid = None
        if first.get("project_name"):
            cid = normalize_project_name(first["project_name"])
        if not cid:
            cid = normalize_project_name(ev.get("project_name_raw") or "")
        if cid:
            ev["_ai_canonical"] = cid

        update_payload = dict(values)
        if cid and not ev.get("canonical_project_id"):
            update_payload["canonical_project_id"] = cid
            if first.get("project_name"):
                update_payload["project_name_raw"] = first["project_name"]
            stats["ai_linked"] += 1

        if args.write and update_payload:
            try:
                events_table.update(update_payload).eq("id", ev_id).execute()
            except Exception as exc:
                stats["event_write_errors"] += 1
                log.warning("  event update error (id=%s): %s", ev_id, exc)

        if (i + 1) % 50 == 0:
            log.info("  Progress: %d/%d | filled=%d linked=%d failed=%d "
                     "empty=%d",
                     i + 1, len(accepted), stats["event_filled"],
                     stats["ai_linked"], stats["llm_failed"],
                     stats["llm_empty"])
        time.sleep(POLITE_DELAY)

    log.info("Step 1 done: %s", dict(stats))
    log.info("Step 1 field extraction: %s", dict(field_stats))

    # ---- Step 2: project roll-up (newest-first, never overwrite) ----
    by_project = {}
    for ev in accepted:
        cid = event_cid(ev)
        if not cid or not ev.get("_tech"):
            continue
        by_project.setdefault(cid, []).append(ev)
    for lst in by_project.values():
        lst.sort(key=lambda e: ((e.get("publication_date") or ""),
                                int(e.get("id") or 0)),
                 reverse=True)

    project_updates = {}  # project id -> {field: value}
    for cid, evs in by_project.items():
        p = slug_index.get(cid)
        if not p:
            continue
        merged = {}
        for ev in evs:
            for f, v in ev["_tech"].items():
                if f not in merged:
                    merged[f] = v
        updates = {f: v for f, v in merged.items()
                   if p.get(f) in (None, "")}
        if updates:
            project_updates[p.get("id")] = updates

    log.info("Step 2: %d projects get tech params", len(project_updates))
    grouped = Counter()
    for pid in project_updates:
        p = projects_by_id.get(pid, {})
        grouped[("pinned" if pinned_rank(p.get("name")) >= 0
                 else "battle" if battle_card_eligible(p) else "other")] += 1
    log.info("Step 2 groups: %s", dict(grouped))

    if args.write:
        written = 0
        for pid, updates in project_updates.items():
            try:
                projects_table.update(updates).eq("id", pid).execute()
                written += 1
            except Exception as exc:
                log.warning("  project update error (id=%s): %s", pid, exc)
        log.info("Step 2 write: %d/%d projects updated",
                 written, len(project_updates))

    # ---- After stats (simulate applied updates on fetched rows) ----
    for pid, updates in project_updates.items():
        p = projects_by_id.get(pid)
        if p:
            p.update(updates)
    after_projects = fill_counts(projects)
    for ev in accepted:
        ev.update(ev.get("_tech") or {})
    after_events = fill_counts(accepted)
    log.info("=" * 56)
    log.info("TECH BACKFILL FROM EVENTS %s",
             "COMPLETE (writes persisted)" if args.write
             else "DRY RUN (nothing written)")
    log.info("BEFORE projects: %s", before_projects)
    log.info("AFTER  projects: %s", after_projects)
    for f in TECH_FIELDS:
        total = len(projects)
        log.info("  %-20s %d -> %d (%d%% -> %d%%)",
                 f, before_projects[f], after_projects[f],
                 before_projects[f] * 100 // total,
                 after_projects[f] * 100 // total)
    log.info("BEFORE accepted events: %s", before_events)
    log.info("AFTER  accepted events: %s", after_events)
    log.info("Events: linked=%d (step0=%d ai=%d) filled=%d (extraction: %s)",
             link_count + stats["ai_linked"], link_count,
             stats["ai_linked"], stats["event_filled"],
             dict(field_stats))
    log.info("Examples:")
    for name, vals in examples:
        log.info("  %-45s %s", name, vals)


if __name__ == "__main__":
    main()
