#!/usr/bin/env python3
"""
Sample-test source_urls: HTTP status + page-type classification.
Also dumps the 3 pinned FPSO projects' URLs.
Usage: python3 crawler/scripts/link_sample_test.py
"""
import os
import re
import sys
import json
import random
from urllib.parse import urlparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

import requests
from supabase import create_client

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/pdf,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

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

def classify(url, status, final_url, ctype):
    """Page type: article / list / search / pdf / home / other"""
    if not url:
        return 'EMPTY'
    path = urlparse(final_url or url).path.lower()
    if ctype and 'pdf' in ctype:
        return 'PDF'
    if status == 404:
        return '404'
    if status in (301, 302, 303, 307, 308) and final_url and final_url != url:
        # redirected: classify the target, note redirect
        return 'REDIR'
    u = final_url.lower() if final_url else url.lower()
    if re.search(r'(/search|/busca|/pesquisa|\?s=|\?q=|\?query=|search\?|/find|/results)', u):
        return 'SEARCH'
    if re.search(r'(/category/|/tag/|/topics?/|\?page=|/page/\d)', u):
        return 'LIST'
    if path in ('', '/', '/index.html', '/index.php'):
        return 'HOME'
    if re.search(r'(/news/|/articles/|/article/|/story|/blog/|/\d{4}/\d{2}/|/newsroom|/press)', u):
        return 'ARTICLE?'
    return 'OTHER'

def check(url):
    if not url:
        return {'url': url, 'status': None, 'type': 'EMPTY', 'final': None, 'ctype': None}
    try:
        r = requests.get(url, headers=HEADERS, timeout=20, allow_redirects=True, stream=True)
        ctype = r.headers.get('content-type', '')
        # peek some body for relevance check
        body = ''
        if 'text/html' in ctype:
            body = r.raw.read(60000, decode_content=True).decode('utf-8', errors='ignore')
        r.close()
        return {'url': url, 'status': r.status_code, 'final': r.url, 'ctype': ctype, 'body': body}
    except requests.exceptions.SSLError:
        return {'url': url, 'status': 'SSL_ERR', 'type': 'SSL_ERR', 'final': None, 'ctype': None}
    except requests.exceptions.ConnectionError as e:
        return {'url': url, 'status': 'CONN_ERR', 'type': 'CONN_ERR', 'final': None, 'ctype': None, 'err': str(e)[:200]}
    except Exception as e:
        return {'url': url, 'status': 'ERR', 'type': 'ERR', 'final': None, 'ctype': None, 'err': str(e)[:200]}

# ---- 3 pinned FPSO projects ----
print('=' * 70)
print('PINNED FPSO PROJECTS (置顶项目)')
print('=' * 70)
pinned_names = ['FPSO ALMIRANTE TAMANDARE', 'FPSO BACALHAU', 'FPSO SEPETIBA']
for nm in pinned_names:
    r = sb.table('projects').select('id,name,source_url,source_name,summary,phase').ilike('name', f'%{nm.split()[1]}%').execute()
    # try exact-ish match
    rows = [x for x in r.data if nm.split()[1].lower() in (x.get('name') or '').lower()]
    if not rows:
        r2 = sb.table('projects').select('id,name,source_url,source_name,summary,phase').execute()
        rows = [x for x in r2.data if nm.lower() in (x.get('name') or '').lower()]
    for x in rows[:3]:
        print(f"  {x.get('name')!r} phase={x.get('phase')}")
        print(f"    url={x.get('source_url')}")
        print(f"    source={x.get('source_name')}")

# ---- sample 20 ----
print('\n' + '=' * 70)
print('SAMPLE 20 source_urls')
print('=' * 70)
random.seed(42)
projs = fetch_all('projects', 'id,name,source_url,source_name,summary')
cands = fetch_all('candidate_events', 'id,project_name_raw,source_url,source_name,summary')
pool = [{'table': 'projects', 'id': p['id'], 'name': p.get('name'),
         'url': p['source_url'], 'source': p.get('source_name'), 'summary': (p.get('summary') or '')[:400]}
        for p in projs if p['source_url']]
pool += [{'table': 'candidate_events', 'id': c['id'], 'name': c.get('project_name_raw'),
          'url': c['source_url'], 'source': c.get('source_name'), 'summary': (c.get('summary') or '')[:400]}
         for c in cands if c['source_url']]

# stratified: 20 across domains
doms = {}
for p in pool:
    doms.setdefault(urlparse(p['url']).netloc.lower(), []).append(p)
sample = []
for d, items in sorted(doms.items(), key=lambda kv: -len(kv[1])):
    sample.append(random.choice(items))
    if len(sample) >= 20:
        break
print(f'sampled {len(sample)} rows across {len(doms)} domains')

results = []
for p in sample:
    res = check(p['url'])
    t = classify(p['url'], res['status'], res['final'], res['ctype'])
    body = res.get('body') or ''
    # crude relevance: does page text mention project keywords?
    kw = (p['name'] or '').split()[:2]
    kw_hit = any(k.lower()[:6] in body.lower() for k in kw if len(k) > 4)
    line = f"[{p['table']}] {t:9s} st={res['status']} kw_hit={kw_hit} {p['name'][:45]!r}"
    if t == 'REDIR':
        line += f"\n    -> {res['final']}"
    line += f"\n    {p['url']}"
    print(line)
    results.append({**p, 'status': res['status'], 'type': t, 'final': res['final'],
                    'ctype': res['ctype'], 'kw_hit': kw_hit})

with open(os.path.join(os.path.dirname(__file__), 'sample_test_results.json'), 'w') as f:
    json.dump(results, f, ensure_ascii=False, indent=1)
