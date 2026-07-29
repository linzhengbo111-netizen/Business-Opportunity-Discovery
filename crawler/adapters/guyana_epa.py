#!/usr/bin/env python3
"""
Guyana EPA Oil & Gas Documents Adapter — P0 专用适配器
========================================================

按《FPSO项目可用信息源使用手册》P0 要求实现：

来源信息:
  名称: Guyana EPA Oil & Gas Documents
  URL:  https://epaguyana.org/download-category/oil-gas/
  类型: HTML 目录 + PDF 附件
  优先级: P0
  层级: 2（官方验证）
  接入方式: 解析页面 WPDM 文档列表，提取文档标题/链接/日期，下载 PDF 附件

功能:
  1. 解析 EPA 页面的 WPDM 文档列表，提取每个文档的标题、链接、发布日期。
  2. 按手册要求自动分类：PROJECT_SUMMARY、EIA、PERMIT、PUBLIC_NOTICE。
  3. 从文件名和标题中提取项目别名（如从 'Payara Development Project EIA' 提取 'Payara'）。
  4. 下载 PDF/ZIP 附件到 crawler/data/guyana_epa/ 目录，保存文件 SHA256 哈希。
  5. 使用 URL + 文件哈希去重，避免同一文档重复入库。
  6. 所有输出写入 candidate_events 表。

合规:
  - 请求间隔 5-10 秒，遵守 robots.txt。
  - 保存原始 HTML 和 PDF 副本。
  - 不绕过任何登录或验证。
  - 区分 publication_date（文档发布日期）和 fetched_at（系统抓取时间）。

Usage:
  python crawler/adapters/guyana_epa.py                 # 完整运行: 解析 → 下载 → 写入
  python crawler/adapters/guyana_epa.py --dry-run       # 仅解析页面、下载文件，不写入数据库
  python crawler/adapters/guyana_epa.py --local-only    # 保存文件到本地，不写入 Supabase
  python crawler/adapters/guyana_epa.py --test          # 自测: 访问页面 → 列文档 → 下载第一个PDF → 验证哈希
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
from urllib.parse import urljoin, urlparse, unquote

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# ---- Paths ---------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent  # crawler/
DATA_DIR = BASE_DIR / "data" / "guyana_epa"
ADAPTER_DIR = Path(__file__).resolve().parent  # crawler/adapters/

# ---- Config --------------------------------------------------------------

load_dotenv(BASE_DIR.parent / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("VITE_SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY")

# EPA Guyana Oil & Gas document listing page
EPA_OIL_GAS_URL = "https://epaguyana.org/download-category/oil-gas/"

# Base URL for resolving relative links
EPA_BASE_URL = "https://epaguyana.org/"

# robots.txt for epaguyana.org allows crawling with reasonable rate.
# We add a polite 5-10 second delay between requests.
MIN_REQUEST_DELAY_SEC = 5.0
MAX_REQUEST_DELAY_SEC = 10.0

USER_AGENT = (
    "Mozilla/5.0 (compatible; FPSOCrawler/1.0; +EPA-Guyana-Open-Data-Adapter)"
)

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")
NOW_ISO = datetime.now(timezone.utc).isoformat()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("guyana-epa-adapter")


# ============================================================================
# 1. 文档分类规则
# ============================================================================

# Event type mapping based on document category
DOC_CATEGORY_EVENT_MAP = {
    "EIA": "EIA_SUBMITTED",
    "PROJECT_SUMMARY": "PROJECT_SUMMARY",
    "PERMIT": "PERMIT_GRANTED",
    "PUBLIC_NOTICE": "PUBLIC_NOTICE",
    "ENV_MANAGEMENT_PLAN": "ENV_MANAGEMENT_PLAN",
    "TERMS_OF_REFERENCE": "TERMS_OF_REFERENCE",
    "SCREENING_DECISION": "SCREENING_DECISION",
    "OTHER": "REGULATORY_DATA",
}

# Classification patterns — ordered by priority (first match wins)
CATEGORY_PATTERNS = [
    ("EIA", [
        r"\beia(?:\b|[_\-.])", r"environmental\s+impact\s+assessment",
        r"environmental\s+impact\s+statement", r"\beis(?:\b|[_\-.])",
        r"environmental\s+assessment", r"\besia(?:\b|[_\-.])",
        # EPA Guyana naming: "Xxx Development Project" / "Xxx Dev Project" (ZIP archives)
        r"(?:dev|development)\s+project\s+vol",
        r"(?:dev|development)\s+project\s*\.(?:zip|pdf)",
    ]),
    ("PROJECT_SUMMARY", [
        r"project\s+summary", r"project\s+description",
        r"project\s+overview", r"project\s+profile",
        r"summary\s+of\s+project", r"non-technical\s+summary",
    ]),
    ("ENV_MANAGEMENT_PLAN", [
        r"environmental\s+management\s+plan", r"\bemp\b",
        r"environmental\s+protection\s+plan",
        r"environmental\s+management\s+framework",
    ]),
    ("TERMS_OF_REFERENCE", [
        r"terms\s+of\s+reference", r"\btor\b",
        r"scoping\s+document",
    ]),
    ("SCREENING_DECISION", [
        r"screening\s+decision", r"environmental\s+screening",
        r"screening\s+report", r"no\s+objection",
    ]),
    ("PERMIT", [
        r"environmental\s+permit", r"environmental\s+authorisation",
        r"environmental\s+authorization", r"permit\s+to\s+operate",
        r"discharge\s+permit", r"air\s+emission\s+permit",
        r"waste\s+management\s+permit", r"environmental\s+licen[cs]e",
        r"permit\s+condition", r"changed\s+permit",
        # Abbreviated forms common in EPA listings
        r"\benv\s+permit\b", r"\benv\s+auth\b",
        r"\benv\.?\s*permit\b", r"\benv\.?\s*auth\b",
        r"\benvironmental\s+permit\b", r"\benvoronmental\s+permit\b",
        r"\benvironemtal\s+permit\b", r"\benvrionmental\s+permit\b",
        r"\benviromental\s+permit\b",
        r"\bpermit\s+(?:renewed|new|interim)\b",
        r"signed\s+permit\b", r"operation\s+permit\b",
    ]),
    ("PUBLIC_NOTICE", [
        r"public\s+notice", r"public\s+notification",
        r"public\s+consultation", r"public\s+hearing",
        r"public\s+disclosure", r"stakeholder\s+engagement",
        r"gazette\s+notice", r"newspaper\s+notice",
    ]),
]


def classify_document(title: str, filename: str = "") -> str:
    """
    Classify a document into one of the standard categories.

    Uses regex matching against title and filename. Returns the category
    key (e.g. 'EIA', 'PERMIT', 'PROJECT_SUMMARY', 'PUBLIC_NOTICE').

    Falls back to 'OTHER' if no pattern matches.
    """
    text = f"{title} {filename}".lower()

    for category, patterns in CATEGORY_PATTERNS:
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                log.debug("  Classified as %s (pattern: %s)", category, pattern)
                return category

    log.debug("  Could not classify, defaulting to OTHER")
    return "OTHER"


# ---- Oil & Gas relevance keywords ------------------------------------------
# Documents must contain at least one of these to be considered relevant
# to FPSO project tracking. The EPA page lists ALL environmental permits,
# including gas stations, banks, and call centers.

OIL_GAS_KEYWORDS = [
    # FPSO / offshore projects
    r"\bfpso\b", r"floating\s+production", r"offshore",
    r"\beia\b", r"environmental\s+impact\s+assessment",
    # Project names
    r"\bliza\b", r"\bpayara\b", r"\byellowtail\b", r"\buaru\b",
    r"\bwhiptail\b", r"\bhammerhead\b", r"\blongtail\b",
    r"\bstabroek\b", r"\bcanje\b", r"\bkaieteur\b", r"\bcorentyne\b",
    # Oil & gas specific
    r"oil\s*(?:&|and)?\s*gas", r"petroleum", r"crude\s+oil",
    r"crude\s+lift", r"hydrocarbon", r"upstream",
    r"drilling", r"exploration\s+well", r"development\s+well",
    r"production\s+platform", r"subsea", r"pipeline",
    # Gas to Energy
    r"gas\s+to\s+energy", r"natural\s+gas\s+(?:pipeline|liquid|processing)",
    # Operators
    r"exxon", r"hess", r"cnooc", r"repsol", r"tullow",
    r"eco\s*\(\s*atlantic\s*\)", r"frontera", r"cgx",
    # Environmental permits specifically for petroleum operations
    r"env(?:ironmental)?\s+permit.*(?:petroleum|crude|oil|offshore|drill|well)",
    r"env(?:ironmental)?\s+auth.*(?:petroleum|crude|oil|offshore|drill|well)",
    r"permit.*crude\s+oil\s+lift",
    r"operation\s+permit.*(?:offshore|petroleum)",
    # Screening/TOR/EMP for oil & gas projects
    r"screening.*(?:offshore|petroleum|oil|drill)",
    r"terms\s+of\s+reference.*(?:offshore|petroleum|oil)",
    r"environmental\s+management\s+plan.*(?:offshore|petroleum|oil)",
    # Block references
    r"block\s+\d+", r"stabroek", r"canje", r"kaieteur",
]

# Documents that should be excluded (common false positives on EPA page)
NON_OIL_GAS_PATTERNS = [
    r"service\s+station", r"gas\s+station", r"petrol\s+station",
    r"bank", r"call\s+center", r"telephone", r"retail",
    r"manufacturing", r"agriculture", r"forestry", r"mining",
    r"quarry", r"hotel", r"restaurant", r"supermarket",
    r"pharmacy", r"hospital", r"school", r"church",
    r"radioactive", r"basel\s+convention", r"noise\s+permit",
    r"osmd", r"existing\s+operations",
]


def is_oil_gas_relevant(title: str, filename: str = "", category: str = "") -> bool:
    """
    Filter: determine if a document is relevant to FPSO/oil & gas tracking.

    The EPA page contains ALL environmental permits, including gas stations,
    banks, call centers, and non-petroleum industries. This function filters
    to keep only documents with oil & gas / offshore / FPSO relevance.

    Documents classified as EIA, PROJECT_SUMMARY, or ENV_MANAGEMENT_PLAN
    are automatically considered relevant.

    Returns True if the document should be kept.
    """
    text = f"{title} {filename}".lower()

    # Auto-include: known project categories
    auto_include_categories = {"EIA", "PROJECT_SUMMARY", "ENV_MANAGEMENT_PLAN",
                                "TERMS_OF_REFERENCE", "SCREENING_DECISION"}
    if category in auto_include_categories:
        return True

    # Check exclusion patterns first (gas stations, shops, etc.)
    for pattern in NON_OIL_GAS_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            log.debug("  Excluded by non-oil-gas pattern: %s", pattern)
            return False

    # Check for oil & gas keywords
    for pattern in OIL_GAS_KEYWORDS:
        if re.search(pattern, text, re.IGNORECASE):
            log.debug("  Included by oil-gas pattern: %s", pattern)
            return True

    # For PERMIT category: only include those with oil/gas keywords
    if category == "PERMIT":
        # Be stricter — many permits are for non-petroleum activities
        log.debug("  Excluded: PERMIT without oil-gas keywords")
        return False

    # Default: exclude
    log.debug("  Excluded: no oil-gas relevance found")
    return False


# ============================================================================
# 2. 项目名称/别名提取
# ============================================================================

# Known Guyana offshore project names for alias extraction
KNOWN_GUYANA_PROJECTS = [
    "Liza", "Payara", "Yellowtail", "Uaru", "Whiptail",
    "Hammerhead", "Longtail", "Gas to Energy",
    "Canje", "Kaieteur", "Stabroek", "Corentyne",
]

# Project name patterns in document titles
PROJECT_NAME_PATTERNS = [
    # "Xxx Development Project EIA" or "Xxx Dev Project EIA" → "Xxx"
    re.compile(
        r"(?P<name>[A-Z][a-zA-Z]+(?:\s+(?:to|de|del|dos|das)\s+[A-Z][a-zA-Z]+(?:\s+Phase\s+\d+)?)?)"
        r"\s+(?:(?:Development|Dev)\s+)?Project",
        re.IGNORECASE,
    ),
    # "Xxx Phase N EIA" → "Xxx Phase N"
    re.compile(
        r"(?P<name>[A-Z][a-zA-Z]+(?:\s+Phase\s+\d+)?)"
        r"\s+(?:EIA|Environmental\s+Impact|ESIA)",
        re.IGNORECASE,
    ),
    # "Xxx Field/Block/Well/Discovery" (but NOT preceded by number/dash like "35Well")
    re.compile(
        r"(?<!\d)(?<![a-z])(?P<name>[A-Z][a-zA-Z]+)"
        r"\s+(?:Field|Block|Well|Discovery)",
        re.IGNORECASE,
    ),
    # "Xxx - EIA" or "Xxx - Environmental ..." (e.g., "Uaru - EIA.pdf")
    re.compile(
        r"(?P<name>[A-Z][a-zA-Z]+(?:\s+Phase\s+\d+)?)"
        r"\s*[-–]\s*(?:EIA|Environmental|ESIA)",
        re.IGNORECASE,
    ),
    # "Xxx Dev Project" or "Xxx Development Project" (ZIP containing EIA volumes)
    re.compile(
        r"(?P<name>[A-Z][a-zA-Z]+(?:\s+(?:to|de)\s+[A-Z][a-zA-Z]+)?)"
        r"\s+(?:Dev|Development)\s+Project",
        re.IGNORECASE,
    ),
]


def extract_project_alias(title: str, filename: str = "") -> str:
    """
    Extract project alias from document title/filename.

    Examples:
      'Payara Development Project EIA' → 'Payara'
      'Liza Phase 2 EIA Vol 1-3' → 'Liza Phase 2'
      'Yellowtail Dev Project Vol 1-3' → 'Yellowtail'
      '35Well-EIA_Compiled_May-2023' → '35Well' (exploratory drilling)

    Returns empty string if no alias can be extracted.
    """
    text = title.strip() if title else filename.strip()

    # First pass: look for known project names (most reliable)
    text_lower = text.lower()
    for proj in sorted(KNOWN_GUYANA_PROJECTS, key=len, reverse=True):
        if proj.lower() in text_lower:
            # Try to capture phase info: "Liza Phase 2"
            phase_m = re.search(
                rf"{re.escape(proj)}\s+(Phase\s+\d+)",
                text,
                re.IGNORECASE,
            )
            if phase_m:
                alias = f"{proj} {phase_m.group(1)}"
                log.debug("  Project alias (known + phase): %s", alias)
                return alias
            log.debug("  Project alias (known): %s", proj)
            return proj

    # Second pass: try structured patterns
    for pattern in PROJECT_NAME_PATTERNS:
        m = pattern.search(text)
        if m:
            name = m.group("name").strip()
            # Normalize
            name = re.sub(r"\s+", " ", name)
            # Filter out false positives
            if name.lower() in ("gas", "oil", "the", "new", "first", "well"):
                continue
            log.debug("  Project alias (pattern): %s", name)
            return name

    # Third pass: try to extract capitalized multi-word phrase from beginning
    words = text.split()
    if words:
        # Take capitalized words from start
        alias_parts = []
        for w in words[:6]:  # look at first 6 words max
            if w[0].isupper() and w.lower() not in (
                "the", "a", "an", "of", "for", "and", "with",
                "development", "project", "environmental", "impact",
                "assessment", "volume", "vol", "rev", "phase",
            ):
                alias_parts.append(w)
            elif w.lower() in ("phase",) and len(words) > words.index(w) + 1:
                # "Phase 2" → keep together
                phase_idx = words.index(w)
                if phase_idx + 1 < len(words):
                    alias_parts.append(f"{w} {words[phase_idx + 1]}")
                break
            else:
                break
        if alias_parts:
            alias = " ".join(alias_parts)
            log.debug("  Project alias (capitalized): %s", alias)
            return alias

    return ""


# ============================================================================
# 3. 日期解析
# ============================================================================

# Month name mapping for date parsing
MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


def parse_date_from_text(text: str) -> Optional[str]:
    """
    Parse a date string from various formats into YYYY-MM-DD.

    Handles:
      - "July 3, 2025"
      - "2025-07-03"
      - "03/07/2025"
      - "June 29, 2026"
      - "2023-09-15"
    """
    if not text:
        return None

    text = text.strip()

    # ISO format: 2025-07-03
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", text)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

    # US date: 07/03/2025
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", text)
    if m:
        return f"{m.group(3)}-{m.group(1)}-{m.group(2)}"

    # "Month DD, YYYY"
    m = re.match(
        r"(January|February|March|April|May|June|July|August|"
        r"September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})",
        text,
        re.IGNORECASE,
    )
    if m:
        month = MONTH_MAP[m.group(1).lower()]
        day = int(m.group(2))
        year = int(m.group(3))
        return f"{year:04d}-{month:02d}-{day:02d}"

    # Try to find any year-month-day pattern in the text
    m = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", text)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

    # Month abbreviation: "Jan 15, 2025"
    m = re.match(
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{1,2}),?\s+(\d{4})",
        text,
        re.IGNORECASE,
    )
    if m:
        month = MONTH_MAP[m.group(1).lower()[:3]]
        day = int(m.group(2))
        year = int(m.group(3))
        return f"{year:04d}-{month:02d}-{day:02d}"

    # Extract year from filename (common in EPA documents)
    m = re.search(r"(?:19|20)(\d{2})[/_-](\d{1,2})[/_-](\d{1,2})", text)
    if m:
        year = 1900 + int(m.group(1)) if int(m.group(1)) > 50 else 2000 + int(m.group(1))
        return f"{year:04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

    return None


def extract_date_from_filename(filename: str) -> Optional[str]:
    """
    Try to extract a date from a filename.

    Examples:
      - 'hammerhead development project eia_september 2025.pdf' → '2025-09-01'
      - 'canje-12-well-eia-sept-2023.pdf' → '2023-09-01'
      - '35well-eia_compiled_may-2023.pdf' → '2023-05-01'
    """
    if not filename:
        return None

    fname_lower = filename.lower()

    # "Month YYYY" pattern
    for month_name, month_num in MONTH_MAP.items():
        m = re.search(rf"\b{month_name}\w*\s+(\d{{4}})\b", fname_lower)
        if m:
            year = int(m.group(1))
            return f"{year:04d}-{month_num:02d}-01"

    # "YYYY-MM" or "YYYY_MM" pattern
    m = re.search(r"(\d{4})[/_-](\d{1,2})(?:[/_-](\d{1,2}))?", fname_lower)
    if m:
        year = int(m.group(1))
        month = int(m.group(2))
        day = int(m.group(3)) if m.group(3) else 1
        if 1 <= month <= 12 and 1 <= day <= 31:
            return f"{year:04d}-{month:02d}-{day:02d}"

    return None


# ============================================================================
# 4. HTTP 会话 & 页面获取
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
    """
    Fetch a page and return its HTML text.

    Returns None on failure.
    """
    try:
        log.info("Fetching %s ...", url)
        resp = session.get(url, timeout=60)
        resp.raise_for_status()
        log.info("  HTTP %d, %d bytes", resp.status_code, len(resp.content))
        return resp.text
    except requests.exceptions.HTTPError as e:
        log.warning("  HTTP %s — %s", e.response.status_code if hasattr(e, 'response') else '?', url)
        return None
    except requests.exceptions.RequestException as e:
        log.warning("  Request failed: %s — %s", e, url)
        return None


# ============================================================================
# 5. 页面解析
# ============================================================================


def parse_wpdm_documents(html: str) -> list[dict]:
    """
    Parse the EPA page HTML and extract all document entries from WPDM grids.

    The page uses WordPress Download Manager (WPDM) with structure:
      <div class="wpdm-filelist-grid" id="wpdm-filelist-grid-PACKAGE_ID">
        <div class="wpdm-filelist-item" data-filename="...">
          <div class="wpdm-filelist-item__title">Display Title</div>
          <a class="inddl" href="...">Download</a>
        </div>
      </div>

    Package-level metadata is in the preceding <div class="doc-summary">:
      - "Create Date" → publication date
      - "Last updated" → last modified date

    Returns:
        List of document dicts with keys:
        - title: display title
        - filename: original filename with extension
        - download_url: WPDM download URL
        - source_url: the page URL for this document
        - publication_date: 'Create Date' from doc-summary (YYYY-MM-DD)
        - last_updated: 'Last updated' from doc-summary (YYYY-MM-DD)
        - package_id: WPDM package ID
        - file_hash: will be populated after download
    """
    soup = BeautifulSoup(html, "html.parser")
    documents = []

    # Find all WPDM filelist grids
    grids = soup.select(".wpdm-filelist-grid")
    log.info("Found %d WPDM filelist grid(s) on page", len(grids))

    for grid in grids:
        # Extract the package ID from the grid's id attribute
        grid_id = grid.get("id", "")
        package_id = ""
        m = re.search(r"wpdm-filelist-grid-(\d+)", grid_id)
        if m:
            package_id = m.group(1)

        # Find the package-level doc-summary metadata
        # The doc-summary is in the same w3eden container, preceding the grid
        package_meta = {}
        container = grid.find_parent(class_="w3eden")
        if container:
            doc_summary = container.find(class_="doc-summary")
            if doc_summary:
                for row in doc_summary.select("tr"):
                    cells = row.select("td")
                    if len(cells) == 2:
                        label = cells[0].get_text(strip=True).lower()
                        value = cells[1].get_text(strip=True)
                        package_meta[label] = value

        # Parse package create date
        create_date_str = package_meta.get("create date", "")
        publication_date = parse_date_from_text(create_date_str)

        last_updated_str = package_meta.get("last updated", "")
        last_updated = parse_date_from_text(last_updated_str)

        # If no create date from doc-summary, try to extract from filenames
        if not publication_date:
            log.debug("  Package %s: no create date in doc-summary", package_id)

        # Parse individual file items
        items = grid.select(".wpdm-filelist-item")
        log.info("  Package %s: %d file item(s)", package_id or "?", len(items))

        for item in items:
            # Extract display title
            title_el = item.select_one(".wpdm-filelist-item__title")
            title = title_el.get_text(strip=True) if title_el else ""

            # Extract data-filename
            filename = item.get("data-filename", "")

            # Extract download URL
            download_link = item.select_one("a.inddl")
            download_url = ""
            if download_link:
                download_url = download_link.get("href", "")
                # Resolve relative URL
                if download_url and not download_url.startswith("http"):
                    download_url = urljoin(EPA_BASE_URL, download_url)

            # If no title from element, use filename
            if not title and filename:
                title = filename

            # Skip items without meaningful titles
            if not title or len(title) < 3:
                continue

            # Try to extract date from filename if no package-level date
            doc_date = publication_date
            if not doc_date:
                doc_date = extract_date_from_filename(filename)
            if not doc_date:
                # Fall back to last updated
                doc_date = last_updated

            # Classify document
            category = classify_document(title, filename)

            # Filter: only keep oil & gas relevant documents
            if not is_oil_gas_relevant(title, filename, category):
                continue

            # Extract project alias
            project_alias = extract_project_alias(title, filename)

            # Build the download URL
            # WPDM download URLs: ?wpdmdl=PACKAGE_ID&ind=INDEX&filename=NAME
            if download_url:
                source_url = EPA_OIL_GAS_URL  # the listing page
            else:
                source_url = EPA_OIL_GAS_URL

            doc = {
                "title": title,
                "filename": filename,
                "download_url": download_url,
                "source_url": source_url,
                "publication_date": doc_date or "",
                "last_updated": last_updated or "",
                "package_id": package_id,
                "category": category,
                "event_type": DOC_CATEGORY_EVENT_MAP.get(category, "REGULATORY_DATA"),
                "project_alias": project_alias,
                "file_hash": "",  # populated after download
                "country": "Guyana",
            }

            documents.append(doc)
            log.info(
                "  [%s] %s (%s)",
                doc["event_type"],
                title[:80],
                project_alias or "no alias",
            )

    log.info("Total documents parsed: %d", len(documents))
    return documents


# ============================================================================
# 6. 文件下载
# ============================================================================


def download_document(
    doc: dict,
    session: requests.Session,
    data_dir: Path = DATA_DIR,
) -> Optional[str]:
    """
    Download a document's PDF/ZIP attachment.

    Uses the WPDM download URL. The URL redirects to the actual file.
    Saves the file to data_dir with a sanitized filename.

    Returns:
        (sha256_hex, local_path) on success, or (None, None) on failure.
    """
    download_url = doc.get("download_url", "")
    if not download_url:
        log.warning("  No download URL for: %s", doc.get("title", "?"))
        return None, None

    data_dir.mkdir(parents=True, exist_ok=True)

    # Generate a safe local filename
    filename = doc.get("filename", "")
    title = doc.get("title", "document")
    if filename:
        # Sanitize: remove path separators, keep extension
        safe_name = re.sub(r"[^\w\-_. ()]", "_", filename)
        safe_name = re.sub(r"_+", "_", safe_name)
    else:
        # Fallback: derive from title
        safe_name = re.sub(r"[^\w\-_. ()]", "_", title)[:100]
        # Ensure extension
        if not re.search(r"\.\w{2,5}$", safe_name):
            safe_name += ".pdf"

    local_path = data_dir / safe_name

    # Check if file already exists (avoid re-download)
    if local_path.exists():
        log.info("  File already exists: %s", local_path.name)
        file_hash = hashlib.sha256(local_path.read_bytes()).hexdigest()
        return file_hash, local_path

    try:
        log.info("  Downloading: %s", safe_name)
        # WPDM uses a download handler URL that redirects to the actual file
        # The WPDM download link format: ?wpdmdl=ID&ind=INDEX&filename=NAME
        resp = session.get(download_url, timeout=120, allow_redirects=True)
        resp.raise_for_status()

        # Check content type — we want PDFs, ZIPs, DOCs
        content_type = resp.headers.get("Content-Type", "").lower()
        content = resp.content

        # If response is empty or HTML (error page), skip
        if len(content) < 100:
            log.warning("  Downloaded file too small (%d bytes): %s", len(content), safe_name)
            return None, None
        if content_type.startswith("text/html") or b"<!DOCTYPE" in content[:100]:
            log.warning("  Response appears to be HTML, not a file: %s", safe_name)
            return None, None

        # Save the file
        local_path.write_bytes(content)
        file_hash = hashlib.sha256(content).hexdigest()

        # Save SHA256 sidecar
        hash_path = data_dir / f"{safe_name}.sha256"
        hash_path.write_text(f"{file_hash}  {safe_name}\n")

        log.info("  Saved: %s (%d bytes, SHA256=%s)", local_path.name, len(content), file_hash[:16])
        return file_hash, local_path

    except requests.exceptions.RequestException as e:
        log.warning("  Download failed: %s — %s", e, safe_name)
        return None, None
    except Exception as e:
        log.warning("  Error saving file: %s — %s", e, safe_name)
        return None, None


# ============================================================================
# 7. 去重
# ============================================================================


def deduplicate_documents(documents: list[dict]) -> list[dict]:
    """
    Deduplicate documents by download URL + file hash.

    Two documents with the same download URL are considered identical.
    Documents with the same file hash but different URLs are also duplicates
    (same file uploaded to different packages).
    """
    seen_urls = set()
    seen_hashes = set()
    unique = []

    for doc in documents:
        url = doc.get("download_url", "")
        fhash = doc.get("file_hash", "")

        # Skip if same URL already seen
        if url and url in seen_urls:
            log.info("  Skipping duplicate (URL): %s", doc.get("title", "")[:80])
            continue

        # Skip if same file hash already seen
        if fhash and fhash in seen_hashes:
            log.info("  Skipping duplicate (hash): %s", doc.get("title", "")[:80])
            continue

        if url:
            seen_urls.add(url)
        if fhash:
            seen_hashes.add(fhash)
        unique.append(doc)

    if len(documents) > len(unique):
        log.info("Dedup: %d → %d documents", len(documents), len(unique))
    return unique


# ============================================================================
# 8. candidate_events 输出
# ============================================================================


def build_candidate_event(doc: dict, raw_html_path: str = "") -> dict:
    """
    Convert a parsed EPA document into a candidate_events table record.

    candidate_events column mapping:
      project_name_raw ← project alias or document title
      country          ← "Guyana"
      summary          ← structured summary (category, filename, date)
      source_name      ← "Guyana EPA Oil & Gas Documents"
      source_url       ← EPA listing page or download URL
      review_status    ← "pending"
      event_type       ← mapped from document category (EIA_SUBMITTED, etc.)
      fetched_at       ← ISO timestamp (system time)
      evidence_quote   ← document title + page reference (if any)
      raw_json         ← full document metadata as JSON
    """
    title = doc.get("title", "")
    filename = doc.get("filename", "")
    category = doc.get("category", "OTHER")
    event_type = doc.get("event_type", "REGULATORY_DATA")
    project_alias = doc.get("project_alias", "")
    publication_date = doc.get("publication_date", "")
    download_url = doc.get("download_url", "")
    file_hash = doc.get("file_hash", "")
    source_url = doc.get("source_url", EPA_OIL_GAS_URL)

    # project_name_raw: use project alias if available, else document title
    project_name_raw = project_alias if project_alias else title

    # Build structured summary
    summary_parts = []
    if category != "OTHER":
        summary_parts.append(f"Category: {category}")
    if filename:
        summary_parts.append(f"File: {filename}")
    if publication_date:
        summary_parts.append(f"Published: {publication_date}")
    if file_hash:
        summary_parts.append(f"SHA256: {file_hash[:16]}")

    summary = " | ".join(summary_parts) if summary_parts else title[:500]

    # evidence_quote: document title, for human review
    evidence_quote = title
    if publication_date:
        evidence_quote += f" (Published: {publication_date})"

    return {
        "project_name_raw": project_name_raw[:255],
        "country": "Guyana",
        "summary": summary[:500],
        "source_name": "Guyana EPA Oil & Gas Documents",
        "source_url": source_url[:2048],
        "review_status": "pending",
        "event_type": event_type,
        "fetched_at": NOW_ISO,
        "evidence_quote": evidence_quote[:500],
        "raw_json": json.dumps(doc, ensure_ascii=False),
    }


# ============================================================================
# 9. Supabase 写入
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
            "source_name": "Guyana EPA Oil & Gas Documents",
            "source_url": EPA_OIL_GAS_URL,
            "snapshot_date": TODAY,
            "fetched_at": NOW_ISO,
            "file_path": str(filepath),
            "file_hash_sha256": sha256,
            "record_count": record_count,
            "source_type": "GOVERNMENT",
            "tier": 2,
            "priority": "P0",
            "country_focus": "Guyana",
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
            "original_url": original_url or EPA_OIL_GAS_URL,
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
# 10. 快照差异对比
# ============================================================================


def _doc_key(doc: dict) -> str:
    """Derive a stable unique key from a document dict.
    Uses download_url (with cache-busting params stripped) if available,
    otherwise title + filename.
    """
    import re as _re
    url = (doc.get("download_url") or "").strip()
    if url:
        # Strip WPDM cache-busting query params (refresh, ind, _)
        normalized = _re.sub(r'[&?]refresh=\d+', '', url)
        normalized = _re.sub(r'[&?]ind=\d+', '', normalized)
        # Also strip trailing ? or & left after param removal
        normalized = normalized.rstrip('?&')
        return f"url:{normalized}"
    title = (doc.get("title") or "").strip()
    fname = (doc.get("filename") or "").strip()
    return f"title:{title}|{fname}"


DOC_COMPARE_FIELDS = [
    "title", "filename", "download_url", "publication_date",
    "file_hash", "category", "event_type", "project_alias",
]


def load_previous_snapshot_local(date_str: str = None) -> Optional[list[dict]]:
    """
    Load the most recent non-today snapshot JSON from the data directory.
    Returns the 'documents' list from the snapshot, or None if no previous snapshot.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    snapshots = sorted(DATA_DIR.glob("*_snapshot.json"), reverse=True)

    if date_str:
        target = DATA_DIR / f"{date_str}_snapshot.json"
        if target.exists():
            data = json.loads(target.read_text(encoding="utf-8"))
            return data.get("documents", [])

    for sp in snapshots:
        if TODAY in sp.name:
            continue
        log.info("Loading previous snapshot from %s", sp)
        data = json.loads(sp.read_text(encoding="utf-8"))
        return data.get("documents", [])

    log.info("No previous local snapshot found.")
    return None


