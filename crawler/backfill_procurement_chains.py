#!/usr/bin/env python3
"""
Procurement-chain backfill via LLM extraction from candidate_events.

Targets: mature projects (tech params + >=1 canonical event) whose
projects.procurement_chain is empty. For each target, feeds the LLM the
concatenated summary + evidence_quote of its linked events and asks for
procurement-chain entities (EPC contractor, shipyard, hull builder, topside
fabricator, conversion yard).

Safety rule (no hallucinated data): an entity is only written when its name
appears verbatim (case-insensitive) in the source text. Entities the LLM
cannot ground in the source text are dropped. Projects with no grounded
entities stay empty.

Usage:
  python3 crawler/backfill_procurement_chains.py           # dry run
  python3 crawler/backfill_procurement_chains.py --write   # persist updates
"""
import argparse
import json
import logging
import os
import re
import sys
from collections import Counter, defaultdict

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_SCRIPT_DIR)
for _d in (_SCRIPT_DIR, os.path.join(_SCRIPT_DIR, "adapters"), _ROOT_DIR):
    if _d not in sys.path:
        sys.path.insert(0, _d)

from dotenv import load_dotenv
load_dotenv(os.path.join(_ROOT_DIR, ".env"))
from supabase import create_client

from adapters.media_common import normalize_project_name  # noqa: E402
from ai_event_extractor import call_llm  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("procurement-backfill")

MAX_SOURCE_CHARS = 8000

SYSTEM_PROMPT = (
    "You are an oil & gas supply-chain analyst. Given snippets from news "
    "articles about one FPSO project, extract the companies that form the "
    "project's procurement chain. Only these categories: "
    "EPC contractor (总包/EPC), shipyard (船厂), hull builder (船体建造), "
    "topside module fabricator (上部模块), FPSO conversion yard (改装厂).\n"
    "Rules:\n"
    "1. Extract ONLY names that appear verbatim in the snippets. Never "
    "invent, infer, or complete a company name.\n"
    "2. If a snippet only mentions a company without an EPC/shipyard/"
    "fabrication role, skip it. In particular, the field OPERATOR "
    "(e.g. PETROBRAS as operator) is NOT a procurement-chain entity — "
    "never include it.\n"
    "3. Return JSON: {\"entities\": [{\"type\": \"<category>\", \"name\": "
    "\"<exact name from text>\"}], \"empty_reason\": \"\"}\n"
    "4. If nothing qualifies, return {\"entities\": [], \"empty_reason\": "
    "\"<why>\"}."
)


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


def ground(entity_name, source_text):
    """Entity must appear verbatim (case-insensitive) in source text."""
    name = re.sub(r"\s+", " ", (entity_name or "").strip())
    if len(name) < 3:
        return False
    return name.lower() in source_text.lower()


def extract_for(project_name, events):
    parts = []
    for e in events:
        for field in ("summary", "evidence_quote"):
            v = (e.get(field) or "").strip()
            if v:
                parts.append(v)
    source = "\n".join(parts)[:MAX_SOURCE_CHARS]
    if not source.strip():
        return [], "no source text", ""

    user = f"Project: {project_name}\n\nSnippets:\n{source}"
    raw = call_llm(
        [{"role": "system", "content": SYSTEM_PROMPT},
         {"role": "user", "content": user}],
        temperature=0.1, max_tokens=600,
    )
    if not raw:
        return [], "llm failed", source

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            return [], "llm bad json", source
        try:
            parsed = json.loads(m.group(0))
        except json.JSONDecodeError:
            return [], "llm bad json", source

    entities = []
    for ent in parsed.get("entities", []):
        name = (ent.get("name") or "").strip()
        if ground(name, source):
            entities.append({
                "type": (ent.get("type") or "vendor").strip(),
                "name": name,
            })
    reason = parsed.get("empty_reason", "") if not entities else ""
    return entities, reason, source


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true",
                    help="persist procurement_chain updates to projects table")
    args = ap.parse_args()

    sb = create_client(os.environ["VITE_SUPABASE_URL"],
                       os.environ["VITE_SUPABASE_ANON_KEY"])

    projects = fetch_all(sb.table("projects").select(
        "id,name,water_depth_m,oil_capacity_bpd,procurement_chain"))
    events = fetch_all(sb.table("candidate_events").select(
        "canonical_project_id,summary,evidence_quote,procurement_chain"))

    ev_by_cid = defaultdict(list)
    direct_chain = defaultdict(set)
    for e in events:
        cid = (e.get("canonical_project_id") or "").strip().lower()
        if not cid:
            continue
        ev_by_cid[cid].append(e)
        chain = (e.get("procurement_chain") or "").strip()
        if chain:
            for part in re.split(r"[,;]", chain):
                part = part.strip()
                if len(part) >= 3:
                    direct_chain[cid].add(part)

    targets = []
    for p in projects:
        name = (p["name"] or "").strip()
        chain = (p["procurement_chain"] or "").strip()
        tech = p["water_depth_m"] is not None or p["oil_capacity_bpd"] is not None
        cid = (normalize_project_name(name) or "").lower()
        linked = ev_by_cid.get(cid, [])
        if tech and linked and not chain:
            targets.append((p, cid, linked))

    log.info("=" * 60)
    log.info("PROCUREMENT CHAIN BACKFILL (LLM extraction)")
    log.info("mature projects missing chain: %d", len(targets))

    written, empty, failed = [], [], []
    for p, cid, linked in targets:
        entities, reason, _src = extract_for(p["name"], linked)
        names = [e["name"] for e in entities]
        # Direct DB values from the events themselves are always trusted;
        # LLM entities were grounded verbatim in source text already.
        direct = sorted(direct_chain.get(cid, set()))
        for d in direct:
            if not any(d.lower() == n.lower() for n in names):
                names.append(d)
        if not names:
            empty.append((p, reason))
            log.info("  [EMPTY] %-45r %s (%d events)",
                     p["name"], reason, len(linked))
            continue
        chain_str = ", ".join(names)
        src_tag = "llm" if entities else "events"
        log.info("  [FOUND/%s] %-45r -> %s", src_tag, p["name"], chain_str)
        if args.write:
            res = sb.table("projects").update(
                {"procurement_chain": chain_str}).eq("id", p["id"]).execute()
            if getattr(res, "error", None):
                failed.append(p["name"])
                log.info("     FAIL: %s", res.error)
            else:
                written.append((p["name"], chain_str))

    found_dry = len(targets) - len(empty)
    log.info("-" * 60)
    log.info("targets: %d  found: %d  empty: %d",
             len(targets),
             len(written) if args.write else found_dry,
             len(empty))
    if args.write:
        log.info("written: %d  failed: %d", len(written), len(failed))
    else:
        log.info("dry run — use --write to persist")
    print(json.dumps({"targets": len(targets),
                      "found": len(written) if args.write else found_dry,
                      "empty": len(empty),
                      "written": len(written) if args.write else 0},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
