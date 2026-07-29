#!/usr/bin/env python3
"""
Equinor Rosebank 公告适配器 — P0 黄金样本来源适配器
=====================================================

按《FPSO项目可用信息源使用手册》P0 要求实现：

来源信息:
  名称: Equinor Rosebank 公告 (Equinor Rosebank Project Announcements)
  URL:  https://www.equinor.com/energy/rosebank
  类型: OPERATOR
  优先级: P0
  层级: 2（官方验证）
  接入方式: HTML — 采集项目页面公告、FID 更新、FPSO 合同授予

功能:
  1. 访问 Equinor Rosebank 项目页面，采集项目公告和进展。
  2. 按事件类型分类: PROJECT_ANNOUNCEMENT, FID_CONFIRMED, CONTRACT_AWARDED。
  3. 提取标题、日期、摘要、链接。
  4. 输出 project_companies（角色 + 公告原文片段）到 raw_json。
  5. 输出到 candidate_events 表，review_status='pending'。
  6. 保存原始 HTML 到 crawler/data/equinor_rosebank/ 目录，记录 SHA256。

合规:
  - 只采集公开页面文本和链接，不自动登录、不提交表单、不绕过验证。
  - 请求间隔 5-10 秒。
  - 支持 --dry-run 和 --local-only 模式。

根据手册原文 ("示范如何从业主公告中提取项目决策、FPSO方案、主要合同方和
计划投产时间。作为黄金样本主证据")，本适配器重点提取:
  - 项目决策 (FID, 开发计划批准)
  - FPSO 方案 (FPSO 选型、设计、建造合同)
  - 主要合同方 (Operator, EPC, FPSO contractor, sub-suppliers)
  - 计划投产时间 (first oil target)

Usage:
  python crawler/adapters/equinor_rosebank.py                 # 完整运行
  python crawler/adapters/equinor_rosebank.py --dry-run       # 仅采集，不写入数据库
  python crawler/adapters/equinor_rosebank.py --local-only    # 保存文件到本地，不写入 Supabase
  python crawler/adapters/equinor_rosebank.py --test          # 自测
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
DATA_DIR = BASE_DIR / "data" / "equinor_rosebank"

# ---- Config --------------------------------------------------------------

load_dotenv(BASE_DIR.parent / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("VITE_SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY")

SOURCE_NAME = "Equinor Rosebank Announcements"
SOURCE_URL = "https://www.equinor.com/energy/rosebank"
EVENT_TYPE_ANNOUNCEMENT = "PROJECT_ANNOUNCEMENT"
EVENT_TYPE_FID = "FID_CONFIRMED"
EVENT_TYPE_CONTRACT = "CONTRACT_AWARDED"

# Additional Equinor Rosebank-related URLs
ADDITIONAL_URLS = [
    "https://www.equinor.com/energy/rosebank",
    "https://www.equinor.com/news",
    "https://www.equinor.com/energy/rosebank-whats-next",
]

MIN_REQUEST_DELAY_SEC = 5.0
MAX_REQUEST_DELAY_SEC = 10.0

USER_AGENT = (
    "Mozilla/5.0 (compatible; FPSOCrawler/1.0; +Equinor-Rosebank-Adapter)"
)

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")
NOW_ISO = datetime.now(timezone.utc).isoformat()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("equinor-rosebank-adapter")


# ============================================================================
# 1. 事件分类规则 (按手册黄金样本要求)
# ============================================================================

# FID / project approval keywords
FID_KEYWORDS = [
    "final investment decision", "FID", "sanction", "approved",
    "green light", "go-ahead", "proceed", "development plan approved",
    "field development plan", "development consent", "NSTA approval",
    "regulatory approval", "government approval",
]

# FPSO contract / award keywords
CONTRACT_KEYWORDS = [
    "FPSO contract", "FPSO award", "FPSO awarded", "FPSO vessel",
    "FPSO construction", "FPSO delivery", "FPSO conversion",
    "FPSO topside", "FPSO mooring", "FPSO riser", "FPSO SURF",
    "FEED contract", "FEED awarded", "EPC contract", "EPC awarded",
    "engineering procurement construction", "subsea contract",
    "drilling contract", "supply chain", "supplier",
    "technipfmc", "altera", "modec", "sbm offshore",
    "aker solutions", "wood group",
]

# Project announcement keywords
PROJECT_KEYWORDS = [
    "rosebank", "north sea", "ukcs", "west of shetland",
    "equinor", "ithaca energy",
]

# Company name extraction patterns (from manual: "主要合同方")
COMPANY_PATTERNS = [
    # Operators
    r"\b(Equinor|Ithaca Energy)\b",
    # FPSO contractors
    r"\b(Altera\s*(?:Infrastructure)?|SBM\s*Offshore|MODEC|BW\s*Offshore|Bluewater)\b",
    # EPC / Subsea
    r"\b(TechnipFMC|Technip\s*(?:Energies)?|Aker\s*Solutions|Wood\s*Group|Subsea\s*7)\b",
    # Drilling
    r"\b(Noble\s*(?:Corporation|Drilling)?|Transocean|Seadrill|Odfjell|Valaris)\b",
    # SURF
    r"\b(Allseas|Saipem|McDermott)\b",
]

# FPSO project aliases for Rosebank
ROSEBANK_ALIASES = [
    "Rosebank", "FPSO Rosebank", "Rosebank FPSO", "Rosebank Field",
    "Rosebank Development", "Rosebank Project", "Equinor Rosebank",
    "Rosebank Oil Field", "Rosebank North Sea",
]


# ============================================================================
# 2. HTTP 会话 & 页面获取
# ============================================================================


def build_session() -> requests.Session:
    """Build a requests Session with appropriate headers."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5,nb;q=0.3",
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
# 3. 页面解析
# ============================================================================


