#!/usr/bin/env python3
"""
Diagnosis for LINK_FIX_PLAN.md: count empty/NULL source_url by source_name in
projects and candidate_events; sample domains nstauthority.co.uk / epaguyana.org;
list demo-news-source empties. Read-only, writes crawler/scripts/link_plan_diag.json.

Usage: python3 crawler/scripts/link_plan_diagnose.py
"""
import os
import re
import sys
import json
from collections import Counter, defaultdict
from urllib.parse import urlparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

from supabase import create_client

sb = create_client(os.environ['VITE_SUPABASE_URL'], os.environ['VITE_SUPABASE_ANON_KEY'])

FILE_EXTS = ('.pdf', '.doc', '.docx', '.xls', '.xlsx', '.csv', '.zip')


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


def classify(url):
    """valid_article / data_file / bad_generic / empty / invalid"""
    if not url or not url.strip():
        return 'empty'
    u = url.strip()
    if not u.startswith(('http://', 'https://')):
        return 'invalid'
    p = urlparse(u).path.lower()
    if p.endswith(FILE_EXTS) or '@@download/file' in u:
        return 'data_file'
    if re.search(r'(/search|/category/|/tag/|\?s=|\?q=)', u.lower()):
        return 'bad_generic'
    return 'valid_article'


def domain_of(url):
    if not url or not url.strip():
        return '(empty)'
    try:
        host = urlparse(url.strip()).netloc.lower()
        host = re.sub(r'^www\.', '', host)
        return host or '(invalid)'
    except Exception:
        return '(invalid)'


projects = fetch_all('projects', 'id,name,source_url,source_name,industry,country,phase')
candidates = fetch_all('candidate_events', 'id,project_name_raw,source_url,source_name,review_status')

out = {'projects': [], 'candidate_events': []}

# ---- projects: empty by source_name ----
p_empty = Counter()
p_total = Counter()
p_cls = Counter()
p_by_source = defaultdict(list)
for r in projects:
    sn = r.get('source_name') or '(null)'
    p_total[sn] += 1
    c = classify(r.get('source_url'))
    p_cls[c] += 1
    if c == 'empty':
        p_empty[sn] += 1
        p_by_source[sn].append({'id': r['id'], 'name': r['name'], 'industry': r.get('industry'), 'country': r.get('country')})

out['projects'].append({
    'total_rows': len(projects),
    'class_counts': dict(p_cls),
    'empty_by_source_name': dict(p_empty.most_common()),
    'total_by_source_name': dict(p_total.most_common()),
    'empty_details': {k: v for k, v in p_by_source.items()},
})

# ---- candidates: empty by source ----
c_empty = Counter()
c_total = Counter()
c_cls = Counter()
for r in candidates:
    sn = r.get('source_name') or '(null)'
    c_total[sn] += 1
    cls = classify(r.get('source_url'))
    c_cls[cls] += 1
    if cls == 'empty':
        c_empty[sn] += 1

out['candidate_events'].append({
    'total_rows': len(candidates),
    'class_counts': dict(c_cls),
    'empty_by_source_name': dict(c_empty.most_common()),
    'total_by_source_name': dict(c_total.most_common()),
})

# ---- domain samples: NSTA / Guyana EPA / demo news ----
def sample_urls(rows, domains, limit=8):
    res = defaultdict(list)
    for r in rows:
        d = domain_of(r.get('source_url'))
        for dom in domains:
            if d == dom or dom in d:
                res[dom].append({'id': r['id'], 'name': r.get('name') or r.get('project_name_raw'),
                                 'source_url': r.get('source_url')})
        if len(res[domains[0]]) >= limit:
            break
    return {k: v[:limit] for k, v in res.items()}

domains = ['nstauthority.co.uk', 'epaguyana.org']
out['nsta_projects'] = []
out['nsta_url_class'] = Counter()
out['guyana_projects'] = []
out['guyana_url_class'] = Counter()
for r in projects:
    sn = (r.get('source_name') or '').lower()
    d = domain_of(r.get('source_url'))
    if 'nstauthority' in sn or 'nstauthority' in d or 'nsta' in sn:
        out['nsta_projects'].append({'id': r['id'], 'name': r['name'], 'source_url': r.get('source_url')})
        out['nsta_url_class'][classify(r.get('source_url'))] += 1
    if 'epaguyana' in d or 'guyana' in (r.get('source_name') or '').lower():
        out['guyana_projects'].append({'id': r['id'], 'name': r['name'], 'source_url': r.get('source_url')})
        out['guyana_url_class'][classify(r.get('source_url'))] += 1

out['nsta_url_class'] = dict(out['nsta_url_class'])
out['guyana_url_class'] = dict(out['guyana_url_class'])

# candidate events on those domains
out['nsta_candidates'] = [{'id': r['id'], 'project_name_raw': r['project_name_raw'], 'source_url': r.get('source_url')}
                          for r in candidates if 'nstauthority' in domain_of(r.get('source_url'))]
out['guyana_candidates'] = [{'id': r['id'], 'project_name_raw': r['project_name_raw'], 'source_url': r.get('source_url')}
                            for r in candidates if 'epaguyana' in domain_of(r.get('source_url'))]

# demo news sources: empties
DEMO_SOURCES = ['World Nuclear News', 'LNG Prime', 'Offshore Energy', 'Upstream Online',
                'Reuters', 'Argus Media', 'Energy Voice', 'MarineLink']
out['demo_news_empty'] = {}
for sn in DEMO_SOURCES:
    p = [{'id': r['id'], 'name': r['name']} for r in projects
         if (r.get('source_name') or '') == sn and classify(r.get('source_url')) == 'empty']
    c = [{'id': r['id'], 'project_name_raw': r['project_name_raw']} for r in candidates
         if (r.get('source_name') or '') == sn and classify(r.get('source_url')) == 'empty']
    out['demo_news_empty'][sn] = {'projects': p, 'candidates': c}

# all distinct source_names with any empty, top-level summary
out['summary'] = {
    'projects_empty': sum(1 for r in projects if classify(r.get('source_url')) == 'empty'),
    'projects_invalid': sum(1 for r in projects if classify(r.get('source_url')) == 'invalid'),
    'projects_bad_generic': sum(1 for r in projects if classify(r.get('source_url')) == 'bad_generic'),
    'candidates_empty': sum(1 for r in candidates if classify(r.get('source_url')) == 'empty'),
    'candidates_bad_generic': sum(1 for r in candidates if classify(r.get('source_url')) == 'bad_generic'),
}

with open(os.path.join(os.path.dirname(__file__), 'link_plan_diag.json'), 'w') as f:
    json.dump(out, f, indent=1, ensure_ascii=False)

print('projects total:', len(projects))
print('projects class:', dict(p_cls))
print('candidates total:', len(candidates))
print('candidates class:', dict(c_cls))
print('NSTA projects matched:', len(out['nsta_projects']), 'class:', out['nsta_url_class'])
print('Guyana projects matched:', len(out['guyana_projects']), 'class:', out['guyana_url_class'])
print('NSTA candidates:', len(out['nsta_candidates']), 'Guyana candidates:', len(out['guyana_candidates']))
print()
print('--- projects: top 25 sources by empty count ---')
for k, v in p_empty.most_common(25):
    print(f'  {k}: empty={v} / total={p_total[k]}')
print()
print('--- candidates: top 25 sources by empty count ---')
for k, v in c_empty.most_common(25):
    print(f'  {k}: empty={v} / total={c_total[k]}')
print()
print('wrote crawler/scripts/link_plan_diag.json')
