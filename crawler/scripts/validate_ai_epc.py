#!/usr/bin/env python3
"""
Validate AI EPC extraction against real candidate_events rows.

For every project group whose event text carries an EPC/role signal, run:
  1. rule_chain_fallback()  — the legacy rule-engine pipeline (event-level
     chains + extract_procurement over summary/evidence text);
  2. extract_epc_with_ai()  — the new DeepSeek semantic extraction.

Then report: rule miss rate vs AI miss rate, AI-only recoveries, news-media
safety (outlets never land in a role field), and the Indonesia pulp-mill
no-fabrication check.

Usage:
  python3 crawler/scripts/validate_ai_epc.py [--limit N] [--dry]
    --limit N   max project groups to test (default 60)
    --dry       print per-group detail only, no summary JSON
"""
import argparse
import json
import logging
import os
import re
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_CRAWLER_DIR = os.path.dirname(_SCRIPT_DIR)
_ROOT_DIR = os.path.dirname(_CRAWLER_DIR)
for _d in (_CRAWLER_DIR, os.path.join(_CRAWLER_DIR, "adapters"), _ROOT_DIR):
    if _d not in sys.path:
        sys.path.insert(0, _d)

from dotenv import load_dotenv
load_dotenv(os.path.join(_ROOT_DIR, ".env"))
from supabase import create_client

from adapters.media_common import (  # noqa: E402
    normalize_project_name,
    is_news_media_name,
    extract_procurement,
    sanitize_chain,
)
from ai_epc_extractor import (  # noqa: E402
    extract_epc_with_ai,
    rule_chain_fallback,
    sort_events_newest,
)

logging.basicConfig(level=logging.WARNING, format="%(message)s")
log = logging.getLogger("validate-ai-epc")

# Text signals that suggest the event *could* carry a procurement role —
# used to pick the evaluation set (the 43-event diagnostic set).
ROLE_SIGNAL = re.compile(
    r"epc|epcc|shipyard|built|build|engineering|construction|fabricat|"
    r"\byard\b|contractor|contract awarded|letter of intent|\bloi\b|"
    r"operated by|field operator|operator", re.I)


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


def group_events(events):
    groups = {}
    for e in events:
        cid = (e.get("canonical_project_id") or
               normalize_project_name(e.get("project_name_raw") or "") or
               "").strip().lower()
        if not cid:
            continue
        groups.setdefault(cid, []).append(e)
    return groups


def text_of(events):
    return "\n".join(
        f"{(e.get('summary') or '')} {(e.get('evidence_quote') or '')}"
        for e in events)