def diff_documents(
    current: list[dict],
    previous: Optional[list[dict]],
) -> dict:
    """
    Compare current document list against previous snapshot.

    Unique key: download_url (preferred) or title + filename.

    Returns:
        {
            "new": [doc, ...],         # documents not in previous snapshot
            "changed": [(doc, prev, diffs), ...],  # same key, different fields
            "removed": [prev_doc, ...],  # in previous but not current
            "unchanged": [doc, ...],    # identical to previous
        }
    """
    if previous is None:
        return {
            "new": list(current),
            "changed": [],
            "removed": [],
            "unchanged": [],
        }

    # Build lookup by key
    cur_by_key = {}
    for doc in current:
        key = _doc_key(doc)
        if key in cur_by_key:
            # Keep the first occurrence; later duplicates were dedup'd
            continue
        cur_by_key[key] = doc

    prev_by_key = {}
    for doc in previous:
        key = _doc_key(doc)
        if key in prev_by_key:
            continue
        prev_by_key[key] = doc

    cur_keys = set(cur_by_key.keys())
    prev_keys = set(prev_by_key.keys())

    new = [cur_by_key[k] for k in (cur_keys - prev_keys)]
    removed = [prev_by_key[k] for k in (prev_keys - cur_keys)]

    changed = []
    unchanged = []

    for key in cur_keys & prev_keys:
        cur_doc = cur_by_key[key]
        prev_doc = prev_by_key[key]

        diffs = []
        for field in DOC_COMPARE_FIELDS:
            cur_val = str(cur_doc.get(field, "")).strip()
            prev_val = str(prev_doc.get(field, "")).strip()
            if cur_val != prev_val:
                diffs.append((field, prev_val, cur_val))

        if diffs:
            changed.append((cur_doc, prev_doc, diffs))
        else:
            unchanged.append(cur_doc)

    return {
        "new": new,
        "changed": changed,
        "removed": removed,
        "unchanged": unchanged,
    }


