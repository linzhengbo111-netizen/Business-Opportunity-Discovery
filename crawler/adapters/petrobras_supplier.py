#!/usr/bin/env python3
"""
Petrobras 供应商注册适配器 — P1 企业来源适配器
=================================================

按《FPSO项目可用信息源使用手册》P1 要求实现：

来源信息:
  名称: Petrobras 供应商注册 (Canal Fornecedor)
  URL:  https://canalfornecedor.petrobras.com.br/en/cadastro-de-fornecedores/sobre-o-cadastro-de-fornecedores
  类型: SUPPLIER_PORTAL
  优先级: P1
  层级: 3（采购链拆解）
  接入方式: HTML — 采集公开页面文本和链接

功能:
  1. 访问 Petrobras 供应商注册门户，采集供应商注册要求、供应品类、预审机制。
  2. 提取页面文本内容和所有相关链接。
  3. 事件类型: VENDOR_REGISTRATION_ACTION。
  4. 输出到 candidate_events 表，review_status='pending'。
  5. 保存原始 HTML 到 crawler/data/petrobras/ 目录，记录 SHA256。

合规:
  - 只采集公开页面文本和链接，不自动登录、不提交表单、不绕过验证。
  - 请求间隔 5-10 秒。
  - 支持 --dry-run 和 --local-only 模式。

Usage:
  python crawler/adapters/petrobras_supplier.py                 # 完整运行
  python crawler/adapters/petrobras_supplier.py --dry-run       # 仅采集，不写入数据库
  python crawler/adapters/petrobras_supplier.py --local-only    # 保存文件到本地，不写入 Supabase
  python crawler/adapters/petrobras_supplier.py --test          # 自测
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

# ---- Paths ---------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent  # crawler/
DATA_DIR = BASE_DIR / "data" / "petrobras"

# ---- Config --------------------------------------------------------------

load_dotenv(BASE_DIR.parent / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("VITE_SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY")

SOURCE_NAME = "Petrobras Canal Fornecedor"
SOURCE_URL = "https://canalfornecedor.petrobras.com.br/en/cadastro-de-fornecedores/sobre-o-cadastro-de-fornecedores"
EVENT_TYPE = "VENDOR_REGISTRATION_ACTION"

# Also fetch the Portuguese version (primary) and main landing page
ADDITIONAL_URLS = [
    "https://canalfornecedor.petrobras.com.br/en/cadastro-de-fornecedores/sobre-o-cadastro-de-fornecedores",
    "https://canalfornecedor.petrobras.com.br/pt-br/cadastro-de-fornecedores/sobre-o-cadastro-de-fornecedores",
]

MIN_REQUEST_DELAY_SEC = 5.0
MAX_REQUEST_DELAY_SEC = 10.0

USER_AGENT = (
    "Mozilla/5.0 (compatible; FPSOCrawler/1.0; +Petrobras-Supplier-Adapter)"
)

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")
NOW_ISO = datetime.now(timezone.utc).isoformat()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("petrobras-supplier-adapter")


# ============================================================================
# 1. HTTP 会话 & 页面获取
# ============================================================================


def build_session() -> requests.Session:
    """Build a requests Session with appropriate headers."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5,pt-BR;q=0.3",
        "Accept-Encoding": "gzip, deflate, br",
    })
    return session


def fetch_page(url: str, session: requests.Session) -> Optional[str]:
    """
    Fetch a page and return its HTML text.
    Returns None on failure.
    """
    try:
        log.info("Fetching %s ...", url)
        resp = session.get(url, timeout=60)
        resp.raise_for_status()
        log.info("  HTTP %d, %d bytes", resp.status_code, len(resp.content))
        ct = resp.headers.get("Content-Type", "")
        if "charset" in ct.lower():
            return resp.text
        try:
            return resp.content.decode("utf-8")
        except UnicodeDecodeError:
            return resp.text
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
        or soup.find("div", class_=re.compile(r"content|main|body", re.I))
        or soup
    )

    # Extract headings and their following content
    for tag in main.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        heading = tag.get_text(strip=True)
        content_parts = []

        # Collect text from siblings until next heading
        sibling = tag.find_next_sibling()
        while sibling and sibling.name not in ("h1", "h2", "h3", "h4", "h5", "h6"):
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

    # If no structured sections found, collect all meaningful text
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
    """
    Extract all meaningful links from the page.
    Returns list of {text, url, category} dicts.
    """
    links = []
    seen_urls = set()

    for a_tag in soup.find_all("a", href=True):
        href = a_tag.get("href", "").strip()
        text = a_tag.get_text(strip=True)

        # Skip empty, javascript, anchor-only, mailto
        if not href or href.startswith("javascript:") or href.startswith("mailto:"):
            continue
        if href == "#" or not text:
            continue

        # Resolve relative URLs
        full_url = urljoin(base_url, href)
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        # Only include links to same domain or related Petrobras domains
        parsed = urlparse(full_url)
        domain = parsed.netloc.lower()

        links.append({
            "text": text[:200],
            "url": full_url[:2048],
            "domain": domain,
            "is_internal": "petrobras.com.br" in domain,
            "is_pdf": href.lower().endswith(".pdf"),
        })

    return links


