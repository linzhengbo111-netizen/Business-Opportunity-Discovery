#!/usr/bin/env python3
"""
Fix non-specific source_urls.

Rules:
  - Specific article/file URLs: keep.
  - Generic (homepage / list / search / portal) URLs:
      * projects: promote a specific article URL from linked candidate_events
        (canonical_project_id or name match), else clear (待补充).
      * candidate_events: extract specific URL from own summary/evidence_quote,
        else clear (待补充).
  - Pinned FPSO projects get curated official news articles.

Backup of every changed row is written to link_fix_backup.json before updating.

Usage: python3 crawler/scripts/link_fix.py --dry-run | --apply
"""
import os
import re
import sys
import json
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

from supabase import create_client

sb = create_client(os.environ['VITE_SUPABASE_URL'], os.environ['VITE_SUPABASE_ANON_KEY'])

URLRE = re.compile(r'https?://[^\s\'"<>)\]，。；、]+')

# Curated replacements for the 3 pinned FPSO projects.
PINNED_OVERRIDES = {
    'FPSO ALMIRANTE TAMANDARE': 'https://agencia.petrobras.com.br/en/w/negocio/fpso-almirante-tamandare-inicia-producao-no-pre-sal',
    'FPSO BACALHAU': 'https://www.modec.com/news/2025/20251016_pr_Bacalhau.html',
    'FPSO SEPETIBA': 'https://www.oedigital.com/news/473742-sbm-offshore-inks-fpso-sepetiba-contracts',
}

# Hosts whose news articles rank highest when promoting to projects.
NEWS_HOST_RANK = {
    'agencia.petrobras.com.br': 0, 'offshore-energy.biz': 1, 'splash247.com': 2,
    'oedigital.com': 3, 'oilfieldtechnology.com': 4, 'worldoil.com': 5,
    'modec.com': 6, 'sbmoffshore.com': 7, 'equinor.com': 8,
    'marketscreener.com': 9, 'hydrocarbonprocessing.com': 10, 'lngprime.com': 11,
    'chemweek.com': 12, 'worldfertilizer.com': 13, 'world-nuclear-news.org': 14,
    'paperadvance.com': 15, 'sugar-online.com': 16,
    'pharmaceutical-technology.com': 17, 'globalwaterintel.com': 18,
    'thinkgeoenergy.com': 19, 'mining.com': 20, 'petroleum.gov.gy': 21,
}

FILE_EXTS = ('.pdf', '.doc', '.docx', '.xls', '.xlsx', '.csv', '.zip')


def is_specific_file(url):
    p = urlparse(url).path.lower()
    return p.endswith(FILE_EXTS) or '@@download/file' in url


def is_generic(url):
    """Homepage / list / search / portal page — not a specific article."""
    if not url:
        return True
    u = urlparse(url.strip())
    p = u.path.lower()
    q = u.query.lower()
    if p in ('', '/', '/index.html', '/index.php', '/index.htm'):
        return True
    if re.search(r'(/search|/busca|/pesquisa|/find|/results)', p) or re.search(r'(\?s=|\?q=|\?query=|search\?)', q):
        return True
    if re.search(r'(/category/|/tag/|/topics?/|\?page=)', u.geturl().lower()):
        return True
    if '/download-category/' in p:
        return True
    if '/data-and-insights/data/themes/' in p:
        return True
    if 'planos-de-desenvolvimento' in p and '@@download' not in url:
        return True
    if p.rstrip('/').endswith('/projects-initiatives'):
        return True
    if p.startswith('/business/'):
        return True
    if '/key-information-for-suppliers' in p:
        return True
    if 'cadastro-de-fornecedores' in p or 'supplier' in urlparse(url).netloc:
        return True
    return False


def fetch_all(table, select):
    rows, start = [], 0
    while True:
        r = sb.table(table).select(select).range(start, start + 999).execute()
        if not r.data:
            break
        rows.extend(r.data)
        if len(r.data) < 999:
            break
        start += 999
    return rows


def norm_name(n):
    return re.sub(r'[^a-z0-9]+', ' ', (n or '').lower()).strip()