# ============================================================================
# 11. 本地存储 (审计)
# ============================================================================


def save_raw_html(html: str, date_str: str = TODAY) -> Path:
    """Save the raw HTML response for audit purposes."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    filepath = DATA_DIR / f"{date_str}_epa_oil_gas.html"
    filepath.write_text(html, encoding="utf-8")

    sha256 = hashlib.sha256(html.encode("utf-8")).hexdigest()
    hash_path = DATA_DIR / f"{date_str}_epa_oil_gas.html.sha256"
    hash_path.write_text(f"{sha256}  {date_str}_epa_oil_gas.html\n")

    log.info("Saved raw HTML to %s (SHA256=%s)", filepath, sha256[:16])
    return filepath


def save_local_snapshot(documents: list[dict], date_str: str = TODAY) -> Path:
    """Save parsed document metadata as JSON snapshot for audit/diff."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    filepath = DATA_DIR / f"{date_str}_snapshot.json"
    data = {
        "date": date_str,
        "fetched_at": NOW_ISO,
        "source_url": EPA_OIL_GAS_URL,
        "total_documents": len(documents),
        "documents": [
            {k: v for k, v in d.items()}
            for d in documents
        ],
    }
    filepath.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info("Saved local snapshot to %s (%d documents)", filepath, len(documents))
    return filepath


