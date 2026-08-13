#!/usr/bin/env python3
"""
Data quality cleanup — three phases.

Phase 1: noise projects (confidence -> 'low', no deletion)
  - name with file extension (.pdf/.csv/.xlsx/.zip/...)
  - person-like names (ALL-CAPS, <10 chars) — SKIPPED for NSTA-sourced rows:
    those are real UK fields (FORBES, GORDON, FORTIES... all NSTA Field
    Development Plans with Operator/Block summaries)
  - title-like text (len>80 or contains 'contract'/'earnings')

Phase 2: resurrect mis-rejected regulatory events
  - candidate_events: review_status='rejected' AND event_type IN
    (DEVELOPMENT_PLAN_SUBMITTED, DEVELOPMENT_CONSENT_GRANTED) AND
    source_name ilike NSTA/ANP -> dedup by (name, type, date, source),
    keep lowest id -> pending, then re-run auto_classify (Rule A P0 accepts
    before Rule E date check).

Phase 3: Tartaruga Verde
  - insert projects row (name/country/industry/confidence per spec)
  - accept the single deduped event + set canonical_project_id

Usage: python3 scripts/data_quality_cleanup.py [--apply]
Without --apply: dry run, prints what would change.
"""
import argparse
import json
import logging
import os
import re
import sys
from collections import Counter

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_SCRIPT_DIR)
for _d in (_SCRIPT_DIR, _ROOT_DIR, os.path.join(_ROOT_DIR, "crawler")):
    if _d not in sys.path:
        sys.path.insert(0, _d)

from dotenv import load_dotenv
load_dotenv(os.path.join(_ROOT_DIR, ".env"))
from supabase import create_client

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("data_quality_cleanup")

TARGET_EVENT_TYPES = ("DEVELOPMENT_PLAN_SUBMITTED", "DEVELOPMENT_CONSENT_GRANTED")
TARTARUGA_CANONICAL_ID = "brazil-tartaruga-verde"
AUTO_TRAIL = re.compile(r"\n\[Auto-(?:accepted|rejected)[^\]]*\]\s*$")
FILE_EXT_RE = re.compile(r"\.(pdf|csv|xlsx|xls|zip|docx?|txt|json)\b", re.I)
PERSON_LIKE_RE = re.compile(r"^[A-Z][A-Z .&/-]{0,9}$")
TITLE_JUNK_RE = re.compile(r"contract|earnings", re.I)


def get_client():
    return create_client(os.environ["VITE_SUPABASE_URL"],
                         os.environ["VITE_SUPABASE_ANON_KEY"])


def fetch_all(query):
    rows, offset = [], 0
    while True:
        resp = query.range(offset, offset + 999).execute()
        rows.extend(resp.data or [])
        if len(resp.data or []) < 1000:
            break
        offset += 1000
    return rows


def update(sb, table, row_id, payload):
    try:
        sb.table(table).update(payload).eq("id", row_id).execute()
        return True
    except Exception as exc:
        log.warning("  update failed id=%s: %s", row_id, exc)
        return False


# ========================================================================
# Phase 1: noise projects
# ========================================================================

def phase1_noise_projects(sb, apply):
    log.info("=" * 60)
    log.info("PHASE 1: noise projects -> confidence='low'")
    log.info("=" * 60)
    rows = fetch_all(sb.table("projects")
                     .select("id,name,confidence,source_name"))
    hits = {"file_ext": [], "person_name": [], "title_text": []}
    skipped_nsta = []

    for r in rows:
        name = r["name"] or ""
        if FILE_EXT_RE.search(name):
            hits["file_ext"].append(r)
        elif len(name) > 80 or TITLE_JUNK_RE.search(name):
            hits["title_text"].append(r)
        if PERSON_LIKE_RE.fullmatch(name) and "fpso" not in name.lower():
            if r.get("source_name") == "NSTA Field Development Plans":
                skipped_nsta.append(r)
            else:
                hits["person_name"].append(r)

    log.info("projects total: %d", len(rows))
    log.info("file-ext matches: %d", len(hits["file_ext"]))
    log.info("title-text matches: %d", len(hits["title_text"]))
    log.info("person-like non-NSTA: %d", len(hits["person_name"]))
    log.info("person-like SKIPPED (NSTA real fields): %d", len(skipped_nsta))

    changed = 0
    for r in hits["file_ext"] + hits["title_text"] + hits["person_name"]:
        if r.get("confidence") != "low":
            log.info("  LOW: id=%s name=%r (was %s)", r["id"], r["name"],
                     r.get("confidence"))
            if apply:
                if update(sb, "projects", r["id"], {"confidence": "low"}):
                    changed += 1
    log.info("phase 1 updates: %d", changed)
    return {"hits": {k: len(v) for k, v in hits.items()},
            "skipped_nsta": len(skipped_nsta), "updated": changed}


