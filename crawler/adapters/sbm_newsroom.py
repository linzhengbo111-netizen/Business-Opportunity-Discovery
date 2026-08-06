#!/usr/bin/env python3
"""
SBM Offshore Newsroom 适配器 — P1 企业来源适配器
==================================================

按《FPSO项目可用信息源使用手册》P1 要求实现：

来源信息:
  名称: SBM Offshore Newsroom
  URL:  https://www.sbmoffshore.com/newsroom/
  类型: CONTRACTOR
  优先级: P1
  层级: 3（采购链拆解）
  接入方式: HTML — 已有行业爬虫，增强按项目别名搜索公告

功能:
  1. 访问 SBM Offshore Newsroom 页面，采集新闻稿和公告列表。
  2. 按 FPSO 项目别名搜索公告标题，识别 FEED_AWARDED 和 FPSO_CONTRACT_AWARDED 事件。
  3. 提取标题、日期、摘要、链接。
  4. 输出到 candidate_events 表，review_status='pending'。
  5. 保存原始 HTML 到 crawler/data/sbm/ 目录，记录 SHA256。

合规:
  - 只采集公开页面文本和链接，不自动登录、不提交表单、不绕过验证。
  - 请求间隔 5-10 秒。
  - 支持 --dry-run 和 --local-only 模式。

Usage:
  python crawler/adapters/sbm_newsroom.py                 # 完整运行
  python crawler/adapters/sbm_newsroom.py --dry-run       # 仅采集，不写入数据库
  python crawler/adapters/sbm_newsroom.py --local-only    # 保存文件到本地，不写入 Supabase
  python crawler/adapters/sbm_newsroom.py --test          # 自测
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
DATA_DIR = BASE_DIR / "data" / "sbm"

# ---- Config --------------------------------------------------------------

load_dotenv(BASE_DIR.parent / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("VITE_SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY")

SOURCE_NAME = "SBM Offshore Newsroom"
SOURCE_URL = "https://www.sbmoffshore.com/newsroom/"
EVENT_TYPE_FEED = "FEED_AWARDED"
EVENT_TYPE_CONTRACT = "FPSO_CONTRACT_AWARDED"

# Additional SBM Offshore URLs
ADDITIONAL_URLS = [
    "https://www.sbmoffshore.com/newsroom/",
    "https://www.sbmoffshore.com/newsroom/?category=press-releases",
]

MIN_REQUEST_DELAY_SEC = 5.0
MAX_REQUEST_DELAY_SEC = 10.0

USER_AGENT = (
    "Mozilla/5.0 (compatible; FPSOCrawler/1.0; +SBM-Newsroom-Adapter)"
)

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")
NOW_ISO = datetime.now(timezone.utc).isoformat()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("sbm-newsroom-adapter")


# ============================================================================
# 1. 项目别名 & 事件分类规则
# ============================================================================

# FPSO project aliases to search for (from project_aliases.ts)
FPSO_PROJECT_ALIASES = [
    # Guyana
    "Liza Destiny", "Liza Unity", "Liza Phase 1", "Liza Phase 2",
    "Prosperity", "ONE GUYANA", "One Guyana", "Errea Wittu", "Jaguar",
    "Payara", "Yellowtail", "Uaru", "Whiptail", "Hammerhead",
    # Brazil
    "Alexandre de Gusmão", "Almirante Barroso", "Duque de Caxias",
    "Anita Garibaldi", "Anna Nery", "Maria Quitéria", "Guanabara",
    "Cidade de", "Marlim", "Búzios", "Mero", "Sepia",
    # Angola
    "Agogo", "Greater Plutonio", "Dalia", "Girassol", "Pazflor", "CLOV",
    "Ndungu", "Kaombo",
    # Nigeria
    "Bonga", "Egina", "Akpo", "Erha", "Agbami", "Usan",
    # Other regions
    "Johan Castberg", "Sangomar", "Baleine", "Jubilee", "TEN",
    "Schiehallion", "Foinaven", "Vito", "Argos", "Stones",
    # Generic
    "FPSO", "FLNG", "FSO",
]

# Contract/award event classification patterns
FEED_PATTERNS = [
    r"\bfeed\b", r"front.end.engineering", r"pre.feed",
    r"conceptual\s+(?:design|study|engineering)",
    r"feasibility\s+study", r"concept\s+select",
]

CONTRACT_AWARD_PATTERNS = [
    r"contract\s+award", r"awarded\s+contract", r"letter\s+of\s+intent",
    r"\bloi\b", r"memorandum\s+of\s+understanding", r"\bmou\b",
    r"epc\s+contract", r"epci\s+contract", r"turnkey\s+contract",
    r"fast4ward", r"new\s+build", r"construction\s+contract",
    r"won\s+contract", r"secured\s+contract", r"signed\s+contract",
    r"\bfid\b", r"final\s+investment\s+decision",
    r"lease\s+and\s+operate", r"operate\s+and\s+maintain",
    r"\bo&m\b\s+contract", r"charter\s+contract",
    r"delivery\s+of\s+fpso", r"fpso\s+delivery",
]

STATUS_DELIVERY_PATTERNS = [
    r"first\s+oil", r"sail\s*away", r"delivered", r"commissioned",
    r"on\s+station", r"started\s+production", r"operational",
    r"achieved\s+first\s+oil", r"commenced\s+production",
]


def classify_event_type(title: str) -> str:
    """
    Classify a news article as FEED_AWARDED or FPSO_CONTRACT_AWARDED.
    Returns the appropriate event_type string.
    """
    title_lower = title.lower()

    # Check FEED patterns first
    for pattern in FEED_PATTERNS:
        if re.search(pattern, title_lower):
            return EVENT_TYPE_FEED

    # Check contract award patterns
    for pattern in CONTRACT_AWARD_PATTERNS:
        if re.search(pattern, title_lower):
            return EVENT_TYPE_CONTRACT

    # Check delivery/status (still a contract-related event)
    for pattern in STATUS_DELIVERY_PATTERNS:
        if re.search(pattern, title_lower):
            return EVENT_TYPE_CONTRACT

    # Default: if it mentions FPSO, it's contract-related
    if "fpso" in title_lower or "flng" in title_lower:
        return EVENT_TYPE_CONTRACT

    return EVENT_TYPE_CONTRACT  # default


def extract_project_alias(title: str) -> list[str]:
    """
    Find matching FPSO project aliases in a title.
    Returns list of matched alias strings (sorted by length, longest first).
    """
    matches = []
    title_lower = title.lower()

    for alias in FPSO_PROJECT_ALIASES:
        if alias.lower() in title_lower:
            matches.append(alias)

    # Sort by length (longest/most specific first), deduplicate
    matches = sorted(set(matches), key=len, reverse=True)
    return matches


# ============================================================================
# 2. HTTP 会话 & 页面获取
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
        return _safe_decode_response(resp)
    except requests.exceptions.HTTPError as e:
        log.warning("  HTTP %s — %s",
                     e.response.status_code if hasattr(e, 'response') else '?', url)
        return None
    except requests.exceptions.RequestException as e:
        log.warning("  Request failed: %s — %s", e, url)
        return None


# ============================================================================
# 3. 页面解析
# ============================================================================


def parse_news_articles(html: str, base_url: str) -> list[dict]:
    """
    Parse newsroom page HTML and extract article entries.
    Returns list of {title, date, summary, url, project_aliases, event_type}.
    """
    soup = BeautifulSoup(html, "html.parser")
    articles = []
    seen_urls = set()

    # Strategy 1: SBM-specific — div.newsroom__article.article-card
    sbm_cards = soup.find_all("div", class_="newsroom__article")
    if sbm_cards:
        log.info("  Found %d SBM newsroom article cards", len(sbm_cards))
        for card in sbm_cards:
            # Title from image alt text or heading
            img = card.find("img")
            title = img.get("alt", "").strip() if img else ""

            # Link from anchor
            link_el = card.find("a", href=True)
            link = urljoin(base_url, link_el["href"]) if link_el else ""

            if not title and link_el:
                title = link_el.get("aria-label", "").strip()

            if not title or len(title) < 10:
                continue

            if link in seen_urls:
                continue
            seen_urls.add(link)

            # Date from paragraph
            content_div = card.find("div", class_="article__content")
            date_el = content_div.find("p") if content_div else None
            raw_date = date_el.get_text(strip=True) if date_el else ""

            # Classify and extract aliases
            event_type = classify_event_type(title)
            aliases = extract_project_alias(title)

            articles.append({
                "title": title[:300],
                "date": raw_date[:50] if raw_date else TODAY,
                "summary": title[:500],
                "url": link[:2048],
                "project_aliases": aliases,
                "event_type": event_type,
            })

        log.info("  Parsed %d articles from SBM cards", len(articles))
        return articles

    # Strategy 2: Generic — try common article/listing selectors
    article_containers = (
        soup.find_all("article")
        or soup.find_all("div", class_=re.compile(r"news|post|article|item|card|listing", re.I))
        or soup.find_all("li", class_=re.compile(r"news|post|article|item", re.I))
    )

    if not article_containers:
        # Fallback: find all links that look like article titles
        article_containers = []
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True)
            if len(text) > 30 and any(
                kw in text.lower() for kw in ["fpso", "contract", "award", "project"]
            ):
                article_containers.append(a)

    for container in article_containers:
        # Title
        title_el = (
            container.find(["h1", "h2", "h3", "h4"])
            or container.find("a", class_=re.compile(r"title|heading", re.I))
            or (container if container.name == "a" else None)
        )
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        if not title or len(title) < 10:
            continue

        # Link
        link = ""
        if title_el.name == "a" and title_el.get("href"):
            link = urljoin(base_url, title_el["href"])
        else:
            link_el = container.find("a", href=True)
            if link_el:
                link = urljoin(base_url, link_el["href"])

        if link in seen_urls:
            continue
        seen_urls.add(link)

        # Date
        date_el = container.find(["time", "span", "div"],
                                 class_=re.compile(r"date|time|published|posted", re.I))
        raw_date = date_el.get_text(strip=True) if date_el else ""
        if not raw_date:
            time_el = container.find("time")
            if time_el:
                raw_date = time_el.get("datetime", "") or time_el.get_text(strip=True)

        # Summary
        summary_el = container.find(["p", "div"],
                                    class_=re.compile(r"summary|excerpt|text|content|body", re.I))
        summary = summary_el.get_text(strip=True) if summary_el else title

        # Classify and extract aliases
        event_type = classify_event_type(title)
        aliases = extract_project_alias(title)

        articles.append({
            "title": title[:300],
            "date": raw_date[:50] if raw_date else TODAY,
            "summary": summary[:500],
            "url": link[:2048],
            "project_aliases": aliases,
            "event_type": event_type,
        })

    log.info("  Parsed %d articles from page", len(articles))
    return articles


# ============================================================================
# 4. FPSO-relevance filtering
# ============================================================================


def is_fpso_relevant(article: dict) -> bool:
    """Check if an article is relevant to FPSO project tracking."""
    text = f"{article['title']} {article['summary']}".lower()

    # Has matched project aliases
    if article.get("project_aliases"):
        return True

    # Contains FPSO/offshore keywords
    fpso_keywords = [
        "fpso", "flng", "fso", "floating production",
        "offshore", "deepwater", "subsea", "topside",
        "mooring", "turret", "spread mooring",
    ]
    for kw in fpso_keywords:
        if kw in text:
            return True

    return False


# ============================================================================
# 5. candidate_events 输出
# ============================================================================


def build_candidate_event(article: dict, html_sha256: str,
                          raw_html_path: str) -> dict:
    """Convert a parsed article into a candidate_events record."""
    aliases = article.get("project_aliases", [])
    project_name = aliases[0] if aliases else article["title"]

    summary_parts = [f"Title: {article['title']}"]
    if article.get("date"):
        summary_parts.append(f"Date: {article['date']}")
    if aliases:
        summary_parts.append(f"Projects: {', '.join(aliases)}")
    if article.get("summary") and article["summary"] != article["title"]:
        summary_parts.append(f"Excerpt: {article['summary'][:200]}")

    full_text = f"{article['title']} {article.get('summary', '')}"
    procurement = extract_procurement(full_text)

    return {
        "project_name_raw": project_name[:255],
        "country": "",  # SBM is global contractor — country extraction needs project context
        "summary": " | ".join(summary_parts)[:2000],
        "source_name": SOURCE_NAME,
        "source_url": article.get("url", SOURCE_URL)[:2048],
        "review_status": "pending",
        "event_type": article.get("event_type", EVENT_TYPE_CONTRACT),
        "fetched_at": NOW_ISO,
        "evidence_quote": f"{article['title']} ({article.get('date', '')})",
        "procurement_chain": procurement,
        "raw_json": json.dumps({
            "article": article,
            "html_sha256": html_sha256,
            "raw_html_path": str(raw_html_path),
        }, ensure_ascii=False),
    }


# ============================================================================
# 6. Supabase 写入
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
            "country_focus": "Guyana",
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
    """Save downloaded file metadata to source_documents table.

    Per 《FPSO项目可用信息源使用手册》: records raw files in the
    source_documents layer for audit trail and deduplication.
    """
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
# 7. 本地存储
# ============================================================================


def save_raw_html(html: str, label: str = "main") -> tuple[Path, str]:
    """Save raw HTML for audit. Returns (path, sha256)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    safe_label = re.sub(r"[^\w\-]", "_", label)
    filepath = DATA_DIR / f"{TODAY}_sbm_{safe_label}.html"
    filepath.write_text(html, encoding="utf-8")
    sha256 = hashlib.sha256(html.encode("utf-8")).hexdigest()
    hash_path = DATA_DIR / f"{TODAY}_sbm_{safe_label}.html.sha256"
    hash_path.write_text(f"{sha256}  {TODAY}_sbm_{safe_label}.html\n")
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
# 8. 主流程
# ============================================================================


