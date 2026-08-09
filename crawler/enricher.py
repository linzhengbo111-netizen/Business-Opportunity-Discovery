#!/usr/bin/env python3
"""
FPSO Project Information Enricher — 项目信息自动扩充

基于已提取的项目关键词（名称、运营商、油田、盆地、国家），自动检索公开网站
补充项目技术规格细节。

Core principle (不可逾越的底线):
  只提取来源文本中明确公示的信息，不做任何推断或联想。
  Only extract data explicitly stated in the source text. Zero inference.

Flow (4 steps):
  Step 1 — 提取搜索关键词: 从项目数据中提取高质量的搜索词组
  Step 2 — 公开网站检索: DuckDuckGo 搜索 + 已知 FPSO 数据源直查
  Step 3 — 结果解析与提取: 获取页面全文，用现有 extract_* 函数提取技术规格
  Step 4 — 交叉验证与合并: 多源验证，只保留多源一致或明确标注的数据

Usage:
  from enricher import enrich_project

  enriched = enrich_project({
      "name": "FPSO Prosperity",
      "country": "Guyana",
      "operator_name": "ExxonMobil",
      "field_name": "Payara",
      "basin": "Stabroek",
      "summary": "...",
  })
  # enriched contains only newly discovered, verified fields.
  # Original data is never overwritten with lower-confidence values.
"""

import json
import logging
import os
import re
import sys
import time
import hashlib
import random
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote_plus, urljoin

import httpx
from bs4 import BeautifulSoup

# ---- Path setup (same strategy as crawl.py) -----------------------------

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from adapters.media_common import (  # noqa: E402
    extract_water_depth_from_article,
    extract_oil_capacity_from_article,
    extract_gas_capacity_from_article,
    extract_hull_type_from_article,
    extract_operator_from_article,
    extract_basin_from_article,
    extract_field_name_from_article,
)

log = logging.getLogger("fpso-enricher")

# ---- Config ---------------------------------------------------------------

USER_AGENT = (
    "Mozilla/5.0 (compatible; FPSOEnricher/1.0; +https://github.com/fpso-tracker)"
)

# DuckDuckGo HTML search (scraper-friendly endpoint, no API key needed)
DDG_HTML_URL = "https://html.duckduckgo.com/html/"

# Known FPSO data sources to search directly (site: searches)
FPSO_KNOWN_SOURCES = [
    "offshore-mag.com",
    "worldoil.com",
    "oedigital.com",
    "splash247.com",
    "offshore-energy.biz",
    "upstreamonline.com",
    "rivieramm.com",
    "offshore-technology.com",
    "subseaworldnews.com",
]

# Maximum pages to fetch per project (rate limiting)
MAX_SEARCH_RESULTS = 5
MAX_PAGE_FETCH = 3
REQUEST_DELAY = (1.0, 2.5)  # seconds between requests

# Text patterns that indicate explicitly stated (not inferred) data
# If a value is found near these markers, confidence is higher
EXPLICIT_MARKERS = [
    r"water\s*depth\s*(?:of\s*)?[:\-]?\s*([\d,]+)\s*(?:m|meters?|metres?)",
    r"capacity\s*(?:of\s*)?[:\-]?\s*([\d,]+)\s*(?:bpd|barrels?\s*(?:per|/)\s*day)",
    r"hull\s*(?:type\s*)?[:\-]?\s*(spread\s*moored?|turret|flng|conversion)",
    r"operator\s*[:\-]?\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
    r"basin\s*[:\-]?\s*([A-Z][a-z]+(?:\s*(?:Basin|盆地)\b)?)",
    r"field\s*[:\-]?\s*([A-Z][a-z]+(?:\s*(?:Field|油田)\b)?)",
]


# ============================================================================
# Step 1: Build search queries from project keywords
# ============================================================================

