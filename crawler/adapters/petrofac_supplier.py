#!/usr/bin/env python3
"""
Petrofac 供应商网络适配器 — P1 企业来源适配器
==============================================

按《FPSO项目可用信息源使用手册》P1 要求实现：

来源信息:
  名称: Petrofac 供应商网络 (Supplier Network)
  URL:  https://supplier.petrofac.com/
  类型: CONTRACTOR
  优先级: P1
  层级: 3（采购链拆解）
  接入方式: HTML — 采集公开页面文本和链接

功能:
  1. 访问 Petrofac 供应商网络页面，采集注册入口和 RFQ 门户说明。
  2. 提取页面文本内容和所有相关链接。
  3. 事件类型: PROCUREMENT_PORTAL。
  4. 输出到 candidate_events 表，review_status='pending'。
  5. 保存原始 HTML 到 crawler/data/petrofac/ 目录，记录 SHA256。

合规:
  - 只采集公开页面文本和链接，不自动登录、不提交表单、不绕过验证。
  - 请求间隔 5-10 秒。
  - 支持 --dry-run 和 --local-only 模式。

Usage:
  python crawler/adapters/petrofac_supplier.py                 # 完整运行
  python crawler/adapters/petrofac_supplier.py --dry-run       # 仅采集，不写入数据库
  python crawler/adapters/petrofac_supplier.py --local-only    # 保存文件到本地，不写入 Supabase
  python crawler/adapters/petrofac_supplier.py --test          # 自测
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
DATA_DIR = BASE_DIR / "data" / "petrofac"

# ---- Config --------------------------------------------------------------

load_dotenv(BASE_DIR.parent / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("VITE_SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY")

SOURCE_NAME = "Petrofac Supplier Network"
SOURCE_URL = "https://supplier.petrofac.com/"
EVENT_TYPE = "PROCUREMENT_PORTAL"

# Additional Petrofac supplier/procurement pages
ADDITIONAL_URLS = [
    "https://supplier.petrofac.com/",
    "https://www.petrofac.com/supply-chain/",
    "https://www.petrofac.com/supply-chain/become-a-supplier/",
]

MIN_REQUEST_DELAY_SEC = 5.0
MAX_REQUEST_DELAY_SEC = 10.0

USER_AGENT = (
    "Mozilla/5.0 (compatible; FPSOCrawler/1.0; +Petrofac-Supplier-Adapter)"
)

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")
NOW_ISO = datetime.now(timezone.utc).isoformat()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("petrofac-supplier-adapter")


# ============================================================================
# 1. HTTP 会话 & 页面获取
# ============================================================================


def build_session() -> requests.Session:
    """Build a requests Session with appropriate headers."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
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

    main = (
        soup.find("main")
        or soup.find("article")
        or soup.find("div", class_=re.compile(r"content|main|body|entry|wrapper", re.I))
        or soup
    )

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
            "is_internal": "petrofac.com" in domain,
            "is_pdf": href.lower().endswith(".pdf"),
            "is_registration": any(kw in text.lower() for kw in
                                   ["register", "sign up", "apply", "portal"]),
        })

    return links


def extract_portal_info(soup: BeautifulSoup) -> list[str]:
    """
    Extract portal/RFQ/supplier registration related information.
    """
    text = soup.get_text().lower()
    info_found = []

    portal_terms = [
        "supplier registration", "register as a supplier",
        "supplier portal", "vendor portal", "rfq", "rfp", "rfx",
        "request for quotation", "request for proposal",
        "tender", "bidding", "bid", "prequalification",
        "supplier qualification", "supplier assessment",
        "supplier code of conduct", "procurement portal",
        "e-sourcing", "e-auction", "contract opportunity",
        "supplier network", "become a supplier",
        "supplier onboarding", "supply chain portal",
        "ariba", "jaggaer", "coupa", "sap",
    ]

    for term in portal_terms:
        if term in text:
            info_found.append(term)

    return info_found


def find_registration_links(links: list[dict]) -> list[dict]:
    """Identify links that appear to be supplier registration or portal entry points."""
    registration = []
    for link in links:
        text_lower = link["text"].lower()
        url_lower = link["url"].lower()

        is_reg = any(kw in text_lower or kw in url_lower for kw in [
            "register", "registration", "sign up", "signup",
            "apply", "application", "portal", "login",
            "supplier", "vendor", "contractor",
        ])

        if is_reg:
            registration.append(link)

    return registration


