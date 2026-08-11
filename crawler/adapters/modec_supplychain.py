#!/usr/bin/env python3
"""
MODEC Supply Chain 适配器 — P1 企业来源适配器
================================================

按《FPSO项目可用信息源使用手册》P1 要求实现：

来源信息:
  名称: MODEC Supply Chain
  URL:  https://www.modec.com/business/supplychain/
  类型: CONTRACTOR
  优先级: P1
  层级: 3（采购链拆解）
  接入方式: HTML — 采集公开页面文本和链接

功能:
  1. 访问 MODEC 供应链页面，采集供应商注册入口、采购理念、承包商合作方式。
  2. 提取页面文本内容和所有相关链接。
  3. 事件类型: PROCUREMENT_CHAIN。
  4. 输出到 candidate_events 表，review_status='pending'。
  5. 保存原始 HTML 到 crawler/data/modec/ 目录，记录 SHA256。

合规:
  - 只采集公开页面文本和链接，不自动登录、不提交表单、不绕过验证。
  - 请求间隔 5-10 秒。
  - 支持 --dry-run 和 --local-only 模式。

Usage:
  python crawler/adapters/modec_supplychain.py                 # 完整运行
  python crawler/adapters/modec_supplychain.py --dry-run       # 仅采集，不写入数据库
  python crawler/adapters/modec_supplychain.py --local-only    # 保存文件到本地，不写入 Supabase
  python crawler/adapters/modec_supplychain.py --test          # 自测
"""

import hashlib
import json
import logging
import os
import re
import sys
import time
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from adapters.media_common import extract_procurement, _safe_decode_response

# ---- Paths ---------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent  # crawler/
DATA_DIR = BASE_DIR / "data" / "modec"

# ---- Config --------------------------------------------------------------

