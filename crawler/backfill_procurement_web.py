#!/usr/bin/env python3
"""
Procurement-chain backfill from web articles (search-sourced URLs).

Phase 2 of the procurement backfill: event source_urls in the DB are ANP
technical CSVs with no procurement text, so per-project article URLs were
collected via web search and stored in crawler/procurement_urls.json.

Pipeline per project:
  1. Fetch each URL (<= 1 req/sec, browser UA, 30s timeout, 1 retry).
  2. Extract visible text (BeautifulSoup for HTML, raw for CSV/text).
  3. Ask DeepSeek for EPC/shipyard/hull/topside/conversion entities.
  4. Grounding: entity name must appear verbatim (case-insensitive) in
     the fetched text — hallucinated names are dropped.
  5. --write persists projects.procurement_chain (comma-separated names).

Usage:
  python3 crawler/backfill_procurement_web.py            # dry run
  python3 crawler/backfill_procurement_web.py --write    # persist
"""
import argparse
import json
import logging
import os
import re
import sys
import time

import requests
from bs4 import BeautifulSoup

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_SCRIPT_DIR)
for _d in (_SCRIPT_DIR, os.path.join(_SCRIPT_DIR, "adapters"), _ROOT_DIR):
    if _d not in sys.path:
        sys.path.insert(0, _d)

from dotenv import load_dotenv
load_dotenv(os.path.join(_ROOT_DIR, ".env"))
from supabase import create_client

from ai_event_extractor import call_llm  # noqa: E402
from adapters.media_common import (  # noqa: E402
    is_news_media_name,
    sanitize_chain,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("procurement-web")

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0 Safari/537.36"),
    "Accept-Language": "en-US,en;q=0.9,pt;q=0.8",
}
FETCH_INTERVAL = 1.0  # seconds between requests — respect target sites
MAX_TEXT_CHARS = 20000

# Manual variant merges: LLM sometimes returns the same company under two
# names despite the dedupe instruction. Applied before writing to DB.
FIXUPS = {
    "FPSO PIONEIRO DE LIBRA": "Sembcorp Marine Jurong Shipyard",
    "FPSO Cidade de Itaguaí": "MODEC, Schahin Shipyard, EBE shipyard, BrasFELS shipyard",
    "PETROBRAS 78": "Keppel Offshore & Marine, Hyundai Heavy Industries, BrasFELS",
}

SYSTEM_PROMPT = (
    "You are an oil & gas supply-chain analyst. Given text extracted from "
    "web articles about one FPSO project, extract the companies that form "
    "the project's procurement chain. Only these categories: "
    "EPC contractor (总包/EPC), shipyard (船厂), hull builder (船体建造), "
    "topside module fabricator (上部模块), FPSO conversion yard (改装厂).\n"
    "Rules:\n"
    "1. Extract ONLY names that appear verbatim in the text. Never invent, "
    "infer, or complete a company name.\n"
    "2. If the text only mentions a company without an EPC/shipyard/"
    "fabrication role, skip it. In particular, the field OPERATOR "
    "(e.g. PETROBRAS as operator) is NOT a procurement-chain entity — "
    "never include it.\n"
    "3. NEWS OUTLETS ARE NEVER PROCUREMENT ENTITIES. Reuters, Bloomberg, "
    "Offshore Energy, World Oil, Paper Advance, Splash247, Upstream, "
    "Rigzone and any other news/trade-media publisher must never appear "
    "in the entities list, even when the text mentions them.\n"
    "4. If the same company appears multiple times or under slightly "
    "different names (e.g. Keppel O&M / Keppel Offshore & Marine), output it "
    "ONCE using the most complete formal name.\n"
    "5. Return JSON: {\"entities\": [{\"type\": \"<category>\", \"name\": "
    "\"<exact name from text>\"}], \"empty_reason\": \"\"}\n"
    "6. If nothing qualifies, return {\"entities\": [], \"empty_reason\": "
    "\"<why>\"}."
)


