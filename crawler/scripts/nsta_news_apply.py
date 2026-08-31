#!/usr/bin/env python3
"""
Apply high-value NSTA news links found by research agents.

Reads /tmp/links_nsta_1.json + /tmp/links_nsta_2.json (arrays of
{id, url, title, domain}), independently re-verifies each URL with HTTP 200
(curl GET), backs up, then PATCHes projects.source_url (overwriting the
bulk XLSX dataset URL for rows with a verified news link).

Usage: python3 crawler/scripts/nsta_news_apply.py [--apply]
"""
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

from supabase import create_client

APPLY = '--apply' in sys.argv
URL = os.environ['VITE_SUPABASE_URL'] + '/rest/v1/'
KEY = os.environ['VITE_SUPABASE_ANON_KEY']
HEADERS = {'apikey': KEY, 'Authorization': f'Bearer {KEY}',
           'Content-Type': 'application/json', 'Prefer': 'return=minimal'}
sb = create_client(os.environ['VITE_SUPABASE_URL'], os.environ['VITE_SUPABASE_ANON_KEY'])


def load():
    entries = []
    for p in ('/tmp/links_nsta_1.json', '/tmp/links_nsta_2.json'):
        if os.path.exists(p):
            for e in json.load(open(p)):
                if e.get('url'):
                    entries.append(e)
    # dedupe by id, keep last
    by_id = {}
    for e in entries:
        by_id[e['id']] = e
    return list(by_id.values())


def verify(u):
    try:
        r = subprocess.run(
            ['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}', '-L', '--max-time', '25',
             '-A', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36', u],
            capture_output=True, text=True, timeout=35)
        return r.stdout.strip()
    except Exception as e:
        return f'ERR {e}'


def main():
    entries = load()
    print(f'candidate links: {len(entries)}')

    with ThreadPoolExecutor(max_workers=6) as ex:
        codes = list(ex.map(lambda e: (e, verify(e['url'])), entries))
    good = [e for e, c in codes if c == '200']
    bad = [(e, c) for e, c in codes if c != '200']
    print(f'verified 200: {len(good)}  dropped: {len(bad)}')
    for e, c in bad:
        print('  BAD', c, e['id'], e['url'][:90])

    # fetch current source_url for these ids to back up
    ids = [e['id'] for e in good]
    rows = []
    for i in range(0, len(ids), 200):
        chunk = ids[i:i + 200]
        r = (sb.table('projects').select('id,name,source_url')
             .in_('id', chunk).execute())
        rows.extend(r.data)
    rowmap = {r['id']: r for r in rows}
    changes = []
    for e in good:
        cur = rowmap.get(e['id'])
        if not cur:
            print('  MISSING DB ROW', e['id'])
            continue
        if cur['source_url'] == e['url']:
            continue
        changes.append({'id': e['id'], 'name': cur['name'], 'old': cur['source_url'], 'new': e['url']})
    print(f'changes to apply: {len(changes)}')
    backup = {'changes': changes, 'dropped': [{'id': e['id'], 'url': e['url'], 'code': c} for e, c in bad]}
    json.dump(backup, open(os.path.join(os.path.dirname(__file__), 'nsta_news_backup.json'), 'w'),
              ensure_ascii=False, indent=1)

    if not APPLY:
        print('DRY RUN. sample:')
        for c in changes[:10]:
            print(f"  #{c['id']} {c['name'][:45]} -> {c['new'][:90]}")
        return

    def patch_one(c):
        payload = json.dumps({'source_url': c['new']})
        for attempt in range(5):
            try:
                r = httpx.patch(f"{URL}projects?id=eq.{c['id']}", headers=HEADERS, content=payload, timeout=30)
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

    ok = fail = 0
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(patch_one, c): c for c in changes}
        for fut in as_completed(futs):
            if fut.result() == 'ok':
                ok += 1
            else:
                fail += 1
                print('fail:', futs[fut]['id'], fut.result())
    print(f'DONE ok={ok} fail={fail}')


if __name__ == '__main__':
    main()
