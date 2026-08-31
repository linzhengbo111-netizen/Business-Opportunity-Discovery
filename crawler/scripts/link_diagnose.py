#!/usr/bin/env python3
"""
Link quality diagnosis: fetch all source_urls from projects + candidate_events,
bucket by domain, classify page type, dump JSON for sampling.
Usage: python3 crawler/scripts/link_diagnose.py
"""
import os
import re
import sys
import json
from collections import Counter
from urllib.parse import urlparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

from supabase import create_client

sb = create_client(os.environ['VITE_SUPABASE_URL'], os.environ['VITE_SUPABASE_ANON_KEY'])

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

projects = fetch_all('projects', 'id,name,source_url,source_name,summary,recommendation_json,phase,country')
candidates = fetch_all('candidate_events', 'id,project_name_raw,source_url,source_name,summary,evidence_quote,event_type')

def domain_of(url):
    if not url:
        return '(empty)'
    try:
        host = urlparse(url.strip()).netloc.lower()
        host = re.sub(r'^www\.', '', host)
        return host or '(invalid)'
    except Exception:
        return '(invalid)'

def is_likely_generic(url):
    """Heuristic: search/list/home page, not a specific article."""
    if not url:
        return True
    u = url.strip().lower()
    path = urlparse(u).path.lower()
    # search pages
    if re.search(r'(/search|/busca|/pesquisa|\?s=|\?q=|\?query=|search\?|/find|/results)', u):
        return True
    # list / category / tag pages
    if re.search(r'(/category/|/tag/|/topics?/|/news/?(#|$)|\?page=)', u):
        return True
    # bare homepage
    if path in ('', '/', '/index.html', '/index.php'):
        return True
    # PDF
    if path.endswith('.pdf'):
        return False  # pdf is specific, flag separately
    return False

# ---- domain distribution ----
p_urls = [(p['source_url'], 'projects', p.get('name'), p['id']) for p in projects]
c_urls = [(c['source_url'], 'candidate_events', c.get('project_name_raw'), c['id']) for c in candidates]

print('=' * 70)
print('DOMAIN DISTRIBUTION')
print('=' * 70)
for label, rows in [('projects', p_urls), ('candidate_events', c_urls)]:
    doms = Counter(domain_of(u) for u, _, _, _ in rows)
    print(f'\n[{label}] total rows={len(rows)}, domains={len(doms)}')
    for d, n in doms.most_common():
        print(f'  {n:5d}  {d}')

# ---- generic-link heuristic ----
print('\n' + '=' * 70)
print('GENERIC-LINK HEURISTIC (search/list/home)')
print('=' * 70)
for label, rows in [('projects', p_urls), ('candidate_events', c_urls)]:
    gen = [r for r in rows if is_likely_generic(r[0])]
    empty = [r for r in rows if not r[0]]
    pdf = [r for r in rows if r[0] and urlparse(r[0].strip()).path.lower().endswith('.pdf')]
    print(f'[{label}] total={len(rows)} generic={len(gen)} empty={len(empty)} pdf={len(pdf)}')
    for r in gen[:15]:
        print(f'  GENERIC {r[2][:50]!r}: {r[0]}')

# ---- dump for sampling ----
dump = {
    'projects': [
        {'id': p['id'], 'name': p.get('name'), 'source_url': p['source_url'],
         'source_name': p.get('source_name'), 'summary': (p.get('summary') or '')[:800],
         'recommendation_json': (p.get('recommendation_json') or '')[:1500],
         'phase': p.get('phase'), 'country': p.get('country')}
        for p in projects
    ],
    'candidate_events': [
        {'id': c['id'], 'name': c.get('project_name_raw'), 'source_url': c['source_url'],
         'source_name': c.get('source_name'), 'summary': (c.get('summary') or '')[:800],
         'evidence_quote': (c.get('evidence_quote') or '')[:800], 'event_type': c.get('event_type')}
        for c in candidates
    ],
}
out = os.path.join(os.path.dirname(__file__), 'link_dump.json')
with open(out, 'w') as f:
    json.dump(dump, f, ensure_ascii=False, indent=1)
print(f'\nDump written: {out}')
print(f"projects={len(dump['projects'])} candidate_events={len(dump['candidate_events'])}")