def run_adapter(dry_run: bool = False, local_only: bool = False,
                supabase=None) -> dict:
    """Adapter main flow."""
    log.info("=" * 60)
    log.info("SBM Offshore Newsroom Adapter — %s", TODAY)
    log.info("=" * 60)

    session = build_session()

    all_articles = []
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

        label = "newsroom" if i == 0 else "press"
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

        articles = parse_news_articles(html, url)
        articles = [a for a in articles if is_fpso_relevant(a)]
        log.info("  FPSO-relevant articles: %d / %d total",
                 len(articles),
                 len(parse_news_articles(html, url)))

        all_articles.extend(articles)

    if not all_articles:
        log.warning("No FPSO-relevant articles found.")
        return {
            "mode": "dry_run" if dry_run else ("local_only" if local_only else "full"),
            "total_articles": 0,
            "error": "No FPSO-relevant articles",
            "html_paths": html_paths,
        }

    # Deduplicate by URL
    seen_urls = set()
    unique_articles = []
    for a in all_articles:
        if a["url"] not in seen_urls:
            seen_urls.add(a["url"])
            unique_articles.append(a)
    log.info("  Unique articles: %d (total: %d)", len(unique_articles), len(all_articles))

    # Build candidate events
    events = []
    for article in unique_articles:
        evt = build_candidate_event(article, html_sha256_main,
                                    html_paths.get("newsroom", ""))
        events.append(evt)

    log.info("  Candidate events: %d", len(events))

    # Snapshot
    snapshot_data = {
        "articles": [
            {
                "title": a["title"],
                "date": a["date"],
                "url": a["url"],
                "project_aliases": a["project_aliases"],
                "event_type": a["event_type"],
            }
            for a in unique_articles
        ],
        "html_paths": html_paths,
        "candidate_events_count": len(events),
    }
    snapshot_path = save_local_snapshot(snapshot_data)

    # Event type breakdown
    feed_count = sum(1 for e in events if e["event_type"] == EVENT_TYPE_FEED)
    contract_count = sum(1 for e in events if e["event_type"] == EVENT_TYPE_CONTRACT)
    log.info("  Event types: %d FEED_AWARDED, %d FPSO_CONTRACT_AWARDED",
             feed_count, contract_count)

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
        "total_articles_parsed": len(unique_articles),
        "feed_awarded": feed_count,
        "fpso_contract_awarded": contract_count,
        "candidate_events": len(events),
        "inserted": inserted,
        "html_paths": html_paths,
        "html_sha256_main": html_sha256_main,
        "snapshot_path": str(snapshot_path),
        "data_dir": str(DATA_DIR),
    }

    log.info("=" * 60)
    log.info("Run complete. Mode: %s", mode_str)
    log.info("  Articles: %d (FEED: %d, Contract: %d)",
             result["total_articles_parsed"], feed_count, contract_count)
    return result


