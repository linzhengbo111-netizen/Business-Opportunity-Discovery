#!/usr/bin/env python3
"""
FPSO Project Crawler
Scrapes offshore industry news sites for FPSO-related articles,
extracts project metadata, and stores results in Supabase.

Usage: python crawler/crawl.py
"""

import os
import re
import sys
import time
import random
import logging
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from supabase import create_client

# ---- Config -----------------------------------------------------------

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("VITE_SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: SUPABASE_URL and SUPABASE_ANON_KEY must be set in .env")
    sys.exit(1)

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")

USER_AGENT = (
    "Mozilla/5.0 (compatible; FPSOCrawler/1.0)"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("fpso-crawler")

# ---- Site definitions ------------------------------------------------

SITES = [
    {
        "name": "Offshore Energy",
        "domain": "offshore-energy.biz",
        "urls": [
            "https://www.offshore-energy.biz/?s=FPSO",
        ],
        "article_tag": "article",
        "fallback_class": re.compile(r"post|article|story|result|item", re.I),
        "title_sel": "h2 a, h3 a, .entry-title a",
        "date_sel": "time, .entry-date, .posted-on, .post-date",
        "summary_sel": ".entry-summary, .entry-content p, .excerpt",
    },
    {
        "name": "OE Digital",
        "domain": "oedigital.com",
        "urls": [
            "https://www.oedigital.com/search?q=FPSO",
            "https://www.oedigital.com/?s=FPSO",
        ],
        "article_tag": "article",
        "fallback_class": re.compile(r"post|article|story|result|item|search-result", re.I),
        "title_sel": "h2 a, h3 a, .title a, .headline a",
        "date_sel": "time, .date, .published, .pub-date",
        "summary_sel": "p, .summary, .excerpt, .teaser, .body",
    },
    {
        "name": "World Oil",
        "domain": "worldoil.com",
        "urls": [
            "https://www.worldoil.com/search?q=FPSO",
            "https://www.worldoil.com/?s=FPSO",
            "https://www.worldoil.com/search/FPSO",
        ],
        "article_tag": "article",
        "fallback_class": re.compile(r"post|article|story|result|item|search-result", re.I),
        "title_sel": "h2 a, h3 a, .headline a, .title a",
        "date_sel": "time, .date, .pub-date, .published",
        "summary_sel": "p, .summary, .excerpt, .abstract, .teaser",
    },
    {
        "name": "Splash247",
        "domain": "splash247.com",
        "urls": [
            "https://splash247.com/?s=FPSO",
        ],
        "article_tag": "article",
        "fallback_class": re.compile(r"post|article|story|result|item", re.I),
        "title_sel": "h2 a, h3 a, .entry-title a, .post-title a",
        "date_sel": "time, .entry-date, .post-date, .published",
        "summary_sel": ".entry-summary, .entry-content p, .excerpt",
    },
]

# ---- Project extraction patterns -------------------------------------

COUNTRY_LIST = [
    "Brazil", "Guyana", "Angola", "Nigeria", "Norway", "UK",
    "China", "Malaysia", "Indonesia", "Australia", "Ghana",
    "Senegal", "Mauritania", "India", "USA", "Canada", "Mexico",
    "Vietnam", "Thailand", "Qatar", "UAE", "Saudi Arabia",
    "Mozambique", "Egypt", "Libya", "Equatorial Guinea", "Congo",
    "Gabon", "Ivory Coast", "Cameroon", "Trinidad and Tobago",
    "Suriname", "Argentina", "Russia", "Azerbaijan", "Kazakhstan",
    "South Korea", "Singapore", "Japan", "Netherlands", "Denmark",
    "Namibia", "South Africa", "Israel", "Cyprus", "Turkey",
    "Iraq", "Iran", "Kuwait", "Oman", "Bahrain", "Yemen",
]

# Country → ISO 3166-1 alpha-2 code for flag emoji generation
COUNTRY_CODE = {
    "Australia": "AU", "Azerbaijan": "AZ", "Angola": "AO", "Argentina": "AR",
    "Bahrain": "BH", "Brazil": "BR", "Cameroon": "CM", "Canada": "CA",
    "China": "CN", "Congo": "CG", "Cyprus": "CY", "Denmark": "DK",
    "Egypt": "EG", "Equatorial Guinea": "GQ", "Gabon": "GA", "Ghana": "GH",
    "Guyana": "GY", "India": "IN", "Indonesia": "ID", "Iran": "IR",
    "Iraq": "IQ", "Israel": "IL", "Ivory Coast": "CI", "Japan": "JP",
    "Kazakhstan": "KZ", "Kuwait": "KW", "Libya": "LY", "Malaysia": "MY",
    "Mauritania": "MR", "Mexico": "MX", "Mozambique": "MZ", "Namibia": "NA",
    "Netherlands": "NL", "Nigeria": "NG", "Norway": "NO", "Oman": "OM",
    "Qatar": "QA", "Russia": "RU", "Saudi Arabia": "SA", "Senegal": "SN",
    "Singapore": "SG", "South Africa": "ZA", "South Korea": "KR",
    "Suriname": "SR", "Thailand": "TH", "Trinidad and Tobago": "TT",
    "Turkey": "TR", "UAE": "AE", "UK": "GB", "USA": "US",
    "Vietnam": "VN", "Yemen": "YE",
}


def country_to_flag(country):
    """Convert country name to flag emoji. Returns empty string if country is empty or unknown."""
    if not country:
        return ""
    code = COUNTRY_CODE.get(country)
    if not code:
        return ""
    # Regional indicator symbols: U+1F1E6 = 🇦 (A), offset from A is 0x1F1E6
    return chr(ord(code[0]) - ord("A") + 0x1F1E6) + chr(ord(code[1]) - ord("A") + 0x1F1E6)


STATUS_PATTERNS = {
    "Under Construction": [
        "under construction", "being built", "construction",
        "building", "fabrication", "under development",
        "steel cut", "first steel", "keel laying", "hull launch",
        "topsides", "integration", "outfitting", "dry dock",
    ],
    "Delivered": [
        "delivered", "delivery", "completed", "commissioned",
        "first oil", "production start", "operational",
        "in operation", "on stream", "started production",
        "commenced production", "onstation", "on station",
        "sailaway", "sail away", "achieved first oil",
        "producing", "production commenced",
    ],
    "Planned": [
        "planned", "planning", "proposed", "sanctioned",
        "approved", "FEED", "pre-FEED",
        "front-end engineering", "conceptual", "study",
        "tender", "bid", "contract awarded",
        "letter of intent", "LOI", "MoU",
        "memorandum", "agreement signed", "secured contract",
        "won contract", "awarded contract",
    ],
}

# Words that are not real project names even if they follow "FPSO"
GENERIC_WORDS = {
    "the", "a", "an", "for", "and", "with", "new", "first", "latest",
    "project", "vessel", "unit", "platform", "production", "storage",
    "offloading", "of", "in", "at", "to", "is", "on", "as", "by",
    "its", "will", "has", "been", "from", "was", "that", "this",
    "next", "two", "three", "four", "one", "major", "another",
    "floating", "fpso", "be", "it", "or", "second", "third",
}


def extract_project_info(title, summary):
    """
    Pull project name, country, and status from article title + summary.
    Falls back to using the title itself as the project name when nothing
    specific can be identified.
    """
    text = f"{title} {summary}"

    # ---- project name ----
    project_name = None

    # 1) "FPSO ThingName"
    m = re.search(
        r"FPSO\s+([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+){0,4})",
        title,
        re.IGNORECASE,
    )
    if m:
        candidate = m.group(1).strip()
        if candidate.lower() not in GENERIC_WORDS and len(candidate) > 2:
            project_name = f"FPSO {candidate}"

    # 2) Quoted name near FPSO
    if not project_name:
        m = re.search(r'["“]([^"”]{3,60})["”]', title)
        if m:
            candidate = m.group(1).strip()
            if candidate.lower() not in GENERIC_WORDS:
                project_name = candidate

    # 3) FPSO Name (more lenient) from full text
    if not project_name:
        m = re.search(
            r'FPSO\s+["“]?([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+){0,4})',
            text,
            re.IGNORECASE,
        )
        if m:
            candidate = m.group(1).strip()
            if candidate.lower() not in GENERIC_WORDS and len(candidate) > 2:
                project_name = f"FPSO {candidate}"

    # fallback: original title
    if not project_name:
        project_name = title.strip()

    # ---- country ----
    country = None
    for c in COUNTRY_LIST:
        if re.search(rf"\b{re.escape(c)}\b", text, re.IGNORECASE):
            country = c
            break

    # ---- status ----
    status = "Unknown"
    text_lower = text.lower()
    for label, keywords in STATUS_PATTERNS.items():
        for kw in keywords:
            if kw in text_lower:
                status = label
                break
        if status != "Unknown":
            break

    return project_name, country, status


# ---- Crawl helpers ---------------------------------------------------

def build_session():
    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    })
    return session


