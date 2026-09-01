#!/usr/bin/env python3
"""
Align source_name with the actual source of source_url.

Rows whose source_url host clearly names a different publisher than
source_name get source_name rewritten from the host:

  - 3 pinned FPSO:      Petrobras Agencia / MODEC / OE Digital
  - 10 previously-linked projects (Belinda, Payara, Victory, Tartaruga Verde,
    Hammerhead, Uaru, Whiptail, Yellowtail, Liza 1, Liza 2) + other obvious
    mismatches in projects and candidate_events.

Every changed row is backed up to source_name_fix_backup.json before update.

Usage: python3 crawler/scripts/source_name_fix.py [--apply]
"""
import os
import re
import sys
import json
import argparse
from urllib.parse import urlparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

from supabase import create_client

sb = create_client(os.environ['VITE_SUPABASE_URL'], os.environ['VITE_SUPABASE_ANON_KEY'])

# host substring -> source_name
HOST_NAMES = [
    ('agencia.petrobras.com.br', 'Petrobras Agencia'),
    ('modec.com', 'MODEC'),
    ('oedigital.com', 'OE Digital'),
    ('offshore-mag.com', 'Offshore Magazine'),
    ('ogj.com', 'Oil & Gas Journal'),
    ('rigzone.com', 'Rigzone'),
    ('offshore-energy.biz', 'Offshore Energy'),
    ('worldoil.com', 'World Oil'),
    ('oilfieldtechnology.com', 'Oilfield Technology'),
    ('equinor.com', 'Equinor'),
    ('hydrocarbonprocessing.com', 'Hydrocarbon Processing'),
    ('petroleum.gov.gy', 'Guyana EPA Oil & Gas Documents'),
    ('marketscreener.com', 'MarketScreener'),
]

# source_name spellings that already mean the same host; never "fix" these.
ALIASES = {
    'offshore-mag.com': ('offshore magazine', 'offshore mag', 'offshore'),
    'oedigital.com': ('oedigital', 'oe digital', 'oe'),
    'marketscreener.com': ('marketscreener',),
}


def host_of(url):
    if not url:
        return ''
    try:
        return (urlparse(url.strip()).hostname or '').lower()
    except Exception:
        return ''


def expected_name(url):
    h = host_of(url)
    for frag, name in HOST_NAMES:
        if frag in h:
            return name
    return ''


def needs_fix(src, url):
    exp = expected_name(url)
    if not exp or not url:
        return ''
    s = (src or '').strip().lower()
    if not s or s == '待补充':
        return ''  # empty name: not a mismatch, leave alone
    if exp.lower() in s:
        return ''
    for frag, aliases in ALIASES.items():
        if frag in host_of(url) and any(a in s for a in aliases):
            return ''
    return exp


def fetch_all(table, cols, page=1000):
    out = []
    start = 0
    while True:
        rows = sb.table(table).select(*cols.split(',')).range(start, start + page - 1).execute().data
        if not rows:
            break
        out.extend(rows)
        if len(rows) < page:
            break
        start += page
    return out


def scan(table, cols, keyfn):
    rows = fetch_all(table, cols)
    changes = []
    for r in rows:
        new = needs_fix(r.get('source_name'), r.get('source_url'))
        if new:
            changes.append({
                'table': table, 'id': r['id'],
                'key': keyfn(r)[:80],
                'old_name': r.get('source_name'), 'new_name': new,
                'url': r.get('source_url'),
            })
    return rows, changes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()

    _, pc = scan('projects', 'id,name,source_name,source_url', lambda r: r.get('name') or '')
    _, cc = scan('candidate_events', 'id,summary,source_name,source_url',
                 lambda r: r.get('summary') or '')
    changes = pc + cc
    print(f'projects changes: {len(pc)}, candidate_events changes: {len(cc)}')
    for c in changes:
        print(f"  [{c['table']}] {c['key']!r} :: {c['old_name']!r} -> {c['new_name']!r}")
        print(f"      {c['url'][:110]}")

    if not args.apply:
        print('\nDry run. Pass --apply to write.')
        return

    if not changes:
        print('Nothing to do.')
        return

    backup_path = os.path.join(os.path.dirname(__file__), 'source_name_fix_backup.json')
    with open(backup_path, 'w') as f:
        json.dump(changes, f, ensure_ascii=False, indent=2)
    print(f'\nBackup: {backup_path} ({len(changes)} rows)')

    for c in changes:
        sb.table(c['table']).update({'source_name': c['new_name']}).eq('id', c['id']).execute()
    print(f'Updated {len(changes)} rows.')


if __name__ == '__main__':
    main()