# ============================================================================
# 11. 主流程
# ============================================================================


def run_adapter(
    dry_run: bool = False,
    local_only: bool = False,
    skip_download: bool = False,
    no_diff: bool = False,
    supabase=None,
) -> dict:
    """
    Adapter main flow.

    Args:
        dry_run: Parse & download, but don't write to Supabase.
        local_only: Save files locally, don't write to Supabase.
        skip_download: Skip downloading PDF attachments (parse only).
        no_diff: Skip snapshot diff — treat all documents as new.
        supabase: Supabase client (optional).

    Returns:
        Result summary dict.
    """
    log.info("=" * 60)
    log.info("Guyana EPA Oil & Gas Document Adapter — %s", TODAY)
    log.info("=" * 60)

    session = build_session()

    # Step 1: Fetch the EPA Oil & Gas listing page
    delay = random.uniform(MIN_REQUEST_DELAY_SEC, MAX_REQUEST_DELAY_SEC)
    log.info("Waiting %.1fs (polite delay per robots.txt)...", delay)
    time.sleep(delay)

    html = fetch_page(EPA_OIL_GAS_URL, session)
    if html is None:
        raise RuntimeError(f"Failed to fetch page: {EPA_OIL_GAS_URL}")

    # Step 2: Save raw HTML for audit
    raw_html_path = save_raw_html(html)
    html_sha256 = hashlib.sha256(html.encode("utf-8")).hexdigest()

    # Save to source_documents for audit trail
    if not dry_run and not local_only:
        save_to_source_documents(
            raw_html_path, html_sha256, "HTML",
            len(html.encode("utf-8")),
            original_url=EPA_OIL_GAS_URL,
            supabase=supabase,
        )

    # Step 3: Parse WPDM document entries
    log.info("--- Parsing WPDM document entries ---")
    documents = parse_wpdm_documents(html)

    if not documents:
        log.warning("No documents found on the page. The page structure may have changed.")
        return {
            "mode": "dry_run" if dry_run else ("local_only" if local_only else "full"),
            "total_documents": 0,
            "diff_new": 0, "diff_changed": 0,
            "diff_removed": 0, "diff_unchanged": 0,
            "error": "No documents parsed",
            "html_path": str(raw_html_path),
            "html_sha256": html_sha256,
        }

    # Step 4: Classify and extract metadata
    log.info("--- Classification Summary ---")
    category_counts = {}
    for doc in documents:
        cat = doc.get("category", "OTHER")
        category_counts[cat] = category_counts.get(cat, 0) + 1
    for cat, count in sorted(category_counts.items()):
        log.info("  %s: %d", cat, count)

    # Step 5: Download attachments (unless --skip-download)
    if not skip_download:
        log.info("--- Downloading Attachments ---")
        for i, doc in enumerate(documents):
            delay = random.uniform(MIN_REQUEST_DELAY_SEC, MAX_REQUEST_DELAY_SEC)
            # No delay before first download (already waited before page fetch)
            if i > 0:
                log.info("  Waiting %.1fs (polite delay)...", delay)
                time.sleep(delay)

            result = download_document(doc, session, DATA_DIR)
            if result and result[0]:
                file_hash, local_path = result
                doc["file_hash"] = file_hash
                # Save to source_documents for audit trail
                if not dry_run and not local_only:
                    ext = (doc.get("filename", "") or "").lower()
                    if ext.endswith(".zip"):
                        file_type = "ZIP"
                    elif ext.endswith(".pdf"):
                        file_type = "PDF"
                    else:
                        file_type = "OTHER"
                    save_to_source_documents(
                        local_path, file_hash, file_type,
                        local_path.stat().st_size if local_path.exists() else 0,
                        original_url=doc.get("source_url", EPA_OIL_GAS_URL),
                        download_url=doc.get("download_url", ""),
                        publication_date=doc.get("publication_date", ""),
                        supabase=supabase,
                    )
    else:
        log.info("--- Skipping Downloads (--skip-download) ---")

    # Step 6: Deduplicate
    documents = deduplicate_documents(documents)

    # Step 7: Snapshot diff — compare with previous run
    if no_diff:
        previous_snapshot = None
        log.info("--- Snapshot Diff: --no-diff (all documents treated as new) ---")
    else:
        log.info("--- Snapshot Diff ---")
        previous_snapshot = load_previous_snapshot_local()

    diff_result = diff_documents(documents, previous_snapshot)

    log.info("  New:        %d", len(diff_result["new"]))
    log.info("  Changed:    %d", len(diff_result["changed"]))
    log.info("  Removed:    %d", len(diff_result["removed"]))
    log.info("  Unchanged:  %d (skipped)", len(diff_result["unchanged"]))

    # Step 8: Save current snapshot for next diff
    snapshot_path = save_local_snapshot(documents)

    # Step 9: Build candidate_events — only for new/changed/removed documents
    log.info("--- Building candidate_events (diff only) ---")
    events = []

    for doc in diff_result["new"]:
        evt = build_candidate_event(doc, str(raw_html_path))
        events.append(evt)

    for cur_doc, prev_doc, diffs in diff_result["changed"]:
        evt = build_candidate_event(cur_doc, str(raw_html_path))
        # Enrich with change details for review
        change_desc = "; ".join(
            f"{f}: {old} → {new}" for f, old, new in diffs
        )
        evt["summary"] = f"[CHANGED] {change_desc} | {evt['summary']}"
        # Include previous metadata in raw_json
        try:
            raw = json.loads(evt.get("raw_json", "{}"))
            raw["_change_details"] = [
                {"field": f, "previous": old, "current": new}
                for f, old, new in diffs
            ]
            evt["raw_json"] = json.dumps(raw, ensure_ascii=False)
        except json.JSONDecodeError:
            pass
        events.append(evt)

    for prev_doc in diff_result["removed"]:
        # Create a removal notice event
        title = prev_doc.get("title", "Unknown Document")
        evt = build_candidate_event(prev_doc, str(raw_html_path))
        evt["event_type"] = "DOCUMENT_REMOVED"
        evt["summary"] = f"[REMOVED] Document no longer on EPA page: {title}"
        events.append(evt)

    log.info("  Candidate events: %d (from %d docs)",
             len(events), len(documents))

    # Step 10: Write to Supabase (unless dry_run or local_only)
    inserted = 0
    write_to_db = not dry_run and not local_only
    if write_to_db and events:
        try:
            inserted = insert_candidate_events(events, supabase)
            log.info("  Inserted %d candidate_events rows", inserted)
        except RuntimeError as e:
            log.warning("  Skipping Supabase write: %s", e)

    # Step 11: Save snapshot metadata to Supabase
    if write_to_db:
        try:
            save_snapshot_to_registry(
                str(snapshot_path),
                html_sha256,
                len(documents),
                supabase,
            )
        except Exception:
            log.debug("snapshot_registry write skipped", exc_info=True)

    mode_str = "dry_run" if dry_run else ("local_only" if local_only else "full")
    result = {
        "mode": mode_str,
        "total_documents": len(documents),
        "by_category": category_counts,
        "diff_new": len(diff_result["new"]),
        "diff_changed": len(diff_result["changed"]),
        "diff_removed": len(diff_result["removed"]),
        "diff_unchanged": len(diff_result["unchanged"]),
        "candidate_events": len(events),
        "inserted": inserted,
        "html_path": str(raw_html_path),
        "html_sha256": html_sha256,
        "snapshot_path": str(snapshot_path),
        "data_dir": str(DATA_DIR),
    }

    log.info("=" * 60)
    log.info("Run complete.")
    log.info("  Mode: %s", mode_str)
    log.info("  Total documents: %d", result["total_documents"])
    log.info("  Diff: new=%d changed=%d removed=%d unchanged=%d",
             result["diff_new"], result["diff_changed"],
             result["diff_removed"], result["diff_unchanged"])
    log.info("  By category: %s", result["by_category"])
    log.info("  Candidate events: %d (inserted: %d)", result["candidate_events"], inserted)
    log.info("  HTML saved: %s", result["html_path"])
    log.info("  Data dir: %s", result["data_dir"])

    return result


