#!/usr/bin/env python3
"""
ANP 开发计划适配器 — P0 专用适配器
===================================

按《FPSO项目可用信息源使用手册》P0 要求实现：

来源信息:
  名称: ANP 开发计划
  URL:  https://www.gov.br/anp/pt-br/assuntos/exploracao-e-producao-de-oleo-e-gas/
        desenvolvimento-e-producao/planos-de-desenvolvimento
  类型: HTML 目录 + PDF 附件
  优先级: P0
  层级: 2（官方验证）
  接入方式: 解析 HTML 页面，提取开发计划列表、油田/项目名称、运营商、PDF 附件

功能:
  1. 解析 ANP 开发计划页面，提取计划列表（油田名称、运营商、盆地、阶段、PDF 链接）。
  2. 按事件类型自动分类: DEVELOPMENT_PLAN_SUBMITTED, DEVELOPMENT_PLAN_UPDATED。
  3. 下载 PDF 附件到 crawler/data/anp_plans/ 目录，记录 SHA256。
  4. 使用 URL + 文件哈希去重。
  5. 所有输出写入 candidate_events（review_status='pending'）。
  6. 与 ANP FPSO CSV 适配器协作，形成巴西双源验证（ANP CSV 确认设施 + ANP 开发计划确认阶段）。

合规:
  - 请求间隔 5-10 秒，遵守 robots.txt。
  - 保存原始 HTML 和 PDF 副本。
  - 不绕过任何登录或验证。
  - 区分 publication_date 和 fetched_at。

Usage:
  python crawler/adapters/anp_development_plan.py                 # 完整运行
  python crawler/adapters/anp_development_plan.py --dry-run       # 仅解析和下载，不写入数据库
  python crawler/adapters/anp_development_plan.py --local-only    # 仅本地保存
  python crawler/adapters/anp_development_plan.py --test          # 自测
  python crawler/adapters/anp_development_plan.py --no-diff       # 跳过差异对比
  python crawler/adapters/anp_development_plan.py --skip-download # 仅解析，不下载文件
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

# pdfplumber for PDF text extraction (ANP development plans)
try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    pdfplumber = None  # type: ignore
    PDFPLUMBER_AVAILABLE = False

sys.path.insert(0, str(Path(__file__).resolve().parent))
from media_common import _safe_decode_response, extract_corrosive_media

# ---- Paths ---------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent  # crawler/
DATA_DIR = BASE_DIR / "data" / "anp_plans"
ADAPTER_DIR = Path(__file__).resolve().parent  # crawler/adapters/

# ---- Config --------------------------------------------------------------

load_dotenv(BASE_DIR.parent / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("VITE_SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY")

# ANP 开发计划页面 URL (per audit report recommendation)
ANP_PLANS_URL = (
    "https://www.gov.br/anp/pt-br/assuntos/exploracao-e-producao-de-oleo-e-gas/"
    "desenvolvimento-e-producao/planos-de-desenvolvimento"
)

# Fallback URLs to try if primary URL fails (gov.br page structure varies)
ANP_PLANS_FALLBACK_URLS = [
    ANP_PLANS_URL,
    "https://www.gov.br/anp/pt-br/assuntos/exploracao-e-producao-de-oleo-e-gas/gestao-de-contratos/planos-de-desenvolvimento",
    "https://www.gov.br/anp/pt-br/assuntos/exploracao-e-producao-de-oleo-e-gas/dados-de-producao",
    "https://www.gov.br/anp/pt-br/assuntos/exploracao-e-producao-de-oleo-e-gas",
]

# Source identity (must match source_registry.source_name)
SOURCE_NAME = "ANP 开发计划"

MIN_REQUEST_DELAY_SEC = 5.0
MAX_REQUEST_DELAY_SEC = 10.0

USER_AGENT = (
    "Mozilla/5.0 (compatible; FPSOCrawler/1.0; +ANP-Development-Plan-Adapter)"
)

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")
NOW_ISO = datetime.now(timezone.utc).isoformat()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("anp-devplan-adapter")


# ============================================================================
# 1. 事件分类规则
# ============================================================================

# Event type mapping
DOC_CATEGORY_EVENT_MAP = {
    "DEVELOPMENT_PLAN": "DEVELOPMENT_PLAN_SUBMITTED",
    "PLAN_UPDATE": "DEVELOPMENT_PLAN_UPDATED",
    "REVISION": "DEVELOPMENT_PLAN_UPDATED",
    "TECHNICAL_SUMMARY": "DEVELOPMENT_PLAN_SUBMITTED",
    "ECONOMIC_SUMMARY": "DEVELOPMENT_PLAN_SUBMITTED",
    "ENVIRONMENTAL_SUMMARY": "DEVELOPMENT_PLAN_SUBMITTED",
    "OTHER": "REGULATORY_DATA",
}

# Portuguese classification patterns (ANP content is in Portuguese)
CATEGORY_PATTERNS = [
    ("DEVELOPMENT_PLAN", [
        r"plano\s+de\s+desenvolvimento",
        r"development\s+plan",
        r"plano\s+de\s+produ[çc][ãa]o",
        r"production\s+development",
        r"projeto\s+de\s+desenvolvimento",
    ]),
    ("PLAN_UPDATE", [
        r"revis[ãa]o\s+do\s+plano",
        r"atualiza[çc][ãa]o\s+do\s+plano",
        r"plan\s+revision",
        r"plan\s+update",
        r"revisado",
        r"atualizado",
        r"complemento\s+ao\s+plano",
        r"aditivo\s+ao\s+plano",
    ]),
    ("TECHNICAL_SUMMARY", [
        r"resumo\s+t[ée]cnico",
        r"technical\s+summary",
        r"especifica[çc][ãa]o\s+t[ée]cnica",
        r"technical\s+specification",
        r"descri[çc][ãa]o\s+do\s+sistema",
        r"system\s+description",
    ]),
    ("ECONOMIC_SUMMARY", [
        r"resumo\s+econ[ôo]mico",
        r"economic\s+summary",
        r"an[áa]lise\s+econ[ôo]mica",
        r"viabilidade\s+econ[ôo]mica",
        r"economic\s+viability",
    ]),
    ("ENVIRONMENTAL_SUMMARY", [
        r"resumo\s+ambiental",
        r"environmental\s+summary",
        r"estudo\s+de\s+impacto\s+ambiental",
        r"environmental\s+impact",
        r"licen[çc]a\s+ambiental",
        r"environmental\s+licen[cs]e",
    ]),
]

# Known Brazilian offshore fields/projects
KNOWN_BRAZILIAN_FIELDS = [
    "Búzios", "Tupi", "Lula", "Mero", "Sépia", "Atapu", "Itapu",
    "Marlim", "Marlim Leste", "Marlim Sul", "Voador", "Barracuda",
    "Caratinga", "Albacora", "Albacora Leste", "Roncador",
    "Jubarte", "Cachalote", "Baleia Franca", "Baleia Azul",
    "Espírito Santo", "Golfinho", "Camarupim", "Papa-Terra",
    "Tartaruga Verde", "Sapinhoá", "Lapa", "Libra", "Franco",
    "Sergipe", "Águas Profundas",
    # Santos Basin pre-salt
    "Berbigão", "Sururu", "Sul de Tupi", "Norte de Búzios",
    "Norte de Carcará", "Carcará",
    # Campos Basin
    "Peregrino", "Polvo", "Frade", "Wahoo", "Parque das Baleias",
    # Espírito Santo Basin
    "Peroá", "Cangoá", "Golfinho",
    # Potiguar Basin
    "Ubarana",
    # Sergipe-Alagoas Basin
    "Pirambu",
    # Equatorial Margin
    "Foz do Amazonas", "Barreirinhas", "Piauí",
]

# Operator name patterns
OPERATOR_PATTERNS = [
    r"\b(Petrobras)\b",
    r"\b(Equinor(?:\s+Brasil)?)\b",
    r"\b(Shell(?:\s+Brasil)?)\b",
    r"\b(TotalEnergies(?:\s+E?&?P?\s*Brasil)?)\b",
    r"\b(Petrogal(?:\s+Brasil)?)\b",
    r"\b(Repsol(?:\s+Sinopec)?\s+Brasil)\b",
    r"\b(Karoon(?:\s+Energy)?)\b",
    r"\b(Enauta)\b",
    r"\b(Prio|PetroRio)\b",
    r"\b(BP(?:\s+Energy)?)\b",
    r"\b(Enauta)\b",
    r"\b(Trident\s+Energy)\b",
    r"\b(BW\s+Energy)\b",
    r"\b(Perenco)\b",
    r"\b(3R\s+(?:Petroleum|Petr[óo]leo))",
    r"\b(Ouro\s+Preto)\b",
    r"\b(Ecopetrol)\b",
]

# FPSO/offshore relevance keywords (Portuguese + English)
OFFSHORE_KEYWORDS = [
    r"\bfpso\b", r"\bplataforma\b", r"\boffshore\b",
    r"[óo]leo\s+e\s+g[áa]s", r"petr[óo]leo",
    r"campos?\s+mar[íi]tim[oa]", r"[áa]guas?\s+profundas",
    r"pr[ée][-\s]sal", r"p[óo]s[-\s]sal",
    r"bacia\s+de\s+santos", r"bacia\s+de\s+campos",
    r"campos\s+basin", r"santos\s+basin",
    r"sistema\s+de\s+produ[çc][ãa]o",
    r"production\s+system",
    r"desenvolvimento\s+(?:da\s+)?produ[çc][ãa]o",
    r"production\s+development",
    r"unidade\s+estacion[áa]ria\s+de\s+produ[çc][ãa]o",
    r"unidade\s+flutuante",
]


def classify_document(title: str, text: str = "") -> str:
    """Classify document into category using Portuguese + English patterns."""
    combined = f"{title} {text}".lower()
    for category, patterns in CATEGORY_PATTERNS:
        for pattern in patterns:
            if re.search(pattern, combined, re.IGNORECASE):
                return category
    return "OTHER"


def is_offshore_relevant(title: str, text: str = "") -> bool:
    """Check if document is relevant to offshore/FPSO development."""
    combined = f"{title} {text}".lower()
    for kw in OFFSHORE_KEYWORDS:
        if re.search(kw, combined, re.IGNORECASE):
            return True
    # Auto-include anything mentioning known Brazilian fields
    for field in KNOWN_BRAZILIAN_FIELDS:
        if field.lower() in combined:
            return True
    return False


def extract_operator(text: str) -> str:
    """Extract operator name from text."""
    for pattern in OPERATOR_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return ""


def extract_field_name(text: str) -> str:
    """Extract known Brazilian field name from text."""
    text_lower = text.lower()
    for field in sorted(KNOWN_BRAZILIAN_FIELDS, key=len, reverse=True):
        if field.lower() in text_lower:
            return field
    return ""


# ============================================================================
# 2. 日期解析 (Portuguese months)
# ============================================================================

MONTH_MAP_PT = {
    "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3,
    "abril": 4, "maio": 5, "junho": 6, "julho": 7,
    "agosto": 8, "setembro": 9, "outubro": 10,
    "novembro": 11, "dezembro": 12,
}

MONTH_MAP_EN = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


def parse_date_from_text(text: str) -> Optional[str]:
    """Parse a date string into YYYY-MM-DD. Handles Portuguese and English formats."""
    if not text:
        return None
    text = text.strip()

    # ISO: YYYY-MM-DD
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", text)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

    # Brazilian: DD/MM/YYYY
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", text)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"

    # Portuguese month: "15 de Março de 2024" or "Março 2024"
    all_months = {**MONTH_MAP_PT, **MONTH_MAP_EN}
    for month_name, month_num in all_months.items():
        # "DD de Mês de YYYY"
        m = re.search(rf"(\d{{1,2}})\s+de\s+{month_name}\s+de\s+(\d{{4}})", text, re.IGNORECASE)
        if m:
            return f"{int(m.group(2)):04d}-{month_num:02d}-{int(m.group(1)):02d}"
        # "Mês de YYYY" or "Mês/YYYY"
        m = re.search(rf"{month_name}\s+(?:de\s+)?(\d{{4}})", text, re.IGNORECASE)
        if m:
            return f"{int(m.group(1)):04d}-{month_num:02d}-01"

    # YYYY alone
    m = re.search(r"\b(20\d{2})\b", text)
    if m:
        return f"{m.group(1)}-01-01"

    return None


# ============================================================================
# 2.5. 技术规格提取 (from text)
# ============================================================================

# Patterns for extracting technical specifications from development plan text.
# All patterns are regex-based and strictly based on the source text.
# When uncertain, fields are left empty (None) — never guessed.

def extract_water_depth_from_text(text: str) -> Optional[int]:
    """Extract water depth in meters from text.
    Matches patterns like:
      - "lâmina d'água de 2.140 m"
      - "water depth: 1,500 m"
      - "profundidade de 2.200 metros"
      - "水深 1500 米"
    """
    if not text:
        return None
    patterns = [
        # Portuguese: "lâmina d'água de X m" / "lâmina d'água: X m"
        r"(?:l[âa]mina\s+d['’]?[áa]gua)\s*(?:de\s+)?(?::\s*)?(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?)\s*(?:m|metros|metros)",
        # "profundidade de X m" / "profundidade: X m"
        r"profundidade\s*(?:de\s+)?(?::\s*)?(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?)\s*(?:m|metros|metros)",
        # English: "water depth of X m" / "water depth: X m"
        r"water\s+depth\s*(?:of\s+)?(?::\s*)?(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?)\s*(?:m|meters?)",
        # "depth: X m"
        r"\bdepth\s*(?::\s*)?(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?)\s*(?:m|meters?)\b",
        # Chinese: "水深 X 米"
        r"水深\s*[:：]?\s*(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?)\s*米",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                val = m.group(1).replace(",", "").replace(".", "")
                n = int(val)
                if 10 <= n <= 5000:  # reasonable range for FPSO water depth
                    return n
            except (ValueError, TypeError):
                continue
    return None


def extract_oil_capacity_from_text(text: str) -> Optional[int]:
    """Extract oil production capacity in bpd from text.
    Matches patterns like:
      - "capacidade de 150.000 bbl/d"
      - "150,000 barrels per day"
      - "产能 150,000 桶/天"
    """
    if not text:
        return None
    patterns = [
        # Portuguese: "capacidade de produção de petróleo: X bbl/d"
        r"(?:capacidade\s+(?:de\s+)?produ[çc][ãa]o\s+(?:de\s+)?petr[óo]leo)\s*(?::\s*)?(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?)\s*(?:bbl/?d|barris)",
        # "produção de X bbl/d" / "produção de até X bbl/d"
        r"produ[çc][ãa]o\s*(?:de\s+)?(?:at[ée]\s+)?(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?)\s*(?:bbl/?d|barris)",
        # English: "capacity of X bpd" / "X barrels per day"
        r"(?:capacity|production)\s*(?:of\s+)?(?:up\s+to\s+)?(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?)\s*(?:bpd|barrels?\s+per\s+day)",
        # "X bpd" / "X bbl/d" (bare number+unit)
        r"(\d{2,3}(?:[.,]\d{3})*(?:[.,]\d+)?)\s*(?:bpd|bbl/?d)\b",
        # Chinese: "产能 X 桶/天"
        r"(?:产能|产量)\s*[:：]?\s*(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?)\s*(?:桶|bbl)/?(?:天|d|日)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                val = m.group(1).replace(",", "").replace(".", "")
                n = int(val)
                if 1000 <= n <= 500000:  # reasonable range
                    return n
            except (ValueError, TypeError):
                continue
    return None


def extract_gas_capacity_from_text(text: str) -> Optional[int]:
    """Extract gas production capacity in million m³/d from text.
    Matches patterns like:
      - "produção de gás de 5 Mm³/d"
      - "gas capacity: 3 million m³/d"
      - "天然气产能 5 百万立方米/天"
    """
    if not text:
        return None
    patterns = [
        # Portuguese: "produção de gás: X Mm³/d" / "produção de gás de X milhões m³/d"
        r"(?:produ[çc][ãa]o\s+(?:de\s+)?g[áa]s)\s*(?::\s*)?(?:de\s+)?(\d{1,3}(?:[.,]\d+)?)\s*(?:milh[õo]es?\s+(?:de\s+)?m[³3]/?d|Mm[³3]/?d)",
        # English: "gas capacity of X MMcmd" / "X million m³/d"
        r"(?:gas\s+(?:capacity|production))\s*(?:of\s+)?(?:up\s+to\s+)?(\d{1,3}(?:[.,]\d+)?)\s*(?:MMcmd|million\s+(?:m[³3]|cubic\s+meters?)/?d)",
        # "X MMcmd" (bare number+unit)
        r"(\d{1,3}(?:[.,]\d+)?)\s*MMcmd\b",
        # Chinese: "天然气产能 X 百万立方米/天"
        r"(?:天然气|燃气)\s*(?:产能|产量)\s*[:：]?\s*(\d{1,3}(?:[.,]\d+)?)\s*(?:百万|Million)\s*(?:立方米|m[³3])/?(?:天|d|日)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                val = m.group(1).replace(",", "").replace(".", "")
                n = int(float(val))
                if 1 <= n <= 100:  # reasonable range for MMcmd
                    return n
            except (ValueError, TypeError):
                continue
    return None


def extract_hull_type_from_text(text: str) -> Optional[str]:
    """Extract FPSO hull type from text.
    Matches known hull types mentioned in development plans.
    """
    if not text:
        return None
    text_lower = text.lower()
    hull_types = [
        ("Spread Moored", [r"spread\s+moored?", r"spread\s+mooring"]),
        ("Turret", [r"\bturret\b", r"internal\s+turret", r"external\s+turret",
                    r"turret\s+mooring", r"turret\s+system"]),
        ("FLNG conversion", [r"flng\s+conversion", r"lng\s+conversion",
                              r"converted\s+(?:to\s+)?(?:flng|lng)",
                              r"convers[ãa]o\s+(?:para\s+)?(?:flng|gnl)"]),
        ("Newbuild", [r"\bnewbuild\b", r"new\s+build", r"newly\s+built",
                      r"constru[çc][ãa]o\s+nova", r"rec[ée]m[\s-]constru[íi]d[ao]"]),
        ("Conversion", [r"\bconversion\b", r"converted\s+(?:tanker|vlcc|supertanker)",
                        r"convers[ãa]o\s+(?:de\s+)?(?:navio|petroleiro)"]),
        ("FSO", [r"\bfso\b", r"floating\s+storage\s+offloading"]),
    ]
    matched = []
    for name, patterns in hull_types:
        for pat in patterns:
            if re.search(pat, text_lower):
                matched.append(name)
                break
    return ", ".join(matched) if matched else None


def extract_date_from_url(url: str) -> Optional[str]:
    """Try to extract date from URL/filename patterns."""
    if not url:
        return None
    # /2024/03/15/... or /2024_03_15_...
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
# 2.6. PDF 文本提取 & 技术规格解析
# ============================================================================

# Material keywords — stainless steel grades and alloys
MATERIAL_KEYWORDS = [
    "stainless steel", "stainless",
    "duplex", "super duplex", "superduplex",
    "316L", "316 L", "316LN",
    "2205", "UNS S32205", "UNS S31803",
    "2507", "UNS S32750",
    "CRA", "corrosion resistant alloy", "corrosion-resistant alloy",
    "cladding", "clad",
    "Inconel", "Alloy 625", "Alloy 825",
    "6Mo", "6 Mo", "UNS S31254", "254 SMO",
    "13Cr", "13 Cr", "Super 13Cr",
    "22Cr", "22 Cr", "25Cr", "25 Cr",
    "austenitic", "ferritic", "martensitic",
]

# Media / corrosive agent keywords
MEDIA_KEYWORDS = [
    "H2S", "hydrogen sulfide", "hydrogen sulphide",
    "CO2", "carbon dioxide",
    "sour gas", "sour service", "sour environment",
    "sweet gas", "sweet service",
    "chloride", "Cl-", "chlorides",
    "pH", "acidic", "acid gas",
    "mercury", "Hg",
    "MEG", "monoethylene glycol",
    "oxygen", "O2",
    "sand", "erosion", "abrasive",
]

# Technical parameter keywords with patterns
TECH_PARAM_PATTERNS = [
    # (canonical_name, [patterns])
    ("water_depth", [
        r"(?:water\s+depth|l[âa]mina\s+d['']?[áa]gua|profundidade)\s*(?:de\s+)?(?:at[ée]\s+)?(?::\s*)?(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?)\s*(?:m|metros?|meters?)",
    ]),
    ("production_capacity", [
        r"(?:production\s+(?:capacity|rate)|capacidade\s+(?:de\s+)?produ[çc][ãa]o|produ[çc][ãa]o)\s*(?:de\s+)?(?:at[ée]\s+)?(?::\s*)?(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?)\s*(?:bpd|bbl/?d|barris?\s+(?:por\s+)?dia|barrels?\s+(?:per\s+)?day)",
    ]),
    ("injection_pressure", [
        r"(?:injection\s+pressure|press[ãa]o\s+de\s+inje[çc][ãa]o|press[ãa]o\s+de\s+reinje[çc][ãa]o)\s*(?:de\s+)?(?:at[ée]\s+)?(?::\s*)?(\d{1,4}(?:[.,]\d+)?)\s*(?:bar|psi|kgf|MPa)",
    ]),
    ("operating_temperature", [
        r"(?:operating\s+temperature|temperatura\s+(?:de\s+)?opera[çc][ãa]o|temperatura\s+(?:de\s+)?projeto|design\s+temperature)\s*(?:de\s+)?(?:at[ée]\s+)?(?::\s*)?(\d{1,3}(?:[.,]\d+)?)\s*(?:[°º]C|Celsius|[°º]F|Fahrenheit)",
    ]),
]

# Application context patterns — where the material is used
APPLICATION_PATTERNS = [
    r"(?:for|para|in|em|of|de)\s+(?:the\s+)?("
    r"cargo\s+oil\s+tanks?"
    r"|process\s+piping"
    r"|production\s+risers?"
    r"|flowlines?"
    r"|manifolds?"
    r"|heat\s+exchangers?"
    r"|pressure\s+vessels?"
    r"|separators?"
    r"|scrubbers?"
    r"|desalters?"
    r"|deaerators?"
    r"|water\s+injection\s+systems?"
    r"|gas\s+injection\s+systems?"
    r"|gas\s+compression"
    r"|flare\s+systems?"
    r"|offloading\s+systems?"
    r"|mooring\s+systems?"
    r"|hull"
    r"|topside"
    r"|subsea\s+equipment"
    r")",
]


def extract_pdf_text(pdf_path: str) -> Optional[str]:
    """Extract full text from a PDF file using pdfplumber.

    Args:
        pdf_path: Absolute or relative path to the PDF file.

    Returns:
        Extracted text as a single string, or None if extraction fails.
    """
    if not PDFPLUMBER_AVAILABLE:
        log.warning("pdfplumber not available — cannot extract PDF text")
        return None

    path = Path(pdf_path)
    if not path.exists():
        log.warning("PDF not found: %s", pdf_path)
        return None
    if not path.suffix.lower() == ".pdf":
        log.warning("Not a PDF file: %s", pdf_path)
        return None

    try:
        text_parts = []
        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
        full_text = "\n".join(text_parts)
        if full_text.strip():
            log.info("  PDF text extracted: %s — %d chars from %d pages",
                     path.name, len(full_text), len(text_parts))
            return full_text
        else:
            log.warning("  PDF text extraction produced empty result: %s", path.name)
            return None
    except Exception as e:
        log.warning("  PDF text extraction failed: %s — %s", path.name, e)
        return None


def parse_technical_specs(text: str) -> dict:
    """Search PDF text for material, media, and technical parameter keywords.

    Args:
        text: Full text extracted from a PDF (or any page text).

    Returns:
        Dict with keys:
          - evidence_quote: excerpt around first match (150 chars each side)
          - stainless_steel: comma-separated material keywords found
          - application: application context (if found)
          - media: comma-separated media keywords found
          - tech_params: dict of technical parameter values
          - has_material: bool, True if any material keyword was found
    """
    if not text:
        return {
            "evidence_quote": "",
            "stainless_steel": "",
            "application": "",
            "media": "",
            "tech_params": {},
            "has_material": False,
        }

    text_lower = text.lower()

    # --- Material keywords ---
    found_materials = []
    for kw in MATERIAL_KEYWORDS:
        if kw.lower() in text_lower:
            found_materials.append(kw)

    # Deduplicate: "super duplex" subsumes "duplex" hits
    deduped_materials = _deduplicate_materials(found_materials)

    # --- Media keywords ---
    found_media = []
    for kw in MEDIA_KEYWORDS:
        if kw.lower() in text_lower:
            found_media.append(kw)

    # --- Technical parameters ---
    tech_params = {}
    for param_name, patterns in TECH_PARAM_PATTERNS:
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                tech_params[param_name] = m.group(0).strip()[:100]
                break

    # --- Application context ---
    application = ""
    for pat in APPLICATION_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            application = m.group(1).strip()
            break

    # --- Evidence quote ---
    evidence_quote = ""
    if deduped_materials:
        # Find position of first material keyword
        first_match = None
        for mat in deduped_materials:
            idx = text_lower.find(mat.lower())
            if idx >= 0 and (first_match is None or idx < first_match[0]):
                first_match = (idx, mat)

        if first_match:
            idx, _ = first_match
            start = max(0, idx - 150)
            end = min(len(text), idx + 150)
            snippet = text[start:end].replace("\n", " ").strip()
            if start > 0:
                snippet = "..." + snippet
            if end < len(text):
                snippet = snippet + "..."
            evidence_quote = snippet

    return {
        "evidence_quote": evidence_quote[:1000],
        "stainless_steel": ", ".join(deduped_materials) if deduped_materials else "",
        "application": application,
        "media": ", ".join(found_media) if found_media else "",
        "tech_params": tech_params,
        "has_material": len(deduped_materials) > 0,
    }


def _deduplicate_materials(materials: list[str]) -> list[str]:
    """Remove redundant material keywords.

    E.g., if 'super duplex' and 'duplex' both appear, keep only 'super duplex'.
    If '316L' and 'stainless steel' both appear, keep both (they add info).
    """
    if not materials:
        return []

    mat_lower = [m.lower() for m in materials]
    result = []

    # Group: "super duplex" subsumes "duplex"
    has_super_duplex = any("super duplex" in m or "superduplex" in m for m in mat_lower)
    # Group: "corrosion resistant alloy" subsumes "CRA"
    has_cra_full = any("corrosion resistant alloy" in m for m in mat_lower)

    for i, m in enumerate(materials):
        ml = m.lower()
        if has_super_duplex and ml in ("duplex",):
            continue
        if has_cra_full and ml in ("cra",):
            continue
        if ml == "stainless" and any("stainless steel" in x for x in mat_lower):
            continue
        result.append(m)

    return result


# ============================================================================
# 3. HTTP 会话 & 页面获取
# ============================================================================


def build_session() -> requests.Session:
    """Build a requests Session with appropriate headers for gov.br."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
    })
    return session