def fetch_url(url, session):
    """GET a URL. Returns response or None on failure."""
    try:
        r = session.get(url, timeout=30)
        r.raise_for_status()
        return r
    except requests.exceptions.HTTPError:
        log.warning("  HTTP %s — %s", r.status_code if 'r' in dir() else "?", url)
        return None
    except requests.exceptions.RequestException as e:
        log.warning("  Request failed: %s — %s", e, url)
        return None


def fetch_search_page(site_config, session):
    """Try each search URL until one works."""
    for url in site_config["urls"]:
        log.info("  Trying %s", url)
        r = fetch_url(url, session)
        if r is not None:
            return r
        time.sleep(1)
    return None


def parse_date(element, selectors):
    """Extract date string from element using a list of CSS selectors."""
    for sel in selectors:
        el = element.select_one(sel.strip())
        if not el:
            continue
        dt = el.get("datetime")
        if dt:
            return dt[:10]

        text = el.get_text(strip=True)
        m = re.search(
            r"(\d{4}[-/]\d{1,2}[-/]\d{1,2}|"
            r"\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4})",
            text,
            re.IGNORECASE,
        )
        if m:
            return m.group(1)
    return None


def find_article_elements(soup, site_config):
    """Locate article containers, falling back to class-based search."""
    elems = soup.select(site_config["article_tag"])
    if len(elems) >= 2:
        return elems

    # fallback: any tag with a post/article/story class
    elems = soup.find_all(
        ["article", "div", "li", "section"],
        class_=site_config["fallback_class"],
    )
    return elems if elems else []


