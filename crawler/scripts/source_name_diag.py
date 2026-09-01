#!/usr/bin/env python3
"""Diagnose source_name vs source_url mismatches across projects + candidate_events.

Prints rows where the source_url host clearly doesn't match source_name, plus
the current state of the 13 named projects (3 pinned FPSO + 10 previously fixed).

Usage: python3 crawler/scripts/source_name_diag.py
"""
import os
import sys
from urllib.parse import urlparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

from supabase import create_client

sb = create_client(os.environ['VITE_SUPABASE_URL'], os.environ['VITE_SUPABASE_ANON_KEY'])

PINNED = ['FPSO ALMIRANTE TAMANDARE', 'FPSO BACALHAU', 'FPSO SEPETIBA']
PREV_FIXED = ['Belinda', 'Payara', 'Victory', 'Tartaruga Verde', 'Hammerhead',
              'Uaru', 'Whiptail', 'Yellowtail', 'Liza 1', 'Liza 2']

# host substring -> expected source_name fragment
HOST_HINTS = {
    'agencia.petrobras.com.br': 'Petrobras Agencia',
    'petrobras.com.br': 'Petrobras',
    'modec.com': 'MODEC',
    'oedigital.com': 'OE Digital',
    'offshore-energy.biz': 'Offshore Energy',
    'sbmoffshore.com': 'SBM Offshore',
    'splash247.com': 'Splash',
    'oilfieldtechnology.com': 'Oilfield Technology',
    'worldoil.com': 'World Oil',
    'equinor.com': 'Equinor',
    'petroleum.gov.gy': 'Guyana EPA',
    'marketscreener.com': 'MarketScreener',
    'hydrocarbonprocessing.com': 'Hydrocarbon Processing',
    'lngprime.com': 'LNG Prime',
    'chemweek.com': 'Chemweek',
    'worldfertilizer.com': 'World Fertilizer',
    'world-nuclear-news.org': 'World Nuclear News',
    'mining.com': 'Mining.com',
    'thinkgeoenergy.com': 'ThinkGeoEnergy',
    'globalwaterintel.com': 'Global Water Intelligence',
    'pharmaceutical-technology.com': 'Pharmaceutical Technology',
    'paperadvance.com': 'Paper Advance',
    'sugar-online.com': 'Sugar Online',
    'gpb.gov.by': 'Belarusian Universal Commodity Exchange',
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
    for frag, name in HOST_HINTS.items():
        if frag in h:
            return name
    return ''


def row_key(r):
    return r.get('name') or r.get('summary', '')[:60]


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


def scan(table, cols):
    rows = fetch_all(table, cols)
    print(f'== {table}: {len(rows)} rows ==')
    named = []
    mism = []
    for r in rows:
        key = (r.get('name') or r.get('summary') or '').strip()
        src = (r.get('source_name') or '').strip()
        url = r.get('source_url') or ''
        exp = expected_name(url)
        if table == 'projects':
            if key in PINNED or any(
                    p.lower() in key.lower() for p in PREV_FIXED):
                named.append(r)
            elif exp and src and exp.lower() not in src.lower():
                mism.append((row_key(r), src, url, exp))
        else:
            # candidate_events: mismatches only, skip noise summaries
            if (exp and url and src and src != '待补充'
                    and exp.lower() not in src.lower()
                    and not key.startswith('[CHANGED]')
                    and not key.startswith('Category:')):
                mism.append((row_key(r), src, url, exp))
    if named:
        print('--- named (pinned + previously fixed) ---')
        for r in named:
            print(f"  {(r.get('name') or r.get('summary', '')[:40])!r} | source_name={r.get('source_name')!r} | url={r.get('source_url')!r} | host={host_of(r.get('source_url') or '')}")
    print(f'--- mismatches: {len(mism)} ---')
    for k, src, url, exp in mism:
        print(f"  {k[:60]!r} | name={src!r} | host={host_of(url)} | expect~{exp!r} | {url[:100]}")
    return rows


def main():
    pcols = 'id,name,source_name,source_url'
    scan('projects', pcols)
    print()
    scan('candidate_events', 'id,summary,source_name,source_url')


if __name__ == '__main__':
    main()