def extract_article_sections(soup: BeautifulSoup) -> list[dict]:
    """
    Extract article/news sections from the page.
    Looks for article elements, news cards, and text sections.
    Returns list of {title, text, date, link} dicts.
    """
    sections = []

    # Strategy 1: Look for article/news-item elements
    for tag_name, class_pattern in [
        ("article", re.compile(r"article|news|post|story|press", re.I)),
        ("div", re.compile(r"article|news.*card|news.*item|post.*card|story.*card|press.*release", re.I)),
        ("li", re.compile(r"news.*item|article.*item|press.*item", re.I)),
    ]:
        for elem in soup.find_all(tag_name, class_=class_pattern):
            # Extract title
            title_el = (
                elem.find(["h1", "h2", "h3", "h4"])
                or elem.find("a", class_=re.compile(r"title|heading|headline", re.I))
            )
            title = title_el.get_text(strip=True) if title_el else ""

            # Extract date
            date_el = elem.find(["time", "span", "div"],
                                class_=re.compile(r"date|time|published|posted", re.I))
            date_str = ""
            if date_el:
                dt = date_el.get("datetime", "")
                if dt:
                    date_str = dt[:10]
                else:
                    date_str = date_el.get_text(strip=True)[:30]

            # Extract link
            link = ""
            link_el = elem.find("a", href=True)
            if link_el:
                link = urljoin(SOURCE_URL, link_el.get("href", ""))

            # Extract text/summary
            text_el = elem.find(["p", "div"],
                                class_=re.compile(r"excerpt|summary|text|description|body|content", re.I))
            text = text_el.get_text(strip=True) if text_el else ""

            if title:
                sections.append({
                    "title": title[:300],
                    "text": (text or title)[:2000],
                    "date": date_str,
                    "link": link[:2048],
                })

    # Strategy 2: Fallback — extract by heading hierarchy
    if not sections:
        main = (
            soup.find("main")
            or soup.find("article")
            or soup.find("div", class_=re.compile(r"content|main|body|page", re.I))
            or soup
        )
        for tag in main.find_all(["h1", "h2", "h3"]):
            heading = tag.get_text(strip=True)
            if not heading or len(heading) < 5:
                continue

            # Collect text until next heading
            content_parts = []
            sibling = tag.find_next_sibling()
            while sibling and sibling.name not in ("h1", "h2", "h3", "h4"):
                if sibling.name in ("p", "li", "div", "span", "td"):
                    text = sibling.get_text(strip=True)
                    if text and len(text) > 10:
                        content_parts.append(text)
                sibling = sibling.find_next_sibling()

            content = "\n".join(content_parts)
            sections.append({
                "title": heading[:300],
                "text": content[:2000],
                "date": "",
                "link": SOURCE_URL,
            })

    # Strategy 3: Last resort — all paragraphs
    if not sections:
        paragraphs = soup.find_all("p")
        all_text = []
        for p in paragraphs:
            text = p.get_text(strip=True)
            if text and len(text) > 20:
                all_text.append(text)
        if all_text:
            sections.append({
                "title": "Rosebank Project Page Content",
                "text": "\n".join(all_text)[:2000],
                "date": TODAY,
                "link": SOURCE_URL,
            })

    return sections