def extract_supplier_categories(soup: BeautifulSoup) -> list[str]:
    """
    Try to identify supplier categories / goods & services classifications.
    Looks for lists, tables, or sections mentioning supply categories.
    """
    categories = []

    # Look for list items in relevant sections
    for ul in soup.find_all("ul"):
        # Check if nearby heading mentions categories
        prev_heading = ul.find_previous(["h1", "h2", "h3", "h4"])
        heading_text = prev_heading.get_text(strip=True).lower() if prev_heading else ""

        if any(kw in heading_text for kw in
               ["categor", "classific", "material", "serviço", "service",
                "supply", "fornec", "goods", "bem", "família"]):
            for li in ul.find_all("li"):
                text = li.get_text(strip=True)
                if text and len(text) > 3:
                    categories.append(text[:200])

    # Also check for definition lists
    for dl in soup.find_all("dl"):
        for dt in dl.find_all("dt"):
            text = dt.get_text(strip=True)
            if text and len(text) > 3:
                categories.append(text[:200])

    return categories[:50]  # cap at 50


# ============================================================================
# 3. 内容摘要生成
# ============================================================================


def build_page_summary(sections: list[dict], links: list[dict],
                       categories: list[str]) -> str:
    """Build a structured summary of the page content."""
    parts = []

    # Section headings found
    headings = [s["heading"] for s in sections if s["heading"]]
    if headings:
        parts.append(f"Sections found: {', '.join(headings[:10])}")

    # Total text
    total_chars = sum(s["char_count"] for s in sections)
    parts.append(f"Total text extracted: {total_chars:,} chars across {len(sections)} sections")

    # Internal links
    internal = [l for l in links if l["is_internal"]]
    external = [l for l in links if not l["is_internal"]]
    parts.append(f"Links: {len(internal)} internal, {len(external)} external, "
                 f"{sum(1 for l in links if l['is_pdf'])} PDFs")

    # Categories
    if categories:
        parts.append(f"Supplier categories identified: {len(categories)}")
        parts.append("Categories: " + "; ".join(categories[:10]))

    # Key content from first section
    if sections and sections[0].get("content"):
        content_preview = sections[0]["content"][:300]
        parts.append(f"Content preview: {content_preview}")

    return " | ".join(parts)


# ============================================================================
# 4. candidate_events 输出
# ============================================================================