# ============================================================================
# 9. 自测
# ============================================================================


def run_test():
    """Self-test: fetch page → parse → classify → show events."""
    log.info("=" * 60)
    log.info("SELF-TEST: SBM Offshore Newsroom Adapter")
    log.info("=" * 60)

    session = build_session()

    print("\n" + "─" * 60)
    print("Step 1: Fetch Newsroom")
    print("─" * 60)
    html = fetch_page(ADDITIONAL_URLS[0], session)
    if html is None:
        print("  FAILED: Could not fetch page.")
        sys.exit(1)
    print(f"  Downloaded: {len(html):,} bytes")
    html_hash = hashlib.sha256(html.encode("utf-8")).hexdigest()
    print(f"  HTML SHA256: {html_hash}")

    html_path, _ = save_raw_html(html, "newsroom")
    print(f"  Saved HTML: {html_path}")

    print("\n" + "─" * 60)
    print("Step 2: Parse Articles")
    print("─" * 60)
    articles = parse_news_articles(html, ADDITIONAL_URLS[0])
    print(f"  Total articles parsed: {len(articles)}")

    fpso_articles = [a for a in articles if is_fpso_relevant(a)]
    print(f"  FPSO-relevant: {len(fpso_articles)}")

    for a in fpso_articles[:5]:
        aliases_str = ", ".join(a["project_aliases"]) if a["project_aliases"] else "(none)"
        print(f"    [{a['event_type']}] {a['title'][:80]}")
        print(f"       Aliases: {aliases_str}")
        print(f"       URL: {a['url'][:100]}")

    print("\n" + "─" * 60)
    print("Step 3: Candidate Events Summary")
    print("─" * 60)
    events = []
    for a in fpso_articles[:5]:
        evt = build_candidate_event(a, html_hash, str(html_path))
        events.append(evt)

    event_types = {}
    for a in fpso_articles:
        event_types[a["event_type"]] = event_types.get(a["event_type"], 0) + 1
    print(f"  Event type breakdown: {event_types}")

    alias_hits = {}
    for a in fpso_articles:
        for alias in a["project_aliases"]:
            alias_hits[alias] = alias_hits.get(alias, 0) + 1
    if alias_hits:
        print(f"  Project alias mentions: {alias_hits}")

    print(f"\n{'─' * 60}")
    print("Self-test complete.")
    print("─" * 60)


# ============================================================================
# 10. CLI
# ============================================================================


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="SBM Offshore Newsroom 适配器 — P1 企业来源适配器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python crawler/adapters/sbm_newsroom.py                 # 完整运行
  python crawler/adapters/sbm_newsroom.py --test          # 自测
  python crawler/adapters/sbm_newsroom.py --dry-run       # 仅采集，不写入数据库
  python crawler/adapters/sbm_newsroom.py --local-only    # 仅本地保存
        """,
    )
    parser.add_argument("--test", action="store_true",
                        help="自测: 访问页面 → 解析新闻 → 分类事件 → 输出摘要。")
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
