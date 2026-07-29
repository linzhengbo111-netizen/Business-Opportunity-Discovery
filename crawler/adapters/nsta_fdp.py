#!/usr/bin/env python3
"""
NSTA Field Development Plans Adapter — P0 专用适配器
=====================================================

按《FPSO项目可用信息源使用手册》P0 要求实现：

来源信息:
  名称: NSTA Field Development Plans
  URL:  https://www.nstauthority.co.uk/regulatory-information/exploration-and-production/
        development/field-development-plans/
  类型: HTML 页面 + XLSX 数据集 + 链接文档
  优先级: P0
  层级: 2（官方验证）
  接入方式: 解析 NSTA FDP 指导页面获取政策文档，解析 Data - Fields 页面发现 XLSX
            数据集链接，下载并解析 offshore-field-consents XLSX 提取项目级数据。

功能:
  1. 解析 NSTA FDP 指导页面，提取所有公开的政策文档（FDP 指导、申请模板等）。
  2. 解析 NSTA Data - Fields 页面，发现并下载 offshore-field-consents XLSX。
  3. 从 XLSX 中提取字段名称、运营商、批准日期、文档类型。
  4. 按手册要求映射事件类型：
     DEVELOPMENT_PLAN_SUBMITTED  ← Field Development Plan / FDP Addendum
     DEVELOPMENT_CONSENT_GRANTED ← Development and Production Consent
     SUPPLY_CHAIN_PLAN           ← Supply Chain Action Plan
  5. 下载可用的 PDF 附件到 crawler/data/nsta/，保存 SHA256 哈希。
  6. 输出到 candidate_events 表。
  7. 保存原始 HTML 和 XLSX 副本用于审计。

合规:
  - 请求间隔 5-10 秒，遵守 robots.txt。
  - 保存原始文件，SHA256 哈希。
  - 不绕过登录或验证。
  - 区分 publication_date（文档日期）和 fetched_at（系统抓取时间）。

Usage:
  python crawler/adapters/nsta_fdp.py                 # 完整运行: 解析 → 下载 → 写入
  python crawler/adapters/nsta_fdp.py --dry-run       # 仅解析页面、下载文件，不写入数据库
  python crawler/adapters/nsta_fdp.py --local-only    # 保存文件到本地，不写入 Supabase
  python crawler/adapters/nsta_fdp.py --test          # 自测: 访问页面 → 列项目 → 输前5条候选事件
  python crawler/adapters/nsta_fdp.py --skip-download # 仅解析，不下载 XLSX/PDF
"""

import hashlib
import io
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
DATA_DIR = BASE_DIR / "data" / "nsta"
ADAPTER_DIR = Path(__file__).resolve().parent  # crawler/adapters/

# ---- Config --------------------------------------------------------------

load_dotenv(BASE_DIR.parent / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("VITE_SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY")

# ============================================================================
# NSTA 信息源 URL 定义
# ============================================================================

# 主页面: FDP 政策/指导页面（用户指定的 P0 来源）
NSTA_FDP_GUIDANCE_URL = (
    "https://www.nstauthority.co.uk/regulatory-information/"
    "exploration-and-production/development/field-development-plans/"
)

# 数据页面: 包含 FDP 批准清单的 XLSX 下载链接
NSTA_DATA_FIELDS_URL = (
    "https://www.nstauthority.co.uk/data-and-insights/data/themes/fields/"
)

# Supply Chain Action Plans 页面
NSTA_SUPPLY_CHAIN_URL = (
    "https://www.nstauthority.co.uk/regulatory-information/"
    "supply-chain/supply-chain-action-plans/"
)

# NSTA 新闻/公告页面（用于发现个别批准公告）
NSTA_NEWS_URL = "https://www.nstauthority.co.uk/news-publications/"

# NSTA 基础 URL，用于解析相对链接
NSTA_BASE_URL = "https://www.nstauthority.co.uk"

# robots.txt 允许爬取，我们使用礼貌的延迟
MIN_REQUEST_DELAY_SEC = 5.0
MAX_REQUEST_DELAY_SEC = 10.0

USER_AGENT = (
    "Mozilla/5.0 (compatible; FPSOCrawler/1.0; +NSTA-Open-Data-Adapter)"
)

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")
NOW_ISO = datetime.now(timezone.utc).isoformat()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("nsta-fdp-adapter")


# ============================================================================
# 1. 事件类型映射规则
# ============================================================================

# 按手册要求的事件类型映射
# "开发计划提交 → DEVELOPMENT_PLAN_SUBMITTED"
# "开发同意 → DEVELOPMENT_CONSENT_GRANTED"
# "供应链行动计划 → SUPPLY_CHAIN_PLAN"

EVENT_TYPE_MAP = {
    # Field Development Plan (primary submission)
    "FIELD_DEVELOPMENT_PLAN": "DEVELOPMENT_PLAN_SUBMITTED",
    "FDP": "DEVELOPMENT_PLAN_SUBMITTED",
    "FDP_ADDENDUM": "DEVELOPMENT_PLAN_SUBMITTED",
    "FDPA": "DEVELOPMENT_PLAN_SUBMITTED",
    # Development and Production Consent (approval)
    "DEVELOPMENT_CONSENT": "DEVELOPMENT_CONSENT_GRANTED",
    "CONSENT": "DEVELOPMENT_CONSENT_GRANTED",
    "PRODUCTION_CONSENT": "DEVELOPMENT_CONSENT_GRANTED",
    # Supply Chain Action Plan
    "SUPPLY_CHAIN_PLAN": "SUPPLY_CHAIN_PLAN",
    "SCAP": "SUPPLY_CHAIN_PLAN",
    # Guidance / reference documents
    "GUIDANCE": "REGULATORY_DATA",
    "TEMPLATE": "REGULATORY_DATA",
    "OTHER": "REGULATORY_DATA",
}

# XLSX 中常见的文档类型描述模式 → 事件类型
CONSENT_TYPE_PATTERNS = [
    ("FIELD_DEVELOPMENT_PLAN", [
        r"field\s*development\s*plan\s*(?!addendum)",
        r"\bfdp\b(?!\s*addendum)",
        r"development\s*plan\s*(?!addendum)",
        r"initial\s*development",
        r"new\s*field\s*development",
    ]),
    ("FDP_ADDENDUM", [
        r"field\s*development\s*plan\s*addendum",
        r"\bfdpa\b",
        r"\bfdp\s*addendum\b",
        r"addendum\s*to\s*field\s*development",
        r"development\s*plan\s*addendum",
    ]),
    ("DEVELOPMENT_CONSENT", [
        r"development\s*(?:and|&)\s*production\s*consent",
        r"consent\s*(?:to|for)\s*develop",
        r"development\s*consent",
        r"production\s*consent",
        r"approved\s*development",
    ]),
    ("SUPPLY_CHAIN_PLAN", [
        r"supply\s*chain\s*action\s*plan",
        r"\bscap\b",
        r"supply\s*chain\s*plan",
    ]),
]


def classify_document_type(title: str, doc_type: str = "", description: str = "") -> str:
    """
    根据文档标题和类型字段分类为事件类型键。

    返回事件类型键（如 'FIELD_DEVELOPMENT_PLAN'），
    再由 EVENT_TYPE_MAP 映射为最终的 event_type 值。
    """
    text = f"{title} {doc_type} {description}".lower()

    for doc_key, patterns in CONSENT_TYPE_PATTERNS:
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return doc_key

    # Fallback heuristics
    if "consent" in text:
        return "DEVELOPMENT_CONSENT"
    if "addendum" in text or "fdpa" in text:
        return "FDP_ADDENDUM"
    if "plan" in text or "fdp" in text:
        return "FIELD_DEVELOPMENT_PLAN"
    if "supply chain" in text:
        return "SUPPLY_CHAIN_PLAN"

    return "OTHER"


# ============================================================================
# 2. 日期解析
# ============================================================================

# 月份名称映射
MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


def parse_date_from_text(text: str) -> Optional[str]:
    """
    从文本中解析日期，支持多种格式。

    处理格式:
      - "2026-03-15" (ISO)
      - "15 March 2026"
      - "March 2026" (返回当月1日)
      - "15/03/2026" (UK 格式)
      - "Mar 2026"
    """
    if not text:
        return None

    text = text.strip()

    # ISO: 2026-03-15 或 2026-03
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", text)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.match(r"(\d{4})-(\d{2})$", text)
    if m:
        return f"{m.group(1)}-{m.group(2)}-01"

    # UK 格式: 15/03/2026
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
    if m:
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"

    # "15 March 2026" 或 "March 15, 2026"
    m = re.match(
        r"(\d{1,2})\s+(January|February|March|April|May|June|July|August|"
        r"September|October|November|December)\s+(\d{4})",
        text,
        re.IGNORECASE,
    )
    if m:
        day, month_name, year = int(m.group(1)), m.group(2).lower(), int(m.group(3))
        return f"{year:04d}-{MONTH_MAP[month_name]:02d}-{day:02d}"

    # "March 2026" (无日期 → 默认1日)
    m = re.match(
        r"(January|February|March|April|May|June|July|August|"
        r"September|October|November|December)\s+(\d{4})",
        text,
        re.IGNORECASE,
    )
    if m:
        month_name, year = m.group(1).lower(), int(m.group(2))
        return f"{year:04d}-{MONTH_MAP[month_name]:02d}-01"

    # "Mar 2026"
    m = re.match(
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{4})",
        text,
        re.IGNORECASE,
    )
    if m:
        month_name = m.group(1).lower()[:3]
        year = int(m.group(2))
        month = {
            "jan": 1, "feb": 2, "mar": 3, "apr": 4,
            "may": 5, "jun": 6, "jul": 7, "aug": 8,
            "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        }[month_name]
        return f"{year:04d}-{month:02d}-01"

    # 从文本中提取 YYYY 和月份
    m = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", text)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{y:04d}-{mo:02d}-{d:02d}"

    return None


# ============================================================================
# 3. HTTP 会话与页面获取
# ============================================================================


def build_session() -> requests.Session:
    """构建带适当请求头的 requests Session。"""
    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-GB,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
    })
    return session