def best_news_url(urls):
    """Pick the best article URL from a candidate list.

    Only hosts with rank <= 20 (real news/media sites) qualify for promotion —
    registry/portal hosts (gov.br, epaguyana, petroleum.gov.gy, nstauthority)
    never get promoted onto a project."""
    cands = [u for u in urls if u and not is_generic(u)]
    cands = [u for u in cands
             if NEWS_HOST_RANK.get(urlparse(u).netloc.lower().replace('www.', ''), 50) <= 20]
    if not cands:
        return None
    cands = sorted(set(cands), key=lambda u: (
        is_specific_file(u),  # html article beats pdf
        NEWS_HOST_RANK.get(urlparse(u).netloc.lower().replace('www.', ''), 50),
        len(u),
    ))
    return cands[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()
    if not args.dry_run and not args.apply:
        ap.error('need --dry-run or --apply')

    projects = fetch_all('projects', 'id,name,source_url')
    candidates = fetch_all('candidate_events',
                           'id,project_name_raw,canonical_project_id,source_url,summary,evidence_quote')

    # candidate article index by canonical id and by normalized name
    by_canon, by_name = {}, {}
    for c in candidates:
        u = (c['source_url'] or '').strip()
        if not u or is_generic(u):
            continue
        cid = c.get('canonical_project_id')
        if cid:
            by_canon.setdefault(cid, []).append(u)
        nm = norm_name(c.get('project_name_raw'))
        if nm:
            by_name.setdefault(nm, []).append(u)

    changes = []  # (table, id, old, new)

    # ---- projects ----
    for p in projects:
        old = (p['source_url'] or '').strip()
        name = p.get('name') or ''
        new = old
        if name.upper() in PINNED_OVERRIDES:
            new = PINNED_OVERRIDES[name.upper()]
        elif is_generic(old):
            # canonical id match only on significant words (len >= 7) to avoid
            # false joins like PIPER-BRAVO <-> brazil-bravo
            words = [w for w in norm_name(name).split() if len(w) >= 7]
            pool = []
            for cid, urls in by_canon.items():
                if any(w in cid for w in words):
                    pool += urls
            best = best_news_url(pool)
            new = best or ''
        if new != old:
            changes.append(('projects', p['id'], old, new))

    # ---- candidate_events ----
    for c in candidates:
        old = (c['source_url'] or '').strip()
        if not is_generic(old):
            continue
        text = ' '.join(x for x in [c.get('summary'), c.get('evidence_quote')] if x)
        found = [u.rstrip('.,;') for u in URLRE.findall(text or '')]
        best = best_news_url(found)
        new = best or ''
        if new != old:
            changes.append(('candidate_events', c['id'], old, new))

    # report
    print(f'projects: {len(projects)} scanned, {sum(1 for x in changes if x[0]=="projects")} changed')
    print(f'candidate_events: {len(candidates)} scanned, {sum(1 for x in changes if x[0]=="candidate_events")} changed')
    proj_fixed = [x for x in changes if x[0] == 'projects' and x[3]]
    proj_blanked = [x for x in changes if x[0] == 'projects' and not x[3]]
    cand_fixed = [x for x in changes if x[0] == 'candidate_events' and x[3]]
    cand_blanked = [x for x in changes if x[0] == 'candidate_events' and not x[3]]
    print(f'  projects: {len(proj_fixed)} promoted URL, {len(proj_blanked)} blanked (待补充)')
    print(f'  candidates: {len(cand_fixed)} extracted URL, {len(cand_blanked)} blanked (待补充)')

    for x in proj_fixed[:10]:
        print(f'  PROMOTE {x[2][:60]} -> {x[3][:80]}')
    for x in proj_blanked[:10]:
        print(f'  BLANK  {x[2][:80]}')

    out = os.path.join(os.path.dirname(__file__), 'link_fix_backup.json')
    with open(out, 'w') as f:
        json.dump(changes, f, ensure_ascii=False, indent=1)
    print(f'backup: {out}')

    if args.apply and changes:
        def do_update(ch):
            table, rid, _old, new = ch
            sb.table(table).update({'source_url': new}).eq('id', rid).execute()
            return True

        ok = 0
        with ThreadPoolExecutor(max_workers=8) as ex:
            futs = [ex.submit(do_update, ch) for ch in changes]
            for fut in as_completed(futs):
                if fut.result():
                    ok += 1
        print(f'APPLIED: {ok} rows updated')
    elif args.apply:
        print('APPLIED: nothing to change')


if __name__ == '__main__':
    main()
