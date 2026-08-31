#!/usr/bin/env python3
"""
Backfill candidate_events.source_url for timeline display:
- NSTA-sourced events: copy the matching project's source_url when the project
  has a verified news article; otherwise set the official dataset XLSX URL.
- Demo-sourced events: copy matching project's source_url; leave empty if none.

Name matching: normalize project_name_raw vs projects.name (exact, then
containment both ways).

Usage: python3 crawler/scripts/candidate_backfill.py [--apply]
"""
import json
import os
import re
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
XLSX = 'https://www.nstauthority.co.uk/media/n5xe0ayq/offshore-field-consents-as-at-march-2026.xlsx'
DEMO = ['Hydrocarbon Processing', 'LNG Prime', 'Chemical Week', 'World Fertilizer',
        'Sugar Online', 'Paper Advance', 'World Nuclear News', 'Pharmaceutical Technology',
        'ThinkGeoEnergy', 'Mining.com', 'Global Water Intelligence']
TARGETS = ['NSTA Field Development Plans'] + DEMO

sb = create_client(os.environ['VITE_SUPABASE_URL'], os.environ['VITE_SUPABASE_ANON_KEY'])


def fetch_all(table, select, source_names):
    rows, start = [], 0
    while True:
        r = (sb.table(table).select(select).in_('source_name', source_names)
             .range(start, start + 999).execute())
        if not r.data:
            break
        rows.extend(r.data)
        if len(r.data) < 999:
            break
        start += 999
    return rows


def norm(s):
    return re.sub(r'[^a-z0-9]+', '', (s or '').lower())


def main():
    candidates = fetch_all('candidate_events', 'id,project_name_raw,source_name,source_url,review_status', TARGETS)
    empty = [c for c in candidates if not (c.get('source_url') or '').strip()]
    print(f'target candidates: {len(candidates)}  empty: {len(empty)}')

    projects = fetch_all('projects', 'id,name,source_url,source_name', TARGETS + ['NSTA Field Development Plans'])
    proj_by_name = {}
    for p in projects:
        key = norm(p['name'])
        if key:
            proj_by_name.setdefault(key, []).append(p)

    changes = []
    unmatched = 0
    for c in empty:
        key = norm(c['project_name_raw'])
        hit = None
        if key in proj_by_name:
            hit = proj_by_name[key][0]
        elif len(key) >= 5:  # containment fallback
            for pk, plist in proj_by_name.items():
                if key in pk or pk in key:
                    hit = plist[0]
                    break
        if hit and (hit.get('source_url') or '').strip():
            new = hit['source_url']
        elif c['source_name'] == 'NSTA Field Development Plans':
            new = XLSX
        else:
            new = None
            unmatched += 1
        if new and new != (c.get('source_url') or ''):
            changes.append({'id': c['id'], 'name': c['project_name_raw'],
                            'source_name': c['source_name'], 'old': c.get('source_url'), 'new': new})
    print(f'changes: {len(changes)}  (demo unmatched left empty: {unmatched})')

    from collections import Counter
    print('by kind:', dict(Counter('xlsx' if c['new'] == XLSX else 'article' for c in changes)))

    backup = {'changes': changes}
    json.dump(backup, open(os.path.join(os.path.dirname(__file__), 'candidate_backfill_backup.json'), 'w'),
              ensure_ascii=False, indent=1)

    if not APPLY:
        print('DRY RUN. sample:')
        for c in changes[:10]:
            print(f"  #{c['id']} {c['name'][:40]} ({c['source_name'][:20]}) -> {c['new'][:80]}")
        return

    def patch_one(c):
        payload = json.dumps({'source_url': c['new']})
        for attempt in range(5):
            try:
                r = httpx.patch(f"{URL}candidate_events?id=eq.{c['id']}", headers=HEADERS, content=payload, timeout=30)
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
        for i, fut in enumerate(as_completed(futs), 1):
            if fut.result() == 'ok':
                ok += 1
            else:
                fail += 1
                print('fail:', futs[fut]['id'], fut.result())
            if i % 500 == 0:
                print(f'progress {i}/{len(changes)} ok={ok} fail={fail}')
    print(f'DONE ok={ok} fail={fail}')


if __name__ == '__main__':
    main()