# ========================================================================
# Phase 2: resurrect mis-rejected regulatory events
# ========================================================================

def phase2_resurrect_regulatory(sb, apply):
    log.info("=" * 60)
    log.info("PHASE 2: resurrect rejected NSTA/ANP regulatory events")
    log.info("=" * 60)
    reg = fetch_all(sb.table("candidate_events")
                    .select("id,project_name_raw,event_type,publication_date,"
                            "source_name,evidence_quote,review_status")
                    .eq("review_status", "rejected")
                    .in_("event_type", list(TARGET_EVENT_TYPES))
                    .or_("source_name.ilike.%NSTA%,source_name.ilike.%ANP%"))
    log.info("target rejected rows: %d", len(reg))

    # dedup: keep lowest id per (name, type, date, source)
    keepers, dupes = {}, []
    key_to_keeper = {}
    for row in reg:
        key = (row["project_name_raw"], row["event_type"],
               row["publication_date"], row["source_name"])
        if key not in keepers or row["id"] < keepers[key]["id"]:
            keepers[key] = row
            key_to_keeper[key] = row["id"]
    keeper_ids = {r["id"] for r in keepers.values()}
    for row in reg:
        if row["id"] not in keeper_ids:
            dupes.append(row)
    log.info("unique keepers: %d, duplicates: %d",
             len(keepers), len(dupes))

    resurrected = 0
    for row in keepers.values():
        evidence = AUTO_TRAIL.sub("", row["evidence_quote"] or "").strip()
        if row["review_status"] == "pending":
            continue
        log.debug("  PENDING: id=%s | %s | %s", row["id"],
                  row["project_name_raw"][:40], row["event_type"])
        if apply:
            if update(sb, "candidate_events", row["id"],
                      {"review_status": "pending", "evidence_quote": evidence}):
                resurrected += 1
    for row in dupes:
        key = (row["project_name_raw"], row["event_type"],
               row["publication_date"], row["source_name"])
        trail = ("\n[Auto-rejected: Duplicate of id %s — "
                 "data_quality_cleanup]" % key_to_keeper[key])
        evidence = row["evidence_quote"] or ""
        if "Duplicate of id" in evidence:
            continue
        log.debug("  DUP: id=%s -> keeper %s", row["id"], key_to_keeper[key])
        if apply:
            update(sb, "candidate_events", row["id"],
                   {"evidence_quote": evidence + trail})

    classify_result = None
    if apply:
        log.info("re-running auto_classify on all pending rows...")
        from crawl import auto_classify
        classify_result = auto_classify(sb)
    log.info("phase 2: resurrected=%d dupes_tagged=%d classify=%s",
             resurrected, len(dupes) if apply else 0,
             json.dumps(classify_result) if classify_result else "dry-run")
    return {"target": len(reg), "keepers": len(keepers),
            "dupes": len(dupes), "resurrected": resurrected,
            "classify": classify_result}


# ========================================================================
# Phase 3: Tartaruga Verde
# ========================================================================