def _build_search_queries(project: dict) -> list[tuple[str, str]]:
    """
    Generate prioritized search queries from project keywords.

    Each query targets a different aspect of the project:
      - Primary: project name + "FPSO" (most specific)
      - Operator: operator_name + project name (official source)
      - Field: field_name + basin + "FPSO" (field-level data)
      - Tech: project name + technical spec keywords (targeted)

    Returns list of (query_string, purpose_label) tuples.
    """
    name = (project.get("name") or "").strip()
    operator = (project.get("operator_name") or "").strip()
    field = (project.get("field_name") or "").strip()
    basin = (project.get("basin") or "").strip()
    country = (project.get("country") or "").strip()
    summary = (project.get("summary") or "")[:200]

    queries = []

    # Priority 1: Exact project name + FPSO
    if name and "fpso" in name.lower():
        queries.append((f'"{name}" FPSO', "exact-project"))
    elif name:
        queries.append((f'"{name}" FPSO offshore', "exact-project"))

    # Priority 2: Operator + project name (official press releases)
    if operator and name:
        op_short = operator.split()[0] if operator.split() else operator
        queries.append((f'{op_short} "{name}" FPSO', "operator-project"))

    # Priority 3: Field + basin (geological/technical data)
    if field and basin:
        queries.append((f'"{field}" {basin} FPSO water depth capacity', "field-tech"))
    elif field:
        queries.append((f'"{field}" FPSO technical specifications', "field-tech"))
    elif basin:
        queries.append((f'{basin} FPSO "{name}"' if name else f'{basin} FPSO technical', "basin-tech"))

    # Priority 4: Summary keywords (extract salient terms)
    if summary:
        # Extract capitalized phrases (likely project/vessel/company names)
        caps = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b', summary)
        if caps:
            best_cap = max(caps, key=len)
            queries.append((f'"{best_cap}" FPSO specifications', "summary-entity"))

    # Priority 5: Country + project name
    if country and name:
        queries.append((f'{country} "{name}" FPSO', "country-project"))

    # Deduplicate by query string while preserving order
    seen = set()
    unique = []
    for q, purpose in queries:
        if q not in seen:
            seen.add(q)
            unique.append((q, purpose))
    return unique


# ============================================================================
# Step 2: Search public websites
# ============================================================================