# ============================================================================
# 12. 自测
# ============================================================================


def run_test():
    """
    Self-test: visit EPA page → list all documents → download first PDF →
    verify hash → output first 3 candidate events.

    Does NOT write to Supabase.
    """
    log.info("=" * 60)
    log.info("SELF-TEST: Guyana EPA Oil & Gas Document Adapter")
    log.info("=" * 60)

    session = build_session()

    # Step 1: Fetch page
    print("\n" + "─" * 60)
    print("Step 1: Fetch EPA Oil & Gas page")
    print("─" * 60)

    html = fetch_page(EPA_OIL_GAS_URL, session)
    if html is None:
        print("  FAILED: Could not fetch page.")
        sys.exit(1)

    print(f"  Downloaded: {len(html):,} bytes")
    html_hash = hashlib.sha256(html.encode("utf-8")).hexdigest()
    print(f"  HTML SHA256: {html_hash}")

    # Save HTML locally
    raw_html_path = save_raw_html(html)
    print(f"  Saved HTML: {raw_html_path}")

    # Step 2: Parse documents
    print("\n" + "─" * 60)
    print("Step 2: Parse WPDM Document Entries")
    print("─" * 60)

    documents = parse_wpdm_documents(html)
    print(f"\n  Total documents found: {len(documents)}")

    if not documents:
        print("  FAILED: No documents parsed. Page structure may have changed.")
        sys.exit(1)

    # Category summary
    from collections import Counter
    categories = Counter(d["category"] for d in documents)
    print("\n  Category breakdown:")
    for cat, count in categories.most_common():
        event_type = DOC_CATEGORY_EVENT_MAP.get(cat, "REGULATORY_DATA")
        print(f"    {cat}: {count} → event_type='{event_type}'")

    # Project aliases found
    aliases = [d["project_alias"] for d in documents if d.get("project_alias")]
    if aliases:
        print(f"\n  Project aliases extracted: {aliases}")

    # Step 3: Download first PDF
    print("\n" + "─" * 60)
    print("Step 3: Download First PDF/ZIP Attachment")
    print("─" * 60)

    # Find the first document with a download URL
    first_doc = None
    for doc in documents:
        if doc.get("download_url"):
            first_doc = doc
            break

    if first_doc:
        print(f"  Document: {first_doc['title'][:120]}")
        print(f"  URL: {first_doc['download_url'][:120]}")
        result = download_document(first_doc, session, DATA_DIR)
        if result and result[0]:
            file_hash, _ = result
            print(f"  Downloaded successfully!")
            print(f"  SHA256: {file_hash}")
            first_doc["file_hash"] = file_hash

            # Verify hash by re-reading the file
            print("\n  Verifying hash by re-reading file...")
            filename = first_doc.get("filename", "")
            safe_name = re.sub(r"[^\w\-_. ()]", "_", filename)
            local_path = DATA_DIR / safe_name
            if local_path.exists():
                verified_hash = hashlib.sha256(local_path.read_bytes()).hexdigest()
                if verified_hash == file_hash:
                    print(f"  ✓ Hash verified: {verified_hash}")
                else:
                    print(f"  ✗ HASH MISMATCH: stored={file_hash}, re-read={verified_hash}")
            else:
                print(f"  ⚠ File not found at {local_path}")
        else:
            print("  Download failed (see log for details).")
    else:
        print("  No downloadable document found (all have empty download_url).")

    # Step 4: Output first 3 candidate events
    print("\n" + "─" * 60)
    print("Step 4: Candidate Events (first 3)")
    print("─" * 60)

    events = []
    for doc in documents[:3]:
        evt = build_candidate_event(doc)
        events.append(evt)

    required_fields = [
        "project_name_raw", "country", "summary", "source_name",
        "source_url", "review_status", "event_type", "fetched_at",
        "evidence_quote",
    ]

    for i, evt in enumerate(events, 1):
        print(f"\n{'─' * 50}")
        print(f"Event #{i}")
        print(f"{'─' * 50}")

        for field in required_fields:
            val = evt.get(field, "MISSING")
            status = "✓" if val else "✗ EMPTY"
            display_val = str(val)[:120] if val else "EMPTY"
            print(f"  {status}  {field}: {display_val}")

        # Show raw_json preview
        raw_json = evt.get("raw_json", "")
        if raw_json:
            try:
                raw_obj = json.loads(raw_json)
                print(f"  ✓  raw_json keys: {list(raw_obj.keys())}")
                print(f"       category: {raw_obj.get('category', '?')}")
                print(f"       file_hash: {raw_obj.get('file_hash', '(not yet downloaded)')[:20]}")
            except json.JSONDecodeError:
                print(f"  ✗  raw_json: invalid JSON")

    # Step 5: Field completeness check
    print("\n" + "─" * 60)
    print("Step 5: Field Completeness Report")
    print("─" * 60)

    all_ok = True
    for i, evt in enumerate(events, 1):
        missing = [f for f in required_fields if not evt.get(f)]
        if missing:
            print(f"  Event #{i}: MISSING {missing}")
            all_ok = False

    if all_ok:
        print("  All events have complete required fields ✓")
    else:
        print("  ⚠ Some fields are missing (see above)")

    # Step 6: Summary
    print(f"\n{'─' * 60}")
    print(f"Step 6: Summary")
    print(f"{'─' * 60}")
    print(f"  Total documents parsed: {len(documents)}")
    print(f"  Category breakdown: {dict(categories)}")
    print(f"  HTML saved: {raw_html_path}")
    print(f"  Data directory: {DATA_DIR}")

    # List files in data dir
    files_in_dir = sorted(DATA_DIR.glob("*"))
    if files_in_dir:
        print(f"\n  Files in data directory ({len(files_in_dir)}):")
        for fp in files_in_dir:
            size = fp.stat().st_size
            print(f"    {fp.name} ({size:,} bytes)")

    print(f"\n{'─' * 60}")
    print("Self-test complete.")
    print("─" * 60)

    return events