def phase3_tartaruga(sb, apply):
    log.info("=" * 60)
    log.info("PHASE 3: Tartaruga Verde project")
    log.info("=" * 60)
    existing = sb.table("projects").select("id,name") \
        .ilike("name", "%tartaruga%").execute().data
    if existing:
        log.info("project row already exists: %s", existing)
        return {"exists": True}

    tv = fetch_all(sb.table("candidate_events").select("*")
                   .ilike("project_name_raw", "%tartaruga%")
                   .order("id"))
    keeper = tv[0] if tv else None
    if not keeper:
        log.warning("no Tartaruga events found")
        return {"exists": False, "events": 0}

    log.info("tartaruga events: %d, keeper id=%s", len(tv), keeper["id"])
    payload = {
        "name": "Tartaruga Verde",
        "country": "Brazil",
        "industry": "FPSO",
        "confidence": "high",
        "status": "Planned",
        "flag": "",
        "summary": keeper.get("summary") or "",
        "source_name": keeper.get("source_name") or "",
        "source_url": keeper.get("source_url") or "",
        "source_date": "2020-01-01",
    }
    new_row = None
    if apply:
        resp = sb.table("projects").insert(payload).execute()
        new_row = resp.data[0] if resp.data else None
        log.info("inserted projects row id=%s", new_row and new_row.get("id"))

    # accept keeper event + link canonical
    if apply and keeper["id"]:
        update(sb, "candidate_events", keeper["id"], {
            "review_status": "accepted",
            "canonical_project_id": TARTARUGA_CANONICAL_ID,
        })
    log.info("keeper event %s -> accepted + canonical=%s (dry-run=%s)",
             keeper["id"], TARTARUGA_CANONICAL_ID, not apply)
    return {"exists": False, "events": len(tv), "keeper_id": keeper["id"],
            "project_row": new_row and new_row.get("id")}


# ========================================================================
# Phase 4: verification
# ========================================================================

def phase4_verify(sb):
    log.info("=" * 60)
    log.info("PHASE 4: verification")
    log.info("=" * 60)
    projects = fetch_all(sb.table("projects")
                         .select("id,name,confidence,status"))
    events = fetch_all(sb.table("candidate_events")
                       .select("id,project_name_raw,canonical_project_id,"
                               "review_status"))
    conf = Counter(p["confidence"] for p in projects)
    log.info("projects total: %d conf=%s", len(projects), dict(conf))
    log.info("events total: %d", len(events))

    # canonical via alias registry display names
    sys.path.insert(0, os.path.join(_ROOT_DIR, "crawler", "adapters"))
    from media_common import PROJECT_ALIASES
    name_to_id = {}
    for cid, labels in PROJECT_ALIASES.items():
        for label in labels:
            name_to_id.setdefault(label.strip().lower(), cid)

    ev_canonical = Counter(e["canonical_project_id"] for e in events
                           if e["canonical_project_id"])
    linked = 0
    empty = []
    for p in projects:
        pname = (p["name"] or "").strip()
        cid = name_to_id.get(pname.lower())
        if cid and ev_canonical.get(cid, 0) > 0:
            linked += 1
            continue
        # fuzzy: core name (before paren) token overlap
        core = pname.split("(")[0].strip().lower()
        matched = False
        for e in events:
            ename = (e["project_name_raw"] or "").lower()
            if len(core) >= 3 and (core in ename or ename in core):
                matched = True
                break
        if matched:
            linked += 1
        else:
            empty.append(p)
    log.info("coverage: %d/%d linked (%.1f%%), empty=%d",
             linked, len(projects), 100.0 * linked / max(len(projects), 1),
             len(empty))
    for p in empty[:20]:
        log.info("  EMPTY: id=%s name=%r conf=%s", p["id"], p["name"],
                 p["confidence"])
    return {"projects": len(projects), "conf": dict(conf),
            "events": len(events), "linked": linked, "empty": len(empty)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="actually write to DB (default: dry run)")
    args = ap.parse_args()
    sb = get_client()
    if not args.apply:
        log.info("DRY RUN — pass --apply to write changes")
    results = {
        "phase1": phase1_noise_projects(sb, args.apply),
        "phase2": phase2_resurrect_regulatory(sb, args.apply),
        "phase3": phase3_tartaruga(sb, args.apply),
    }
    if args.apply:
        results["phase4"] = phase4_verify(sb)
    print(json.dumps(results, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
