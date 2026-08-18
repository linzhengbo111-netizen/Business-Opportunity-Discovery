#!/usr/bin/env python3
"""
Tech-parameter enrichment backfill — make early/mid-phase projects mature.

The default dashboard (maturity filter) requires BOTH:
  1. tech params (water_depth_m or oil_capacity_bpd) on the project row
  2. >= 1 candidate_events linked via canonical_project_id

After the 9-phase recalibration, every early/mid project (Approval 284,
etc.) has empty tech params, so the default view is empty. This tool:

  Step 0  Event linkage — for events whose canonical_project_id is NULL,
          re-derive it from project_name_raw via the alias registry
          (exact / strip-"FPSO" / keyword-overlap, mirroring
          normalizeProjectName() in src/data/project_aliases.ts) and write
          it back. Mechanical, no text generation.
  Step 1  Direct propagation — if a project's linked events already carry
          tech columns (water_depth_m, oil_capacity_bpd, ...), take the
          most recent non-null value and copy it to the project row.
          No LLM involved.
  Step 2  LLM extraction — for remaining early/mid projects with >= 1
          linked event, extract tech params from event text (summary +
          evidence_quote + raw_json snippet). Strict evidence rule: every
          extracted field must carry a verbatim quote that appears in the
          input text (verified mechanically); fields without evidence are
          dropped. Nothing is invented.
  Step 3  source_url fallback — when event text yields nothing and an
          event has a fetchable URL, download the article/PDF, extract
          text, and retry the LLM once. Fetch failures are logged and the
          project is skipped.

Safety: dry run by default (--write to persist). Before the first write a
local backup of the affected project rows and event linkage changes is
saved under crawler/data/tech_backfill_backup_*.json.

Usage:
  python3 crawler/backfill_tech_params.py              # dry run
  python3 crawler/backfill_tech_params.py --write      # persist
  python3 crawler/backfill_tech_params.py --limit 12   # first N projects
"""
import argparse
import io
import json
import logging
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_SCRIPT_DIR)
for _d in (_SCRIPT_DIR, os.path.join(_SCRIPT_DIR, "adapters"), _ROOT_DIR):
    if _d not in sys.path:
        sys.path.insert(0, _d)

import requests  # noqa: E402
from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(_ROOT_DIR, ".env"))
from supabase import create_client  # noqa: E402

from adapters.media_common import normalize_project_name  # noqa: E402
from ai_event_extractor import call_llm, _extract_json_object  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("tech-backfill")

PAGE_SIZE = 1000
MAX_EVENTS_TEXT = 4000
MAX_FETCH_TEXT = 6000
MAX_FETCH_BYTES = 5 * 1024 * 1024

# Phases the default dashboard shows (filter excludes Delivery/Commissioning).
EARLY_MID_PHASES = {
    "Concept", "Planning", "Design", "Approval",
    "EPC Award", "Procurement", "Construction",
    "Commissioning", None,
}

TECH_FIELDS = ("water_depth_m", "oil_capacity_bpd", "gas_capacity_mmcmd",
               "field_name", "operator_name", "basin", "hull_type")

# Sanity bounds for numeric fields — values outside are adapter/LLM junk.
SANITY = {
    "water_depth_m": (10, 4000),
    "oil_capacity_bpd": (500, 3000000),
    "gas_capacity_mmcmd": (0.1, 500),
}

_EXTRACT_PROMPT = """\
Extract technical parameters from evidence text about ONE oil & gas project.

STRICT RULES:
1. Extract ONLY values explicitly stated in the text. Never guess, infer,
   or use outside knowledge. Absent = null.
2. For every extracted field, provide the verbatim quote from the text
   that supports it (exact words, no rewording).
3. Numbers may appear as "2,200 m", "220,000 bpd", "180k b/d". Convert to
   plain numbers (2200, 220000). Unit context decides the field.
4. If a value appears multiple times, prefer the most specific/recent.

Return JSON only:
{
  "water_depth_m": number|null,
  "oil_capacity_bpd": number|null,
  "gas_capacity_mmcmd": number|null,
  "field_name": string|null,
  "operator_name": string|null,
  "basin": string|null,
  "hull_type": string|null,
  "evidence": {"water_depth_m": "verbatim quote", "oil_capacity_bpd": "...", "gas_capacity_mmcmd": "...", "field_name": "...", "operator_name": "...", "basin": "...", "hull_type": "..."},
  "reasoning": "one short sentence"
}
Only include a key in \"evidence\" when its field is non-null.

TEXT:
"""


def _fetch_all_paged(table, select):
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