def build_candidate_events(sections: list[dict], links: list[dict],
                           categories: list[str], raw_html_path: str,
                           html_sha256: str, url_fetched: str) -> list[dict]:
    """
    Build candidate_events records from extracted data.
    Each significant section or link group becomes a candidate event.
    """
    events = []

    summary = build_page_summary(sections, links, categories)

    # Determine substantive content for evidence_quote
    all_text = " ".join(s["content"] for s in sections if s.get("content"))
    evidence = all_text[:500] if all_text else summary[:500]

    # Build raw metadata
    raw_meta = {
        "source_url_fetched": url_fetched,
        "html_sha256": html_sha256,
        "sections_count": len(sections),
        "links_count": len(links),
        "categories_count": len(categories),
        "sections": [{"heading": s["heading"], "char_count": s["char_count"]}
                      for s in sections[:20]],
        "categories": categories[:30],
        "internal_links": [
            {"text": l["text"], "url": l["url"]}
            for l in links if l["is_internal"]
        ][:30],
    }

    # Main event: page-level registration info
    events.append({
        "project_name_raw": "Petrobras Supplier Registration",
        "country": "Brazil",
        "summary": summary[:2000],
        "source_name": SOURCE_NAME,
        "source_url": url_fetched[:2048],
        "review_status": "pending",
        "event_type": EVENT_TYPE,
        "fetched_at": NOW_ISO,
        "evidence_quote": evidence[:500],
        "raw_json": json.dumps(raw_meta, ensure_ascii=False),
    })

    # Per-section events for significant sections
    for section in sections:
        if section["char_count"] > 100 and section["heading"]:
            sec_meta = {
                "section_heading": section["heading"],
                "content": section["content"][:500],
                "html_sha256": html_sha256,
                "source_url_fetched": url_fetched,
            }
            events.append({
                "project_name_raw": f"Petrobras: {section['heading'][:200]}",
                "country": "Brazil",
                "summary": section["content"][:500],
                "source_name": SOURCE_NAME,
                "source_url": url_fetched[:2048],
                "review_status": "pending",
                "event_type": EVENT_TYPE,
                "fetched_at": NOW_ISO,
                "evidence_quote": section["content"][:500],
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

    for evt in events:
        try:
            table.insert(evt).execute()
            inserted += 1
        except Exception:
            log.warning(
                "Insert error for %s",
                evt.get("project_name_raw", "?"),
                exc_info=True,
            )

    return inserted


def save_snapshot_to_registry(
    filepath: str,
    sha256: str,
    record_count: int,
    supabase=None,
) -> bool:
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
            "source_type": "SUPPLIER_PORTAL",
            "tier": 3,
            "priority": "P1",
            "country_focus": "Brazil",
            "access_method": "HTML",
        }
        table.insert(record).execute()
        log.info("Saved snapshot metadata to snapshot_registry")
        return True
    except Exception:
        log.warning(
            "Could not write to snapshot_registry (table may not exist yet). "
            "Local snapshot is saved and sufficient."
        )
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


def save_raw_html(html: str, label: str = "main") -> Path:
    """Save the raw HTML response for audit purposes."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    safe_label = re.sub(r"[^\w\-]", "_", label)
    filepath = DATA_DIR / f"{TODAY}_petrobras_{safe_label}.html"
    filepath.write_text(html, encoding="utf-8")

    sha256 = hashlib.sha256(html.encode("utf-8")).hexdigest()
    hash_path = DATA_DIR / f"{TODAY}_petrobras_{safe_label}.html.sha256"
    hash_path.write_text(f"{sha256}  {TODAY}_petrobras_{safe_label}.html\n")

    log.info("Saved raw HTML to %s (SHA256=%s)", filepath, sha256[:16])
    return filepath, sha256


def save_local_snapshot(data: dict) -> Path:
    """Save extracted metadata as JSON snapshot for audit/diff."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    filepath = DATA_DIR / f"{TODAY}_snapshot.json"
    data["date"] = TODAY
    data["fetched_at"] = NOW_ISO
    data["source_url"] = SOURCE_URL

    filepath.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info("Saved local snapshot to %s", filepath)
    return filepath


# ============================================================================
# 7. 主流程
# ============================================================================


def run_adapter(
    dry_run: bool = False,
    local_only: bool = False,
    supabase=None,
) -> dict:
    """
    Adapter main flow.

    Args:
        dry_run: Parse & save files, but don't write to Supabase.
        local_only: Save files locally, don't write to Supabase.
        supabase: Supabase client (optional).

    Returns:
        Result summary dict.
    """
    log.info("=" * 60)
    log.info("Petrobras Supplier Registration Adapter — %s", TODAY)
    log.info("=" * 60)

    session = build_session()

    all_sections = []
    all_links = []
    all_categories = []
    html_paths = {}
    html_sha256_main = ""

    # Fetch each URL
    for i, url in enumerate(ADDITIONAL_URLS):
        if i > 0:
            delay = random.uniform(MIN_REQUEST_DELAY_SEC, MAX_REQUEST_DELAY_SEC)
            log.info("Waiting %.1fs (polite delay)...", delay)
            time.sleep(delay)

        html = fetch_page(url, session)
        if html is None:
            log.warning("  Failed to fetch: %s", url)
            continue

        # Save raw HTML
        label = "en" if "/en/" in url else "pt"
        html_path, sha = save_raw_html(html, label)
        html_paths[label] = str(html_path)
        if label == "en":
            html_sha256_main = sha

        # Save to source_documents for audit trail
        if not dry_run and not local_only:
            save_to_source_documents(
                html_path, sha, "HTML",
                len(html.encode("utf-8")),
                original_url=url,
                supabase=supabase,
            )

        # Parse
        soup = BeautifulSoup(html, "html.parser")
        sections = extract_text_sections(soup)
        links = extract_links(soup, url)
        categories = extract_supplier_categories(soup)

        log.info("  [%s] Sections: %d, Links: %d, Categories: %d",
                 label, len(sections), len(links), len(categories))

        all_sections.extend(sections)
        all_links.extend(links)
        all_categories.extend(categories)

    if not all_sections and not all_links:
        log.warning("No content extracted from any URL.")
        return {
            "mode": "dry_run" if dry_run else ("local_only" if local_only else "full"),
            "total_sections": 0,
            "total_links": 0,
            "error": "No content extracted",
            "html_paths": html_paths,
        }

    # Deduplicate categories
    unique_categories = list(dict.fromkeys(all_categories))

    # Build candidate events
    events = build_candidate_events(
        all_sections, all_links, unique_categories,
        html_paths.get("en", ""), html_sha256_main,
        ADDITIONAL_URLS[0],
    )

    log.info("  Candidate events: %d", len(events))

    # Save local snapshot
    snapshot_data = {
        "sections": [{"heading": s["heading"], "content": s["content"][:200]}
                      for s in all_sections],
        "links": all_links[:50],
        "categories": unique_categories,
        "html_paths": html_paths,
        "candidate_events_count": len(events),
    }
    snapshot_path = save_local_snapshot(snapshot_data)

    # Write to Supabase (unless dry_run or local_only)
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
            save_snapshot_to_registry(
                str(snapshot_path),
                html_sha256_main,
                len(events),
                supabase,
            )
        except Exception:
            log.debug("snapshot_registry write skipped", exc_info=True)

    mode_str = "dry_run" if dry_run else ("local_only" if local_only else "full")
    result = {
        "mode": mode_str,
        "total_sections": len(all_sections),
        "total_links": len(all_links),
        "total_categories": len(unique_categories),
        "candidate_events": len(events),
        "inserted": inserted,
        "html_paths": html_paths,
        "html_sha256_main": html_sha256_main,
        "snapshot_path": str(snapshot_path),
        "data_dir": str(DATA_DIR),
    }

    log.info("=" * 60)
    log.info("Run complete.")
    log.info("  Mode: %s", mode_str)
    log.info("  Sections: %d, Links: %d, Categories: %d",
             result["total_sections"], result["total_links"], result["total_categories"])
    log.info("  Candidate events: %d (inserted: %d)", result["candidate_events"], inserted)

    return result


# ============================================================================
# 8. 自测
# ============================================================================


def run_test():
    """Self-test: fetch page → parse → show summary."""
    log.info("=" * 60)
    log.info("SELF-TEST: Petrobras Supplier Registration Adapter")
    log.info("=" * 60)

    session = build_session()

    # Fetch
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

    # Save HTML
    html_path, _ = save_raw_html(html, "en")
    print(f"  Saved HTML: {html_path}")

    # Parse
    print("\n" + "─" * 60)
    print("Step 2: Parse Content")
    print("─" * 60)

    soup = BeautifulSoup(html, "html.parser")
    sections = extract_text_sections(soup)
    links = extract_links(soup, ADDITIONAL_URLS[0])
    categories = extract_supplier_categories(soup)

    print(f"  Sections found: {len(sections)}")
    for s in sections[:5]:
        print(f"    [{s['char_count']} chars] {s['heading'][:80]}")

    print(f"\n  Links found: {len(links)}")
    internal = [l for l in links if l["is_internal"]]
    print(f"    Internal: {len(internal)}, External: {len(links) - len(internal)}")

    print(f"\n  Supplier categories: {len(categories)}")
    for c in categories[:10]:
        print(f"    - {c[:120]}")

    # Build candidate events
    print("\n" + "─" * 60)
    print("Step 3: Candidate Events")
    print("─" * 60)

    events = build_candidate_events(sections, links, categories,
                                    str(html_path), html_hash,
                                    ADDITIONAL_URLS[0])
    print(f"  Events: {len(events)}")
    for i, evt in enumerate(events[:3]):
        print(f"\n  Event #{i+1}:")
        print(f"    event_type: {evt['event_type']}")
        print(f"    project_name_raw: {evt['project_name_raw'][:100]}")
        print(f"    summary: {evt['summary'][:150]}")
        print(f"    source_url: {evt['source_url'][:100]}")

    print(f"\n{'─' * 60}")
    print("Self-test complete.")
    print("─" * 60)


# ============================================================================
# 9. CLI
# ============================================================================


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Petrobras 供应商注册适配器 — P1 企业来源适配器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python crawler/adapters/petrobras_supplier.py                 # 完整运行
  python crawler/adapters/petrobras_supplier.py --test          # 自测
  python crawler/adapters/petrobras_supplier.py --dry-run       # 仅采集，不写入数据库
  python crawler/adapters/petrobras_supplier.py --local-only    # 仅本地保存
        """,
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="自测: 访问页面 → 解析内容 → 输出候选事件摘要。",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅采集页面、保存文件，不写入数据库。",
    )
    parser.add_argument(
        "--local-only",
        action="store_true",
        help="保存文件到本地，不写入 Supabase。",
    )
    args = parser.parse_args()

    if args.test:
        try:
            run_test()
        except Exception as e:
            log.error("Self-test failed: %s", e, exc_info=True)
            sys.exit(1)
        return

    try:
        result = run_adapter(
            dry_run=args.dry_run,
            local_only=args.local_only,
        )
    except requests.exceptions.HTTPError as e:
        log.error("HTTP error: %s", e)
        sys.exit(1)
    except Exception as e:
        log.error("Adapter failed: %s", e, exc_info=True)
        sys.exit(1)

    print("\n" + json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
