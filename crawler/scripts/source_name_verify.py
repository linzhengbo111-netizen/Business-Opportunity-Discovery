#!/usr/bin/env python3
"""Spot-check: 5 random projects — card source_name vs where source_url actually lands.

Also re-checks the 3 pinned FPSO + 10 previously fixed projects.
Prints source_name, URL host, final host after redirects, and HTTP status.

Usage: python3 crawler/scripts/source_name_verify.py
"""
import os
import random
import sys
from urllib.parse import urlparse

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

from supabase import create_client

sb = create_client(os.environ['VITE_SUPABASE_URL'], os.environ['VITE_SUPABASE_ANON_KEY'])

PINNED = ['FPSO ALMIRANTE TAMANDARE', 'FPSO BACALHAU', 'FPSO SEPETIBA']
PREV_FIXED = ['Belinda', 'Payara', 'Victory', 'Tartaruga Verde', 'Hammerhead',
              'Uaru', 'Whiptail', 'Yellowtail', 'Liza Phase 1', 'Liza Phase 2']


def check(row, client):
    name = row.get('name') or row.get('summary', '')[:50]
    src = row.get('source_name') or ''
    url = row.get('source_url') or ''
    if not url:
        return f'{name[:50]:50} | name={src:25} | NO URL'
    try:
        r = client.get(url, follow_redirects=True, timeout=20)
        final = str(r.url)
        status = r.status_code
    except Exception as e:
        final, status = '', f'ERR {type(e).__name__}'
    uhost = (urlparse(url).hostname or '?')
    fhost = (urlparse(final).hostname or '?')
    ok = 'OK ' if status == 200 else f'{status}'
    return f'{name[:50]:50} | {src:25} | {uhost:24} -> {fhost:24} | {ok}'


def main():
    named = []
    for name in PINNED:
        rows = sb.table('projects').select('id,name,source_name,source_url').eq('name', name).execute().data
        named.extend(rows)
    for p in PREV_FIXED:
        rows = sb.table('projects').select('id,name,source_name,source_url').ilike('name', f'%{p}%').execute().data
        named.extend(rows)

    allrows = sb.table('projects').select('id,name,source_name,source_url').not_.is_('source_url', 'null').neq('source_url', '').execute().data
    random.seed(20260901)
    sample = random.sample(allrows, 5)

    with httpx.Client(headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}) as client:
        print('--- pinned + previously fixed ---')
        seen = set()
        for r in named:
            if r['id'] in seen:
                continue
            seen.add(r['id'])
            print(' ', check(r, client))
        print('--- random sample 5 ---')
        for r in sample:
            print(' ', check(r, client))


if __name__ == '__main__':
    main()
