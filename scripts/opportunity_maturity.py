#!/usr/bin/env python3
"""
Opportunity maturity audit — classifies every project as:

  mature     = (water_depth_m OR oil_capacity_bpd)
               AND >= 1 candidate_events linked (canonical id or fuzzy name)
  potential  = everything else (goes to the 待挖掘 pool)

Matches the frontend logic in src/lib/project_maturity.ts / DashboardPage.

Usage:
  python3 scripts/opportunity_maturity.py            # audit only
  python3 scripts/opportunity_maturity.py --write    # mark zero-event rows:
      real FPSO project  -> projects.maturity = 'potential'
      noise (not a project name) -> projects.confidence = 'low'

Requires migrations/023_add_maturity.sql applied before --write.
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
for _d in (_SCRIPT_DIR, _ROOT_DIR, os.path.join(_ROOT_DIR, "crawler"),
           os.path.join(_ROOT_DIR, "crawler", "adapters")):
    if _d not in sys.path:
        sys.path.insert(0, _d)

from dotenv import load_dotenv
load_dotenv(os.path.join(_ROOT_DIR, ".env"))
from supabase import create_client

from media_common import normalize_project_name  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("opportunity_maturity")

FILE_EXT_RE = re.compile(r"\.(pdf|csv|xlsx|xls|zip|docx?|txt|json)\b", re.I)
PERSON_LIKE_RE = re.compile(r"^[A-Z][A-Z .&/-]{0,9}$")
TITLE_JUNK_RE = re.compile(r"contract|earnings", re.I)
PLATFORM_RE = re.compile(r"\bP-\d{2,3}\b", re.I)
FPSO_RE = re.compile(r"\bfpso\b", re.I)


def get_client():
    return create_client(os.environ["VITE_SUPABASE_URL"],
                         os.environ["VITE_SUPABASE_ANON_KEY"])


def fetch_all(query):
    rows, out = [], []
    start, size = 0, 1000
    while True:
        page = query.range(start, start + size - 1).execute()
        if page.data is None:
            raise RuntimeError(f"fetch failed: {page}")
        out.extend(page.data)
        if len(page.data) < size:
            return out
        start += size


def looks_real_fpso(p):
    """Heuristic: is this row a real FPSO/floating project vs. noise?"""
    name = (p["name"] or "").strip()
    phase = (p["phase"] or p["status"] or "").strip()
    if FILE_EXT_RE.search(name) or TITLE_JUNK_RE.search(name):
        return False
    if len(name) > 80:
        return False
    if PERSON_LIKE_RE.match(name) and phase in ("", "Unknown"):
        return False
    if PLATFORM_RE.search(name) or FPSO_RE.search(name):
        return True
    if phase not in ("", "Unknown"):
        return True
    return normalize_project_name(name) is not None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true",
                    help="mark zero-event rows: maturity='potential' / confidence='low'")
    args = ap.parse_args()
    sb = get_client()

    projects = fetch_all(sb.table("projects").select(
        "id,name,country,phase,status,confidence,source_name,"
        "water_depth_m,oil_capacity_bpd,procurement_chain"))
    events = fetch_all(sb.table("candidate_events").select(
        "canonical_project_id,project_name_raw,review_status"))

    ev_by_canonical = Counter(
        (e["canonical_project_id"] or "").strip().lower()
        for e in events if e["canonical_project_id"])
    raw_names = [(e["project_name_raw"] or "").strip().lower() for e in events]

    def event_count(p, fuzzy=False):
        name = (p["name"] or "").strip()
        cid = normalize_project_name(name)
        if cid and ev_by_canonical.get(cid.lower(), 0) > 0:
            return ev_by_canonical[cid.lower()]
        if not fuzzy:
            return 0
        # fuzzy fallback: mirrors frontend ilike %core% on project_name_raw
        core = name.split("(")[0].strip().lower().replace(")", "")
        if len(core) >= 3:
            for raw in raw_names:
                if core in raw:
                    return 1
        return 0

    def is_mature(p, n_events):
        tech = p["water_depth_m"] is not None or p["oil_capacity_bpd"] is not None
        return tech and n_events >= 1

    mature, potential = [], []
    zero_event, fuzzy_only = [], []
    for p in projects:
        n = event_count(p)
        nf = event_count(p, fuzzy=True)
        row = {**p, "_events": n, "_events_fuzzy": nf}
        if is_mature(p, n):
            mature.append(row)
        else:
            potential.append(row)
            if n == 0:
                zero_event.append(row)
                if nf > 0:
                    fuzzy_only.append(row)

    log.info("=" * 60)
    log.info("OPPORTUNITY MATURITY AUDIT")
    log.info("=" * 60)
    log.info("projects total: %d", len(projects))
    log.info("candidate_events total: %d", len(events))
    log.info("mature: %d", len(mature))
    log.info("potential: %d (of which zero-event: %d)", len(potential), len(zero_event))
    log.info("zero-event via fuzzy-name-only link: %d", len(fuzzy_only))

    reasons = Counter()
    for p in potential:
        n = p["_events"]
        tech = p["water_depth_m"] is not None or p["oil_capacity_bpd"] is not None
        key = "no-events" if n == 0 else "no-tech"
        reasons[key] += 1
    log.info("potential breakdown: %s", dict(reasons))

    log.info("-" * 60)
    log.info("zero-event projects (%d):", len(zero_event))
    for p in sorted(zero_event, key=lambda r: (r["name"] or "").lower()):
        real = looks_real_fpso(p)
        log.info("  %-8s id=%-5s %-45r phase=%-16s fuzzy=%d src=%s",
                 "REAL" if real else "NOISE", p["id"], p["name"],
                 (p["phase"] or p["status"] or "")[:16], p["_events_fuzzy"],
                 p["source_name"] or "-")

    # Brazilian platform spot check (ANP targets)
    log.info("-" * 60)
    log.info("Brazil platform spot check (P-74..P-85, Buzios, Mero):")
    anp_interest = re.compile(
        r"p-7[4-9]\b|p-8[0-5]\b|petrobras\s+(?:7[4-9]|8[0-5])\b|b[úu]zios|mero",
        re.I)
    for p in projects:
        name = (p["name"] or "").strip()
        if anp_interest.search(name):
            n = event_count(p)
            log.info("  %-50r events=%d tech=%s mature=%s",
                     name, n,
                     p["water_depth_m"] is not None or p["oil_capacity_bpd"] is not None,
                     is_mature(p, n))

    summary = {
        "projects": len(projects),
        "events": len(events),
        "mature": len(mature),
        "potential": len(potential),
        "zero_event": len(zero_event),
    }

    if args.write:
        log.info("=" * 60)
        log.info("WRITE MODE — marking zero-event rows")
        real = [p for p in zero_event if looks_real_fpso(p)]
        noise = [p for p in zero_event if not looks_real_fpso(p)]
        updated_real, updated_noise, failed = 0, 0, 0
        maturity_ready = True
        if real:
            try:
                sb.table("projects").update(
                    {"maturity": "potential"}).eq("id", real[0]["id"]).execute()
            except Exception as exc:  # PGRST204: column missing from schema cache
                maturity_ready = False
                log.info("  maturity column NOT FOUND — run migrations/023_add_maturity.sql "
                         "in Supabase SQL Editor, then re-run this script. (%s)", exc)
        for p in real:
            if not maturity_ready:
                break
            try:
                res = sb.table("projects").update(
                    {"maturity": "potential"}).eq("id", p["id"]).execute()
            except Exception as exc:
                failed += 1
                log.info("  FAIL %s (%s): %s", p["id"], p["name"], exc)
                continue
            if getattr(res, "error", None):
                failed += 1
                log.info("  FAIL %s (%s): %s", p["id"], p["name"],
                         res.error.message if hasattr(res.error, "message") else res.error)
            else:
                updated_real += 1
                log.info("  maturity=potential  id=%s %r", p["id"], p["name"])
        for p in noise:
            res = sb.table("projects").update(
                {"confidence": "low"}).eq("id", p["id"]).execute()
            if getattr(res, "error", None):
                failed += 1
                log.info("  FAIL %s (%s): %s", p["id"], p["name"],
                         res.error.message if hasattr(res.error, "message") else res.error)
            else:
                updated_noise += 1
                log.info("  confidence=low     id=%s %r", p["id"], p["name"])
        log.info("done: real=%d noise=%d failed=%d",
                 updated_real, updated_noise, failed)
        summary.update({"marked_potential": updated_real,
                        "marked_low": updated_noise, "failed": failed})

    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