def _strip_html(text):
    text = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>",
                  " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _fetch_url_text(url, headers):
    """Download a URL and return plain text (HTML stripped, PDF parsed).
    Returns None on any failure. Never raises."""
    if not url:
        return None
    try:
        resp = requests.get(url, timeout=30, headers=headers,
                            stream=True)
        if resp.status_code != 200:
            log.warning("    fetch HTTP %s for %s", resp.status_code, url[:100])
            return None
        raw = resp.raw.read(MAX_FETCH_BYTES + 1)
        if len(raw) > MAX_FETCH_BYTES:
            log.warning("    fetch too large (%d bytes): %s",
                        len(raw), url[:100])
            return None
        ctype = resp.headers.get("content-type", "")
        if raw[:4] == b"PK\x03\x04":
            log.warning("    fetch is a zip archive — cannot parse: %s",
                        url[:100])
            return None
        if raw[:5] == b"%PDF-" or "pdf" in ctype:
            try:
                from pypdf import PdfReader
                reader = PdfReader(io.BytesIO(raw))
                text = " ".join((page.extract_text() or "")
                                for page in reader.pages)
            except Exception as exc:  # pypdf parse failure
                log.warning("    pdf parse failed for %s: %s",
                            url[:100], str(exc)[:80])
                return None
        else:
            text = raw.decode("utf-8", errors="ignore")
            text = _strip_html(text)
        if len(text) < 200:
            log.warning("    fetch too small (%d chars, ctype=%s): %s",
                        len(text), ctype[:40], url[:100])
            return None
        return text.strip()[:MAX_FETCH_TEXT]
    except requests.exceptions.RequestException as exc:
        log.warning("    fetch error for %s: %s", url[:100], exc)
        return None


def _event_text(events, max_chars=MAX_EVENTS_TEXT):
    """Concatenate summary + evidence_quote + raw_json snippet. Events
    whose raw_json carries a long document text are preferred (more
    content = more likely to hold specs)."""
    def text_len(ev):
        rj = ev.get("raw_json")
        if isinstance(rj, dict):
            for key in ("text", "description", "snippet"):
                val = (rj.get(key) or "").strip()
                if val:
                    return len(val)
        return 0

    parts = []
    for ev in sorted(events[:10], key=text_len, reverse=True):
        for field in ("summary", "evidence_quote"):
            val = (ev.get(field) or "").strip()
            if val:
                parts.append(val)
        rj = ev.get("raw_json")
        if isinstance(rj, dict):
            for key in ("text", "description", "snippet"):
                val = (rj.get(key) or "").strip()
                if val and len(val) > 40:
                    parts.append(val[:3000])
                    break
    text = " ".join(parts)
    return text[:max_chars]


def _parse_extraction(reply, input_text):
    """Parse LLM JSON reply; verify each evidence quote appears verbatim in
    the input text (anti-hallucination). Returns (values, kept_reason)."""
    empty = {f: None for f in TECH_FIELDS}
    obj = _extract_json_object(reply) if isinstance(reply, str) else None
    if not isinstance(obj, dict):
        return empty, "unparseable LLM reply"
    text_lower = input_text.lower()
    values = {}
    for field in TECH_FIELDS:
        val = obj.get(field)
        if val is None or (isinstance(val, str) and not val.strip()):
            continue
        quote = ((obj.get("evidence") or {}).get(field) or "").strip()
        if field in ("water_depth_m", "oil_capacity_bpd", "gas_capacity_mmcmd"):
            try:
                val = int(float(str(val).replace(",", "")))
            except (TypeError, ValueError):
                continue
            lo, hi = SANITY[field]
            if val < lo or val > hi:
                continue  # outside plausible range — drop
        else:
            val = str(val).strip()[:120]
        if not quote or quote.lower() not in text_lower:
            continue  # evidence missing or not verbatim — drop field
        values[field] = val
    return values, (obj.get("reasoning") or "")[:120]


def link_unlinked_events(events, write):
    """Re-derive canonical_project_id for unlinked events from raw name."""
    linked = 0
    for ev in events:
        if ev.get("canonical_project_id"):
            continue
        cid = normalize_project_name(ev.get("project_name_raw") or "")
        if cid:
            linked += 1
            ev["_new_canonical"] = cid
    return linked


def build_event_index(events):
    """cid -> list of events (newest first), including pending _new_canonical."""
    index = {}
    for ev in events:
        cid = ev.get("canonical_project_id") or ev.get("_new_canonical")
        if cid:
            index.setdefault(cid, []).append(ev)
    for lst in index.values():
        lst.sort(key=lambda e: e.get("publication_date") or "",
                 reverse=True)
    return index


def _has_depth_or_cap(values):
    return bool(values.get("water_depth_m") or values.get("oil_capacity_bpd"))