def classify_event(title: str, text: str) -> str:
    """
    Classify a section/article into event type per manual requirements.
    Returns one of: PROJECT_ANNOUNCEMENT, FID_CONFIRMED, CONTRACT_AWARDED.
    """
    combined = f"{title} {text}".lower()

    # Check FID/sanction keywords first (highest signal)
    fid_score = sum(1 for kw in FID_KEYWORDS if kw.lower() in combined)
    contract_score = sum(1 for kw in CONTRACT_KEYWORDS if kw.lower() in combined)

    if fid_score >= 2:
        return EVENT_TYPE_FID
    if contract_score >= 2:
        return EVENT_TYPE_CONTRACT
    if fid_score >= 1:
        return EVENT_TYPE_FID
    if contract_score >= 1:
        return EVENT_TYPE_CONTRACT

    return EVENT_TYPE_ANNOUNCEMENT


def extract_project_companies(text: str) -> list[dict]:
    """
    Extract company mentions and their roles from text.
    Per manual: "项目决策、FPSO方案、主要合同方和计划投产时间"
    Returns list of {company, role, context_snippet}.
    """
    companies = []
    seen = set()

    # Role assignment based on company identity
    OPERATORS = {"equinor", "ithaca energy"}
    FPSO_CONTRACTORS = {"altera", "altera infrastructure", "sbm offshore",
                         "modec", "bw offshore", "bluewater"}
    EPC_CONTRACTORS = {"technipfmc", "technip", "technip energies",
                        "aker solutions", "wood group", "subsea 7"}
    DRILLING_CONTRACTORS = {"noble", "noble corporation", "noble drilling",
                             "transocean", "seadrill", "odfjell", "valaris"}
    SURF_CONTRACTORS = {"allseas", "saipem", "mcdermott"}

    for pattern in COMPANY_PATTERNS:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            company = m.group(0).strip()
            key = company.lower()
            if key in seen:
                continue
            seen.add(key)

            # Determine role
            if key in OPERATORS:
                role = "Operator"
            elif key in FPSO_CONTRACTORS:
                role = "FPSO Contractor"
            elif key in EPC_CONTRACTORS:
                role = "EPC/Subsea Contractor"
            elif key in DRILLING_CONTRACTORS:
                role = "Drilling Contractor"
            elif key in SURF_CONTRACTORS:
                role = "SURF Contractor"
            else:
                role = "Company"

            # Extract context snippet (100 chars around mention)
            start = max(0, m.start() - 60)
            end = min(len(text), m.end() + 60)
            snippet = text[start:end].strip()

            companies.append({
                "company": company,
                "role": role,
                "context_snippet": snippet[:200],
            })

    return companies


def extract_first_oil_date(text: str) -> Optional[str]:
    """
    Extract planned first oil date from text.
    Per manual: "计划投产时间"
    """
    patterns = [
        r"first\s*oil\s*(?:expected|planned|targeted|scheduled|in|by)?\s*(\d{4})",
        r"(?:production|start[- ]up|startup)\s*(?:expected|planned|targeted)?\s*(?:in|by)?\s*(\d{4})",
        r"come\s*on\s*stream\s*(?:in|by)?\s*(\d{4})",
    ]

    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1)

    return None


# ============================================================================
# 4. candidate_events 输出
# ============================================================================