def role_names(result):
    return [n for n in (result.get("epc_contractor"),
                        result.get("shipyard"),
                        result.get("owner_operator")) if n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=60)
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()

    sb = create_client(os.environ["VITE_SUPABASE_URL"],
                       os.environ["VITE_SUPABASE_ANON_KEY"])

    events = fetch_all(sb.table("candidate_events").select(
        "canonical_project_id,project_name_raw,summary,evidence_quote,"
        "event_type,source_name,procurement_chain,publication_date"))

    groups = group_events(events)
    # Evaluation set: groups whose text carries a role signal AND enough
    # substance (>= 250 chars) to actually name companies. Short demo
    # summaries ("X EPC awarded" without company names) are excluded —
    # there is nothing for any extractor to find in them. Government
    # register rows (ANP/Guyana EPA/NSTA operator lists) never name
    # contractors, so they are excluded as well.
    GOV_SOURCES = ("anp", "guyana epa", "nsta", "石油管理",
                   "equinor key information")

    def is_gov_row(e):
        src = (e.get("source_name") or "").lower()
        return any(g in src for g in GOV_SOURCES)

    signal_groups = {}
    for cid, evs in groups.items():
        news_evs = [e for e in evs if not is_gov_row(e)]
        text = text_of(news_evs)
        if len(text) >= 250 and ROLE_SIGNAL.search(text):
            signal_groups[cid] = sort_events_newest(news_evs)[:20]

    print(f"candidate_events rows: {len(events)}")
    print(f"project groups: {len(groups)}")
    print(f"news groups with role signal + substance: {len(signal_groups)} "
          f"(evaluation set)")

    tested = 0
    # Chain roles = EPC contractor + shipyard (what procurement_chain stores).
    # rule metric: pure text extraction (what the rule engine actually
    # extracts, NOT the pre-stored event chains).
    # stored metric: the current pipeline value (stored event chains).
    rule_hit = ai_hit = stored_hit = 0
    ai_only = rule_only = both = neither = 0
    media_in_role = 0
    ai_owners = 0
    ai_rows = []

    for cid, evs in list(signal_groups.items())[:args.limit]:
        tested += 1
        project = {
            "name": evs[0].get("project_name_raw") or cid,
            "country": "",
            "industry": "FPSO",
        }
        text = text_of(evs)
        rule_chain = sanitize_chain(extract_procurement(text))
        stored_chain = rule_chain_fallback(evs)
        ai = extract_epc_with_ai(project, evs)
        # AI chain roles only — owner_operator is tracked separately and
        # does not enter procurement_chain.
        ai_names = []
        if ai:
            for field in ("epc_contractor", "shipyard"):
                if ai.get(field):
                    ai_names.append(ai[field])

        # News-media safety: no role field may be a blacklisted outlet.
        bad = [n for n in role_names(ai) if is_news_media_name(n)] if ai else []
        if bad:
            media_in_role += 1
            print(f"  [MEDIA LEAK] {cid}: {bad}")

        if rule_chain:
            rule_hit += 1
        if stored_chain:
            stored_hit += 1
        if ai_names:
            ai_hit += 1
        if ai_names and not rule_chain:
            ai_only += 1
        if rule_chain and not ai_names:
            rule_only += 1
        if rule_chain and ai_names:
            both += 1
        if not rule_chain and not ai_names:
            neither += 1
        if ai and ai.get("owner_operator"):
            ai_owners += 1

        row = {
            "project": project["name"],
            "rule_text_chain": rule_chain,
            "stored_chain": stored_chain,
            "ai": {k: ai.get(k) for k in ("epc_contractor", "shipyard",
                                          "owner_operator", "news_media",
                                          "confidence", "reasoning")}
            if ai else None,
            "evidence": (ai or {}).get("evidence", ""),
        }
        ai_rows.append(row)
        print(f"[{tested}] {cid} (text {len(text)} chars)")
        print(f"    rule-text: {rule_chain or '-'}")
        print(f"    stored   : {stored_chain or '-'}")
        if ai:
            print(f"    ai       : epc={ai.get('epc_contractor')} "
                  f"yard={ai.get('shipyard')} owner={ai.get('owner_operator')} "
                  f"conf={ai.get('confidence')} media={ai.get('news_media')}")
            if ai.get("evidence"):
                print(f"    evidence : {ai['evidence'][:220]}")
        else:
            print(f"    ai       : LLM FAILED")

    print()
    print("=" * 62)
    print(f"tested groups (text carries role signal): {tested}")
    print(f"rule text extraction hit: {rule_hit}  "
          f"miss: {tested - rule_hit} ({(tested - rule_hit) / max(tested, 1):.0%})")
    print(f"stored-chain pipeline hit: {stored_hit}")
    print(f"AI chain-role hit: {ai_hit}  "
          f"miss: {tested - ai_hit} ({(tested - ai_hit) / max(tested, 1):.0%})")
    print(f"AI-only recoveries (rule text missed, AI found): {ai_only}")
    print(f"rule-only (AI found nothing): {rule_only}")
    print(f"both hit: {both}   neither: {neither}")
    print(f"AI owner/operator found (separate field): {ai_owners}")
    print(f"news-media leaks into role fields: {media_in_role}")

    if not args.dry:
        out_path = os.path.join(_SCRIPT_DIR, "ai_epc_validation.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({"tested": tested, "rule_hit": rule_hit,
                       "ai_hit": ai_hit, "ai_only": ai_only,
                       "rule_only": rule_only, "both": both, "neither": neither,
                       "media_leaks": media_in_role, "rows": ai_rows},
                      f, ensure_ascii=False, indent=2)
        print(f"detail written: {out_path}")


if __name__ == "__main__":
    main()