def fetch_page(url: str, session: requests.Session) -> Optional[str]:
    """
    获取页面并返回 HTML 文本。

    失败时返回 None。
    """
    try:
        log.info("Fetching %s ...", url)
        resp = session.get(url, timeout=60)
        resp.raise_for_status()
        log.info("  HTTP %d, %d bytes", resp.status_code, len(resp.content))
        return resp.text
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if hasattr(e, 'response') else '?'
        log.warning("  HTTP %s — %s", status, url)
        return None
    except requests.exceptions.RequestException as e:
        log.warning("  Request failed: %s — %s", e, url)
        return None


def download_file(url: str, session: requests.Session) -> Optional[bytes]:
    """
    下载二进制文件（PDF, XLSX 等）。

    失败时返回 None。
    """
    try:
        log.info("Downloading %s ...", url)
        resp = session.get(url, timeout=120)
        resp.raise_for_status()

        content_type = resp.headers.get("Content-Type", "").lower()
        content = resp.content

        if len(content) < 100:
            log.warning("  File too small (%d bytes)", len(content))
            return None
        if content_type.startswith("text/html") or b"<!DOCTYPE" in content[:200]:
            log.warning("  Response is HTML, not expected file type")
            return None

        log.info("  Downloaded %d bytes (type=%s)", len(content), content_type)
        return content

    except requests.exceptions.RequestException as e:
        log.warning("  Download failed: %s — %s", e, url)
        return None


# ============================================================================
# 4. 页面解析：FDP 指导页面
# ============================================================================


def parse_guidance_page(html: str) -> list[dict]:
    """
    解析 NSTA FDP 指导页面，提取所有政策文档和模板。

    该页面包含:
      - FDP 指导文件 (PDF)
      - FDP 内容指导 (PDF)
      - 碳估值方法论 (PDF)
      - FDP 申请信模板 (DOCX)
      - 董事会信函模板 (DOC)
      - 供应链行动计划指导链接
      - 标准经济学模板 (XLSX)

    关键: 仅解析主内容区（main#Main 或 .article），排除侧边栏导航。

    Returns:
        文档字典列表，每个包含:
        - title: 文档标题
        - url: 文档/链接 URL
        - file_type: PDF/DOCX/DOC/XLSX/HTML
        - category: GUIDANCE/TEMPLATE/REFERENCE
        - description: 周围文本描述
    """
    soup = BeautifulSoup(html, "html.parser")
    documents = []

    # 查找主要内容区域 — NSTA 网站使用 <main id="Main"> 包含内容
    # 和 <article class="article"> 包含正文
    # 排除侧边栏导航（通常在 <nav> 中或带有 sidebar/left-nav 类）
    main_content = soup.select_one("main#Main") or soup.select_one("main")

    if not main_content:
        # Fallback: 使用第一个 article 元素（正文区域）
        main_content = soup.select_one("article.article") or soup.select_one("article")

    if not main_content:
        # 最后 fallback: 使用 body 但排除明显是导航的元素
        main_content = soup

    # 排除导航相关元素
    for nav_el in main_content.select(
        "nav, .sidebar, .side-nav, .left-nav, .navigation, "
        ".main-nav, .header-nav, .breadcrumb, .footer, footer, "
        ".footer-nav, .social-links, .search-box, .search-form"
    ):
        nav_el.decompose()

    # 提取所有有意义的链接
    seen_urls = set()
    all_links = main_content.select("a[href]")

    for link in all_links:
        href = link.get("href", "").strip()
        if not href:
            continue

        # 跳过锚点、javascript、邮件链接
        if href.startswith("#") or href.startswith("javascript:") or href.startswith("mailto:"):
            continue

        # 解析为绝对 URL
        full_url = urljoin(NSTA_BASE_URL, href)

        # 去重
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        # 仅保留 NSTA 域下的链接（包括 media 子域）
        parsed = urlparse(full_url)
        if parsed.netloc and "nstauthority.co.uk" not in parsed.netloc:
            continue

        title = link.get_text(strip=True)
        if not title or len(title) < 3:
            title = link.get("aria-label", "") or link.get("title", "") or title
        if not title or len(title) < 3:
            continue

        # 确定文件类型
        path_lower = full_url.lower()
        if path_lower.endswith(".pdf"):
            file_type = "PDF"
            category = "GUIDANCE"
        elif path_lower.endswith((".docx", ".doc")):
            file_type = "DOC"
            category = "TEMPLATE"
        elif path_lower.endswith((".xlsx", ".xls")):
            file_type = "XLSX"
            category = "REFERENCE"
        else:
            file_type = "HTML"
            # 对于 HTML 页面，根据文本内容分类
            title_lower = title.lower()
            if any(kw in title_lower for kw in ["guidance", "guideline", "guide"]):
                category = "GUIDANCE"
            elif any(kw in title_lower for kw in ["supply chain", "scap"]):
                category = "SUPPLY_CHAIN"
            else:
                # 跳过一般导航页面（仅收集文件下载链接和关键页面）
                continue

        # 获取周围文本作为描述
        parent = link.parent
        description = ""
        if parent:
            desc_parts = []
            for sibling in parent.children:
                if sibling == link:
                    continue
                if hasattr(sibling, 'get_text'):
                    txt = sibling.get_text(strip=True)
                    if txt:
                        desc_parts.append(txt)
            description = " ".join(desc_parts)[:500]

        doc = {
            "title": title,
            "url": full_url,
            "file_type": file_type,
            "category": category,
            "description": description,
            "source_url": NSTA_FDP_GUIDANCE_URL,
            "source_page": "FDP Guidance Page",
            "event_type": EVENT_TYPE_MAP.get(category, "REGULATORY_DATA"),
            "publication_date": "",
            "country": "UK",
        }

        documents.append(doc)
        log.info("  [%s] %s (%s)", doc["event_type"], title[:80], file_type)

    log.info("Guidance page: %d documents found", len(documents))
    return documents