# ============================================================================
# 3. 内容摘要生成
# ============================================================================


def build_page_summary(sections: list[dict], links: list[dict],
                       portal_info: list[str],
                       reg_links: list[dict]) -> str:
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

    if reg_links:
        parts.append(f"Registration/portal links: {len(reg_links)}")
        for rl in reg_links[:5]:
            parts.append(f"  → {rl['text'][:100]}: {rl['url'][:120]}")

    if portal_info:
        parts.append(f"Portal terms: {', '.join(portal_info[:15])}")

    return " | ".join(parts)


# ============================================================================
# 4. candidate_events 输出
# ============================================================================


def build_candidate_events(sections: list[dict], links: list[dict],
                           portal_info: list[str], reg_links: list[dict],
                           raw_html_path: str, html_sha256: str,
                           url_fetched: str) -> list[dict]:
    """Build candidate_events records from extracted data."""
    events = []
    summary = build_page_summary(sections, links, portal_info, reg_links)

    all_text = " ".join(s["content"] for s in sections if s.get("content"))
    evidence = all_text[:500] if all_text else summary[:500]

    raw_meta = {
        "source_url_fetched": url_fetched,
        "html_sha256": html_sha256,
        "sections_count": len(sections),
        "links_count": len(links),
        "portal_info": portal_info,
        "registration_links": [
            {"text": l["text"], "url": l["url"]} for l in reg_links
        ],
        "sections": [{"heading": s["heading"], "char_count": s["char_count"]}
                      for s in sections[:20]],
    }

    # Main event
    events.append({
        "project_name_raw": "Petrofac Supplier Network Portal",
        "country": "UK",
        "summary": summary[:2000],
        "source_name": SOURCE_NAME,
        "source_url": url_fetched[:2048],
        "review_status": "pending",
        "event_type": EVENT_TYPE,
        "fetched_at": NOW_ISO,
        "evidence_quote": evidence[:500],
        "raw_json": json.dumps(raw_meta, ensure_ascii=False),
    })

    # Per-registration-link events
    for rl in reg_links[:15]:
        events.append({
            "project_name_raw": f"Petrofac Portal: {rl['text'][:200]}",
            "country": "UK",
            "summary": f"Registration/portal link: {rl['text'][:300]} → {rl['url'][:300]}",
            "source_name": SOURCE_NAME,
            "source_url": rl["url"][:2048],
            "review_status": "pending",
            "event_type": EVENT_TYPE,
            "fetched_at": NOW_ISO,
            "evidence_quote": rl["text"][:500],
            "raw_json": json.dumps({
                "link": rl,
                "html_sha256": html_sha256,
                "source_page": url_fetched,
            }, ensure_ascii=False),
        })

    # Per-section events
    for section in sections:
        if section["char_count"] > 100 and section["heading"]:
            sec_meta = {
                "section_heading": section["heading"],
                "content": section["content"][:500],
                "html_sha256": html_sha256,
            }
            events.append({
                "project_name_raw": f"Petrofac: {section['heading'][:200]}",
                "country": "UK",
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
            log.warning("Insert error for %s",
                         evt.get("project_name_raw", "?"), exc_info=True)
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
            "country_focus": "UK",
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
    filepath = DATA_DIR / f"{TODAY}_petrofac_{safe_label}.html"
    filepath.write_text(html, encoding="utf-8")
    sha256 = hashlib.sha256(html.encode("utf-8")).hexdigest()
    hash_path = DATA_DIR / f"{TODAY}_petrofac_{safe_label}.html.sha256"
    hash_path.write_text(f"{sha256}  {TODAY}_petrofac_{safe_label}.html\n")
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
    log.info("Petrofac Supplier Network Adapter — %s", TODAY)
    log.info("=" * 60)

    session = build_session()

    all_sections = []
    all_links = []
    all_portal_info = []
    all_reg_links = []
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

        label = url.rstrip("/").split("/")[-1].replace("-", "_") or "index"
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
        portal_info = extract_portal_info(soup)
        reg_links = find_registration_links(links)

        log.info("  [%s] Sections: %d, Links: %d, PortalInfo: %d, RegLinks: %d",
                 label, len(sections), len(links), len(portal_info), len(reg_links))

        all_sections.extend(sections)
        all_links.extend(links)
        all_portal_info.extend(portal_info)
        all_reg_links.extend(reg_links)

    if not all_sections and not all_links:
        log.warning("No content extracted from any URL.")
        return {
            "mode": "dry_run" if dry_run else ("local_only" if local_only else "full"),
            "total_sections": 0, "total_links": 0,
            "error": "No content extracted", "html_paths": html_paths,
        }

    unique_portal_info = sorted(set(all_portal_info))
    unique_reg_links = list({l["url"]: l for l in all_reg_links}.values())

    events = build_candidate_events(
        all_sections, all_links, unique_portal_info, unique_reg_links,
        html_paths.get("index", ""), html_sha256_main,
        ADDITIONAL_URLS[0],
    )
    log.info("  Candidate events: %d", len(events))

    snapshot_data = {
        "sections": [{"heading": s["heading"], "content": s["content"][:200]}
                      for s in all_sections],
        "links": all_links[:50],
        "portal_info": unique_portal_info,
        "registration_links": [{"text": l["text"], "url": l["url"]}
                               for l in unique_reg_links],
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
        "registration_links": len(unique_reg_links),
        "portal_terms_found": len(unique_portal_info),
        "portal_terms": unique_portal_info,
        "candidate_events": len(events),
        "inserted": inserted,
        "html_paths": html_paths,
        "html_sha256_main": html_sha256_main,
        "snapshot_path": str(snapshot_path),
        "data_dir": str(DATA_DIR),
    }

    log.info("=" * 60)
    log.info("Run complete. Mode: %s", mode_str)
    log.info("  Sections: %d, Links: %d, RegLinks: %d, PortalTerms: %d",
             result["total_sections"], result["total_links"],
             result["registration_links"], result["portal_terms_found"])
    return result


# ============================================================================
# 8. 自测
# ============================================================================


def run_test():
    """Self-test: fetch page → parse → show summary."""
    log.info("=" * 60)
    log.info("SELF-TEST: Petrofac Supplier Network Adapter")
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

    html_path, _ = save_raw_html(html, "index")
    print(f"  Saved HTML: {html_path}")

    print("\n" + "─" * 60)
    print("Step 2: Parse Content")
    print("─" * 60)
    soup = BeautifulSoup(html, "html.parser")
    sections = extract_text_sections(soup)
    links = extract_links(soup, ADDITIONAL_URLS[0])
    portal_info = extract_portal_info(soup)
    reg_links = find_registration_links(links)

    print(f"  Sections: {len(sections)}")
    for s in sections[:5]:
        print(f"    [{s['char_count']} chars] {s['heading'][:80]}")
    print(f"  Links: {len(links)} (internal: {sum(1 for l in links if l['is_internal'])})")
    print(f"  Registration/portal links: {len(reg_links)}")
    for rl in reg_links[:5]:
        print(f"    → {rl['text'][:80]}")
        print(f"      {rl['url'][:120]}")
    print(f"  Portal terms found: {portal_info}")

    print("\n" + "─" * 60)
    print("Step 3: Candidate Events")
    print("─" * 60)
    events = build_candidate_events(sections, links, portal_info, reg_links,
                                    str(html_path), html_hash, ADDITIONAL_URLS[0])
    print(f"  Events: {len(events)}")
    for i, evt in enumerate(events[:3]):
        print(f"\n  Event #{i+1}:")
        print(f"    event_type: {evt['event_type']}")
        print(f"    project_name_raw: {evt['project_name_raw'][:100]}")
        print(f"    country: {evt['country']}")

    print(f"\n{'─' * 60}")
    print("Self-test complete.")
    print("─" * 60)


# ============================================================================
# 9. CLI
# ============================================================================


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Petrofac 供应商网络适配器 — P1 企业来源适配器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python crawler/adapters/petrofac_supplier.py                 # 完整运行
  python crawler/adapters/petrofac_supplier.py --test          # 自测
  python crawler/adapters/petrofac_supplier.py --dry-run       # 仅采集，不写入数据库
  python crawler/adapters/petrofac_supplier.py --local-only    # 仅本地保存
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
