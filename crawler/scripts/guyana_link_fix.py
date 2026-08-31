#!/usr/bin/env python3
"""
Guyana EPA strict link fix:
1. Parse local snapshot crawler/data/guyana_epa/2026-08-28_epa_oil_gas.html
2. Extract WPDM /download/ links with filename= param, clean cache params
3. Match DB rows (projects + candidate_events, source_name = Guyana EPA Oil & Gas Documents)
   by File name in summary vs filename param
4. Verify every unique URL returns HTTP 200 (HEAD then GET fallback)
5. Backup + PATCH source_url

Dry run default. Apply with --apply.
Usage: python3 crawler/scripts/guyana_link_fix.py [--apply]
"""
import hashlib
import json
import os
import re
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, parse_qs, unquote

import httpx
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

from supabase import create_client

APPLY = '--apply' in sys.argv
SNAPSHOT = os.path.join(os.path.dirname(__file__), '..', 'data', 'guyana_epa', '2026-08-28_epa_oil_gas.html')
URL = os.environ['VITE_SUPABASE_URL'] + '/rest/v1/'
KEY = os.environ['VITE_SUPABASE_ANON_KEY']
HEADERS = {'apikey': KEY, 'Authorization': f'Bearer {KEY}',
           'Content-Type': 'application/json', 'Prefer': 'return=minimal'}

sb = create_client(os.environ['VITE_SUPABASE_URL'], os.environ['VITE_SUPABASE_ANON_KEY'])


def clean_wpdm_url(url: str) -> str:
    """Strip refresh/ind cache params, keep wpdmdl + filename. Returns '' if no wpdmdl."""
    if not url:
        return ''
    p = urlparse(url)
    qs = parse_qs(p.query)
    keep = {}
    for k in ('wpdmdl', 'filename'):
        if k in qs:
            keep[k] = qs[k][0]
    if 'wpdmdl' not in keep:
        return ''
    base = p._replace(query='&'.join(f'{k}={v}' for k, v in keep.items())).geturl()
    return base


def norm(s: str) -> str:
    s = unquote(s or '')
    s = s.split('.')[0] if s.lower().endswith(('.pdf', '.doc', '.docx', '.xlsx', '.xls')) else s
    return re.sub(r'[^a-z0-9]+', '', s.lower())


def extract_map(snapshot_path):
    html = open(snapshot_path, encoding='utf-8', errors='replace').read()
    soup = BeautifulSoup(html, 'html.parser')
    mapping = {}  # norm(filename) -> (clean_url, raw_filename)
    for a in soup.find_all('a', href=True):
        href = a['href']
        if '/download/' not in href:
            continue
        qs = parse_qs(urlparse(href).query)
        if 'filename' not in qs or 'wpdmdl' not in qs:
            continue
        raw_fn = qs['filename'][0]
        clean = clean_wpdm_url(href)
        if not clean:
            continue
        key = norm(raw_fn)
        if key and key not in mapping:
            mapping[key] = (clean, raw_fn)
    return mapping


def fetch_all(table, select, source_name):
    rows, start = [], 0
    while True:
        r = (sb.table(table).select(select).eq('source_name', source_name)
             .range(start, start + 999).execute())
        if not r.data:
            break
        rows.extend(r.data)
        if len(r.data) < 999:
            break
        start += 999
    return rows