def build_candidate_events(sections: list[dict], raw_html_path: str,
                           html_sha256: str, url_fetched: str) -> list[dict]:
    """
    Build candidate_events records from extracted sections.
    Each section becomes a candidate_event with appropriate event_type.
    """
    events = []

    for section in sections:
        title = section.get("title", "")
        text = section.get("text", "")
        date = section.get("date", "") or TODAY
        link = section.get("link", "")

        event_type = classify_event(title, text)
        companies = extract_project_companies(f"{title} {text}")
        first_oil_year = extract_first_oil_date(f"{title} {text}")

        # Check relevance: only include if related to Rosebank/FPSO/UKCS
        combined = f"{title} {text}".lower()
        is_relevant = any(alias.lower() in combined for alias in ROSEBANK_ALIASES)
        if not is_relevant:
            # Check for FPSO + North Sea relevance
            has_fpso = "fpso" in combined
            has_north_sea = "north sea" in combined or "ukcs" in combined
            if not (has_fpso and has_north_sea):
                continue

        summary_parts = [title]
        if text:
            summary_parts.append(text[:200])
        summary = " | ".join(summary_parts)[:2000]

        evidence = (text or title)[:500]

        raw_meta = {
            "source_url_fetched": url_fetched,
            "html_sha256": html_sha256,
            "section_title": title[:300],
            "section_date": date,
            "section_link": link,
            "event_classification": event_type,
            "project_companies": companies,
            "first_oil_target_year": first_oil_year,
            "rosebank_alias_matched": [
                a for a in ROSEBANK_ALIASES if a.lower() in combined
            ],
            "classification_keywords": {
                "fid_matched": [kw for kw in FID_KEYWORDS if kw.lower() in combined],
                "contract_matched": [kw for kw in CONTRACT_KEYWORDS if kw.lower() in combined],
            },
        }

        events.append({
            "project_name_raw": title[:300],
            "country": "UK",
            "summary": summary,
            "source_name": SOURCE_NAME,
            "source_url": link or url_fetched[:2048],
            "review_status": "pending",
            "event_type": event_type,
            "fetched_at": NOW_ISO,
            "evidence_quote": evidence,
            "publication_date": date,
            "raw_json": json.dumps(raw_meta, ensure_ascii=False),
        })

    # If no section-based events, create one from the full page
    if not events and sections:
        all_text = "\n".join(s["text"] for s in sections)
        all_titles = " | ".join(s["title"] for s in sections)

        combined_lower = all_text.lower()
        event_type = classify_event(all_titles, all_text)
        companies = extract_project_companies(all_text)
        first_oil_year = extract_first_oil_date(all_text)

        evidence = all_text[:500]
        summary = f"Rosebank Project: {all_titles[:200]}"

        raw_meta = {
            "source_url_fetched": url_fetched,
            "html_sha256": html_sha256,
            "full_page": True,
            "sections_found": len(sections),
            "section_titles": [s["title"][:100] for s in sections],
            "event_classification": event_type,
            "project_companies": companies,
            "first_oil_target_year": first_oil_year,
        }

        events.append({
            "project_name_raw": "Rosebank FPSO",
            "country": "UK",
            "summary": summary[:2000],
            "source_name": SOURCE_NAME,
            "source_url": url_fetched[:2048],
            "review_status": "pending",
            "event_type": event_type,
            "fetched_at": NOW_ISO,
            "evidence_quote": evidence,
            "publication_date": TODAY,
            "raw_json": json.dumps(raw_meta, ensure_ascii=False),
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
            "source_type": "OPERATOR",
            "tier": 2,
            "priority": "P0",
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
    filepath = DATA_DIR / f"{TODAY}_rosebank_{safe_label}.html"
    filepath.write_text(html, encoding="utf-8")
    sha256 = hashlib.sha256(html.encode("utf-8")).hexdigest()
    hash_path = DATA_DIR / f"{TODAY}_rosebank_{safe_label}.html.sha256"
    hash_path.write_text(f"{sha256}  {TODAY}_rosebank_{safe_label}.html\n")
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
    log.info("Equinor Rosebank Announcements Adapter — P0 Gold Sample — %s", TODAY)
    log.info("=" * 60)

    session = build_session()

    all_sections = []
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

        label = url.rstrip("/").split("/")[-1].replace("-", "_") or "main"
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
        sections = extract_article_sections(soup)

        log.info("  [%s] Sections extracted: %d", label, len(sections))

        # Enrich sections with URL info
        for s in sections:
            if not s.get("link"):
                s["link"] = url

        all_sections.extend(sections)

    if not all_sections:
        log.warning("No content extracted from any URL. Creating fallback entry.")
        # Fallback: still create a candidate_event so the source is tracked
        all_sections = [{
            "title": "Equinor Rosebank Project — P0 Gold Sample Source",
            "text": (
                "The Rosebank oil and gas field is located west of Shetland in the UK "
                "North Sea. Equinor is the operator (80%) with Ithaca Energy (20%). "
                "The development concept is an FPSO vessel. "
                "Source: https://www.equinor.com/energy/rosebank"
            ),
            "date": TODAY,
            "link": SOURCE_URL,
        }]

    events = build_candidate_events(
        all_sections,
        html_paths.get("rosebank", html_paths.get("main", "")),
        html_sha256_main,
        ADDITIONAL_URLS[0],
    )
    log.info("  Candidate events: %d (from %d sections)", len(events), len(all_sections))

    # Build event type distribution for reporting
    event_types = {}
    for evt in events:
        et = evt.get("event_type", "?")
        event_types[et] = event_types.get(et, 0) + 1
    for et, count in event_types.items():
        log.info("    %s: %d", et, count)

    snapshot_data = {
        "sections": [{"title": s["title"][:200], "text": s["text"][:300],
                       "date": s["date"], "link": s["link"]}
                      for s in all_sections],
        "html_paths": html_paths,
        "candidate_events_count": len(events),
        "event_type_distribution": event_types,
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
        "candidate_events": len(events),
        "inserted": inserted,
        "event_type_distribution": event_types,
        "html_paths": html_paths,
        "html_sha256_main": html_sha256_main,
        "snapshot_path": str(snapshot_path),
        "data_dir": str(DATA_DIR),
    }

    log.info("=" * 60)
    log.info("Run complete. Mode: %s", mode_str)
    log.info("  Sections: %d, Events: %d, Inserted: %d",
             result["total_sections"], result["candidate_events"], result["inserted"])
    return result


# ============================================================================
# 8. 自测
# ============================================================================


def run_test():
    """Self-test: fetch page → parse → show summary."""
    log.info("=" * 60)
    log.info("SELF-TEST: Equinor Rosebank Announcements Adapter")
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

    html_path, _ = save_raw_html(html, "rosebank")
    print(f"  Saved HTML: {html_path}")

    print("\n" + "─" * 60)
    print("Step 2: Parse Content")
    print("─" * 60)
    soup = BeautifulSoup(html, "html.parser")
    sections = extract_article_sections(soup)

    print(f"  Sections: {len(sections)}")
    for s in sections[:5]:
        print(f"    [{s['date']}] {s['title'][:100]}")
        print(f"      Text: {s['text'][:150]}...")

    print("\n" + "─" * 60)
    print("Step 3: Classify Events")
    print("─" * 60)
    for s in sections[:5]:
        title = s.get("title", "")
        text = s.get("text", "")
        event_type = classify_event(title, text)
        companies = extract_project_companies(f"{title} {text}")
        first_oil = extract_first_oil_date(f"{title} {text}")
        print(f"  [{event_type}] {title[:80]}")
        if companies:
            for c in companies:
                print(f"    {c['role']}: {c['company']} — {c['context_snippet'][:80]}...")
        if first_oil:
            print(f"    First oil target: {first_oil}")

    print("\n" + "─" * 60)
    print("Step 4: Candidate Events")
    print("─" * 60)
    events = build_candidate_events(sections, str(html_path), html_hash, ADDITIONAL_URLS[0])
    print(f"  Events: {len(events)}")
    for i, evt in enumerate(events[:3]):
        print(f"\n  Event #{i+1}:")
        print(f"    event_type: {evt['event_type']}")
        print(f"    project_name_raw: {evt['project_name_raw'][:100]}")
        print(f"    country: {evt['country']}")
        print(f"    evidence_quote: {evt.get('evidence_quote', '')[:100]}")

        # Show raw_json project_companies if present
        try:
            meta = json.loads(evt.get("raw_json", "{}"))
            pcs = meta.get("project_companies", [])
            if pcs:
                print(f"    project_companies: {len(pcs)}")
                for pc in pcs:
                    print(f"      {pc['role']}: {pc['company']}")
            if meta.get("first_oil_target_year"):
                print(f"    first_oil_target: {meta['first_oil_target_year']}")
        except json.JSONDecodeError:
            pass

    print(f"\n{'─' * 60}")
    print("Self-test complete.")
    print("─" * 60)


# ============================================================================
# 9. CLI
# ============================================================================


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Equinor Rosebank 公告适配器 — P0 黄金样本来源适配器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python crawler/adapters/equinor_rosebank.py                 # 完整运行
  python crawler/adapters/equinor_rosebank.py --test          # 自测
  python crawler/adapters/equinor_rosebank.py --dry-run       # 仅采集，不写入数据库
  python crawler/adapters/equinor_rosebank.py --local-only    # 仅本地保存
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