def fetch_text(url):
    """Fetch URL, return extracted text or raise RuntimeError on failure."""
    for attempt in (1, 2):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            ctype = resp.headers.get("Content-Type", "")
            if "text/html" in ctype or url.endswith(".html"):
                soup = BeautifulSoup(resp.text, "html.parser")
                for tag in soup(["script", "style", "noscript", "header",
                                 "footer", "nav"]):
                    tag.decompose()
                text = soup.get_text(" ", strip=True)
            else:
                text = resp.text
            text = re.sub(r"\s+", " ", text).strip()
            if len(text) < 200:
                raise RuntimeError(f"page too short ({len(text)} chars)")
            return text
        except (requests.exceptions.RequestException, RuntimeError) as exc:
            log.info("    fetch fail (attempt %d) %s: %s", attempt, url, exc)
            if attempt == 1:
                time.sleep(FETCH_INTERVAL)
    raise RuntimeError(f"unreachable: {url}")


def ground(entity_name, source_text):
    name = re.sub(r"\s+", " ", (entity_name or "").strip())
    if len(name) < 3:
        return False
    return name.lower() in source_text.lower()


def extract_for(project_name, texts):
    source = "\n\n".join(texts)[:MAX_TEXT_CHARS]
    if not source.strip():
        return [], "no text", ""
    user = f"Project: {project_name}\n\nArticle text:\n{source}"
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

    entities, seen = [], set()
    for ent in parsed.get("entities", []):
        name = re.sub(r"\s+", " ", (ent.get("name") or "").strip())
        key = name.lower()
        if key in seen or is_news_media_name(name) or not ground(name, source):
            continue
        seen.add(key)
        entities.append({"type": (ent.get("type") or "vendor").strip(),
                         "name": name})
    reason = parsed.get("empty_reason", "") if not entities else ""
    return entities, reason, source


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true",
                    help="persist procurement_chain updates to projects table")
    ap.add_argument("--urls", default=os.path.join(
        _SCRIPT_DIR, "procurement_urls.json"),
        help="JSON file mapping project name -> [urls]")
    args = ap.parse_args()

    with open(args.urls, encoding="utf-8") as fh:
        url_map = json.load(fh)

    sb = create_client(os.environ["VITE_SUPABASE_URL"],
                       os.environ["VITE_SUPABASE_ANON_KEY"])
    projects = sb.table("projects").select(
        "id,name,procurement_chain").execute().data

    by_name = {p["name"].strip(): p for p in projects}
    missing = [name for name in url_map if name not in by_name]
    if missing:
        log.info("names not in DB (skipped): %s", missing)

    url_cache = {}  # dedupe fetches across projects
    results = []
    for name, urls in url_map.items():
        p = by_name.get(name)
        if not p:
            continue
        texts, url_errors = [], []
        for url in urls:
            time.sleep(FETCH_INTERVAL)
            if url not in url_cache:
                try:
                    url_cache[url] = fetch_text(url)
                except RuntimeError as exc:
                    url_cache[url] = None
                    url_errors.append(str(exc))
            text = url_cache[url]
            if text:
                texts.append(text)
        if not texts:
            results.append((p, [], f"all urls failed: {len(url_errors)}",
                            "url-unreachable"))
            log.info("[URL-FAIL] %-45r (%d urls unreachable)",
                     name, len(url_errors))
            continue
        entities, reason, _src = extract_for(name, texts)
        if not entities:
            results.append((p, [], reason, "no-entities"))
            log.info("[NO-ENTITIES] %-45r %s", name, reason)
            continue
        chain_str = sanitize_chain(
            FIXUPS.get(name, ", ".join(e["name"] for e in entities)))
        results.append((p, entities, "", "ok"))
        log.info("[OK] %-45r -> %s", name, chain_str)
        if args.write:
            res = sb.table("projects").update(
                {"procurement_chain": chain_str}).eq("id", p["id"]).execute()
            if getattr(res, "error", None):
                log.info("    WRITE FAIL: %s", res.error)

    ok = [r for r in results if r[3] == "ok"]
    url_fail = [r for r in results if r[3] == "url-unreachable"]
    no_ent = [r for r in results if r[3] == "no-entities"]
    log.info("=" * 60)
    log.info("SUMMARY: ok=%d url-unreachable=%d no-entities=%d",
             len(ok), len(url_fail), len(no_ent))
    if not args.write:
        log.info("dry run — use --write to persist")

    print(json.dumps({
        "projects": len(url_map),
        "ok": [{"project": r[0]["name"],
                "chain": ", ".join(e["name"] for e in r[1])} for r in ok],
        "url_unreachable": [r[0]["name"] for r in url_fail],
        "no_entities": [{"project": r[0]["name"], "reason": r[2]}
                        for r in no_ent],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