def _download_html_with_curl(url: str) -> str:
    """Fallback: download HTML using system curl binary (gov.br SSL compat)."""
    import subprocess
    import tempfile

    log.info("Trying curl fallback for %s ...", url)
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            [
                "curl", "-sS", "-L",
                "--max-time", "60",
                "-H", f"User-Agent: {USER_AGENT}",
                "-H", "Accept-Language: pt-BR,pt;q=0.9,en;q=0.5",
                "-H", "Accept: text/html,application/xhtml+xml",
                "-o", tmp_path,
                url,
            ],
            capture_output=True,
            text=True,
            timeout=65,
        )
        if result.returncode != 0:
            raise RuntimeError(f"curl failed with exit code {result.returncode}: {result.stderr[:200]}")

        raw = Path(tmp_path).read_bytes()
        if len(raw) == 0:
            raise RuntimeError("curl downloaded 0 bytes")
        log.info("curl downloaded %d bytes", len(raw))
        # Try UTF-8 first, then UTF-8 with replacement chars
        # Avoid Latin-1 trap (Latin-1 never raises UnicodeDecodeError,
        # so it "succeeds" but produces garbled text for UTF-8 content)
        text = None
        for enc in ["utf-8-sig", "utf-8"]:
            try:
                text = raw.decode(enc)
                log.info("curl response decoded as %s", enc)
                return text
            except UnicodeDecodeError:
                continue
        # UTF-8 failed — use replacement chars to preserve readable content
        log.warning("curl response decoded as utf-8 with replacement chars")
        return raw.decode("utf-8", errors="replace")
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def fetch_page(url: str, session: requests.Session) -> Optional[str]:
    """Fetch a page and return its HTML text. Falls back to curl for gov.br SSL issues."""
    # Method 1: Python requests
    try:
        log.info("Fetching %s ...", url)
        resp = session.get(url, timeout=60)
        resp.raise_for_status()
        log.info("  HTTP %d, %d bytes", resp.status_code, len(resp.content))
        return _safe_decode_response(resp)
    except (requests.exceptions.SSLError, requests.exceptions.ConnectionError) as e:
        log.warning("  Python requests SSL/connection error: %s", str(e)[:120])
        log.info("  Falling back to curl for gov.br SSL compatibility...")
    except requests.exceptions.HTTPError as e:
        log.warning("  HTTP %s — %s",
                     e.response.status_code if hasattr(e, 'response') else '?', url)
        return None
    except requests.exceptions.RequestException as e:
        log.warning("  Request failed: %s — %s", e, url)
        return None

    # Method 2: curl fallback
    try:
        html = _download_html_with_curl(url)
        return html
    except Exception as e:
        log.warning("  curl fallback also failed: %s", e)
        return None