# ============================================================================
# 13. CLI
# ============================================================================


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Guyana EPA Oil & Gas Documents Adapter — P0 专用适配器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python crawler/adapters/guyana_epa.py                 # 完整运行
  python crawler/adapters/guyana_epa.py --test           # 自测
  python crawler/adapters/guyana_epa.py --dry-run        # 仅解析和下载，不写入Supabase
  python crawler/adapters/guyana_epa.py --local-only     # 仅本地保存
  python crawler/adapters/guyana_epa.py --skip-download  # 仅解析，不下载文件
  python crawler/adapters/guyana_epa.py --no-diff        # 跳过差异对比，全量输出
        """,
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="自测: 访问EPA页面 → 列出所有文档 → 下载第一个PDF → 验证哈希 → 输出前3条候选事件。",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅解析页面、下载文件，不写入数据库。",
    )
    parser.add_argument(
        "--local-only",
        action="store_true",
        help="保存文件到本地，不写入 Supabase。",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="跳过 PDF/ZIP 下载，仅解析页面元数据。",
    )
    parser.add_argument(
        "--no-diff",
        action="store_true",
        help="跳过快照差异对比，将所有文档作为新增处理（首次运行或强制全量刷新）。",
    )
    args = parser.parse_args()

    # Self-test mode
    if args.test:
        try:
            run_test()
        except Exception as e:
            log.error("Self-test failed: %s", e, exc_info=True)
            sys.exit(1)
        return

    # Normal mode
    try:
        result = run_adapter(
            dry_run=args.dry_run,
            local_only=args.local_only,
            skip_download=args.skip_download,
            no_diff=args.no_diff,
        )
    except requests.exceptions.HTTPError as e:
        log.error("HTTP error: %s", e)
        sys.exit(1)
    except Exception as e:
        log.error("Adapter failed: %s", e, exc_info=True)
        sys.exit(1)

    # Output result summary as JSON
    print("\n" + json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
