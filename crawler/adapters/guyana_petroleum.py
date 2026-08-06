#!/usr/bin/env python3
"""
Guyana 石油管理计划适配器 — P0 专用适配器
==========================================

按《FPSO项目可用信息源使用手册》P0 要求实现：

来源信息:
  名称: Guyana 石油管理计划
  URL:  https://petroleum.gov.gy/projects-initiatives/environmental-protection-agency-
        esso-exploration-and-production-guyana-limited/
  类型: HTML 页面 + 附件链接
  优先级: P0
  层级: 2（官方验证）
  接入方式: 解析 HTML 页面，提取项目阶段、许可状态、开发范围、FPSO/海底系统描述

功能:
  1. 解析 Guyana 石油管理计划页面，提取项目信息（项目阶段、许可状态、开发范围等）。
  2. 按事件类型自动分类: PROJECT_SUMMARY, EIA_SUBMITTED, PERMIT_GRANTED。
  3. 下载附件到 crawler/data/guyana_petroleum/ 目录，记录 SHA256。
  4. 使用 URL + 文件哈希去重。
  5. 所有输出写入 candidate_events（review_status='pending'）。
  6. 与 Guyana EPA 适配器协作，形成圭亚那双源验证
     （EPA 确认环境许可 + 石油管理计划确认项目阶段/许可状态）。

合规:
  - 请求间隔 5-10 秒，遵守 robots.txt。
  - 保存原始 HTML 和附件副本。
  - 不绕过任何登录或验证。
  - 区分 publication_date 和 fetched_at。

Usage:
  python crawler/adapters/guyana_petroleum.py                 # 完整运行
  python crawler/adapters/guyana_petroleum.py --dry-run       # 仅解析和下载，不写入数据库
  python crawler/adapters/guyana_petroleum.py --local-only    # 仅本地保存
  python crawler/adapters/guyana_petroleum.py --test          # 自测
  python crawler/adapters/guyana_petroleum.py --no-diff       # 跳过差异对比
  python crawler/adapters/guyana_petroleum.py --skip-download # 仅解析，不下载文件
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
DATA_DIR = BASE_DIR / "data" / "guyana_petroleum"
ADAPTER_DIR = Path(__file__).resolve().parent  # crawler/adapters/

# ---- Config --------------------------------------------------------------

load_dotenv(BASE_DIR.parent / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("VITE_SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY")

# Guyana Petroleum Management — Project Initiatives page (per audit report)
GUYANA_PETROLEUM_URL = (
    "https://petroleum.gov.gy/projects-initiatives/"
    "environmental-protection-agency-esso-exploration-and-production-guyana-limited/"
)

# Additional URLs to check
ADDITIONAL_URLS = [
    GUYANA_PETROLEUM_URL,
    "https://petroleum.gov.gy/projects-initiatives/",
    "https://petroleum.gov.gy/",
]

# Source identity (must match source_registry.source_name)
SOURCE_NAME = "Guyana 石油管理计划"

MIN_REQUEST_DELAY_SEC = 5.0
MAX_REQUEST_DELAY_SEC = 10.0

USER_AGENT = (
    "Mozilla/5.0 (compatible; FPSOCrawler/1.0; +Guyana-Petroleum-Adapter)"
)

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")
NOW_ISO = datetime.now(timezone.utc).isoformat()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("guyana-petroleum-adapter")


# ============================================================================
# 1. 事件分类规则
# ============================================================================

# Event type mapping
DOC_CATEGORY_EVENT_MAP = {
    "PROJECT_SUMMARY": "PROJECT_SUMMARY",
    "EIA": "EIA_SUBMITTED",
    "PERMIT": "PERMIT_GRANTED",
    "LICENSE": "PERMIT_GRANTED",
    "FPSO_DETAIL": "PROJECT_SUMMARY",
    "SUBSEA_DETAIL": "PROJECT_SUMMARY",
    "LICENSING_ROUND": "REGULATORY_DATA",
    "PRODUCTION_LICENSE": "PERMIT_GRANTED",
    "OTHER": "REGULATORY_DATA",
}

CATEGORY_PATTERNS = [
    ("PROJECT_SUMMARY", [
        r"project\s+summary", r"project\s+description",
        r"project\s+overview", r"project\s+profile",
        r"development\s+scope", r"development\s+concept",
        r"field\s+development", r"production\s+profile",
        r"fpso\s+description", r"fpso\s+specification",
        r"fpso\s+design", r"fpso\s+vessel",
        r"subsea\s+system", r"subsea\s+description",
        r"subsea\s+infrastructure", r"subsea\s+architecture",
        r"production\s+facility", r"offshore\s+facility",
        r"operational\s+phase", r"production\s+phase",
        r"project\s+phase", r"development\s+timeline",
    ]),
    ("EIA", [
        r"\beia\b", r"environmental\s+impact\s+assessment",
        r"environmental\s+impact\s+statement", r"\beis\b",
        r"\besia\b", r"environmental\s+assessment",
        r"environmental\s+baseline\s+study",
        r"environmental\s+and\s+social\s+impact",
    ]),
    ("PERMIT", [
        r"environmental\s+permit", r"environmental\s+authorisation",
        r"environmental\s+authorization", r"permit\s+granted",
        r"permit\s+issued", r"permit\s+condition",
        r"environmental\s+licen[cs]e",
        r"\bpermiso\b",  # Spanish influence
    ]),
    ("LICENSE", [
        r"petroleum\s+licen[cs]e", r"production\s+licen[cs]e",
        r"exploration\s+licen[cs]e", r"development\s+licen[cs]e",
        r"licen[cs]e\s+(?:granted|issued|awarded|approved)",
        r"licensing\s+round", r"bid\s+round",
    ]),
    ("FPSO_DETAIL", [
        r"fpso\s+(?:vessel|unit|facility)", r"floating\s+production",
        r"production\s+storage\s+and\s+offloading",
        r"fpso\s+mooring", r"fpso\s+topside",
        r"fpso\s+capacity", r"fpso\s+contract",
        r"fpso\s+delivery", r"fpso\s+conversion",
        r"turret\s+mooring", r"spread\s+mooring",
    ]),
    ("SUBSEA_DETAIL", [
        r"subsea\s+(?:production|manifold|well|tree|umbilical|flowline|riser)",
        r"subsea\s+control\s+system", r"subsea\s+tieback",
        r"subsea\s+boosting", r"subsea\s+processing",
    ]),
    ("PRODUCTION_LICENSE", [
        r"production\s+licen[cs]e", r"petroleum\s+agreement",
        r"production\s+sharing\s+agreement", r"\bpsa\b",
        r"development\s+and\s+production\s+agreement",
    ]),
    ("LICENSING_ROUND", [
        r"licensing\s+round", r"bid\s+round",
        r"competitive\s+bidding", r"open\s+blocks",
        r"available\s+blocks", r"oil\s+blocks?\s+for\s+bid",
    ]),
]


def classify_document(title: str, text: str = "") -> str:
    """Classify document into category. First match wins."""
    combined = f"{title} {text}".lower()
    for category, patterns in CATEGORY_PATTERNS:
        for pattern in patterns:
            if re.search(pattern, combined, re.IGNORECASE):
                return category
    return "OTHER"


# ---- Guyana offshore project names for alias extraction --------------------

KNOWN_GUYANA_PROJECTS = [
    "Liza", "Liza Destiny", "Liza Unity", "Liza Phase 1", "Liza Phase 2",
    "Payara", "Payara Development",
    "Yellowtail", "Yellowtail Development",
    "Uaru", "Uaru Development",
    "Whiptail", "Whiptail Development",
    "Hammerhead", "Hammerhead Development",
    "Longtail", "Longtail Development",
    "Gas to Energy", "Gas-to-Energy",
    "Stabroek", "Stabroek Block",
    "Canje", "Canje Block",
    "Kaieteur", "Kaieteur Block",
    "Corentyne", "Corentyne Block",
    "35Well", "Pluma", "Tilapia", "Haimara",
    "Turbot", "Ranger", "Pacora", "Snoek",
]

PROJECT_NAME_PATTERNS = [
    re.compile(
        r"(?P<name>[A-Z][a-zA-Z]+(?:\s+(?:to|de|del|dos|das)\s+[A-Z][a-zA-Z]+(?:\s+Phase\s+\d+)?)?)"
        r"\s+(?:(?:Development|Dev)\s+)?Project",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?P<name>[A-Z][a-zA-Z]+(?:\s+Phase\s+\d+)?)"
        r"\s+(?:EIA|Environmental\s+Impact|ESIA|Development)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?P<name>[A-Z][a-zA-Z]+)"
        r"\s+(?:FPSO|Field|Block|Well|Discovery)",
        re.IGNORECASE,
    ),
    re.compile(
        r"Petroleum\s+(?:Agreement|Licen[cs]e)\s+(?:for|:)\s+(?P<name>[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)",
        re.IGNORECASE,
    ),
]


def extract_project_alias(title: str, text: str = "") -> str:
    """Extract project alias from title/text."""
    combined = f"{title} {text}"

    # Known project names first (most reliable)
    combined_lower = combined.lower()
    for proj in sorted(KNOWN_GUYANA_PROJECTS, key=len, reverse=True):
        if proj.lower() in combined_lower:
            phase_m = re.search(
                rf"{re.escape(proj)}\s+(Phase\s+\d+)",
                combined, re.IGNORECASE,
            )
            if phase_m:
                return f"{proj} {phase_m.group(1)}"
            return proj

    # Structured patterns
    for pattern in PROJECT_NAME_PATTERNS:
        m = pattern.search(combined)
        if m:
            name = m.group("name").strip()
            name = re.sub(r"\s+", " ", name)
            if name.lower() in ("gas", "oil", "the", "new", "first", "offshore"):
                continue
            return name

    return ""


# ---- Operator extraction ---------------------------------------------------

GUYANA_OPERATORS = [
    "ExxonMobil", "Exxon", "Hess", "CNOOC", "Nexen",
    "Repsol", "Tullow", "Eco Atlantic", "Frontera", "CGX",
    "Esso", "EEPGL",  # Esso Exploration and Production Guyana Limited
]

OPERATOR_PATTERNS = [
    re.compile(rf"\b({'|'.join(re.escape(o) for o in GUYANA_OPERATORS)})\b", re.IGNORECASE),
]


def extract_operator(text: str) -> str:
    """Extract operator from text."""
    for pattern in OPERATOR_PATTERNS:
        m = pattern.search(text)
        if m:
            op = m.group(1).strip()
            # Normalize
            op_lower = op.lower()
            if op_lower in ("exxon", "exxonmobil"):
                return "ExxonMobil"
            if op_lower == "esso":
                return "Esso (EEPGL)"
            if op_lower == "eepgl":
                return "EEPGL (Esso)"
            return op
    return ""


# ---- Relevance filter ------------------------------------------------------

OIL_GAS_KEYWORDS = [
    r"\bfpso\b", r"floating\s+production", r"offshore",
    r"oil\s*(?:&|and)?\s*gas", r"petroleum", r"crude\s+oil",
    r"hydrocarbon", r"upstream", r"drilling",
    r"exploration\s+well", r"development\s+well",
    r"production\s+platform", r"subsea", r"pipeline",
    r"stainless\s+steel", r"duplex", r"super\s+duplex",
    r"environmental\s+impact", r"\beia\b",
    r"environmental\s+permit", r"production\s+licen[cs]e",
    r"stabroek", r"liza", r"payara", r"yellowtail",
    r"uaru", r"whiptail", r"hammerhead", r"longtail",
    r"production\s+sharing", r"petroleum\s+agreement",
]

NON_OIL_GAS_PATTERNS = [
    r"service\s+station", r"gas\s+station",
    r"bank", r"call\s+center", r"retail",
    r"manufacturing", r"agriculture", r"forestry",
    r"mining", r"quarry", r"hotel", r"restaurant",
    r"pharmacy", r"hospital", r"school",
]


def is_oil_gas_relevant(title: str, text: str = "", category: str = "") -> bool:
    """Filter for oil/gas/FPSO relevance."""
    combined = f"{title} {text}".lower()

    auto_include = {"PROJECT_SUMMARY", "EIA", "FPSO_DETAIL", "SUBSEA_DETAIL",
                    "LICENSE", "PRODUCTION_LICENSE", "LICENSING_ROUND"}
    if category in auto_include:
        return True

    for pattern in NON_OIL_GAS_PATTERNS:
        if re.search(pattern, combined, re.IGNORECASE):
            return False

    for pattern in OIL_GAS_KEYWORDS:
        if re.search(pattern, combined, re.IGNORECASE):
            return True

    return False


# ============================================================================
# 2. 日期解析
# ============================================================================

MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


def parse_date_from_text(text: str) -> Optional[str]:
    """Parse date from various formats into YYYY-MM-DD."""
    if not text:
        return None
    text = text.strip()

    # ISO: YYYY-MM-DD
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", text)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

    # US: MM/DD/YYYY or DD/MM/YYYY
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", text)
    if m:
        return f"{m.group(3)}-{m.group(1)}-{m.group(2)}"

    # "Month DD, YYYY"
    for month_name, month_num in MONTH_MAP.items():
        m = re.match(
            rf"{month_name}\s+(\d{{1,2}}),?\s+(\d{{4}})",
            text, re.IGNORECASE,
        )
        if m:
            return f"{int(m.group(2)):04d}-{month_num:02d}-{int(m.group(1)):02d}"

    # "YYYY-MM" or "YYYY_MM"
    m = re.search(r"(\d{4})[/_-](\d{1,2})(?:[/_-](\d{1,2}))?", text)
    if m and 1 <= int(m.group(2)) <= 12:
        y = int(m.group(1))
        mo = int(m.group(2))
        d = int(m.group(3)) if m.group(3) else 1
        return f"{y:04d}-{mo:02d}-{d:02d}"

    return None


def extract_date_from_url(url: str) -> Optional[str]:
    """Try to extract date from URL patterns."""
    if not url:
        return None
    patterns = [
        r"/(\d{4})/(\d{2})/(\d{2})/",
        r"/(\d{4})[/_-](\d{2})[/_-](\d{2})[/_-]",
        r"_(\d{4})[/_-](\d{2})[/_-](\d{2})",
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if 2020 <= y <= 2030 and 1 <= mo <= 12 and 1 <= d <= 31:
                return f"{y:04d}-{mo:02d}-{d:02d}"
    return None


# ============================================================================
# 3. HTTP 会话 & 页面获取
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
# 4. 页面解析
# ============================================================================


def parse_petroleum_page(html: str, source_url: str = "") -> list[dict]:
    """
    Parse Guyana Petroleum Management page HTML.

    Uses multiple strategies:
      1. Content sections with headings and text
      2. Tables with project/permit data
      3. All links (especially PDFs) with surrounding context

    Returns:
        List of document dicts.
    """
    soup = BeautifulSoup(html, "html.parser")
    documents = []

    # Remove noise elements
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    # Strategy 1: Content sections by headings
    main_content = (
        soup.find("main")
        or soup.find("article")
        or soup.find("div", id=re.compile(r"content|main|primary|post|page", re.I))
        or soup.find("div", class_=re.compile(r"content|main|entry|post|page|project", re.I))
        or soup
    )

    headings = main_content.find_all(["h1", "h2", "h3", "h4"])
    for heading in headings:
        title = heading.get_text(strip=True)
        if not title or len(title) < 5:
            continue

        # Collect text until next heading
        content_parts = []
        sibling = heading.find_next_sibling()
        while sibling and sibling.name not in ("h1", "h2", "h3", "h4"):
            if sibling.name in ("p", "li", "div", "span", "td", "article", "section"):
                text = sibling.get_text(strip=True)
                if text and len(text) > 10:
                    content_parts.append(text)
            sibling = sibling.find_next_sibling()

        content = " ".join(content_parts)

        # Find links in this section
        section_pdf_links = []
        for a in heading.find_all("a", href=True):
            href = a.get("href", "")
            if href.lower().endswith((".pdf", ".doc", ".docx", ".xlsx")):
                section_pdf_links.append(urljoin(source_url, href))
        if sibling and hasattr(sibling, "find_all"):
            for a in sibling.find_all("a", href=True):
                href = a.get("href", "")
                if href.lower().endswith((".pdf", ".doc", ".docx", ".xlsx")):
                    pdf_url = urljoin(source_url, href)
                    if pdf_url not in section_pdf_links:
                        section_pdf_links.append(pdf_url)

        if not is_oil_gas_relevant(title, content):
            continue

        category = classify_document(title, content)
        operator = extract_operator(f"{title} {content}")
        project_alias = extract_project_alias(title, content)
        pub_date = parse_date_from_text(content)

        if section_pdf_links:
            for pdf_url in section_pdf_links:
                url_date = extract_date_from_url(pdf_url)
                effective_date = pub_date or url_date or ""
                documents.append({
                    "title": title[:300],
                    "text": content[:2000],
                    "download_url": pdf_url,
                    "source_url": source_url or GUYANA_PETROLEUM_URL,
                    "publication_date": effective_date,
                    "category": category,
                    "event_type": DOC_CATEGORY_EVENT_MAP.get(category, "REGULATORY_DATA"),
                    "project_alias": project_alias,
                    "operator": operator,
                    "file_hash": "",
                    "country": "Guyana",
                })
        else:
            documents.append({
                "title": title[:300],
                "text": content[:2000],
                "download_url": "",
                "source_url": source_url or GUYANA_PETROLEUM_URL,
                "publication_date": pub_date or "",
                "category": category,
                "event_type": DOC_CATEGORY_EVENT_MAP.get(category, "REGULATORY_DATA"),
                "project_alias": project_alias,
                "operator": operator,
                "file_hash": "",
                "country": "Guyana",
            })

    if documents:
        log.info("Heading strategy: found %d documents", len(documents))
        return documents

    # Strategy 2: Tables with project/permit data
    tables = main_content.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        if not rows:
            continue
        for row in rows:
            cells = row.find_all(["td", "th"])
            cell_texts = [c.get_text(strip=True) for c in cells]
            full_text = " ".join(cell_texts)

            if not is_oil_gas_relevant(cell_texts[0] if cell_texts else "", full_text):
                continue

            pdf_links = []
            for a in row.find_all("a", href=True):
                href = a.get("href", "")
                if href.lower().endswith((".pdf", ".doc", ".docx")):
                    pdf_links.append(urljoin(source_url, href))

            title = cell_texts[0] if cell_texts else "Guyana Petroleum Document"
            category = classify_document(title, full_text)
            operator = extract_operator(full_text)
            project_alias = extract_project_alias(title, full_text)
            pub_date = parse_date_from_text(full_text)

            if pdf_links:
                for pdf_url in pdf_links:
                    url_date = extract_date_from_url(pdf_url)
                    documents.append({
                        "title": title[:300],
                        "text": full_text[:2000],
                        "download_url": pdf_url,
                        "source_url": source_url or GUYANA_PETROLEUM_URL,
                        "publication_date": pub_date or url_date or "",
                        "category": category,
                        "event_type": DOC_CATEGORY_EVENT_MAP.get(category, "REGULATORY_DATA"),
                        "project_alias": project_alias,
                        "operator": operator,
                        "file_hash": "",
                        "country": "Guyana",
                    })
            else:
                documents.append({
                    "title": title[:300],
                    "text": full_text[:2000],
                    "download_url": "",
                    "source_url": source_url or GUYANA_PETROLEUM_URL,
                    "publication_date": pub_date or "",
                    "category": category,
                    "event_type": DOC_CATEGORY_EVENT_MAP.get(category, "REGULATORY_DATA"),
                    "project_alias": project_alias,
                    "operator": operator,
                    "file_hash": "",
                    "country": "Guyana",
                })

    if documents:
        log.info("Table strategy: found %d documents", len(documents))
        return documents

    # Strategy 3: All PDF/file links with surround context
    all_links = main_content.find_all("a", href=True)
    file_links = [
        (a, urljoin(source_url, a["href"]))
        for a in all_links
        if re.search(r"\.(pdf|doc|docx|xlsx)$", a["href"], re.IGNORECASE)
    ]

    for anchor, file_url in file_links:
        link_text = anchor.get_text(strip=True)
        parent = anchor.find_parent(["li", "p", "div", "td", "tr", "span", "article"])
        context = parent.get_text(strip=True) if parent else link_text

        title = link_text or Path(unquote(file_url)).stem
        category = classify_document(title, context)
        operator = extract_operator(context)
        project_alias = extract_project_alias(title, context)
        pub_date = parse_date_from_text(context) or extract_date_from_url(file_url)

        documents.append({
            "title": title[:300],
            "text": context[:2000],
            "download_url": file_url,
            "source_url": source_url or GUYANA_PETROLEUM_URL,
            "publication_date": pub_date or "",
            "category": category,
            "event_type": DOC_CATEGORY_EVENT_MAP.get(category, "REGULATORY_DATA"),
            "project_alias": project_alias,
            "operator": operator,
            "file_hash": "",
            "country": "Guyana",
        })

    if documents:
        log.info("File link strategy: found %d documents", len(documents))
        return documents

    # Strategy 4: Fallback — create entry from page content
    page_title = ""
    title_tag = soup.find("title")
    if title_tag:
        page_title = title_tag.get_text(strip=True)

    all_text = main_content.get_text(separator="\n", strip=True)[:5000]

    if is_oil_gas_relevant(page_title, all_text):
        documents.append({
            "title": page_title or "Guyana Petroleum Management",
            "text": all_text[:2000],
            "download_url": "",
            "source_url": source_url or GUYANA_PETROLEUM_URL,
            "publication_date": TODAY,
            "category": "OTHER",
            "event_type": "REGULATORY_DATA",
            "project_alias": extract_project_alias(page_title, all_text),
            "operator": extract_operator(all_text),
            "file_hash": "",
            "country": "Guyana",
        })

    log.info("Fallback strategy: found %d documents", len(documents))
    return documents


# ============================================================================
# 5. 文件下载
# ============================================================================


def download_document(
    doc: dict,
    session: requests.Session,
    data_dir: Path = DATA_DIR,
) -> tuple[Optional[str], Optional[str]]:
    """Download a file attachment. Returns (sha256_hex, local_path) or (None, None)."""
    download_url = doc.get("download_url", "")
    if not download_url:
        return None, None

    data_dir.mkdir(parents=True, exist_ok=True)

    # Generate safe filename
    parsed = urlparse(download_url)
    raw_name = unquote(Path(parsed.path).name)
    if not raw_name or not re.search(r"\.(pdf|doc|docx|xlsx)$", raw_name, re.IGNORECASE):
        # Derive from title
        raw_name = re.sub(r"[^\w\-_. ()]", "_", doc.get("title", "document"))[:100]
        # Guess extension
        if ".pdf" not in raw_name.lower():
            raw_name += ".pdf"

    safe_name = re.sub(r"[^\w\-_. ()]", "_", raw_name)
    safe_name = re.sub(r"_+", "_", safe_name)

    local_path = data_dir / safe_name

    if local_path.exists():
        log.info("  File already exists: %s", local_path.name)
        file_hash = hashlib.sha256(local_path.read_bytes()).hexdigest()
        return file_hash, str(local_path)

    try:
        log.info("  Downloading: %s", safe_name[:80])
        resp = session.get(download_url, timeout=120, allow_redirects=True)
        resp.raise_for_status()

        content = resp.content
        if len(content) < 100:
            log.warning("  Downloaded file too small (%d bytes)", len(content))
            return None, None
        if b"<!DOCTYPE" in content[:100] or content[:50].strip().startswith(b"<html"):
            log.warning("  Response appears to be HTML, not a file")
            return None, None

        local_path.write_bytes(content)
        file_hash = hashlib.sha256(content).hexdigest()

        hash_path = data_dir / f"{safe_name}.sha256"
        hash_path.write_text(f"{file_hash}  {safe_name}\n")

        log.info("  Saved: %s (%d bytes, SHA256=%s)", safe_name[:80], len(content), file_hash[:16])
        return file_hash, str(local_path)

    except requests.exceptions.RequestException as e:
        log.warning("  Download failed: %s — %s", e, safe_name[:80])
        return None, None
    except Exception as e:
        log.warning("  Error saving file: %s — %s", e, safe_name[:80])
        return None, None


# ============================================================================
# 6. 去重
# ============================================================================


def _doc_key(doc: dict) -> str:
    """Derive stable unique key."""
    url = (doc.get("download_url") or "").strip()
    if url:
        return f"url:{url}"
    title = (doc.get("title") or "").strip()
    text = (doc.get("text") or "")[:100].strip()
    return f"title:{title}|{text}"


def deduplicate_documents(documents: list[dict]) -> list[dict]:
    """Deduplicate by download URL + file hash."""
    seen_urls = set()
    seen_hashes = set()
    unique = []
    for doc in documents:
        url = doc.get("download_url", "")
        fhash = doc.get("file_hash", "")
        if url and url in seen_urls:
            continue
        if fhash and fhash in seen_hashes:
            continue
        if url:
            seen_urls.add(url)
        if fhash:
            seen_hashes.add(fhash)
        unique.append(doc)
    if len(documents) > len(unique):
        log.info("Dedup: %d -> %d documents", len(documents), len(unique))
    return unique


# ============================================================================
# 7. candidate_events 输出
# ============================================================================


def build_candidate_event(doc: dict, raw_html_path: str = "") -> dict:
    """Convert a parsed document into a candidate_events record."""
    title = doc.get("title", "")
    text = doc.get("text", "")
    category = doc.get("category", "OTHER")
    event_type = doc.get("event_type", "REGULATORY_DATA")
    project_alias = doc.get("project_alias", "")
    operator = doc.get("operator", "")
    publication_date = doc.get("publication_date", "")
    download_url = doc.get("download_url", "")
    file_hash = doc.get("file_hash", "")

    project_name_raw = project_alias if project_alias else title

    # Structured summary
    summary_parts = []
    if category != "OTHER":
        summary_parts.append(f"Category: {category}")
    if operator:
        summary_parts.append(f"Operator: {operator}")
    if project_alias:
        summary_parts.append(f"Project: {project_alias}")
    if publication_date:
        summary_parts.append(f"Published: {publication_date}")
    if file_hash:
        summary_parts.append(f"SHA256: {file_hash[:16]}")

    summary = " | ".join(summary_parts) if summary_parts else text[:500]

    # evidence_quote for human review
    evidence_quote = title
    if text:
        evidence_quote += f" — {text[:400]}"
    if publication_date:
        evidence_quote += f" (Published: {publication_date})"

    return {
        "project_name_raw": project_name_raw[:255],
        "country": "Guyana",
        "summary": summary[:500],
        "source_name": SOURCE_NAME,
        "source_url": doc.get("source_url", GUYANA_PETROLEUM_URL)[:2048],
        "review_status": "pending",
        "event_type": event_type,
        "fetched_at": NOW_ISO,
        "evidence_quote": evidence_quote[:500],
        "publication_date": publication_date or TODAY,
        "raw_json": json.dumps(doc, ensure_ascii=False),
    }


# ============================================================================
# 8. Supabase 写入
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
            "source_url": GUYANA_PETROLEUM_URL,
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
            "original_url": original_url or GUYANA_PETROLEUM_URL,
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
# 9. 快照差异对比
# ============================================================================


DOC_COMPARE_FIELDS = [
    "title", "text", "download_url", "publication_date",
    "file_hash", "category", "event_type", "project_alias", "operator",
]


def load_previous_snapshot_local(date_str: str = None) -> Optional[list[dict]]:
    """Load most recent non-today snapshot JSON."""
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


def diff_documents(current: list[dict], previous: Optional[list[dict]]) -> dict:
    """Compare current document list against previous snapshot."""
    if previous is None:
        return {"new": list(current), "changed": [], "removed": [], "unchanged": []}

    cur_by_key = {}
    for doc in current:
        key = _doc_key(doc)
        if key not in cur_by_key:
            cur_by_key[key] = doc

    prev_by_key = {}
    for doc in previous:
        key = _doc_key(doc)
        if key not in prev_by_key:
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
            cv = str(cur_doc.get(field, "")).strip()
            pv = str(prev_doc.get(field, "")).strip()
            if cv != pv:
                diffs.append((field, pv, cv))
        if diffs:
            changed.append((cur_doc, prev_doc, diffs))
        else:
            unchanged.append(cur_doc)

    return {"new": new, "changed": changed, "removed": removed, "unchanged": unchanged}


# ============================================================================
# 10. 本地存储
# ============================================================================


def save_raw_html(html: str, label: str = "main", date_str: str = TODAY) -> Path:
    """Save raw HTML for audit."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    safe_label = re.sub(r"[^\w\-]", "_", label)
    filepath = DATA_DIR / f"{date_str}_guyana_petroleum_{safe_label}.html"
    filepath.write_text(html, encoding="utf-8")
    sha256 = hashlib.sha256(html.encode("utf-8")).hexdigest()
    hash_path = DATA_DIR / f"{date_str}_guyana_petroleum_{safe_label}.html.sha256"
    hash_path.write_text(f"{sha256}  {date_str}_guyana_petroleum_{safe_label}.html\n")
    log.info("Saved raw HTML to %s (SHA256=%s)", filepath, sha256[:16])
    return filepath