load_dotenv(BASE_DIR.parent / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("VITE_SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY")

SOURCE_NAME = "MODEC Supply Chain"
SOURCE_URL = "https://www.modec.com/business/supplychain/"
EVENT_TYPE = "PROCUREMENT_CHAIN"

# Additional MODEC pages to crawl for procurement context
ADDITIONAL_URLS = [
    "https://www.modec.com/business/supplychain/",
    "https://www.modec.com/business/",
    "https://www.modec.com/about/policy/procurement/",
]

MIN_REQUEST_DELAY_SEC = 5.0
MAX_REQUEST_DELAY_SEC = 10.0

USER_AGENT = (
    "Mozilla/5.0 (compatible; FPSOCrawler/1.0; +MODEC-SupplyChain-Adapter)"
)

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")
NOW_ISO = datetime.now(timezone.utc).isoformat()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("modec-supplychain-adapter")


# ============================================================================
# 1. HTTP 会话 & 页面获取
# ============================================================================


def build_session() -> requests.Session:
    """Build a requests Session with appropriate headers."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5,ja;q=0.3",
        "Accept-Encoding": "gzip, deflate, br",
    })
    return session


def fetch_page(url: str, session: requests.Session) -> Optional[str]:
    """Fetch a page and return its HTML text. Returns None on failure."""
    try:
        log.info("Fetching %s ...", url)
        resp = session.get(url, timeout=60)
        resp.raise_for_status()
        log.info("  HTTP %d, %d bytes", resp.status_code, len(resp.content))
        return _safe_decode_response(resp)
    except requests.exceptions.HTTPError as e:
        log.warning("  HTTP %s — %s",
                     e.response.status_code if hasattr(e, 'response') else '?', url)
        return None
    except requests.exceptions.RequestException as e:
        log.warning("  Request failed: %s — %s", e, url)
        return None


# ============================================================================
# 2. 页面解析
# ============================================================================


def extract_text_sections(soup: BeautifulSoup) -> list[dict]:
    """
    Extract text content organized by heading/section.
    Returns list of {heading, content, char_count} dicts.
    """
    sections = []

    # Try to find main content area
    main = (
        soup.find("main")
        or soup.find("article")
        or soup.find("div", class_=re.compile(r"content|main|body|entry", re.I))
        or soup
    )

    # Extract headings and their following content
    for tag in main.find_all(["h1", "h2", "h3", "h4"]):
        heading = tag.get_text(strip=True)
        content_parts = []

        sibling = tag.find_next_sibling()
        while sibling and sibling.name not in ("h1", "h2", "h3", "h4"):
            if sibling.name in ("p", "li", "div", "span", "td", "dt", "dd"):
                text = sibling.get_text(strip=True)
                if text and len(text) > 10:
                    content_parts.append(text)
            sibling = sibling.find_next_sibling()

        content = "\n".join(content_parts)
        if heading or content:
            sections.append({
                "heading": heading,
                "content": content[:2000],
                "char_count": len(content),
            })

    # If no structured sections, collect all paragraphs
    if not sections:
        paragraphs = main.find_all("p")
        all_text = []
        for p in paragraphs:
            text = p.get_text(strip=True)
            if text and len(text) > 20:
                all_text.append(text)
        if all_text:
            sections.append({
                "heading": "Page Content",
                "content": "\n".join(all_text)[:2000],
                "char_count": sum(len(t) for t in all_text),
            })

    return sections


def extract_links(soup: BeautifulSoup, base_url: str) -> list[dict]:
    """Extract all meaningful links from the page."""
    links = []
    seen_urls = set()

    for a_tag in soup.find_all("a", href=True):
        href = a_tag.get("href", "").strip()
        text = a_tag.get_text(strip=True)

        if not href or href.startswith("javascript:") or href.startswith("mailto:"):
            continue
        if href == "#" or not text:
            continue

        full_url = urljoin(base_url, href)
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        parsed = urlparse(full_url)
        domain = parsed.netloc.lower()

        links.append({
            "text": text[:200],
            "url": full_url[:2048],
            "domain": domain,
            "is_internal": "modec.com" in domain,
            "is_pdf": href.lower().endswith(".pdf"),
        })

    return links


def extract_supply_keywords(soup: BeautifulSoup) -> list[str]:
    """
    Extract procurement/supply-chain related keywords and topics from the page.
    Looks for terms like 'supplier', 'procurement', 'registration', 'RFQ', etc.
    """
    text = soup.get_text().lower()
    keywords_found = []

    procurement_terms = [
        "supplier registration", "supplier qualification", "procurement",
        "supply chain", "prequalification", "vendor registration",
        "request for quotation", "rfq", "tender", "bidding",
        "contract award", "purchase order", "framework agreement",
        "local content", "hse requirements", "quality management",
        "supplier code of conduct", "supplier diversity",
        "sourcing", "category management", "strategic procurement",
    ]

    for term in procurement_terms:
        if term in text:
            keywords_found.append(term)

    return keywords_found


# ============================================================================
# 3. 内容摘要生成
# ============================================================================


def build_page_summary(sections: list[dict], links: list[dict],
                       keywords: list[str]) -> str:
    """Build a structured summary of the page content."""
    parts = []

    headings = [s["heading"] for s in sections if s["heading"]]
    if headings:
        parts.append(f"Sections: {', '.join(headings[:10])}")

    total_chars = sum(s["char_count"] for s in sections)
    parts.append(f"Text: {total_chars:,} chars in {len(sections)} sections")

    internal = [l for l in links if l["is_internal"]]
    external = [l for l in links if not l["is_internal"]]
    parts.append(f"Links: {len(internal)} internal, {len(external)} external, "
                 f"{sum(1 for l in links if l['is_pdf'])} PDFs")

    if keywords:
        parts.append(f"Procurement terms: {', '.join(keywords[:15])}")

    if sections and sections[0].get("content"):
        parts.append(f"Preview: {sections[0]['content'][:300]}")

    return " | ".join(parts)


# ============================================================================
# 4. candidate_events 输出
# ============================================================================


def build_candidate_events(sections: list[dict], links: list[dict],
                           keywords: list[str], raw_html_path: str,
                           html_sha256: str, url_fetched: str) -> list[dict]:
    """Build candidate_events records from extracted data."""
    events = []
    summary = build_page_summary(sections, links, keywords)

    all_text = " ".join(s["content"] for s in sections if s.get("content"))
    evidence = all_text[:500] if all_text else summary[:500]

    raw_meta = {
        "source_url_fetched": url_fetched,
        "html_sha256": html_sha256,
        "sections_count": len(sections),
        "links_count": len(links),
        "keywords_found": keywords,
        "sections": [{"heading": s["heading"], "char_count": s["char_count"]}
                      for s in sections[:20]],
        "internal_links": [
            {"text": l["text"], "url": l["url"]}
            for l in links if l["is_internal"]
        ][:30],
    }

    # Main event
    procurement_main = extract_procurement(all_text) if all_text else ""
    events.append({
        "project_name_raw": "MODEC Supply Chain Registration",
        "country": "Brazil",
        "summary": summary[:2000],
        "source_name": SOURCE_NAME,
        "source_url": url_fetched[:2048],
        "review_status": "pending",
        "event_type": EVENT_TYPE,
        "fetched_at": NOW_ISO,
        "evidence_quote": evidence[:500],
        "procurement_chain": procurement_main,
        "raw_json": json.dumps(raw_meta, ensure_ascii=False),
    })

    # Per-section events for substantial sections
    for section in sections:
        if section["char_count"] > 100 and section["heading"]:
            sec_meta = {
                "section_heading": section["heading"],
                "content": section["content"][:500],
                "html_sha256": html_sha256,
                "source_url_fetched": url_fetched,
            }
            sec_procurement = extract_procurement(section["content"]) if section.get("content") else ""
            events.append({
                "project_name_raw": f"MODEC: {section['heading'][:200]}",
                "country": "Brazil",
                "summary": section["content"][:500],
                "source_name": SOURCE_NAME,
                "source_url": url_fetched[:2048],
                "review_status": "pending",
                "event_type": EVENT_TYPE,
                "fetched_at": NOW_ISO,
                "evidence_quote": section["content"][:500],
                "procurement_chain": sec_procurement,
                "raw_json": json.dumps(sec_meta, ensure_ascii=False),
            })

    return events


# ============================================================================
# 5. Supabase 写入
# ============================================================================


def get_supabase():
    """Lazy-init Supabase client."""
    from supabase import create_client
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_ANON_KEY must be set in .env. "
            "Use --local-only to skip Supabase writes."
        )
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def insert_candidate_events(events: list[dict], supabase=None) -> int:
    """Write candidate_events rows to Supabase. Returns count inserted."""
    if supabase is None:
        supabase = get_supabase()
    table = supabase.table("candidate_events")
    inserted = 0
    skipped = 0
    for evt in events:
        try:
            # Dedup: skip if (project_name_raw, event_type, summary) already exists
            existing = table.select("id")                 .eq("project_name_raw", evt.get("project_name_raw", ""))                 .eq("event_type", evt.get("event_type", ""))                 .eq("summary", evt.get("summary", ""))                 .limit(1)                 .execute()
            if existing.data:
                skipped += 1
                continue

            table.insert(evt).execute()
            inserted += 1
        except Exception:
            log.warning("Insert error for %s",
                         evt.get("project_name_raw", "?"), exc_info=True)
    if skipped:
        log.info("Dedup: skipped %d duplicate(s)", skipped)
    return inserted


def save_snapshot_to_registry(filepath: str, sha256: str,
                              record_count: int, supabase=None) -> bool:
    """Save snapshot metadata to snapshot_registry table."""
    if supabase is None:
        try:
            supabase = get_supabase()
        except RuntimeError:
            return False
    try:
        table = supabase.table("snapshot_registry")
        record = {
            "source_name": SOURCE_NAME,
            "source_url": SOURCE_URL,
            "snapshot_date": TODAY,
            "fetched_at": NOW_ISO,
            "file_path": str(filepath),
            "file_hash_sha256": sha256,
            "record_count": record_count,
            "source_type": "CONTRACTOR",
            "tier": 3,
            "priority": "P1",
            "country_focus": "Brazil",
            "access_method": "HTML",
        }
        table.insert(record).execute()
        log.info("Saved snapshot metadata to snapshot_registry")
        return True
    except Exception:
        log.warning("Could not write to snapshot_registry. Local snapshot is sufficient.")
        return False


def save_to_source_documents(file_path, file_hash_sha256, file_type,
                             file_size_bytes, original_url="",
                             download_url="", publication_date="",
                             supabase=None) -> bool:
    """Save downloaded file metadata to source_documents table."""
    if supabase is None:
        try:
            supabase = get_supabase()
        except RuntimeError:
            return False
    try:
        table = supabase.table("source_documents")
        record = {
            "file_name": Path(file_path).name,
            "file_path": str(file_path),
            "file_hash_sha256": file_hash_sha256,
            "file_type": file_type,
            "file_size_bytes": file_size_bytes,
            "publication_date": publication_date or TODAY,
            "fetched_at": NOW_ISO,
            "original_url": original_url or SOURCE_URL,
            "download_url": download_url or "",
        }
        table.insert(record).execute()
        log.info("Saved to source_documents: %s (%s, %d bytes)",
                 Path(file_path).name, file_type, file_size_bytes)
        return True
    except Exception:
        log.debug("Could not write to source_documents (table may not exist yet).")
        return False


# ============================================================================
# 6. 本地存储
# ============================================================================


def save_raw_html(html: str, label: str = "main") -> tuple[Path, str]:
    """Save raw HTML for audit. Returns (path, sha256)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    safe_label = re.sub(r"[^\w\-]", "_", label)
    filepath = DATA_DIR / f"{TODAY}_modec_{safe_label}.html"
    filepath.write_text(html, encoding="utf-8")
    sha256 = hashlib.sha256(html.encode("utf-8")).hexdigest()
    hash_path = DATA_DIR / f"{TODAY}_modec_{safe_label}.html.sha256"
    hash_path.write_text(f"{sha256}  {TODAY}_modec_{safe_label}.html\n")
    log.info("Saved raw HTML to %s (SHA256=%s)", filepath, sha256[:16])
    return filepath, sha256


def save_local_snapshot(data: dict) -> Path:
    """Save extracted metadata as JSON snapshot."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    filepath = DATA_DIR / f"{TODAY}_snapshot.json"
    data["date"] = TODAY
    data["fetched_at"] = NOW_ISO
    data["source_url"] = SOURCE_URL
    filepath.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Saved local snapshot to %s", filepath)
    return filepath


# ============================================================================
# 7. 主流程
# ============================================================================


def run_adapter(dry_run: bool = False, local_only: bool = False,
                supabase=None) -> dict:
    """Adapter main flow."""
    log.info("=" * 60)
    log.info("MODEC Supply Chain Adapter — %s", TODAY)
    log.info("=" * 60)

    session = build_session()

    all_sections = []
    all_links = []
    all_keywords = []
    html_paths = {}
    html_sha256_main = ""

    for i, url in enumerate(ADDITIONAL_URLS):
        if i > 0:
            delay = random.uniform(MIN_REQUEST_DELAY_SEC, MAX_REQUEST_DELAY_SEC)
            log.info("Waiting %.1fs (polite delay)...", delay)
            time.sleep(delay)

        html = fetch_page(url, session)
        if html is None:
            log.warning("  Failed to fetch: %s", url)
            continue

        label = url.rstrip("/").split("/")[-1] or "index"
        html_path, sha = save_raw_html(html, label)
        html_paths[label] = str(html_path)
        if i == 0:
            html_sha256_main = sha

        # Save to source_documents for audit trail
        if not dry_run and not local_only:
            save_to_source_documents(
                html_path, sha, "HTML",
                len(html.encode("utf-8")),
                original_url=url,
                supabase=supabase,
            )

        soup = BeautifulSoup(html, "html.parser")
        sections = extract_text_sections(soup)
        links = extract_links(soup, url)
        keywords = extract_supply_keywords(soup)

        log.info("  [%s] Sections: %d, Links: %d, Keywords: %d",
                 label, len(sections), len(links), len(keywords))

        all_sections.extend(sections)
        all_links.extend(links)
        all_keywords.extend(keywords)

    if not all_sections and not all_links:
        log.warning("No content extracted from any URL.")
        return {
            "mode": "dry_run" if dry_run else ("local_only" if local_only else "full"),
            "total_sections": 0, "total_links": 0,
            "error": "No content extracted", "html_paths": html_paths,
        }

    unique_keywords = sorted(set(all_keywords))

    events = build_candidate_events(
        all_sections, all_links, unique_keywords,
        html_paths.get("supplychain", ""), html_sha256_main,
        ADDITIONAL_URLS[0],
    )
    log.info("  Candidate events: %d", len(events))

    snapshot_data = {
        "sections": [{"heading": s["heading"], "content": s["content"][:200]}
                      for s in all_sections],
        "links": all_links[:50],
        "keywords": unique_keywords,
        "html_paths": html_paths,
        "candidate_events_count": len(events),
    }
    snapshot_path = save_local_snapshot(snapshot_data)

    inserted = 0
    write_to_db = not dry_run and not local_only
    if write_to_db and events:
        try:
            inserted = insert_candidate_events(events, supabase)
            log.info("  Inserted %d candidate_events rows", inserted)
        except RuntimeError as e:
            log.warning("  Skipping Supabase write: %s", e)

    if write_to_db and html_sha256_main:
        try:
            save_snapshot_to_registry(str(snapshot_path), html_sha256_main,
                                      len(events), supabase)
        except Exception:
            log.debug("snapshot_registry write skipped", exc_info=True)

    mode_str = "dry_run" if dry_run else ("local_only" if local_only else "full")
    result = {
        "mode": mode_str,
        "total_sections": len(all_sections),
        "total_links": len(all_links),
        "total_keywords": len(unique_keywords),
        "candidate_events": len(events),
        "inserted": inserted,
        "html_paths": html_paths,
        "html_sha256_main": html_sha256_main,
        "snapshot_path": str(snapshot_path),
        "data_dir": str(DATA_DIR),
    }

    log.info("=" * 60)
    log.info("Run complete. Mode: %s", mode_str)
    log.info("  Sections: %d, Links: %d, Keywords: %d",
             result["total_sections"], result["total_links"], result["total_keywords"])
    log.info("  Candidate events: %d (inserted: %d)", result["candidate_events"], inserted)
    return result


# ============================================================================
# 8. 自测
# ============================================================================


def run_test():
    """Self-test: fetch page → parse → show summary."""
    log.info("=" * 60)
    log.info("SELF-TEST: MODEC Supply Chain Adapter")
    log.info("=" * 60)

    session = build_session()

    print("\n" + "─" * 60)
    print("Step 1: Fetch page")
    print("─" * 60)
    html = fetch_page(ADDITIONAL_URLS[0], session)
    if html is None:
        print("  FAILED: Could not fetch page.")
        sys.exit(1)
    print(f"  Downloaded: {len(html):,} bytes")
    html_hash = hashlib.sha256(html.encode("utf-8")).hexdigest()
    print(f"  HTML SHA256: {html_hash}")

    html_path, _ = save_raw_html(html, "supplychain")
    print(f"  Saved HTML: {html_path}")

    print("\n" + "─" * 60)
    print("Step 2: Parse Content")
    print("─" * 60)
    soup = BeautifulSoup(html, "html.parser")
    sections = extract_text_sections(soup)
    links = extract_links(soup, ADDITIONAL_URLS[0])
    keywords = extract_supply_keywords(soup)

    print(f"  Sections: {len(sections)}")
    for s in sections[:5]:
        print(f"    [{s['char_count']} chars] {s['heading'][:80]}")
    print(f"  Links: {len(links)} (internal: {sum(1 for l in links if l['is_internal'])})")
    print(f"  Procurement keywords: {keywords}")

    print("\n" + "─" * 60)
    print("Step 3: Candidate Events")
    print("─" * 60)
    events = build_candidate_events(sections, links, keywords,
                                    str(html_path), html_hash, ADDITIONAL_URLS[0])
    print(f"  Events: {len(events)}")
    for i, evt in enumerate(events[:3]):
        print(f"\n  Event #{i+1}:")
        print(f"    event_type: {evt['event_type']}")
        print(f"    project_name_raw: {evt['project_name_raw'][:100]}")
        print(f"    summary: {evt['summary'][:150]}")

    print(f"\n{'─' * 60}")
    print("Self-test complete.")
    print("─" * 60)


# ============================================================================
# 9. CLI
# ============================================================================


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="MODEC Supply Chain 适配器 — P1 企业来源适配器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python crawler/adapters/modec_supplychain.py                 # 完整运行
  python crawler/adapters/modec_supplychain.py --test          # 自测
  python crawler/adapters/modec_supplychain.py --dry-run       # 仅采集，不写入数据库
  python crawler/adapters/modec_supplychain.py --local-only    # 仅本地保存
        """,
    )
    parser.add_argument("--test", action="store_true",
                        help="自测: 访问页面 → 解析内容 → 输出候选事件摘要。")
    parser.add_argument("--dry-run", action="store_true",
                        help="仅采集页面、保存文件，不写入数据库。")
    parser.add_argument("--local-only", action="store_true",
                        help="保存文件到本地，不写入 Supabase。")
    args = parser.parse_args()

    if args.test:
        try:
            run_test()
        except Exception as e:
            log.error("Self-test failed: %s", e, exc_info=True)
            sys.exit(1)
        return

    try:
        result = run_adapter(dry_run=args.dry_run, local_only=args.local_only)
    except requests.exceptions.HTTPError as e:
        log.error("HTTP error: %s", e)
        sys.exit(1)
    except Exception as e:
        log.error("Adapter failed: %s", e, exc_info=True)
        sys.exit(1)

    print("\n" + json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