def _sane_propagate(events):
    """Copy newest-first non-null event tech columns. Numeric fields are
    only propagated when they are consistent: if multiple tech events
    disagree (>10% spread), the value is dropped rather than pick one."""
    values = {}
    numeric_candidates = {}
    for ev in events:
        for field in TECH_FIELDS:
            val = ev.get(field)
            if val is None or val == "":
                continue
            if field in SANITY:
                try:
                    num = float(val)
                except (TypeError, ValueError):
                    continue
                lo, hi = SANITY[field]
                if num < lo or num > hi:
                    continue
                numeric_candidates.setdefault(field, []).append(num)
            elif field not in values:
                values[field] = val
    for field, nums in numeric_candidates.items():
        if len(nums) == 1:
            values[field] = int(nums[0])
            continue
        lo, hi = min(nums), max(nums)
        if hi > lo * 1.1:  # >10% spread — contradictory, drop
            log.info("    propagate drop %s: contradictory values %s",
                     field, sorted(set(nums)))
            continue
        values[field] = int(sum(nums) / len(nums))
    return values


def enrich_project(p, events, headers):
    """Return (values, source) — 'propagate', 'llm', 'url', or None.
    Maturity gate needs water_depth_m or oil_capacity_bpd, so the url
    fallback also runs whenever those two are missing."""
    # Step 1: direct propagation from event tech columns
    values = _sane_propagate(events)
    if _has_depth_or_cap(values):
        return values, "propagate"

    # Step 2: LLM extraction from event text
    text = _event_text(events)
    if len(text) >= 40:
        reply = call_llm([{"role": "user",
                           "content": _EXTRACT_PROMPT + text}],
                         max_tokens=900)
        if reply:
            llm_values, reasoning = _parse_extraction(reply, text)
            for k, v in llm_values.items():
                values.setdefault(k, v)
            if _has_depth_or_cap(values):
                return values, "llm"
            log.info("    llm no depth/capacity (%s) — trying source_url",
                     reasoning)

    # Step 3: source_url fallback — fetch article/PDF until one yields
    # depth or capacity
    for ev in events[:5]:
        url = None
        rj = ev.get("raw_json")
        if isinstance(rj, dict):
            url = rj.get("download_url") or rj.get("url") or rj.get("source_url")
        if not url:
            url = ev.get("source_url")
        if not url:
            continue
        fetched = _fetch_url_text(url, headers)
        if not fetched:
            continue
        reply = call_llm([{"role": "user",
                           "content": _EXTRACT_PROMPT + fetched}],
                         max_tokens=900)
        if reply:
            url_values, reasoning = _parse_extraction(reply, fetched)
            for k, v in url_values.items():
                values.setdefault(k, v)
            if _has_depth_or_cap(values):
                return values, "url"
            log.info("    url fetch no depth/capacity (%s)", reasoning)
    return (values or None), ("partial" if values else None)


def simulate_dashboard(projects, event_index):
    """Mirror frontend pipeline: mature = tech + events; default view
    excludes Delivery/Commissioning and Low confidence."""
    from adapters.media_common import normalize_project_name
    visible = []
    per_phase = Counter()
    for p in projects:
        has_tech = bool(p.get("water_depth_m") or p.get("oil_capacity_bpd"))
        cid = normalize_project_name(p.get("name") or "")
        n_events = len(event_index.get(cid, [])) if cid else 0
        if not (has_tech and n_events >= 1):
            continue
        phase = p.get("phase")
        if phase in ("Delivery", "Commissioning"):
            continue
        if (p.get("confidence") or "") == "Low":
            continue
        visible.append((p.get("name"), phase, n_events))
        per_phase[phase] += 1
    return visible, per_phase


