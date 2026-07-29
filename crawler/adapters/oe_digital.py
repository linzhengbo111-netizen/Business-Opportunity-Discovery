#!/usr/bin/env python3
"""
OE Digital 适配器 — P1 行业媒体来源适配器
==========================================

按《FPSO项目可用信息源使用手册》P1 要求实现：

来源信息:
  名称: OE Digital
  URL:  https://www.oedigital.com/
  类型: MEDIA
  优先级: P1
  层级: 1（线索发现）
  接入方式: HTML — 搜索页面抓取

功能:
  1. 访问 oedigital.com 搜索页面，采集 FPSO 相关文章列表。
  2. 提取标题、日期、摘要、链接，输出 event_type='ARTICLE_MENTION'。
  3. 输出到 candidate_events 表，review_status='pending'。
  4. 保存原始 HTML 到 crawler/data/media/ 目录，记录 SHA256。
  5. 写入 source_documents 表建立审计链。

合规:
  - 只采集公开搜索页面文本和链接，不自动登录、不绕过验证。
  - 请求间隔 2-5 秒（由调用方控制）。
  - 支持 --dry-run 和 --local-only 模式。

Usage:
  python crawler/adapters/oe_digital.py                 # 完整运行
  python crawler/adapters/oe_digital.py --dry-run       # 仅采集，不写入数据库
  python crawler/adapters/oe_digital.py --local-only    # 保存文件到本地，不写入 Supabase
  python crawler/adapters/oe_digital.py --test          # 自测
"""

import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

try:
    from . import media_common as mc
except ImportError:
    import media_common as mc

# ---- Paths ---------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent  # crawler/
DATA_DIR = BASE_DIR / "data" / "media"

# ---- Config --------------------------------------------------------------

load_dotenv(BASE_DIR.parent / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("VITE_SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY")

SOURCE_NAME = "OE Digital"
SOURCE_DOMAIN = "oedigital.com"

SITE_CONFIG = {
    "name": SOURCE_NAME,
    "domain": SOURCE_DOMAIN,
    "urls": [
        "https://www.oedigital.com/search?q=FPSO",
        "https://www.oedigital.com/?s=FPSO",
    ],
    "article_tag": "article",
    "fallback_class": re.compile(r"post|article|story|result|item|search-result", re.I),
    "title_sel": "h2 a, h3 a, .title a, .headline a",
    "date_sel": "time, .date, .published, .pub-date",
    "summary_sel": "p, .summary, .excerpt, .teaser, .body",
}

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")
NOW_ISO = datetime.now(timezone.utc).isoformat()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("oedigital-adapter")


# ============================================================================
# Adapter runner
# ============================================================================


def get_supabase():
    """Return Supabase client or raise if credentials missing."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError(
            "Missing SUPABASE_URL/SUPABASE_ANON_KEY. "
            "Set them in .env or use --local-only to skip Supabase writes."
        )
    from supabase import create_client
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def run_adapter(dry_run: bool = False, local_only: bool = False):
    """
    Run the OE Digital adapter.

    Args:
        dry_run: Fetch + parse + save files, but don't write to DB.
        local_only: Save files locally only, no Supabase connection needed.

    Returns:
        dict with keys: mode, total_articles, candidate_events, inserted.
    """
    log.info("=" * 60)
    mode_str = "DRY-RUN" if dry_run else ("LOCAL-ONLY" if local_only else "FULL")
    log.info("OE Digital Adapter — %s — %s", mode_str, TODAY)
    log.info("=" * 60)

    write_to_db = not dry_run and not local_only
    supabase = None
    if write_to_db:
        supabase = get_supabase()

    session = mc.build_session()

    # Crawl
    articles = mc.crawl_media_site(SITE_CONFIG, session, supabase=supabase)

    if not articles:
        log.warning("No FPSO-relevant articles found.")
        return {
            "mode": mode_str.lower().replace("-", "_"),
            "total_articles": 0,
            "candidate_events": 0,
            "inserted": 0,
            "error": "No FPSO-relevant articles found",
        }

    log.info("Total articles found: %d", len(articles))

    # Country recognition stats
    recognized = sum(1 for a in articles if a["country"])
    unrecognized = len(articles) - recognized
    log.info("Country recognition: %d/%d (%.1f%%)",
             recognized, len(articles),
             100 * recognized / len(articles) if articles else 0)

    inserted = 0
    if write_to_db:
        inserted = mc.insert_candidate_events(supabase, articles)
        log.info("Inserted %d candidate_events rows", inserted)
    elif articles:
        log.info("DRY-RUN / LOCAL-ONLY: %d articles would be inserted", len(articles))

    result = {
        "mode": mode_str.lower().replace("-", "_"),
        "total_articles": len(articles),
        "candidate_events": len(articles),
        "inserted": inserted,
        "recognized_countries": recognized,
        "unrecognized": unrecognized,
    }

    log.info("=" * 60)
    log.info("Run complete. Mode: %s | Articles: %d | Inserted: %d",
             mode_str, len(articles), inserted)
    return result


# ============================================================================
# Self-test
# ============================================================================


def run_test():
    """Self-test: fetch page → parse → show articles."""
    log.info("=" * 60)
    log.info("SELF-TEST: OE Digital Adapter")
    log.info("=" * 60)

    session = mc.build_session()
    articles = mc.crawl_media_site(SITE_CONFIG, session, supabase=None)

    print(f"\nTotal articles found: {len(articles)}")
    for a in articles[:10]:
        print(f"  [{a.get('status', '?')}] {a['name'][:80]}")
        print(f"       Country: {a.get('country', '?')} | Date: {a.get('source_date', '?')}")
        print(f"       URL: {a.get('source_url', '')[:100]}")

    recognized = sum(1 for a in articles if a["country"])
    print(f"\nCountry recognition: {recognized}/{len(articles)}")
    print("Self-test complete.")


# ============================================================================
# CLI
# ============================================================================


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="OE Digital 适配器 — P1 行业媒体来源适配器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python crawler/adapters/oe_digital.py                 # 完整运行
  python crawler/adapters/oe_digital.py --test          # 自测
  python crawler/adapters/oe_digital.py --dry-run       # 仅采集，不写入数据库
  python crawler/adapters/oe_digital.py --local-only    # 仅本地保存
        """,
    )
    parser.add_argument("--test", action="store_true",
                        help="自测: 访问页面 → 解析文章 → 输出摘要。")
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
    except Exception as e:
        log.error("Adapter failed: %s", e, exc_info=True)
        sys.exit(1)

    if result.get("error"):
        log.warning("Adapter completed with warning: %s", result["error"])
        sys.exit(1)


if __name__ == "__main__":
    main()