# ============================================================================
# 5. 页面解析：Data - Fields 页面（发现 XLSX 数据集）
# ============================================================================


def parse_data_fields_page(html: str) -> list[dict]:
    """
    解析 NSTA Data - Fields 页面，提取所有 XLSX 数据集下载链接。

    该页面包含:
      - offshore-field-consents-as-at-MONTH-YEAR.xlsx
      - offshore-fdp-addenda-as-at-MONTH-YEAR.xlsx
      - offshore-field-start-ups-in-YEAR-as-at-MONTH-YEAR.xlsx
      - offshore-fields-in-production-as-at-MONTH-YEAR.xlsx
      - ArcGIS Open Data 链接

    Returns:
        XLSX 数据集字典列表。
    """
    soup = BeautifulSoup(html, "html.parser")
    datasets = []

    # 查找页面中的所有链接
    all_links = soup.select("a[href]")
    seen = set()

    for link in all_links:
        href = link.get("href", "").strip()
        if not href:
            continue

        full_url = urljoin(NSTA_BASE_URL, href)

        # 去重
        if full_url in seen:
            continue
        seen.add(full_url)

        title = link.get_text(strip=True)

        # 优先收集 XLSX 文件
        path_lower = full_url.lower()
        is_xlsx = path_lower.endswith(".xlsx")
        is_arcgis = "arcgis.com" in parsed_url(full_url).netloc if full_url else False

        if not is_xlsx and not is_arcgis:
            continue

        # 确定数据集类型
        title_lower = title.lower() if title else ""
        url_lower = full_url.lower()

        if "addenda" in url_lower or "addenda" in title_lower or "fdp addenda" in title_lower:
            dataset_type = "FDP_ADDENDA"
        elif "consent" in url_lower or "consent" in title_lower:
            dataset_type = "FIELD_CONSENTS"
        elif "start-up" in url_lower or "start-up" in title_lower or "start up" in title_lower:
            dataset_type = "FIELD_STARTUPS"
        elif "production" in url_lower or "production" in title_lower:
            dataset_type = "FIELDS_IN_PRODUCTION"
        elif "equity" in url_lower or "equity" in title_lower or is_arcgis:
            dataset_type = "EQUITY_SHARES"
        else:
            dataset_type = "OTHER_DATA"

        # 尝试从周围文本提取日期
        parent_text = ""
        if link.parent:
            parent_text = link.parent.get_text(strip=True)
        # 从 URL 中提取日期
        date_from_url = ""
        m = re.search(r"(\d{4})", url_lower)
        if m:
            date_from_url = m.group(1)

        datasets.append({
            "title": title or Path(urlparse(full_url).path).name,
            "url": full_url,
            "dataset_type": dataset_type,
            "file_type": "XLSX",
            "date_hint": date_from_url,
            "source_url": NSTA_DATA_FIELDS_URL,
            "source_page": "Data - Fields",
        })

        log.info("  [%s] %s", dataset_type, (title or full_url)[:100])

    log.info("Data - Fields page: %d datasets found", len(datasets))
    return datasets


def parsed_url(url: str):
    """Parse a URL, returning a result with netloc attribute."""
    return urlparse(url)


# ============================================================================
# 6. XLSX 解析
# ============================================================================


# XLSX 列名映射 — NSTA offshore field consents XLSX 实际列名
# 基于 2026-03 数据文件分析:
#   Row 1: 合并标题 "UKCS OFFSHORE FIELD CONSENTS SINCE 1/1/1976"
#   Row 2: "Field Name", "Block Number", "Consent Date",
#           "Operator at time of consent", "HC Type", ...
#   Row 3+: 数据行

XLSX_COLUMN_MAP = {
    "field_name": [
        "field name", "field_name", "field",
        "name", "field / installation", "installation",
        "field or installation",
    ],
    "operator": [
        "operator at time of consent", "operator",
        "operator(s)", "operators", "licensee", "licensees",
        "operator name", "operator company", "company",
    ],
    "consent_date": [
        "consent date", "date of consent", "date",
        "approval date", "date of approval",
        "consent granted", "date granted",
        "year of consent", "year",
    ],
    "consent_type": [
        "consent type", "type", "document type",
        "fdp type", "approval type", "category",
        "consent category", "plan type", "development type",
        "hc type",  # hydrocarbon type can help classify
    ],
    "block": [
        "block number", "block", "blocks",
        "licence block", "license block",
        "quadrant", "quad", "quadrant / block",
    ],
    "basin": [
        "basin", "area", "region",
        "geological basin", "sedimentary basin",
        "north sea area", "geographical area",
    ],
    "status": [
        "status", "current status",
        "development status", "project status",
        "consent status", "approval status",
    ],
    "description": [
        "description", "details", "notes",
        "additional information", "comments",
        "summary", "overview",
    ],
}