def crawl_site(site_config, session):
    """Crawl one site, return list of article dicts."""
    articles = []
    log.info("--- %s ---", site_config["name"])

    r = fetch_search_page(site_config, session)
    if r is None:
        log.warning("  All search URLs failed, skipping.")
        return articles

    soup = BeautifulSoup(r.text, "html.parser")
    elem_list = find_article_elements(soup, site_config)
    log.info("  Found %d candidate containers", len(elem_list))

    title_selectors = [s.strip() for s in site_config["title_sel"].split(",")]
    date_selectors = [s.strip() for s in site_config["date_sel"].split(",")]
    summary_selectors = [s.strip() for s in site_config["summary_sel"].split(",")]

    for elem in elem_list:
        try:
            # title + link
            title_el = None
            for sel in title_selectors:
                title_el = elem.select_one(sel)
                if title_el:
                    break
            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            if not title or "FPSO" not in title.upper():
                continue

            link = title_el.get("href", "")
            if link:
                link = urljoin(site_config["urls"][0], link)

            # summary
            summary = ""
            for sel in summary_selectors:
                s_el = elem.select_one(sel)
                if s_el:
                    txt = s_el.get_text(strip=True)
                    if len(txt) > 20:
                        summary = txt
                        break

            # date
            raw_date = parse_date(elem, date_selectors)

            project_name, country, status = extract_project_info(title, summary)

            articles.append({
                "name": project_name,
                "country": country or "",
                "flag": country_to_flag(country or ""),
                "status": status or "Unknown",
                "summary": (summary or title)[:500],
                "source_name": site_config["name"],
                "source_url": link or site_config["urls"][0],
                "source_date": raw_date or TODAY,
                "stainless_steel": "",
                "application": "",
            })
            log.info("  %s | %s | %s", status, country or "?", project_name[:50])

        except Exception:
            log.warning("  Parse error in %s element", site_config["name"], exc_info=True)

    return articles


# ---- Supabase --------------------------------------------------------

def upsert_projects(supabase, articles):
    """
    Write articles to Supabase projects table.
    Match by 'name' column. Update existing, insert new.
    Returns (new, updated) counts.
    """
    new = 0
    updated = 0
    table = supabase.table("projects")

    for a in articles:
        try:
            existing = table.select("id").eq("name", a["name"]).execute()
            if existing.data:
                table.update({
                    "country": a["country"],
                    "flag": a["flag"],
                    "status": a["status"],
                    "summary": a["summary"],
                    "source_name": a["source_name"],
                    "source_url": a["source_url"],
                    "source_date": a["source_date"],
                }).eq("name", a["name"]).execute()
                updated += 1
            else:
                table.insert(a).execute()
                new += 1
        except Exception:
            log.warning("  DB error: %s", a["name"], exc_info=True)

    return new, updated


# ---- Main ------------------------------------------------------------

def main():
    log.info("=" * 54)
    log.info("FPSO Project Crawler  —  %s", TODAY)
    log.info("=" * 54)

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    session = build_session()

    all_articles = []

    for i, site in enumerate(SITES):
        articles = crawl_site(site, session)
        all_articles.extend(articles)

        if i < len(SITES) - 1:
            delay = random.uniform(2, 5)
            log.info("Sleeping %.1fs ...", delay)
            time.sleep(delay)

    log.info("=" * 54)
    log.info("Total articles found: %d", len(all_articles))

    if all_articles:
        new, updated = upsert_projects(supabase, all_articles)
        log.info(
            "抓取完成，共处理 %d 条项目（新增 %d 条，更新 %d 条）",
            len(all_articles),
            new,
            updated,
        )
    else:
        log.info("No articles with FPSO found.")

    log.info("Crawl complete.")


if __name__ == "__main__":
    main()