def save_local_snapshot(documents: list[dict], date_str: str = TODAY) -> Path:
    """Save parsed document metadata as JSON snapshot."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    filepath = DATA_DIR / f"{date_str}_snapshot.json"
    data = {
        "date": date_str,
        "fetched_at": NOW_ISO,
        "source_url": GUYANA_PETROLEUM_URL,
        "total_documents": len(documents),
        "documents": [{k: v for k, v in d.items()} for d in documents],
    }
    filepath.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
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
    """Adapter main flow."""
    log.info("=" * 60)
    log.info("Guyana Petroleum Management Adapter — P0 — %s", TODAY)
    log.info("=" * 60)

    session = build_session()
    all_documents = []
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

        label = url.rstrip("/").split("/")[-1] or "main"
        label = re.sub(r"[^\w\-]", "_", label)[:50]
        raw_html_path = save_raw_html(html, label)
        html_paths[label] = str(raw_html_path)

        if i == 0:
            html_sha256_main = hashlib.sha256(html.encode("utf-8")).hexdigest()

        if not dry_run and not local_only:
            save_to_source_documents(
                str(raw_html_path), hashlib.sha256(html.encode("utf-8")).hexdigest(),
                "HTML", len(html.encode("utf-8")),
                original_url=url,
                supabase=supabase,
            )

        log.info("--- Parsing: %s ---", url)
        documents = parse_petroleum_page(html, url)
        log.info("  [%s] Documents extracted: %d", label, len(documents))
        all_documents.extend(documents)

    if not all_documents:
        log.warning("No documents extracted from any URL.")
        return {
            "mode": "dry_run" if dry_run else ("local_only" if local_only else "full"),
            "total_documents": 0,
            "diff_new": 0, "diff_changed": 0,
            "diff_removed": 0, "diff_unchanged": 0,
            "error": "No documents parsed",
            "html_paths": html_paths,
            "html_sha256_main": html_sha256_main,
        }

    # Classification summary
    log.info("--- Classification Summary ---")
    category_counts = {}
    for doc in all_documents:
        cat = doc.get("category", "OTHER")
        category_counts[cat] = category_counts.get(cat, 0) + 1
    for cat, count in sorted(category_counts.items()):
        log.info("  %s: %d", cat, count)

    # Download attachments
    if not skip_download:
        log.info("--- Downloading Attachments ---")
        download_count = 0
        for i, doc in enumerate(all_documents):
            if not doc.get("download_url"):
                continue
            if download_count > 0:
                delay = random.uniform(MIN_REQUEST_DELAY_SEC, MAX_REQUEST_DELAY_SEC)
                log.info("  Waiting %.1fs (polite delay)...", delay)
                time.sleep(delay)
            result = download_document(doc, session, DATA_DIR)
            if result and result[0]:
                file_hash, local_path = result
                doc["file_hash"] = file_hash
                download_count += 1
                if not dry_run and not local_only:
                    ext = (doc.get("download_url", "") or "").lower()
                    if ".pdf" in ext:
                        file_type = "PDF"
                    elif ".doc" in ext:
                        file_type = "DOC"
                    elif ".xlsx" in ext:
                        file_type = "XLSX"
                    else:
                        file_type = "OTHER"
                    save_to_source_documents(
                        local_path, file_hash, file_type,
                        Path(local_path).stat().st_size if Path(local_path).exists() else 0,
                        original_url=doc.get("source_url", GUYANA_PETROLEUM_URL),
                        download_url=doc.get("download_url", ""),
                        publication_date=doc.get("publication_date", ""),
                        supabase=supabase,
                    )
        log.info("  Downloaded %d files", download_count)
    else:
        log.info("--- Skipping Downloads (--skip-download) ---")

    # Deduplicate
    all_documents = deduplicate_documents(all_documents)

    # Snapshot diff
    if no_diff:
        previous_snapshot = None
        log.info("--- Snapshot Diff: --no-diff (all treated as new) ---")
    else:
        log.info("--- Snapshot Diff ---")
        previous_snapshot = load_previous_snapshot_local()

    diff_result = diff_documents(all_documents, previous_snapshot)

    log.info("  New:        %d", len(diff_result["new"]))
    log.info("  Changed:    %d", len(diff_result["changed"]))
    log.info("  Removed:    %d", len(diff_result["removed"]))
    log.info("  Unchanged:  %d (skipped)", len(diff_result["unchanged"]))

    # Save current snapshot
    snapshot_path = save_local_snapshot(all_documents)

    # Build candidate_events
    log.info("--- Building candidate_events (diff only) ---")
    events = []

    for doc in diff_result["new"]:
        evt = build_candidate_event(doc, html_paths.get("main", ""))
        events.append(evt)

    for cur_doc, prev_doc, diffs in diff_result["changed"]:
        evt = build_candidate_event(cur_doc, html_paths.get("main", ""))
        change_desc = "; ".join(f"{f}: {old} -> {new}" for f, old, new in diffs)
        evt["summary"] = f"[CHANGED] {change_desc} | {evt['summary']}"
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
        title = prev_doc.get("title", "Unknown")
        evt = build_candidate_event(prev_doc, html_paths.get("main", ""))
        evt["event_type"] = "DOCUMENT_REMOVED"
        evt["summary"] = f"[REMOVED] No longer on petroleum page: {title}"
        events.append(evt)

    log.info("  Candidate events: %d (from %d docs)", len(events), len(all_documents))

    # Write to Supabase
    inserted = 0
    write_to_db = not dry_run and not local_only
    if write_to_db and events:
        try:
            inserted = insert_candidate_events(events, supabase)
            log.info("  Inserted %d candidate_events rows", inserted)
        except RuntimeError as e:
            log.warning("  Skipping Supabase write: %s", e)

    # Save snapshot registry record
    if write_to_db:
        try:
            save_snapshot_to_registry(
                str(snapshot_path), html_sha256_main, len(all_documents), supabase,
            )
        except Exception:
            log.debug("snapshot_registry write skipped", exc_info=True)

    mode_str = "dry_run" if dry_run else ("local_only" if local_only else "full")
    result = {
        "mode": mode_str,
        "total_documents": len(all_documents),
        "by_category": category_counts,
        "diff_new": len(diff_result["new"]),
        "diff_changed": len(diff_result["changed"]),
        "diff_removed": len(diff_result["removed"]),
        "diff_unchanged": len(diff_result["unchanged"]),
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
    log.info("  Total documents: %d", result["total_documents"])
    log.info("  Diff: new=%d changed=%d removed=%d unchanged=%d",
             result["diff_new"], result["diff_changed"],
             result["diff_removed"], result["diff_unchanged"])
    log.info("  By category: %s", result["by_category"])
    log.info("  Candidate events: %d (inserted: %d)", result["candidate_events"], inserted)

    return result


# ============================================================================
# 12. 自测
# ============================================================================


def run_test():
    """Self-test: fetch page -> parse -> download first attachment -> show events."""
    log.info("=" * 60)
    log.info("SELF-TEST: Guyana Petroleum Management Adapter")
    log.info("=" * 60)

    session = build_session()

    print("\n" + "─" * 60)
    print("Step 1: Fetch Guyana Petroleum page")
    print("─" * 60)

    html = fetch_page(GUYANA_PETROLEUM_URL, session)
    if html is None:
        print("  FAILED: Could not fetch primary page. Trying root URL...")
        html = fetch_page(ADDITIONAL_URLS[-1], session)
        if html is None:
            print("  FAILED: Could not fetch any page.")
            sys.exit(1)

    print(f"  Downloaded: {len(html):,} bytes")
    html_hash = hashlib.sha256(html.encode("utf-8")).hexdigest()
    print(f"  HTML SHA256: {html_hash}")

    raw_html_path = save_raw_html(html)
    print(f"  Saved HTML: {raw_html_path}")

    print("\n" + "─" * 60)
    print("Step 2: Parse Page Content")
    print("─" * 60)

    documents = parse_petroleum_page(html, GUYANA_PETROLEUM_URL)
    print(f"\n  Total documents found: {len(documents)}")

    if not documents:
        print("  No documents parsed. Page structure may have changed.")
        print("  Saving HTML for manual inspection.")
        sys.exit(0)

    from collections import Counter
    categories = Counter(d["category"] for d in documents)
    print("\n  Category breakdown:")
    for cat, count in categories.most_common():
        event_type = DOC_CATEGORY_EVENT_MAP.get(cat, "REGULATORY_DATA")
        print(f"    {cat}: {count} -> event_type='{event_type}'")

    project_aliases = [d["project_alias"] for d in documents if d.get("project_alias")]
    if project_aliases:
        print(f"\n  Projects identified: {sorted(set(project_aliases))}")

    operators = [d["operator"] for d in documents if d.get("operator")]
    if operators:
        print(f"\n  Operators identified: {sorted(set(operators))}")

    print("\n" + "─" * 60)
    print("Step 3: Download First Attachment")
    print("─" * 60)

    first_with_file = None
    for doc in documents:
        if doc.get("download_url"):
            first_with_file = doc
            break

    if first_with_file:
        print(f"  Title: {first_with_file['title'][:120]}")
        print(f"  URL: {first_with_file['download_url'][:120]}")
        result = download_document(first_with_file, session, DATA_DIR)
        if result and result[0]:
            file_hash, _ = result
            print(f"  Downloaded successfully!")
            print(f"  SHA256: {file_hash}")
            first_with_file["file_hash"] = file_hash
        else:
            print("  Download failed (see log).")
    else:
        print("  No downloadable attachment found.")

    print("\n" + "─" * 60)
    print("Step 4: Candidate Events (first 3)")
    print("─" * 60)

    required_fields = [
        "project_name_raw", "country", "summary", "source_name",
        "source_url", "review_status", "event_type", "fetched_at",
        "evidence_quote", "publication_date",
    ]

    for i, doc in enumerate(documents[:3]):
        evt = build_candidate_event(doc, str(raw_html_path))
        print(f"\n  Event #{i+1}:")
        for field in required_fields:
            val = evt.get(field, "MISSING")
            status = "OK" if val else "EMPTY"
            display_val = str(val)[:120] if val else "EMPTY"
            print(f"    [{status}] {field}: {display_val}")

    print("\n" + "─" * 60)
    print("Step 5: Field Completeness Check")
    print("─" * 60)

    all_ok = True
    for i, doc in enumerate(documents[:3]):
        evt = build_candidate_event(doc, str(raw_html_path))
        missing = [f for f in required_fields if not evt.get(f)]
        if missing:
            print(f"  Event #{i+1}: MISSING {missing}")
            all_ok = False
    if all_ok:
        print("  All events have complete required fields.")

    print(f"\n  Total documents parsed: {len(documents)}")
    print(f"  Categories: {dict(categories)}")
    print(f"  HTML saved: {raw_html_path}")
    print(f"  Data directory: {DATA_DIR}")

    files_in_dir = sorted(DATA_DIR.glob("*"))
    if files_in_dir:
        print(f"\n  Files in data directory ({len(files_in_dir)}):")
        for fp in files_in_dir:
            print(f"    {fp.name} ({fp.stat().st_size:,} bytes)")

    print(f"\n{'=' * 60}")
    print("Self-test complete.")
    print("=" * 60)


# ============================================================================
# 13. CLI
# ============================================================================


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Guyana 石油管理计划适配器 — P0 专用适配器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python crawler/adapters/guyana_petroleum.py                 # 完整运行
  python crawler/adapters/guyana_petroleum.py --test          # 自测
  python crawler/adapters/guyana_petroleum.py --dry-run       # 仅解析和下载，不写入数据库
  python crawler/adapters/guyana_petroleum.py --local-only    # 仅本地保存
  python crawler/adapters/guyana_petroleum.py --skip-download # 仅解析，不下载文件
  python crawler/adapters/guyana_petroleum.py --no-diff       # 跳过差异对比，全量输出
        """,
    )
    parser.add_argument("--test", action="store_true",
                        help="自测: 访问页面 -> 解析 -> 下载第一个附件 -> 输出前3条候选事件。")
    parser.add_argument("--dry-run", action="store_true",
                        help="仅解析页面、下载文件，不写入数据库。")
    parser.add_argument("--local-only", action="store_true",
                        help="保存文件到本地，不写入 Supabase。")
    parser.add_argument("--skip-download", action="store_true",
                        help="跳过附件下载，仅解析页面元数据。")
    parser.add_argument("--no-diff", action="store_true",
                        help="跳过快照差异对比，将所有文档作为新增处理。")
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
            skip_download=args.skip_download,
            no_diff=args.no_diff,
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