def normalize_col_name(raw: str) -> str:
    """标准化列名: 小写 + 去特殊字符 + 多余空白。"""
    s = raw.strip().lower()
    s = re.sub(r"[()]", " ", s)
    s = re.sub(r"[_\-/]+", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def build_xlsx_column_index(headers: list[str]) -> dict[str, int]:
    """根据 XLSX 表头构建列索引映射。"""
    norm_headers = [normalize_col_name(h) for h in headers]
    index = {}

    for std_field, aliases in XLSX_COLUMN_MAP.items():
        norm_aliases = [normalize_col_name(a) for a in aliases]

        # 精确匹配
        for i, nh in enumerate(norm_headers):
            if nh in norm_aliases:
                index[std_field] = i
                log.debug("  Column: %s → idx %d (%s)", std_field, i, headers[i])
                break

        # 模糊匹配
        if std_field not in index:
            for i, nh in enumerate(norm_headers):
                for alias in norm_aliases:
                    if alias and (alias in nh or nh in alias):
                        index[std_field] = i
                        log.debug("  Column (fuzzy): %s → idx %d (%s ≈ %s)",
                                  std_field, i, headers[i], alias)
                        break
                if std_field in index:
                    break

        if std_field not in index:
            log.debug("  Column: %s → NOT FOUND in %s", std_field, headers)

    return index


def parse_xlsx(raw: bytes, dataset_type: str = "FIELD_CONSENTS") -> list[dict]:
    """
    解析 NSTA XLSX 文件，提取记录列表。

    NSTA XLSX 格式（经实测验证）:
      Row 1: 合并标题 "UKCS OFFSHORE FIELD CONSENTS SINCE 1/1/1976"
      Row 2: 列标题 "Field Name", "Block Number", "Consent Date",
              "Operator at time of consent", "HC Type", ...
      Row 3+: 数据行

    自动检测并跳过标题行，找到真正的列标题行。

    Returns:
        记录列表，每条记录是 {standard_field: value} 字典。
    """
    try:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    except ImportError:
        raise ImportError(
            "openpyxl is required. Install: pip install openpyxl"
        )

    sheet = wb.active
    log.info("Sheet: %s", sheet.title)

    # 读取所有行
    all_rows = list(sheet.iter_rows(values_only=True))

    if len(all_rows) < 2:
        log.warning("XLSX has only %d rows; expected header + data", len(all_rows))
        return []

    # ---- 检测标题行 ----
    # NSTA 格式: 第1行是合并标题（如 "UKCS OFFSHORE FIELD CONSENTS..."），
    # 第2行才是列标题。自动检测: 如果第1行只有一个非空列且第2行有更多非空列，
    # 则第1行是标题，第2行是列标题。
    header_row_idx = 0  # 默认第1行是标题
    data_start_idx = 1

    if len(all_rows) >= 2:
        row0_nonempty = sum(1 for c in all_rows[0] if c is not None and str(c).strip())
        row1_nonempty = sum(1 for c in all_rows[1] if c is not None and str(c).strip())

        # 情况1: 第1行是单列标题（如 "UKCS OFFSHORE FIELD CONSENTS..."）
        if row0_nonempty <= 2 and row1_nonempty > row0_nonempty:
            header_row_idx = 1
            data_start_idx = 2
            log.info("Detected title row (row 1), column headers on row 2")
        # 情况2: 第1行看起来像列标题（包含多个已知列名）
        else:
            row0_text = " ".join(str(c) for c in all_rows[0] if c).lower()
            if any(kw in row0_text for kw in ["field name", "operator", "consent date", "block"]):
                header_row_idx = 0
                data_start_idx = 1
                log.info("Column headers on row 1")
            elif row1_nonempty > 2:
                # 第2行更像标题
                row1_text = " ".join(str(c) for c in all_rows[1] if c).lower()
                if any(kw in row1_text for kw in ["field name", "operator", "consent date", "block"]):
                    header_row_idx = 1
                    data_start_idx = 2
                    log.info("Column headers detected on row 2")

    # 提取列标题
    headers = [str(h).strip() if h is not None else "" for h in all_rows[header_row_idx]]
    log.info("XLSX headers (row %d): %s", header_row_idx + 1, headers)
    log.info("Total data rows: %d", len(all_rows) - data_start_idx)

    col_index = build_xlsx_column_index(headers)

    # 验证必需列
    if "field_name" not in col_index:
        log.warning(
            "Field name column not found in XLSX. Available mapped columns: %s",
            {k: headers[v] for k, v in col_index.items()},
        )

    records = []
    for row_num, row in enumerate(all_rows[data_start_idx:], start=data_start_idx + 1):
        # 跳过完全空行
        if not row or all(c is None or str(c).strip() == "" for c in row):
            continue

        # 处理行数据，正确转换 openpyxl 返回的 datetime 对象
        from datetime import datetime as dt_module
        record = {}
        for std_field, idx in col_index.items():
            if idx < len(row):
                val = row[idx]
                if val is None:
                    record[std_field] = ""
                elif isinstance(val, dt_module):
                    # openpyxl 已将 Excel 日期转为 datetime 对象
                    record[std_field] = val.strftime("%Y-%m-%d")
                else:
                    record[std_field] = str(val).strip()
            else:
                record[std_field] = ""

        # 跳过没有字段名称的行
        if not record.get("field_name", "").strip():
            continue

        # 标准化 consent_date：如果还不是 YYYY-MM-DD 格式，尝试解析
        consent_date_raw = record.get("consent_date", "")
        if consent_date_raw:
            parsed = parse_date_from_text(consent_date_raw)
            if parsed:
                record["consent_date"] = parsed
            else:
                # 可能是 Excel 序列号
                try:
                    serial = float(consent_date_raw)
                    if 10000 < serial < 100000:
                        excel_epoch = dt_module(1899, 12, 30)
                        from datetime import timedelta
                        converted = excel_epoch + timedelta(days=int(serial))
                        record["consent_date"] = converted.strftime("%Y-%m-%d")
                except (ValueError, OverflowError):
                    pass  # 保持原始值

        record["dataset_type"] = dataset_type
        records.append(record)

    log.info("Parsed %d records from XLSX", len(records))
    return records


# ============================================================================
# 7. PDF 下载与哈希
# ============================================================================


def download_guidance_pdf(doc: dict, session: requests.Session) -> Optional[str]:
    """
    下载指导页面文档的 PDF 附件。

    Returns:
        SHA256 哈希，或 None（失败时）。
    """
    url = doc.get("url", "")
    file_type = doc.get("file_type", "")

    if file_type != "PDF":
        return None  # 跳过非 PDF 文档

    if not url:
        return None

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 从 URL 或标题生成安全的本地文件名
    title = doc.get("title", "document")
    safe_name = re.sub(r"[^\w\-_. ()]", "_", title)[:120]
    if not safe_name.lower().endswith(".pdf"):
        safe_name += ".pdf"
    safe_name = re.sub(r"_+", "_", safe_name)

    local_path = DATA_DIR / safe_name

    # 如果文件已存在则跳过
    if local_path.exists():
        log.info("  PDF already exists: %s", local_path.name)
        return hashlib.sha256(local_path.read_bytes()).hexdigest()

    content = download_file(url, session)
    if content is None:
        return None

    local_path.write_bytes(content)
    file_hash = hashlib.sha256(content).hexdigest()

    # 保存哈希边车文件
    hash_path = DATA_DIR / f"{safe_name}.sha256"
    hash_path.write_text(f"{file_hash}  {safe_name}\n")

    log.info("  Saved PDF: %s (%d bytes, SHA256=%s)",
             local_path.name, len(content), file_hash[:16])
    return file_hash


# ============================================================================
# 8. candidate_events 输出
# ============================================================================


def build_candidate_event_from_guidance(doc: dict,
                                         raw_html_path: str = "") -> dict:
    """
    从指导页面文档构建 candidate_events 记录。
    """
    title = doc.get("title", "")
    category = doc.get("category", "REFERENCE")
    event_type = doc.get("event_type", "REGULATORY_DATA")
    file_type = doc.get("file_type", "")
    url = doc.get("url", "")
    file_hash = doc.get("file_hash", "")
    description = doc.get("description", "")

    # project_name_raw: 使用文档标题
    project_name_raw = title

    # evidence_quote: 文档描述片段
    evidence_quote = description if description else title
    if file_type:
        evidence_quote += f" [{file_type}]"

    # summary
    summary_parts = [f"Category: {category}", f"Type: {file_type}"]
    if file_hash:
        summary_parts.append(f"SHA256: {file_hash[:16]}")
    summary = " | ".join(summary_parts)

    return {
        "project_name_raw": project_name_raw[:255],
        "country": doc.get("country", "UK"),
        "summary": summary[:500],
        "source_name": "NSTA Field Development Plans",
        "source_url": (url or NSTA_FDP_GUIDANCE_URL)[:2048],
        "review_status": "pending",
        "event_type": event_type,
        "fetched_at": NOW_ISO,
        "evidence_quote": evidence_quote[:500],
        "raw_json": json.dumps(doc, ensure_ascii=False),
    }


def build_candidate_event_from_xlsx(record: dict,
                                     dataset_type: str = "FIELD_CONSENTS") -> dict:
    """
    从 XLSX 记录构建 candidate_events 记录。

    映射:
      field_name    → project_name_raw
      operator      → 用于 summary
      consent_date  → publication_date
      consent_type  → 用于 event_type 分类
      block/basin   → 用于 summary
    """
    field_name = record.get("field_name", "").strip()
    operator = record.get("operator", "").strip()
    consent_date = record.get("consent_date", "").strip()
    consent_type_raw = record.get("consent_type", "").strip()
    block = record.get("block", "").strip()
    basin = record.get("basin", "").strip()
    status = record.get("status", "").strip()
    description = record.get("description", "").strip()

    # 分类事件类型
    # NSTA XLSX 数据集的 consent_type 字段通常是 HC Type (GAS/OIL)，
    # 不是文档分类。因此使用 dataset_type 来确定事件类型:
    #   FIELD_CONSENTS → DEVELOPMENT_CONSENT_GRANTED (FDP 批准)
    #   FDP_ADDENDA → DEVELOPMENT_PLAN_SUBMITTED (FDP 附录提交)
    if dataset_type == "FDP_ADDENDA":
        event_type = "DEVELOPMENT_PLAN_SUBMITTED"
    elif dataset_type == "FIELD_CONSENTS":
        event_type = "DEVELOPMENT_CONSENT_GRANTED"
    else:
        # 否则尝试从文本分类
        doc_key = classify_document_type(field_name, consent_type_raw, description)
        event_type = EVENT_TYPE_MAP.get(doc_key, "REGULATORY_DATA")

    # project_name_raw: 使用字段名称
    project_name_raw = field_name

    # evidence_quote: 使用 consent_type 或 description，包含 field + operator + date
    evidence_quote = f"{field_name}"
    if operator:
        evidence_quote += f" | Operator: {operator}"
    if consent_date:
        evidence_quote += f" | Date: {consent_date}"
    if consent_type_raw:
        evidence_quote += f" | Type: {consent_type_raw}"
    if description:
        evidence_quote += f" | {description}"

    # 构建结构化摘要
    summary_parts = []
    if operator:
        summary_parts.append(f"Operator: {operator}")
    if basin:
        summary_parts.append(f"Basin: {basin}")
    if block:
        summary_parts.append(f"Block: {block}")
    if consent_type_raw:
        summary_parts.append(f"Type: {consent_type_raw}")
    if consent_date:
        summary_parts.append(f"Consent Date: {consent_date}")
    if status:
        summary_parts.append(f"Status: {status}")
    summary = " | ".join(summary_parts) if summary_parts else ""

    # 构建 source_url — 使用 Data Fields 页面
    source_url = NSTA_DATA_FIELDS_URL

    return {
        "project_name_raw": project_name_raw[:255],
        "country": "UK",
        "summary": summary[:500],
        "source_name": "NSTA Field Development Plans",
        "source_url": source_url[:2048],
        "review_status": "pending",
        "event_type": event_type,
        "fetched_at": NOW_ISO,
        "evidence_quote": evidence_quote[:500],
        "publication_date": consent_date if consent_date else None,
        "raw_json": json.dumps(record, ensure_ascii=False),
    }


# ============================================================================
# 9. 本地快照 (审计)
# ============================================================================


def save_raw_html(html: str, label: str = "fdp_guidance",
                   date_str: str = TODAY) -> Path:
    """保存原始 HTML 响应用于审计。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    filepath = DATA_DIR / f"{date_str}_{label}.html"
    filepath.write_text(html, encoding="utf-8")

    sha256 = hashlib.sha256(html.encode("utf-8")).hexdigest()
    hash_path = DATA_DIR / f"{date_str}_{label}.html.sha256"
    hash_path.write_text(f"{sha256}  {date_str}_{label}.html\n")

    log.info("Saved raw HTML to %s (SHA256=%s)", filepath, sha256[:16])
    return filepath


def save_raw_xlsx(raw: bytes, label: str, sha256: str = "",
                   date_str: str = TODAY) -> Path:
    """保存原始 XLSX 文件用于审计。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    safe_label = re.sub(r"[^\w\-_.]", "_", label)
    filepath = DATA_DIR / f"{date_str}_{safe_label}.xlsx"
    filepath.write_bytes(raw)

    if not sha256:
        sha256 = hashlib.sha256(raw).hexdigest()

    hash_path = DATA_DIR / f"{date_str}_{safe_label}.xlsx.sha256"
    hash_path.write_text(f"{sha256}  {date_str}_{safe_label}.xlsx\n")

    log.info("Saved raw XLSX to %s (SHA256=%s)", filepath, sha256[:16])
    return filepath


def save_local_snapshot(documents: list[dict], date_str: str = TODAY) -> Path:
    """保存解析后的文档元数据为 JSON 快照。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    filepath = DATA_DIR / f"{date_str}_snapshot.json"
    data = {
        "date": date_str,
        "fetched_at": NOW_ISO,
        "source_url": NSTA_FDP_GUIDANCE_URL,
        "total_documents": len(documents),
        "documents": documents,
    }
    filepath.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info("Saved local snapshot to %s (%d documents)", filepath, len(documents))
    return filepath


# ============================================================================
# 10. Supabase 写入
# ============================================================================


def get_supabase():
    """惰性初始化 Supabase 客户端。"""
    from supabase import create_client

    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_ANON_KEY must be set in .env. "
            "Use --local-only to skip Supabase writes."
        )
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def insert_candidate_events(events: list[dict], supabase=None) -> int:
    """写入 candidate_events 到 Supabase。返回已插入数量。"""
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
    """保存快照元数据到 snapshot_registry 表。"""
    if supabase is None:
        try:
            supabase = get_supabase()
        except RuntimeError:
            return False

    try:
        table = supabase.table("snapshot_registry")
        record = {
            "source_name": "NSTA Field Development Plans",
            "source_url": NSTA_FDP_GUIDANCE_URL,
            "snapshot_date": TODAY,
            "fetched_at": NOW_ISO,
            "file_path": str(filepath),
            "file_hash_sha256": sha256,
            "record_count": record_count,
            "source_type": "GOVERNMENT",
            "tier": 2,
            "priority": "P0",
            "country_focus": "UK",
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
            "original_url": original_url or NSTA_FDP_GUIDANCE_URL,
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
# 11. 快照差异对比
# ============================================================================


def _nsta_record_key(record: dict) -> str:
    """
    Derive a stable unique key from an NSTA record.
    Uses field_name + consent_date (per manual spec) for XLSX records;
    for guidance documents, uses title + url.
    """
    field_name = (record.get("field_name") or "").strip()
    consent_date = (record.get("consent_date") or "").strip()
    if field_name:
        return f"xlsx:{field_name}|{consent_date}"

    # Fallback for guidance documents
    title = (record.get("title") or "").strip()
    url = (record.get("url") or "").strip()
    return f"guidance:{title}|{url}"


NSTA_COMPARE_FIELDS = [
    # XLSX fields
    "field_name", "operator", "consent_date", "consent_type",
    "block", "basin", "status", "description",
    # Guidance doc fields
    "title", "url", "category", "file_type", "file_hash",
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


def diff_records(
    current: list[dict],
    previous: Optional[list[dict]],
) -> dict:
    """
    Compare current NSTA records against previous snapshot.

    Unique key for XLSX records: field_name + consent_date.
    For guidance documents: title + url.

    Returns:
        {
            "new": [record, ...],
            "changed": [(cur, prev, diffs), ...],
            "removed": [prev_record, ...],
            "unchanged": [record, ...],
        }
    """
    if previous is None:
        return {
            "new": list(current),
            "changed": [],
            "removed": [],
            "unchanged": [],
        }

    cur_by_key = {}
    for rec in current:
        key = _nsta_record_key(rec)
        if key in cur_by_key:
            continue
        cur_by_key[key] = rec

    prev_by_key = {}
    for rec in previous:
        key = _nsta_record_key(rec)
        if key in prev_by_key:
            continue
        prev_by_key[key] = rec

    cur_keys = set(cur_by_key.keys())
    prev_keys = set(prev_by_key.keys())

    new = [cur_by_key[k] for k in (cur_keys - prev_keys)]
    removed = [prev_by_key[k] for k in (prev_keys - cur_keys)]

    changed = []
    unchanged = []

    for key in cur_keys & prev_keys:
        cur_rec = cur_by_key[key]
        prev_rec = prev_by_key[key]

        diffs = []
        for field in NSTA_COMPARE_FIELDS:
            cur_val = str(cur_rec.get(field, "")).strip()
            prev_val = str(prev_rec.get(field, "")).strip()
            if cur_val != prev_val:
                diffs.append((field, prev_val, cur_val))

        if diffs:
            changed.append((cur_rec, prev_rec, diffs))
        else:
            unchanged.append(cur_rec)

    return {
        "new": new,
        "changed": changed,
        "removed": removed,
        "unchanged": unchanged,
    }


# ============================================================================
# 12. 主流程
# ============================================================================


def run_adapter(
    dry_run: bool = False,
    local_only: bool = False,
    skip_download: bool = False,
    no_diff: bool = False,
    supabase=None,
) -> dict:
    """
    适配器主流程。

    步骤:
      1. 获取 FDP 指导页面 → 提取政策文档
      2. 获取 Data - Fields 页面 → 发现 XLSX 数据集
      3. 下载主要 XLSX (field consents) → 解析记录
      4. 下载 FDP Addenda XLSX → 解析记录
      5. 下载指导页面 PDF 附件 → 计算 SHA256
      6. 构建 candidate_events
      7. 写入 Supabase（或本地快照）

    Args:
        dry_run: 仅解析和下载，不写入 Supabase。
        local_only: 仅保存本地，不写入 Supabase。
        skip_download: 跳过文件下载（仅解析页面）。
        supabase: Supabase 客户端（可选）。

    Returns:
        结果摘要字典。
    """
    log.info("=" * 60)
    log.info("NSTA Field Development Plans Adapter — %s", TODAY)
    log.info("Source: %s", NSTA_FDP_GUIDANCE_URL)
    log.info("=" * 60)

    session = build_session()
    all_events = []
    all_documents = []

    # ---- Step 1: FDP 指导页面 ----

    log.info("--- Step 1: FDP Guidance Page ---")
    delay = random.uniform(MIN_REQUEST_DELAY_SEC, MAX_REQUEST_DELAY_SEC)
    log.info("Waiting %.1fs (polite delay)...", delay)
    time.sleep(delay)

    guidance_html = fetch_page(NSTA_FDP_GUIDANCE_URL, session)
    if guidance_html is None:
        log.warning("Failed to fetch FDP guidance page. Continuing with Data - Fields only.")
        guidance_path = ""
        guidance_sha256 = ""
    else:
        guidance_path = save_raw_html(guidance_html, "fdp_guidance")
        guidance_sha256 = hashlib.sha256(guidance_html.encode("utf-8")).hexdigest()

        # Save to source_documents for audit trail
        if not dry_run and not local_only:
            save_to_source_documents(
                guidance_path, guidance_sha256, "HTML",
                len(guidance_html.encode("utf-8")),
                original_url=NSTA_FDP_GUIDANCE_URL,
                supabase=supabase,
            )

        guidance_docs = parse_guidance_page(guidance_html)
        all_documents.extend(guidance_docs)

        for doc in guidance_docs:
            evt = build_candidate_event_from_guidance(
                doc, str(guidance_path) if guidance_path else "",
            )
            all_events.append(evt)

    # ---- Step 2: Data - Fields 页面 ----

    log.info("--- Step 2: Data - Fields Page ---")
    delay = random.uniform(MIN_REQUEST_DELAY_SEC, MAX_REQUEST_DELAY_SEC)
    log.info("Waiting %.1fs (polite delay)...", delay)
    time.sleep(delay)

    fields_html = fetch_page(NSTA_DATA_FIELDS_URL, session)
    datasets = []
    if fields_html is None:
        log.warning("Failed to fetch Data - Fields page. Skipping XLSX discovery.")
    else:
        fields_path = save_raw_html(fields_html, "data_fields")
        # Save to source_documents for audit trail
        if not dry_run and not local_only:
            save_to_source_documents(
                fields_path,
                hashlib.sha256(fields_html.encode("utf-8")).hexdigest(),
                "HTML",
                len(fields_html.encode("utf-8")),
                original_url=NSTA_DATA_FIELDS_URL,
                supabase=supabase,
            )
        datasets = parse_data_fields_page(fields_html)

    # ---- Step 3: 下载并解析 Field Consents XLSX ----

    xlsx_records = []

    if not skip_download and datasets:
        log.info("--- Step 3: Downloading XLSX Datasets ---")

        # 优先下载 field consents 和 FDP addenda
        priority_types = ["FIELD_CONSENTS", "FDP_ADDENDA"]
        priority_datasets = [d for d in datasets if d["dataset_type"] in priority_types]
        other_datasets = [d for d in datasets if d["dataset_type"] not in priority_types]

        for i, ds in enumerate(priority_datasets + other_datasets):
            url = ds.get("url", "")
            if not url:
                continue

            delay = random.uniform(MIN_REQUEST_DELAY_SEC, MAX_REQUEST_DELAY_SEC)
            if i > 0:
                log.info("  Waiting %.1fs (polite delay)...", delay)
                time.sleep(delay)

            xlsx_raw = download_file(url, session)
            if xlsx_raw is None:
                log.warning("  Failed to download: %s", url)
                continue

            xlsx_sha256 = hashlib.sha256(xlsx_raw).hexdigest()
            label = ds.get("dataset_type", "dataset").lower()
            xlsx_path = save_raw_xlsx(xlsx_raw, label, xlsx_sha256)

            # Save to source_documents for audit trail
            if not dry_run and not local_only:
                save_to_source_documents(
                    xlsx_path, xlsx_sha256, "XLSX",
                    len(xlsx_raw),
                    original_url=NSTA_DATA_FIELDS_URL,
                    download_url=url,
                    supabase=supabase,
                )

            try:
                records = parse_xlsx(xlsx_raw, ds.get("dataset_type", "FIELD_CONSENTS"))
                xlsx_records.extend(records)
                log.info("  Extracted %d records from %s", len(records),
                         ds.get("title", label))
            except Exception as e:
                log.warning("  XLSX parse error: %s", e)

        # 将 XLSX 记录添加到文档列表（用于快照和 diff）
        all_documents.extend(xlsx_records)

    # ---- Step 4: 下载指导页面 PDF 附件 ----

    if not skip_download:
        log.info("--- Step 4: Downloading Guidance PDFs ---")
        guidance_docs = [d for d in all_documents
                         if d.get("file_type") == "PDF" and d.get("url")]
        for i, doc in enumerate(guidance_docs):
            if i > 0:
                delay = random.uniform(MIN_REQUEST_DELAY_SEC, MAX_REQUEST_DELAY_SEC)
                time.sleep(delay)
            file_hash = download_guidance_pdf(doc, session)
            if file_hash:
                doc["file_hash"] = file_hash

    # ---- Step 5: 快照差异对比 ----

    if no_diff:
        previous_snapshot = None
        log.info("--- Snapshot Diff: --no-diff (all records treated as new) ---")
    else:
        log.info("--- Snapshot Diff ---")
        previous_snapshot = load_previous_snapshot_local()

    diff_result = diff_records(all_documents, previous_snapshot)

    log.info("  New:        %d", len(diff_result["new"]))
    log.info("  Changed:    %d", len(diff_result["changed"]))
    log.info("  Removed:    %d", len(diff_result["removed"]))
    log.info("  Unchanged:  %d (skipped)", len(diff_result["unchanged"]))

    # ---- Step 6: 保存本地快照 ----

    log.info("--- Step 6: Saving Local Snapshot ---")
    snapshot_path = save_local_snapshot(all_documents)

    # ---- Step 7: 构建 candidate_events (仅 diff 变更) ----

    log.info("--- Step 7: Building candidate_events (diff only) ---")
    all_events = []

    # Guidance docs → events
    for doc in diff_result["new"]:
        if doc.get("source_page") == "FDP Guidance Page":
            all_events.append(build_candidate_event_from_guidance(
                doc, str(guidance_path) if guidance_path else "",
            ))
        elif doc.get("field_name"):
            all_events.append(build_candidate_event_from_xlsx(
                doc, doc.get("dataset_type", "FIELD_CONSENTS"),
            ))
        else:
            all_events.append(build_candidate_event_from_guidance(
                doc, str(guidance_path) if guidance_path else "",
            ))

    for cur_doc, prev_doc, diffs in diff_result["changed"]:
        if cur_doc.get("source_page") == "FDP Guidance Page":
            evt = build_candidate_event_from_guidance(
                cur_doc, str(guidance_path) if guidance_path else "",
            )
        elif cur_doc.get("field_name"):
            evt = build_candidate_event_from_xlsx(
                cur_doc, cur_doc.get("dataset_type", "FIELD_CONSENTS"),
            )
        else:
            evt = build_candidate_event_from_guidance(
                cur_doc, str(guidance_path) if guidance_path else "",
            )

        # Enrich with change details
        change_desc = "; ".join(
            f"{f}: {old} → {new}" for f, old, new in diffs
        )
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
        all_events.append(evt)

    for prev_doc in diff_result["removed"]:
        name = prev_doc.get("field_name") or prev_doc.get("title", "Unknown")
        evt = {
            "project_name_raw": str(name)[:255],
            "country": prev_doc.get("country", "UK"),
            "summary": f"[REMOVED] Record no longer in NSTA dataset: {name}",
            "source_name": "NSTA Field Development Plans",
            "source_url": (prev_doc.get("url") or NSTA_FDP_GUIDANCE_URL)[:2048],
            "review_status": "pending",
            "event_type": "RECORD_REMOVED",
            "fetched_at": NOW_ISO,
            "evidence_quote": str(name)[:500],
            "raw_json": json.dumps(prev_doc, ensure_ascii=False),
        }
        all_events.append(evt)

    # ---- Step 8: 输出统计 ----

    log.info("--- Step 8: Event Summary ---")
    event_type_counts = {}
    for evt in all_events:
        et = evt.get("event_type", "UNKNOWN")
        event_type_counts[et] = event_type_counts.get(et, 0) + 1
    for et, count in sorted(event_type_counts.items()):
        log.info("  %s: %d", et, count)

    log.info("  Total candidate_events (diff only): %d", len(all_events))

    # ---- Step 9: 写入 Supabase ----

    inserted = 0
    write_to_db = not dry_run and not local_only
    if write_to_db and all_events:
        try:
            inserted = insert_candidate_events(all_events, supabase)
            log.info("  Inserted %d candidate_events rows", inserted)
        except RuntimeError as e:
            log.warning("  Skipping Supabase write: %s", e)

    if write_to_db and snapshot_path.exists():
        try:
            save_snapshot_to_registry(
                str(snapshot_path),
                guidance_sha256 if guidance_sha256 else "no-guidance-page",
                len(all_documents),
                supabase,
            )
        except Exception:
            log.debug("snapshot_registry write skipped", exc_info=True)

    # ---- 构建结果 ----

    mode_str = "dry_run" if dry_run else ("local_only" if local_only else "full")
    result = {
        "mode": mode_str,
        "source_url": NSTA_FDP_GUIDANCE_URL,
        "data_fields_url": NSTA_DATA_FIELDS_URL,
        "guidance_documents": sum(1 for d in all_documents
                                  if d.get("source_page") == "FDP Guidance Page"),
        "xlsx_records": len(xlsx_records),
        "total_documents": len(all_documents),
        "diff_new": len(diff_result["new"]),
        "diff_changed": len(diff_result["changed"]),
        "diff_removed": len(diff_result["removed"]),
        "diff_unchanged": len(diff_result["unchanged"]),
        "by_event_type": event_type_counts,
        "candidate_events": len(all_events),
        "inserted": inserted,
        "guidance_html_sha256": guidance_sha256 if guidance_sha256 else "",
        "snapshot_path": str(snapshot_path),
        "data_dir": str(DATA_DIR),
    }

    log.info("=" * 60)
    log.info("Run complete.")
    log.info("  Mode: %s", mode_str)
    log.info("  Guidance documents: %d", result["guidance_documents"])
    log.info("  XLSX records: %d", result["xlsx_records"])
    log.info("  Total documents: %d", result["total_documents"])
    log.info("  Diff: new=%d changed=%d removed=%d unchanged=%d",
             result["diff_new"], result["diff_changed"],
             result["diff_removed"], result["diff_unchanged"])
    log.info("  Event types: %s", result["by_event_type"])
    log.info("  Candidate events: %d (inserted: %d)",
             result["candidate_events"], inserted)
    log.info("  Snapshot: %s", result["snapshot_path"])
    log.info("  Data dir: %s", result["data_dir"])

    return result


# ============================================================================
# 12. 自测
# ============================================================================


def run_test():
    """
    自测: 访问 NSTA 页面 → 列出所有项目和文档链接 → 输出前 5 条候选事件。

    不写入 Supabase。
    """
    log.info("=" * 60)
    log.info("SELF-TEST: NSTA Field Development Plans Adapter")
    log.info("=" * 60)

    session = build_session()

    # ---- Test 1: Fetch FDP Guidance Page ----
    print("\n" + "─" * 60)
    print("Step 1: Fetch NSTA FDP Guidance Page")
    print("─" * 60)
    print(f"  URL: {NSTA_FDP_GUIDANCE_URL}")

    guidance_html = fetch_page(NSTA_FDP_GUIDANCE_URL, session)
    if guidance_html is None:
        print("  FAILED: Could not fetch guidance page.")
        print("  (This is not fatal — the adapter can still work with Data - Fields.)")
        guidance_docs = []
    else:
        print(f"  Downloaded: {len(guidance_html):,} bytes")
        guidance_hash = hashlib.sha256(guidance_html.encode("utf-8")).hexdigest()
        print(f"  HTML SHA256: {guidance_hash}")

        # Save HTML locally
        guidance_path = save_raw_html(guidance_html, "fdp_guidance")
        print(f"  Saved HTML: {guidance_path}")

        # Parse guidance documents
        print("\n  Parsing guidance documents...")
        guidance_docs = parse_guidance_page(guidance_html)
        print(f"  Found {len(guidance_docs)} guidance documents/links")

        if guidance_docs:
            print("\n  Guidance documents:")
            for i, doc in enumerate(guidance_docs, 1):
                print(f"    {i}. [{doc.get('category', '?')}] {doc.get('title', '?')[:100]}")
                print(f"       URL: {doc.get('url', '?')[:120]}")
                print(f"       Type: {doc.get('file_type', '?')}")

    # ---- Test 2: Fetch Data - Fields Page ----
    print("\n" + "─" * 60)
    print("Step 2: Fetch NSTA Data - Fields Page")
    print("─" * 60)
    print(f"  URL: {NSTA_DATA_FIELDS_URL}")

    time.sleep(random.uniform(3, 5))  # polite delay

    fields_html = fetch_page(NSTA_DATA_FIELDS_URL, session)
    if fields_html is None:
        print("  FAILED: Could not fetch Data - Fields page.")
        datasets = []
    else:
        print(f"  Downloaded: {len(fields_html):,} bytes")
        fields_hash = hashlib.sha256(fields_html.encode("utf-8")).hexdigest()
        print(f"  HTML SHA256: {fields_hash}")

        # Save HTML locally
        fields_path = save_raw_html(fields_html, "data_fields")
        print(f"  Saved HTML: {fields_path}")

        # Parse datasets
        print("\n  Discovering XLSX datasets...")
        datasets = parse_data_fields_page(fields_html)
        print(f"  Found {len(datasets)} datasets")

        if datasets:
            print("\n  Available XLSX datasets:")
            for i, ds in enumerate(datasets, 1):
                print(f"    {i}. [{ds.get('dataset_type', '?')}] {ds.get('title', '?')[:100]}")
                print(f"       URL: {ds.get('url', '?')[:120]}")

    # ---- Test 3: Try downloading first XLSX ----
    print("\n" + "─" * 60)
    print("Step 3: Download & Parse First XLSX Dataset")
    print("─" * 60)

    xlsx_records = []
    if datasets:
        # Try field consents first
        priority = [d for d in datasets
                    if d["dataset_type"] in ("FIELD_CONSENTS", "FDP_ADDENDA")]
        target = priority[0] if priority else datasets[0]

        print(f"  Dataset: {target.get('title', '?')[:120]}")
        print(f"  URL: {target.get('url', '?')[:120]}")

        time.sleep(random.uniform(3, 5))

        xlsx_raw = download_file(target["url"], session)
        if xlsx_raw is None:
            print("  FAILED: Could not download XLSX.")
            print("  (NSTA may serve XLSX files differently than expected.)")
        else:
            print(f"  Downloaded: {len(xlsx_raw):,} bytes")
            xlsx_sha256 = hashlib.sha256(xlsx_raw).hexdigest()
            print(f"  SHA256: {xlsx_sha256}")

            # Save XLSX
            label = target.get("dataset_type", "dataset").lower()
            xlsx_path = save_raw_xlsx(xlsx_raw, label, xlsx_sha256)
            print(f"  Saved: {xlsx_path}")

            # Parse
            try:
                xlsx_records = parse_xlsx(xlsx_raw, target.get("dataset_type", "FIELD_CONSENTS"))
                print(f"\n  Parsed {len(xlsx_records)} records from XLSX")

                if xlsx_records:
                    print("\n  First 5 XLSX records:")
                    for i, rec in enumerate(xlsx_records[:5], 1):
                        print(f"\n  Record {i}:")
                        for k, v in rec.items():
                            if v:
                                print(f"    {k}: {str(v)[:80]}")
            except Exception as e:
                print(f"  PARSE ERROR: {e}")
                import traceback
                traceback.print_exc()
    else:
        print("  No datasets to download. Skipping XLSX step.")

    # ---- Test 4: Build Candidate Events ----
    print("\n" + "─" * 60)
    print("Step 4: Candidate Events (first 5)")
    print("─" * 60)

    # Build events from guidance docs
    guidance_events = []
    for doc in guidance_docs:
        evt = build_candidate_event_from_guidance(doc)
        guidance_events.append(evt)

    # Build events from XLSX records
    xlsx_events = []
    for rec in xlsx_records:
        evt = build_candidate_event_from_xlsx(rec)
        xlsx_events.append(evt)

    all_test_events = guidance_events + xlsx_events

    required_fields = [
        "project_name_raw", "country", "summary", "source_name",
        "source_url", "review_status", "event_type", "fetched_at",
        "evidence_quote",
    ]

    # Show first 3 guidance events + first 3 XLSX events (or all if fewer)
    display_events = guidance_events[:3] + xlsx_events[:3]
    # Fallback if not enough events
    if len(display_events) < 5:
        display_events = all_test_events[:5]

    for i, evt in enumerate(display_events, 1):
        source_type = "XLSX" if evt.get("publication_date") else "Guidance"
        print(f"\n{'─' * 50}")
        print(f"Event #{i} [{source_type}]")
        print(f"{'─' * 50}")

        for field in required_fields:
            val = evt.get(field, "MISSING")
            status = "✓" if val else "✗ EMPTY"
            display_val = str(val)[:120] if val else "EMPTY"
            print(f"  {status}  {field}: {display_val}")

        # Show extra fields specific to XLSX events
        if evt.get("publication_date"):
            print(f"  ✓  publication_date: {evt['publication_date']}")

        # Show raw_json preview
        if evt.get("raw_json"):
            try:
                raw_obj = json.loads(evt["raw_json"])
                if isinstance(raw_obj, dict):
                    keys = [k for k in raw_obj if raw_obj[k]]
                    print(f"  ✓  raw_json keys: {keys[:8]}")
            except json.JSONDecodeError:
                print(f"  ✗  raw_json: invalid JSON")

    # ---- Test 5: Field Completeness ----
    print("\n" + "─" * 60)
    print("Step 5: Field Completeness Report")
    print("─" * 60)

    if all_test_events:
        all_ok = True
        for i, evt in enumerate(all_test_events[:5], 1):
            missing = [f for f in required_fields if not evt.get(f)]
            if missing:
                print(f"  Event #{i}: MISSING {missing}")
                all_ok = False

        if all_ok:
            print("  All events have complete required fields ✓")
    else:
        print("  No events to validate.")
        print("  This is expected if the guidance page has no documents and")
        print("  no XLSX datasets were downloaded.")
        print("  The adapter structure is correct; data availability depends on NSTA's")
        print("  current page structure and XLSX hosting.")

    # ---- Test 6: Summary ----
    print(f"\n{'─' * 60}")
    print(f"Step 6: Summary")
    print(f"{'─' * 60}")
    print(f"  Guidance documents found: {len(guidance_docs)}")
    print(f"  XLSX datasets discovered: {len(datasets)}")
    print(f"  XLSX records parsed: {len(xlsx_records)}")
    print(f"  Total candidate events: {len(all_test_events)}")
    print(f"  Event type breakdown: ", end="")
    type_counts = {}
    for evt in all_test_events:
        et = evt.get("event_type", "UNKNOWN")
        type_counts[et] = type_counts.get(et, 0) + 1
    print(dict(type_counts))

    # List files in data dir
    if DATA_DIR.exists():
        files_in_dir = sorted(DATA_DIR.glob("*"))
        if files_in_dir:
            print(f"\n  Files in data directory ({len(files_in_dir)}):")
            for fp in files_in_dir:
                size = fp.stat().st_size
                print(f"    {fp.name} ({size:,} bytes)")

    print(f"\n{'─' * 60}")
    print("Self-test complete.")
    print("─" * 60)

    return all_test_events


# ============================================================================
# 13. CLI
# ============================================================================


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="NSTA Field Development Plans Adapter — P0 专用适配器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python crawler/adapters/nsta_fdp.py                 # 完整运行
  python crawler/adapters/nsta_fdp.py --test           # 自测
  python crawler/adapters/nsta_fdp.py --dry-run        # 仅解析和下载，不写入Supabase
  python crawler/adapters/nsta_fdp.py --local-only     # 仅本地保存
  python crawler/adapters/nsta_fdp.py --skip-download  # 仅解析，不下载文件
  python crawler/adapters/nsta_fdp.py --no-diff        # 跳过差异对比，全量输出
        """,
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="自测: 访问页面 → 列出所有项目和文档链接 → 输出前5条候选事件。",
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
        help="跳过文件下载（XLSX/PDF），仅解析页面元数据。",
    )
    parser.add_argument(
        "--no-diff",
        action="store_true",
        help="跳过快照差异对比，将所有记录作为新增处理（首次运行或强制全量刷新）。",
    )
    args = parser.parse_args()

    # 自测模式
    if args.test:
        try:
            run_test()
        except Exception as e:
            log.error("Self-test failed: %s", e, exc_info=True)
            sys.exit(1)
        return

    # 正常模式
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

    # 输出结果摘要
    print("\n" + json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
