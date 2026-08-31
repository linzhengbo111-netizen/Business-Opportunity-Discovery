#!/usr/bin/env python3
"""Idempotent applier for link_fix_backup.json — PATCH each row with retries."""
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

URL = os.environ['VITE_SUPABASE_URL'] + '/rest/v1/'
KEY = os.environ['VITE_SUPABASE_ANON_KEY']
HEADERS = {'apikey': KEY, 'Authorization': f'Bearer {KEY}',
           'Content-Type': 'application/json',
           'Prefer': 'return=minimal'}

changes = json.load(open(os.path.join(os.path.dirname(__file__), 'link_fix_backup.json')))
print(f'changes to apply: {len(changes)}')

errors = []


def patch_one(ch):
    table, rid, _old, new = ch
    url = f'{URL}{table}?id=eq.{rid}'
    payload = json.dumps({'source_url': new})
    for attempt in range(5):
        try:
            r = httpx.patch(url, headers=HEADERS, content=payload, timeout=30)
            if r.status_code in (204, 200):
                return 'ok'
            if r.status_code in (429, 500, 502, 503):
                time.sleep(1.5 * (attempt + 1))
                continue
            return f'HTTP {r.status_code}: {r.text[:120]}'
        except Exception as e:
            if attempt < 4:
                time.sleep(1.5 * (attempt + 1))
                continue
            return f'ERR {e}'
    return 'ERR retries exhausted'


ok = fail = 0
with ThreadPoolExecutor(max_workers=4) as ex:
    futs = {ex.submit(patch_one, ch): i for i, ch in enumerate(changes)}
    for i, fut in enumerate(as_completed(futs), 1):
        res = fut.result()
        if res == 'ok':
            ok += 1
        else:
            fail += 1
            errors.append((changes[futs[fut]][0], changes[futs[fut]][1], res))
        if i % 500 == 0:
            print(f'progress {i}/{len(changes)} ok={ok} fail={fail}')

print(f'DONE ok={ok} fail={fail}')
if errors:
    print('first errors:')
    for e in errors[:10]:
        print(' ', e)