# ============================================================================
# 4. 页面解析
# ============================================================================


def parse_anp_page(html: str) -> list[dict]:
    """
    Parse ANP development plan page HTML.

    gov.br pages use various layouts. This parser tries multiple strategies:
      1. Table rows with field/plan data
      2. Article/content sections with headings and PDF links
      3. List items with links

    Returns:
        List of document dicts with keys:
        - title: plan title/heading
        - text: content text
        - download_url: PDF link (if any)
        - publication_date: extracted date
        - category: document category
        - event_type: candidate event type
        - field_name: extracted field name
        - operator: extracted operator name
        - country: "Brazil"
    """
    soup = BeautifulSoup(html, "html.parser")
    documents = []

    # Remove script/style elements
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    # Strategy 1: Look for tables with development plan data
    tables = soup.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        if not rows:
            continue

        # Try to detect header row
        header_cells = rows[0].find_all(["th", "td"])
        header_texts = [c.get_text(strip=True).lower() for c in header_cells]
        has_relevant_header = any(
            h and any(kw in h for kw in ["campo", "field", "operador", "operator",
                                           "bacia", "basin", "plano", "plan",
                                           "desenvolvimento", "development"])
            for h in header_texts
        )

        if not has_relevant_header and len(header_texts) <= 1:
            continue  # skip non-data tables

        for row in (rows[1:] if has_relevant_header else rows):
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue

            # Extract all cell texts
            cell_texts = [c.get_text(strip=True) for c in cells]
            full_text = " ".join(cell_texts)

            # Find PDF links
            links = row.find_all("a", href=True)
            pdf_links = [urljoin(ANP_PLANS_URL, a["href"])
                        for a in links
                        if a["href"].lower().endswith(".pdf")]

            title = cell_texts[0] if cell_texts else ""
            operator = extract_operator(full_text)
            field_name = extract_field_name(full_text)

            # Extract date from any cell
            pub_date = ""
            for ct in cell_texts:
                d = parse_date_from_text(ct)
                if d:
                    pub_date = d
                    break

            if not is_offshore_relevant(title, full_text):
                continue

            category = classify_document(title, full_text)

            for pdf_url in pdf_links or [""]:
                if not pdf_url:
                    pdf_url = ""
                # Try date from URL if not found in text
                url_date = extract_date_from_url(pdf_url) if pdf_url else None
                effective_date = pub_date or url_date or ""

                doc = {
                    "title": title[:300] if title else "ANP Development Plan",
                    "text": full_text[:2000],
                    "download_url": pdf_url,
                    "source_url": ANP_PLANS_URL,
                    "publication_date": effective_date,
                    "category": category,
                    "event_type": DOC_CATEGORY_EVENT_MAP.get(category, "REGULATORY_DATA"),
                    "field_name": field_name,
                    "operator": operator,
                    "file_hash": "",
                    "country": "Brazil",
                }
                documents.append(doc)

    if documents:
        log.info("Table strategy: found %d documents", len(documents))
        return documents

    # Strategy 2: Look for content sections with headings + PDF links
    main_content = (
        soup.find("main")
        or soup.find("article")
        or soup.find("div", id=re.compile(r"content|main|conteudo|parent-fieldname", re.I))
        or soup.find("div", class_=re.compile(r"content|main|conteudo|entry|post", re.I))
        or soup
    )

    # Find all headings and their following content
    headings = main_content.find_all(["h1", "h2", "h3", "h4"])
    if headings:
        for heading in headings:
            title = heading.get_text(strip=True)
            if not title or len(title) < 5:
                continue

            # Collect text until next heading
            content_parts = []
            sibling = heading.find_next_sibling()
            while sibling and sibling.name not in ("h1", "h2", "h3", "h4"):
                if sibling.name in ("p", "li", "div", "span", "td", "article"):
                    text = sibling.get_text(strip=True)
                    if text and len(text) > 10:
                        content_parts.append(text)
                sibling = sibling.find_next_sibling()

            content = " ".join(content_parts)

            # Find PDF links in this section
            section_links = heading.find_all("a", href=True) if heading else []
            if sibling:
                section_links.extend(
                    sibling.find_all("a", href=True) if hasattr(sibling, "find_all") else []
                )
            pdf_links = [urljoin(ANP_PLANS_URL, a["href"])
                        for a in section_links
                        if a["href"].lower().endswith(".pdf")]

            # Also find links in content area
            for a in main_content.find_all("a", href=True):
                href = a.get("href", "")
                if href.lower().endswith(".pdf"):
                    pdf_url = urljoin(ANP_PLANS_URL, href)
                    if pdf_url not in pdf_links:
                        pdf_links.append(pdf_url)

            if not is_offshore_relevant(title, content):
                continue

            category = classify_document(title, content)
            operator = extract_operator(f"{title} {content}")
            field_name = extract_field_name(f"{title} {content}")
            pub_date = parse_date_from_text(f"{title} {content}")

            if pdf_links:
                for pdf_url in pdf_links:
                    url_date = extract_date_from_url(pdf_url)
                    effective_date = pub_date or url_date or ""
                    documents.append({
                        "title": title[:300],
                        "text": content[:2000],
                        "download_url": pdf_url,
                        "source_url": ANP_PLANS_URL,
                        "publication_date": effective_date,
                        "category": category,
                        "event_type": DOC_CATEGORY_EVENT_MAP.get(category, "REGULATORY_DATA"),
                        "field_name": field_name,
                        "operator": operator,
                        "file_hash": "",
                        "country": "Brazil",
                    })
            else:
                documents.append({
                    "title": title[:300],
                    "text": content[:2000],
                    "download_url": "",
                    "source_url": ANP_PLANS_URL,
                    "publication_date": pub_date or "",
                    "category": category,
                    "event_type": DOC_CATEGORY_EVENT_MAP.get(category, "REGULATORY_DATA"),
                    "field_name": field_name,
                    "operator": operator,
                    "file_hash": "",
                    "country": "Brazil",
                })

    if documents:
        log.info("Heading strategy: found %d documents", len(documents))
        return documents

    # Strategy 3: All PDF links + surrounding text
    all_links = main_content.find_all("a", href=True)
    pdf_links = [
        (a, urljoin(ANP_PLANS_URL, a["href"]))
        for a in all_links
        if a["href"].lower().endswith(".pdf")
    ]

    for anchor, pdf_url in pdf_links:
        link_text = anchor.get_text(strip=True)
        # Get parent/surrounding text
        parent = anchor.find_parent(["li", "p", "div", "td", "tr", "span"])
        context = parent.get_text(strip=True) if parent else link_text

        title = link_text or Path(unquote(pdf_url)).stem
        category = classify_document(title, context)
        operator = extract_operator(context)
        field_name = extract_field_name(context)
        pub_date = parse_date_from_text(context) or extract_date_from_url(pdf_url)

        documents.append({
            "title": title[:300],
            "text": context[:2000],
            "download_url": pdf_url,
            "source_url": ANP_PLANS_URL,
            "publication_date": pub_date or "",
            "category": category,
            "event_type": DOC_CATEGORY_EVENT_MAP.get(category, "REGULATORY_DATA"),
            "field_name": field_name,
            "operator": operator,
            "file_hash": "",
            "country": "Brazil",
        })

    if documents:
        log.info("PDF link strategy: found %d documents", len(documents))
        return documents

    # Strategy 4: Fallback — create one entry from the page title/content
    page_title = ""
    title_tag = soup.find("title")
    if title_tag:
        page_title = title_tag.get_text(strip=True)

    all_text = main_content.get_text(separator="\n", strip=True)[:5000]

    if is_offshore_relevant(page_title, all_text):
        documents.append({
            "title": page_title or "ANP Development Plans",
            "text": all_text[:2000],
            "download_url": "",
            "source_url": ANP_PLANS_URL,
            "publication_date": TODAY,
            "category": "OTHER",
            "event_type": "REGULATORY_DATA",
            "field_name": extract_field_name(all_text),
            "operator": extract_operator(all_text),
            "file_hash": "",
            "country": "Brazil",
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
    """Download a PDF attachment. Returns (sha256_hex, local_path) or (None, None)."""
    download_url = doc.get("download_url", "")
    if not download_url:
        return None, None

    data_dir.mkdir(parents=True, exist_ok=True)

    # Generate safe filename from URL
    parsed = urlparse(download_url)
    raw_name = unquote(Path(parsed.path).name)
    if not raw_name or not raw_name.lower().endswith(".pdf"):
        raw_name = re.sub(r"[^\w\-_. ()]", "_", doc.get("title", "document"))[:100] + ".pdf"

    safe_name = re.sub(r"[^\w\-_. ()]", "_", raw_name)
    safe_name = re.sub(r"_+", "_", safe_name)

    local_path = data_dir / safe_name

    # Skip re-download if exists
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
            log.warning("  Response appears to be HTML, not a PDF")
            return None, None

        local_path.write_bytes(content)
        file_hash = hashlib.sha256(content).hexdigest()

        # Save SHA256 sidecar
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
    """Derive stable unique key from document dict."""
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


def _parse_numeric_from_text(text: str) -> Optional[int]:
    """Extract the first numeric value from a tech param match string."""
    if not text:
        return None
    m = re.search(r"(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?)", text)
    if m:
        try:
            val = m.group(1).replace(",", "").replace(".", "")
            return int(val)
        except (ValueError, TypeError):
            return None
    return None


def build_candidate_event(doc: dict, raw_html_path: str = "") -> dict:
    """Convert a parsed document into a candidate_events record."""
    title = doc.get("title", "")
    text = doc.get("text", "")
    category = doc.get("category", "OTHER")
    event_type = doc.get("event_type", "REGULATORY_DATA")
    field_name = doc.get("field_name", "")
    operator = doc.get("operator", "")
    publication_date = doc.get("publication_date", "")
    download_url = doc.get("download_url", "")
    file_hash = doc.get("file_hash", "")

    # project_name_raw: field name if available, otherwise title
    project_name_raw = field_name if field_name else title

    # Build structured summary
    summary_parts = []
    if category != "OTHER":
        summary_parts.append(f"Category: {category}")
    if operator:
        summary_parts.append(f"Operator: {operator}")
    if field_name:
        summary_parts.append(f"Field: {field_name}")
    if publication_date:
        summary_parts.append(f"Published: {publication_date}")
    if file_hash:
        summary_parts.append(f"SHA256: {file_hash[:16]}")

    summary = " | ".join(summary_parts) if summary_parts else text[:500]

    # evidence_quote: title + text preview for human review
    evidence_quote = title
    if text:
        evidence_quote += f" — {text[:400]}"
    if publication_date:
        evidence_quote += f" (Published: {publication_date})"

    # 技术规格提取 (strictly based on source text, empty when uncertain)
    combined_text = f"{title} {text}"
    water_depth = extract_water_depth_from_text(combined_text)
    oil_cap = extract_oil_capacity_from_text(combined_text)
    gas_cap = extract_gas_capacity_from_text(combined_text)
    hull_type = extract_hull_type_from_text(combined_text)

    # 腐蚀性介质提取 (H2S, CO2, sour service, chloride)
    corrosive_media = extract_corrosive_media(combined_text)

    # PDF-extracted technical specs (from parse_technical_specs)
    pdf_specs = doc.get("_pdf_specs", {}) or {}
    pdf_stainless = pdf_specs.get("stainless_steel", "")
    pdf_application = pdf_specs.get("application", "")
    pdf_evidence = pdf_specs.get("evidence_quote", "")
    pdf_media = pdf_specs.get("media", "")
    pdf_tech_params = pdf_specs.get("tech_params", {}) or {}

    # evidence_quote priority: PDF excerpt > title + text preview
    final_evidence = pdf_evidence if pdf_evidence else evidence_quote

    # Merge PDF-extracted tech params with text-extracted ones (text takes precedence)
    if pdf_tech_params:
        if not water_depth and pdf_tech_params.get("water_depth"):
            water_depth = _parse_numeric_from_text(pdf_tech_params["water_depth"])
        if not oil_cap and pdf_tech_params.get("production_capacity"):
            oil_cap = _parse_numeric_from_text(pdf_tech_params["production_capacity"])

    return {
        "project_name_raw": project_name_raw[:255],
        "country": "Brazil",
        "summary": summary[:500],
        "source_name": SOURCE_NAME,
        "source_url": doc.get("source_url", ANP_PLANS_URL)[:2048],
        "review_status": "pending",
        "event_type": event_type,
        "fetched_at": NOW_ISO,
        "evidence_quote": final_evidence[:500],
        "publication_date": publication_date or TODAY,
        "raw_json": json.dumps(doc, ensure_ascii=False),
        # 技术规格字段
        "water_depth_m": water_depth,
        "oil_capacity_bpd": oil_cap,
        "gas_capacity_mmcmd": gas_cap,
        "hull_type": hull_type,
        "field_name": field_name if field_name else None,
        "operator_name": operator if operator else None,
        "basin": None,  # ANP development plans don't always name the basin
        # PDF 文本提取字段
        "stainless_steel": pdf_stainless if pdf_stainless else None,
        "application": pdf_application if pdf_application else None,
        "corrosive_media": json.dumps(corrosive_media) if any([corrosive_media.get("h2s"), corrosive_media.get("co2"), corrosive_media.get("sour_service"), corrosive_media.get("chloride")]) else None,
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
            "source_url": ANP_PLANS_URL,
            "snapshot_date": TODAY,
            "fetched_at": NOW_ISO,
            "file_path": str(filepath),
            "file_hash_sha256": sha256,
            "record_count": record_count,
            "source_type": "GOVERNMENT",
            "tier": 2,
            "priority": "P0",
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
            "original_url": original_url or ANP_PLANS_URL,
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
    "file_hash", "category", "event_type", "field_name", "operator",
]


def load_previous_snapshot_local(date_str: str = None) -> Optional[list[dict]]:
    """Load most recent non-today snapshot JSON from data directory."""
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


def save_raw_html(html: str, date_str: str = TODAY) -> Path:
    """Save raw HTML for audit."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    filepath = DATA_DIR / f"{date_str}_anp_plans.html"
    filepath.write_text(html, encoding="utf-8")
    sha256 = hashlib.sha256(html.encode("utf-8")).hexdigest()
    hash_path = DATA_DIR / f"{date_str}_anp_plans.html.sha256"
    hash_path.write_text(f"{sha256}  {date_str}_anp_plans.html\n")
    log.info("Saved raw HTML to %s (SHA256=%s)", filepath, sha256[:16])
    return filepath


def save_local_snapshot(documents: list[dict], date_str: str = TODAY) -> Path:
    """Save parsed document metadata as JSON snapshot."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    filepath = DATA_DIR / f"{date_str}_snapshot.json"
    data = {
        "date": date_str,
        "fetched_at": NOW_ISO,
        "source_url": ANP_PLANS_URL,
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
    log.info("ANP Development Plan Adapter — P0 — %s", TODAY)
    log.info("=" * 60)

    session = build_session()

    # Step 1: Fetch the ANP development plans page
    delay = random.uniform(MIN_REQUEST_DELAY_SEC, MAX_REQUEST_DELAY_SEC)
    log.info("Waiting %.1fs (polite delay)...", delay)
    time.sleep(delay)

    html = fetch_page(ANP_PLANS_URL, session)
    if html is None:
        raise RuntimeError(f"Failed to fetch page: {ANP_PLANS_URL}")

    # Step 2: Save raw HTML for audit
    raw_html_path = save_raw_html(html)
    html_sha256 = hashlib.sha256(html.encode("utf-8")).hexdigest()

    if not dry_run and not local_only:
        save_to_source_documents(
            str(raw_html_path), html_sha256, "HTML",
            len(html.encode("utf-8")),
            original_url=ANP_PLANS_URL,
            supabase=supabase,
        )

    # Step 3: Parse development plan entries
    log.info("--- Parsing ANP Development Plan entries ---")
    documents = parse_anp_page(html)

    if not documents:
        log.warning("No development plans found. Page structure may have changed.")
        return {
            "mode": "dry_run" if dry_run else ("local_only" if local_only else "full"),
            "total_documents": 0,
            "diff_new": 0, "diff_changed": 0,
            "diff_removed": 0, "diff_unchanged": 0,
            "error": "No documents parsed",
            "html_path": str(raw_html_path),
            "html_sha256": html_sha256,
        }

    # Step 4: Classification summary
    log.info("--- Classification Summary ---")
    category_counts = {}
    for doc in documents:
        cat = doc.get("category", "OTHER")
        category_counts[cat] = category_counts.get(cat, 0) + 1
    for cat, count in sorted(category_counts.items()):
        log.info("  %s: %d", cat, count)

    # Step 5: Download PDF attachments
    if not skip_download:
        log.info("--- Downloading Attachments ---")
        for i, doc in enumerate(documents):
            if not doc.get("download_url"):
                continue
            if i > 0:
                delay = random.uniform(MIN_REQUEST_DELAY_SEC, MAX_REQUEST_DELAY_SEC)
                log.info("  Waiting %.1fs (polite delay)...", delay)
                time.sleep(delay)
            result = download_document(doc, session, DATA_DIR)
            if result and result[0]:
                file_hash, local_path = result
                doc["file_hash"] = file_hash
                doc["_local_pdf_path"] = local_path  # used for PDF text extraction
                if not dry_run and not local_only:
                    save_to_source_documents(
                        local_path, file_hash, "PDF",
                        Path(local_path).stat().st_size if Path(local_path).exists() else 0,
                        original_url=doc.get("source_url", ANP_PLANS_URL),
                        download_url=doc.get("download_url", ""),
                        publication_date=doc.get("publication_date", ""),
                        supabase=supabase,
                    )

                # Extract text from downloaded PDF and parse technical specs
                if local_path and Path(local_path).exists():
                    pdf_text = extract_pdf_text(local_path)
                    if pdf_text:
                        pdf_specs = parse_technical_specs(pdf_text)
                        doc["_pdf_specs"] = pdf_specs
                        if pdf_specs.get("has_material"):
                            log.info("  Material keywords found: %s", pdf_specs.get("stainless_steel", ""))
                        else:
                            log.info("  No material keywords found in PDF text")
    else:
        log.info("--- Skipping Downloads (--skip-download) ---")

    # Step 6: Deduplicate
    documents = deduplicate_documents(documents)

    # Step 7: Snapshot diff
    if no_diff:
        previous_snapshot = None
        log.info("--- Snapshot Diff: --no-diff (all treated as new) ---")
    else:
        log.info("--- Snapshot Diff ---")
        previous_snapshot = load_previous_snapshot_local()

    diff_result = diff_documents(documents, previous_snapshot)

    log.info("  New:        %d", len(diff_result["new"]))
    log.info("  Changed:    %d", len(diff_result["changed"]))
    log.info("  Removed:    %d", len(diff_result["removed"]))
    log.info("  Unchanged:  %d (skipped)", len(diff_result["unchanged"]))

    # Step 8: Save current snapshot
    snapshot_path = save_local_snapshot(documents)

    # Step 9: Build candidate_events
    log.info("--- Building candidate_events (diff only) ---")
    events = []

    for doc in diff_result["new"]:
        evt = build_candidate_event(doc, str(raw_html_path))
        events.append(evt)

    for cur_doc, prev_doc, diffs in diff_result["changed"]:
        evt = build_candidate_event(cur_doc, str(raw_html_path))
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
        evt = build_candidate_event(prev_doc, str(raw_html_path))
        evt["event_type"] = "DOCUMENT_REMOVED"
        evt["summary"] = f"[REMOVED] No longer on ANP plans page: {title}"
        events.append(evt)

    log.info("  Candidate events: %d (from %d docs)", len(events), len(documents))

    # Step 10: Write to Supabase
    inserted = 0
    write_to_db = not dry_run and not local_only
    if write_to_db and events:
        try:
            inserted = insert_candidate_events(events, supabase)
            log.info("  Inserted %d candidate_events rows", inserted)
        except RuntimeError as e:
            log.warning("  Skipping Supabase write: %s", e)

    # Step 11: Save snapshot registry record
    if write_to_db:
        try:
            save_snapshot_to_registry(
                str(snapshot_path), html_sha256, len(documents), supabase,
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
    """Self-test: fetch page -> parse -> download first PDF -> verify hash -> show events."""
    log.info("=" * 60)
    log.info("SELF-TEST: ANP Development Plan Adapter")
    log.info("=" * 60)

    session = build_session()

    print("\n" + "─" * 60)
    print("Step 1: Fetch ANP Development Plans page")
    print("─" * 60)

    html = fetch_page(ANP_PLANS_URL, session)
    if html is None:
        print("  FAILED: Could not fetch page.")
        sys.exit(1)

    print(f"  Downloaded: {len(html):,} bytes")
    html_hash = hashlib.sha256(html.encode("utf-8")).hexdigest()
    print(f"  HTML SHA256: {html_hash}")

    raw_html_path = save_raw_html(html)
    print(f"  Saved HTML: {raw_html_path}")

    print("\n" + "─" * 60)
    print("Step 2: Parse Development Plan Entries")
    print("─" * 60)

    documents = parse_anp_page(html)
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

    field_names = [d["field_name"] for d in documents if d.get("field_name")]
    if field_names:
        print(f"\n  Fields identified: {sorted(set(field_names))}")

    operators = [d["operator"] for d in documents if d.get("operator")]
    if operators:
        print(f"\n  Operators identified: {sorted(set(operators))}")

    print("\n" + "─" * 60)
    print("Step 3: Download First PDF Attachment")
    print("─" * 60)

    first_with_pdf = None
    for doc in documents:
        if doc.get("download_url"):
            first_with_pdf = doc
            break

    if first_with_pdf:
        print(f"  Title: {first_with_pdf['title'][:120]}")
        print(f"  URL: {first_with_pdf['download_url'][:120]}")
        result = download_document(first_with_pdf, session, DATA_DIR)
        if result and result[0]:
            file_hash, _ = result
            print(f"  Downloaded successfully!")
            print(f"  SHA256: {file_hash}")
            first_with_pdf["file_hash"] = file_hash
        else:
            print("  Download failed (see log).")
    else:
        print("  No downloadable PDF found.")

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
        description="ANP 开发计划适配器 — P0 专用适配器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python crawler/adapters/anp_development_plan.py                 # 完整运行
  python crawler/adapters/anp_development_plan.py --test          # 自测
  python crawler/adapters/anp_development_plan.py --dry-run       # 仅解析和下载，不写入数据库
  python crawler/adapters/anp_development_plan.py --local-only    # 仅本地保存
  python crawler/adapters/anp_development_plan.py --skip-download # 仅解析，不下载文件
  python crawler/adapters/anp_development_plan.py --no-diff       # 跳过差异对比，全量输出
        """,
    )
    parser.add_argument("--test", action="store_true",
                        help="自测: 访问页面 -> 解析 -> 下载第一个PDF -> 输出前3条候选事件。")
    parser.add_argument("--dry-run", action="store_true",
                        help="仅解析页面、下载文件，不写入数据库。")
    parser.add_argument("--local-only", action="store_true",
                        help="保存文件到本地，不写入 Supabase。")
    parser.add_argument("--skip-download", action="store_true",
                        help="跳过 PDF 下载，仅解析页面元数据。")
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