def file_value_of(row):
    """Extract the File: value from summary."""
    s = row.get('summary') or ''
    m = re.search(r'File:\s*(.*?)(?:\||$)', s, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return ''


def match_row(row, mapping):
    fv = file_value_of(row)
    if not fv:
        return None
    key = norm(fv)
    if key in mapping:
        return mapping[key]
    # containment fallback (long filenames may be truncated on either side)
    if len(key) >= 12:
        for mk, (url, raw) in mapping.items():
            if key[:40] == mk[:40] or mk[:40] == key[:40]:
                return (url, raw)
            if key in mk or mk in key:
                return (url, raw)
    return None


def verify(urls):
    """HEAD then GET fallback; returns set of URLs with HTTP 200."""
    ok, bad = set(), {}
    uniq = sorted(set(u for u in urls if u))

    def check(u):
        for method in ('HEAD', 'GET'):
            try:
                r = httpx.request(method, u, follow_redirects=True, timeout=30)
                if r.status_code == 200:
                    return u, True, r.status_code
                if r.status_code in (403, 405) and method == 'HEAD':
                    continue
                return u, False, r.status_code
            except Exception as e:
                if method == 'GET':
                    return u, False, str(e)
                continue
        return u, False, 'no-200'

    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = [ex.submit(check, u) for u in uniq]
        for fut in as_completed(futs):
            u, is_ok, code = fut.result()
            if is_ok:
                ok.add(u)
            else:
                bad[u] = code
    return ok, bad


def main():
    print('parse snapshot:', SNAPSHOT)
    mapping = extract_map(SNAPSHOT)
    print(f'WPDM filename map: {len(mapping)} unique files')

    projects = fetch_all('projects', 'id,name,summary,source_url', 'Guyana EPA Oil & Gas Documents')
    candidates = fetch_all('candidate_events', 'id,project_name_raw,summary,source_url', 'Guyana EPA Oil & Gas Documents')
    candidates = [c for c in candidates if (c.get('review_status') or '') == 'accepted']
    # need review_status in select; refetch with it
    candidates = [c for c in fetch_all('candidate_events', 'id,project_name_raw,summary,source_url,review_status', 'Guyana EPA Oil & Gas Documents')
                  if c.get('review_status') == 'accepted']
    print(f'projects total={len(projects)}  candidates accepted={len(candidates)}')

    changes, unmatched_p, unmatched_c = [], [], []
    for row in projects:
        m = match_row(row, mapping)
        if m and not (row.get('source_url') or '').strip():
            changes.append({'table': 'projects', 'id': row['id'], 'name': row['name'],
                            'old': row.get('source_url'), 'new': m[0], 'filename': m[1]})
        elif not (row.get('source_url') or '').strip():
            unmatched_p.append({'id': row['id'], 'name': row['name'], 'file': file_value_of(row)})
    for row in candidates:
        m = match_row(row, mapping)
        if m and not (row.get('source_url') or '').strip():
            changes.append({'table': 'candidate_events', 'id': row['id'], 'name': row['project_name_raw'],
                            'old': row.get('source_url'), 'new': m[0], 'filename': m[1]})
        elif not (row.get('source_url') or '').strip():
            unmatched_c.append({'id': row['id'], 'name': row['project_name_raw'], 'file': file_value_of(row)})

    print(f'matched changes: {len(changes)}  (projects unmatched: {len(unmatched_p)}, candidates unmatched: {len(unmatched_c)})')

    # verify all unique URLs
    ok, bad = verify([c['new'] for c in changes])
    print(f'urls verified 200: {len(ok)} / {len(set(c["new"] for c in changes))}')
    if bad:
        print('bad sample:', list(bad.items())[:5])

    valid = [c for c in changes if c['new'] in ok]
    skipped = [c for c in changes if c['new'] not in ok]
    print(f'changes after verify: {len(valid)}  (dropped {len(skipped)})')

    # backup
    backup = {'generated': time.strftime('%Y-%m-%dT%H:%M:%SZ'),
              'changes': [(c['table'], c['id'], c['old'], c['new']) for c in valid],
              'unmatched_projects': unmatched_p, 'unmatched_candidates': unmatched_c,
              'dropped_bad_urls': skipped}
    bpath = os.path.join(os.path.dirname(__file__), 'guyana_link_fix_backup.json')
    with open(bpath, 'w') as f:
        json.dump(backup, f, indent=1, ensure_ascii=False)
    print('backup written:', bpath)

    if not APPLY:
        print('DRY RUN — no writes. Re-run with --apply to PATCH.')
        print('sample changes:')
        for c in valid[:8]:
            print(f"  {c['table']}#{c['id']} {c['name'][:45]} -> {c['new'][:100]}")
        return

    okn = failn = 0
    errors = []

    def patch_one(c):
        url = f"{URL}{c['table']}?id=eq.{c['id']}"
        payload = json.dumps({'source_url': c['new']})
        for attempt in range(5):
            try:
                r = httpx.patch(url, headers=HEADERS, content=payload, timeout=30)
                if r.status_code in (204, 200):
                    return 'ok'
                if r.status_code in (429, 500, 502, 503):
                    time.sleep(1.5 * (attempt + 1))
                    continue
                return f'HTTP {r.status_code}'
            except Exception as e:
                if attempt < 4:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                return f'ERR {e}'
        return 'ERR retries'

    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(patch_one, c): c for c in valid}
        for i, fut in enumerate(as_completed(futs), 1):
            res = fut.result()
            c = futs[fut]
            if res == 'ok':
                okn += 1
            else:
                failn += 1
                errors.append((c['table'], c['id'], res))
            if i % 100 == 0:
                print(f'progress {i}/{len(valid)} ok={okn} fail={failn}')
    print(f'DONE ok={okn} fail={failn}')
    if errors:
        print('first errors:')
        for e in errors[:10]:
            print(' ', e)


if __name__ == '__main__':
    main()