def main():
    ap = argparse.ArgumentParser(description="Tech-param enrichment backfill")
    ap.add_argument("--write", action="store_true",
                    help="persist updates (default: dry run)")
    ap.add_argument("--limit", type=int, default=0,
                    help="only process the first N enrichment candidates")
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
        "id,name,phase,water_depth_m,oil_capacity_bpd,gas_capacity_mmcmd,"
        "field_name,operator_name,basin,hull_type,confidence,summary,"
        "source_name,source_url")
    events = _fetch_all_paged(
        events_table,
        "id,canonical_project_id,project_name_raw,publication_date,summary,"
        "evidence_quote,raw_json,source_url,source_name,"
        "water_depth_m,oil_capacity_bpd,gas_capacity_mmcmd,"
        "field_name,operator_name,basin,hull_type")
    log.info("Loaded %d projects, %d events", len(projects), len(events))

    # ---- Step 0: event linkage ----
    link_count = 0
    if not args.skip_link:
        link_count = link_unlinked_events(events, args.write)
        log.info("Step 0 linkage: %d unlinked events re-linkable by alias",
                 link_count)
    event_index = build_event_index(events)

    # ---- Candidate pool: early/mid, no tech, has events ----
    def has_tech(p):
        return bool(p.get("water_depth_m") or p.get("oil_capacity_bpd"))

    candidates = []
    for p in projects:
        if p.get("phase") not in EARLY_MID_PHASES:
            continue
        if has_tech(p):
            continue
        cid = normalize_project_name(p.get("name") or "")
        if cid and event_index.get(cid):
            candidates.append((p, event_index[cid]))
    candidates.sort(key=lambda t: len(t[1]), reverse=True)
    if args.limit:
        candidates = candidates[:args.limit]
    log.info("Enrichment candidates: %d (early/mid, no tech, has events)",
             len(candidates))

    # ---- Backup before write ----
    if args.write:
        data_dir = os.path.join(_SCRIPT_DIR, "data")
        os.makedirs(data_dir, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = os.path.join(data_dir, f"tech_backfill_backup_{stamp}.json")
        backup = {
            "projects": [
                {k: p.get(k) for k in ("id", "name", "phase") + TECH_FIELDS}
                for p, _ in candidates
            ],
            "event_links": [
                {"id": e.get("id"),
                 "old_canonical": e.get("canonical_project_id"),
                 "new_canonical": e.get("_new_canonical")}
                for e in events if e.get("_new_canonical")
            ],
        }
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(backup, fh, ensure_ascii=False, indent=2)
        log.info("Backup written: %s", path)

    # ---- Write event linkage ----
    if args.write and link_count:
        written = 0
        for ev in events:
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

    # ---- Enrich ----
    headers = {"User-Agent": "Mozilla/5.0 (compatible; tech-backfill/1.0)"}
    applied = {}  # project id -> written tech values (for simulation)
    stats = {"total": 0, "filled": 0, "propagate": 0, "llm": 0, "url": 0,
             "partial": 0, "skipped": 0, "write_errors": 0,
             "distribution": Counter(), "examples": []}
    for i, (p, p_events) in enumerate(candidates):
        stats["total"] += 1
        values, source = enrich_project(p, p_events, headers)
        if values:
            applied[p.get("id")] = values
            stats["filled"] += 1
            stats[source] += 1
            stats["distribution"][p.get("phase") or "NULL"] += 1
            if len(stats["examples"]) < 8:
                stats["examples"].append({
                    "name": (p.get("name") or "?")[:55],
                    "phase": p.get("phase") or "NULL",
                    "source": source,
                    "values": {k: v for k, v in values.items()
                               if v is not None},
                })
            if args.write:
                try:
                    projects_table.update(values).eq("id", p.get("id")) \
                        .execute()
                except Exception as exc:
                    stats["write_errors"] += 1
                    log.warning("  update error (id=%s): %s",
                                p.get("id"), exc)
        else:
            stats["skipped"] += 1
            log.info("  skip: %s (phase=%s, %d events)",
                     (p.get("name") or "?")[:50],
                     p.get("phase") or "NULL", len(p_events))
        if (i + 1) % 10 == 0:
            log.info("  Progress: %d/%d | filled=%d (propagate=%d llm=%d "
                     "url=%d)",
                     i + 1, len(candidates), stats["filled"],
                     stats["propagate"], stats["llm"], stats["url"])

    log.info("=" * 56)
    log.info("TECH BACKFILL %s",
             "COMPLETE (writes persisted)" if args.write
             else "DRY RUN (nothing written)")
    log.info("total=%d | filled=%d (propagate=%d llm=%d url=%d "
             "partial=%d) | skipped=%d | write_errors=%d",
             stats["total"], stats["filled"], stats["propagate"],
             stats["llm"], stats["url"], stats["partial"],
             stats["skipped"], stats["write_errors"])
    log.info("Filled per phase: %s",
             dict(stats["distribution"].most_common()))
    log.info("Examples:")
    for ex in stats["examples"]:
        log.info("  [%-12s %-9s] %-55s %s",
                 ex["phase"], ex["source"], ex["name"], ex["values"])

    # ---- Dashboard simulation ----
    if args.write:
        # refetch projects to include persisted tech params
        projects = _fetch_all_paged(
            projects_table,
            "id,name,phase,water_depth_m,oil_capacity_bpd,confidence")
    for p in projects:
        vals = applied.get(p.get("id"))
        if vals:
            p.update(vals)
    visible, per_phase = simulate_dashboard(projects, event_index)
    log.info("-" * 56)
    log.info("Default dashboard simulation: %d visible early/mid projects",
             len(visible))
    log.info("Visible per phase: %s", dict(per_phase.most_common()))
    for name, phase, n in visible[:40]:
        log.info("  %-14s %-40s events=%d", phase, name[:40], n)


if __name__ == "__main__":
    main()