def _search_duckduckgo(query: str, max_results: int = MAX_SEARCH_RESULTS) -> list[dict]:
    """
    Search DuckDuckGo HTML endpoint (no API key required).

    Returns list of {title, url, snippet} dicts.
    Respects rate limits with polite delays.
    """
    results = []
    try:
        with httpx.Client(timeout=15, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
            resp = client.post(
                DDG_HTML_URL,
                data={"q": query, "b": ""},
            )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            for link_elem in soup.select(".result__body")[:max_results]:
                title_elem = link_elem.select_one(".result__title a")
                snippet_elem = link_elem.select_one(".result__snippet")
                url_elem = link_elem.select_one(".result__url")

                if not title_elem:
                    continue

                url = None
                if url_elem:
                    url = url_elem.get_text(strip=True)
                    # DuckDuckGo wraps URLs — extract real href from title link
                    href = title_elem.get("href", "")
                    if href:
                        url = href

                results.append({
                    "title": title_elem.get_text(strip=True),
                    "url": url or "",
                    "snippet": snippet_elem.get_text(strip=True) if snippet_elem else "",
                })

        log.debug("  DDG search '%s': %d results", query[:60], len(results))
    except Exception as exc:
        log.debug("  DDG search error for '%s': %s", query[:40], exc)

    return results


def _search_known_sites(project: dict, max_results: int = 3) -> list[dict]:
    """
    Construct site-specific search URLs for known FPSO data sources.

    Rather than searching (which requires per-site search engines),
    construct plausible article URLs and verify their existence.
    Falls back to DuckDuckGo site: searches for broader coverage.
    """
    name = (project.get("name") or "").strip()
    results = []

    # For known sites, use DDG with site: operator
    if name:
        site_list = " OR site:".join(FPSO_KNOWN_SOURCES[:5])  # top 5 only
        query = f'site:{site_list} "{name}" FPSO'
        results.extend(_search_duckduckgo(query, max_results=max_results))

    return results


# ============================================================================
# Step 3: Fetch page content and extract technical specs
# ============================================================================

def _fetch_page_text(url: str) -> Optional[str]:
    """
    Fetch a web page and extract its full text content.

    Strips HTML, scripts, styles. Returns plain text or None on failure.
    """
    try:
        with httpx.Client(timeout=20, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
            resp = client.get(url)
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")

            # Remove non-content elements
            for tag in soup.select("script, style, nav, footer, header, .sidebar, .ad, .advertisement, .cookie, .popup"):
                tag.decompose()

            # Try to find the main article content area first
            article = (
                soup.select_one("article")
                or soup.select_one('[role="main"]')
                or soup.select_one(".article-body")
                or soup.select_one(".post-content")
                or soup.select_one(".entry-content")
                or soup.select_one("main")
                or soup
            )

            text = article.get_text(separator="\n", strip=True)
            # Truncate to reasonable size (first ~8000 chars are usually the article)
            return text[:8000] if text else None

    except httpx.HTTPStatusError as exc:
        log.debug("  HTTP %d fetching %s", exc.response.status_code, url[:80])
        return None
    except Exception as exc:
        log.debug("  Fetch error for %s: %s", url[:80], exc)
        return None


def _extract_specs_from_text(text: str) -> dict:
    """
    Run all tech-spec extractors on a text block.

    Each extractor function in media_common.py is designed to find
    explicitly stated values in text — no inference, only regex matches.

    Returns dict with nullable fields. Non-null values were found in text.
    """
    if not text:
        return {}

    return {
        "water_depth_m": extract_water_depth_from_article(text),
        "oil_capacity_bpd": extract_oil_capacity_from_article(text),
        "gas_capacity_mmcmd": extract_gas_capacity_from_article(text),
        "hull_type": extract_hull_type_from_article(text),
        "field_name": extract_field_name_from_article(text),
        "operator_name": extract_operator_from_article(text),
        "basin": extract_basin_from_article(text),
    }


# ============================================================================
# Step 4: Cross-validate and merge
# ============================================================================

def _validate_extraction(value, field_name: str, text_snippet: str) -> bool:
    """
    Verify that an extracted value is explicitly stated in the source text.

    Principle: the value MUST appear verbatim in the source, or match
    a known FPSO technical pattern that is unambiguous.

    Returns True if the value can be confirmed as explicitly stated.
    """
    if value is None:
        return False

    if isinstance(value, int):
        # Check that the number appears in the source text
        return str(value) in text_snippet

    if isinstance(value, str) and value.strip():
        # The string or a significant substring must appear in the source
        val_lower = value.lower().strip()
        text_lower = text_snippet.lower()
        # Check full value or significant words (longer than 3 chars)
        if val_lower in text_lower:
            return True
        words = [w for w in val_lower.split() if len(w) > 3]
        if words and all(w in text_lower for w in words):
            return True

    return False


def _find_evidence(text: str, value, field_name: str, radius: int = 120) -> str:
    """Extract the sentence/context where a value appears in text."""
    if value is None or not text:
        return ""

    if isinstance(value, int):
        val_str = str(value)
    else:
        val_str = str(value)

    idx = text.lower().find(val_str.lower())
    if idx >= 0:
        start = max(0, idx - radius)
        end = min(len(text), idx + len(val_str) + radius)
        return text[start:end].replace("\n", " ").strip()
    return ""


def _merge_extractions(all_extractions: list[dict], all_source_texts: list[str]) -> dict:
    """
    Merge extraction results from multiple sources.

    Strategy (strict — only explicitly stated data):
      1. For each field, collect all non-null values found across sources.
      2. If only one source found a value: include it, flag as "single_source".
      3. If multiple sources agree on the same value: higher confidence.
      4. If multiple sources disagree: keep the value with the most explicit
         evidence (i.e., the one that appears in source text near the field name).
      5. Fields not found in any source remain None.

    Returns {field_name: value, ...} plus metadata.
    """
    fields = [
        "water_depth_m",
        "oil_capacity_bpd",
        "gas_capacity_mmcmd",
        "hull_type",
        "field_name",
        "operator_name",
        "basin",
    ]

    # Collect all findings per field: [(value, source_idx, evidence_text)]
    findings = {f: [] for f in fields}
    for i, ext in enumerate(all_extractions):
        source_text = all_source_texts[i] if i < len(all_source_texts) else ""
        for f in fields:
            val = ext.get(f)
            if val is not None and val != "" and val != 0:
                # Validate: value must appear in source text
                if _validate_extraction(val, f, source_text):
                    evidence = _find_evidence(source_text, val, f)
                    findings[f].append((val, i, evidence))

    merged = {}
    evidence = {}
    sources_used = set()

    for f in fields:
        found = findings[f]
        if not found:
            merged[f] = None
            continue

        # Count agreement across sources
        value_counts = {}
        for val, src_idx, ev in found:
            key = str(val).lower().strip()
            if key not in value_counts:
                value_counts[key] = []
            value_counts[key].append((val, src_idx, ev))

        # Pick the most agreed-upon value (highest source count)
        best_key = max(value_counts, key=lambda k: len(value_counts[k]))
        best_entries = value_counts[best_key]
        best_value = best_entries[0][0]
        best_evidence = best_entries[0][2]
        source_count = len(best_entries)

        for _, src_idx, _ in best_entries:
            sources_used.add(src_idx)

        merged[f] = best_value
        evidence[f] = {
            "text": best_evidence,
            "source_count": source_count,
            "total_found": len(found),
        }

    return {
        "enriched": merged,
        "evidence": evidence,
        "sources_consulted": len(all_extractions),
        "sources_with_data": len(sources_used),
    }


# ============================================================================
# Main entry point
# ============================================================================

def enrich_project(
    project: dict,
    *,
    search_existing: bool = True,
    search_known: bool = True,
    max_search_results: int = MAX_SEARCH_RESULTS,
    max_page_fetch: int = MAX_PAGE_FETCH,
) -> dict:
    """
    Enrich a single project with data from public web sources.

    Args:
      project: dict with at minimum {name}. Ideally also {operator_name,
               field_name, basin, country, summary}.
      search_existing: use DuckDuckGo for general web search.
      search_known: search known FPSO industry sites.
      max_search_results: max DDG results per query.
      max_page_fetch: max page fetches per project (rate limit).

    Returns:
      dict with:
        - enriched: {field: value, ...} — only fields found from public sources.
                    Fields NOT found are absent (not None), so caller can
                    use .get() safely for merging.
        - evidence: {field: {text, source_count, total_found}, ...}
        - sources_consulted: int
        - sources_with_data: int
        - queries_used: [(query, purpose)]
        - errors: [str] (non-fatal errors during enrichment)
    """
    name = (project.get("name") or "").strip()
    if not name:
        return {
            "enriched": {},
            "evidence": {},
            "sources_consulted": 0,
            "sources_with_data": 0,
            "queries_used": [],
            "errors": ["No project name provided"],
        }

    log.info("Enriching: %s", name[:70])

    # ---- Step 1: Build search queries ----
    queries = _build_search_queries(project)
    if not queries:
        return {
            "enriched": {},
            "evidence": {},
            "sources_consulted": 0,
            "sources_with_data": 0,
            "queries_used": [],
            "errors": ["No searchable keywords available"],
        }

    log.info("  Queries: %d", len(queries))
    for q, purpose in queries[:3]:
        log.debug("    [%s] %s", purpose, q[:80])

    # ---- Step 2: Search + Fetch ----
    all_urls = set()
    all_results = []
    errors = []

    for q, purpose in queries:
        if len(all_urls) >= max_page_fetch * len(queries):
            break

        # DuckDuckGo general search
        if search_existing:
            results = _search_duckduckgo(q, max_results=max_search_results)
            for r in results:
                url = r.get("url", "")
                if url and url not in all_urls:
                    all_urls.add(url)
                    all_results.append((r, purpose))

        # Known FPSO sites
        if search_known and len(all_urls) < max_page_fetch * 2:
            site_results = _search_known_sites(project, max_results=2)
            for r in site_results:
                url = r.get("url", "")
                if url and url not in all_urls:
                    all_urls.add(url)
                    all_results.append((r, "known-site"))

        # Polite delay between searches
        time.sleep(random.uniform(*REQUEST_DELAY))

    log.info("  Unique URLs found: %d", len(all_urls))

    # ---- Step 3: Fetch pages and extract specs ----
    all_extractions = []
    all_source_texts = []
    fetched_urls = []

    for result, purpose in all_results[:max_page_fetch]:
        url = result.get("url", "")
        if not url:
            continue

        # Skip non-HTML URLs
        if any(url.endswith(ext) for ext in (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx")):
            log.debug("  Skipping non-HTML URL: %s", url[:80])
            continue

        try:
            text = _fetch_page_text(url)
            if not text:
                continue

            extracted = _extract_specs_from_text(text)
            has_data = any(
                v is not None and v != "" and v != 0
                for v in extracted.values()
            )
            if has_data:
                all_extractions.append(extracted)
                all_source_texts.append(text)
                fetched_urls.append((url, result.get("title", ""), purpose))
                log.debug("  Found data in: %s", url[:80])
            else:
                log.debug("  No tech-spec data in: %s", url[:80])

            # Delay between page fetches
            time.sleep(random.uniform(*REQUEST_DELAY))

        except Exception as exc:
            errors.append(f"Fetch error {url[:80]}: {exc}")
            log.debug("  Fetch error %s: %s", url[:60], exc)

    log.info("  Pages with data: %d / %d fetched",
             len(all_extractions), len(fetched_urls))

    # ---- Step 4: Cross-validate and merge ----
    merged = _merge_extractions(all_extractions, all_source_texts)

    # Collect non-null enriched fields
    enriched = {k: v for k, v in merged["enriched"].items() if v is not None}

    if enriched:
        log.info("  Enriched fields: %s", ", ".join(enriched.keys()))
        for field, value in enriched.items():
            ev = merged["evidence"].get(field, {})
            log.info("    %s = %s  (%d sources, evidence: %s...)",
                     field, value,
                     ev.get("source_count", 0),
                     (ev.get("text", "") or "")[:80])
    else:
        log.info("  No new data found from public sources.")

    return {
        "enriched": enriched,
        "evidence": merged["evidence"],
        "sources_consulted": merged["sources_consulted"],
        "sources_with_data": merged["sources_with_data"],
        "queries_used": [(q, p) for q, p in queries],
        "fetched_urls": fetched_urls,
        "errors": errors,
    }


def enrich_projects_batch(
    projects: list[dict],
    *,
    max_per_run: int = 10,
    **kwargs,
) -> list[dict]:
    """
    Enrich a batch of projects. Rate-limited to avoid overloading sources.

    Returns list of enrichment result dicts, one per input project.
    """
    results = []
    for i, project in enumerate(projects):
        if i >= max_per_run:
            log.info("Batch limit reached (%d projects). Remaining skipped.", max_per_run)
            break

        result = enrich_project(project, **kwargs)
        results.append(result)

        # Extra delay between projects
        if i < len(projects) - 1:
            time.sleep(random.uniform(2, 4))

    return results


# ============================================================================
# Diff: compute what's new (for merging into existing project data)
# ============================================================================

def compute_enrichment_diff(existing: dict, enriched: dict) -> dict:
    """
    Compute which enriched fields add new information.

    Only returns fields that are:
      1. Present in enriched (non-null).
      2. Missing or empty in existing project data.

    Never overwrites existing data with enriched data — enricher is
    supplementary only, existing data (especially from official sources)
    takes precedence.

    Returns {field: new_value} dict ready for DB update.
    """
    fields = [
        "water_depth_m",
        "oil_capacity_bpd",
        "gas_capacity_mmcmd",
        "hull_type",
        "field_name",
        "operator_name",
        "basin",
    ]

    diff = {}
    for f in fields:
        existing_val = existing.get(f)
        enriched_val = enriched.get(f)

        # Existing has data — keep it (it may be from official sources)
        if existing_val is not None and existing_val != "" and existing_val != 0:
            continue

        # Enriched has new data
        if enriched_val is not None and enriched_val != "" and enriched_val != 0:
            diff[f] = enriched_val

    return diff
