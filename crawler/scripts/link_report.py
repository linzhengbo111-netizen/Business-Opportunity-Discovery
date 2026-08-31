#!/usr/bin/env python3
"""
Generate link quality report (post-fix). Outputs markdown to
docs/link-quality-report.md and prints a summary.

Usage: python3 crawler/scripts/link_report.py
"""
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
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
    """valid_article / data_file / empty(待补充) / other"""
    if not url:
        return 'empty'
    p = urlparse(url.strip()).path.lower()
    if p.endswith(FILE_EXTS) or '@@download/file' in url:
        return 'data_file'
    if re.search(r'(/search|/category/|/tag/|\?s=|\?q=)', url.lower()):
        return 'bad_generic'
    return 'valid_article'


projects = fetch_all('projects', 'id,name,source_url,source_name,industry')
candidates = fetch_all('candidate_events', 'id,project_name_raw,source_url,review_status')

report = {}
for label, rows, name_key in [('projects', projects, 'name'), ('candidate_events', candidates, 'project_name_raw')]:
    cls = Counter(classify(r['source_url']) for r in rows)
    doms = Counter()
    for r in rows:
        u = (r['source_url'] or '').strip()
        if u:
            doms[urlparse(u).netloc.lower().replace('www.', '')] += 1
    report[label] = {'total': len(rows), 'cls': dict(cls), 'doms': doms}

now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
md = [f'# 链接质量报告 (Link Quality Report)\n',
      f'> 生成时间: {now}',
      f'> 数据: Supabase `projects` + `candidate_events`\n']

for label, info in report.items():
    cls = info['cls']
    md.append(f'## {label} ({info["total"]} rows)\n')
    md.append(f'| 状态 | 数量 |')
    md.append(f'|---|---|')
    md.append(f'| ✅ 有效文章/页面链接 | {cls.get("valid_article", 0)} |')
    md.append(f'| 📄 数据文件 (CSV/PDF/DOC 下载) | {cls.get("data_file", 0)} |')
    md.append(f'| ⬜ 待补充 (无链接) | {cls.get("empty", 0)} |')
    md.append(f'| ⚠️ 仍为泛页面 | {cls.get("bad_generic", 0)} |')
    md.append('')
    md.append(f'### 域名分布 (top 15)\n')
    md.append('| 域名 | 数量 |')
    md.append('|---|---|')
    for d, n in info['doms'].most_common(15):
        md.append(f'| {d} | {n} |')
    md.append('')

md.append('## 修复记录\n')
md.append('- 3 个置顶 FPSO 项目已替换为官方/媒体报道文章:')
md.append('  - FPSO ALMIRANTE TAMANDARE → agencia.petrobras.com.br (Petrobras 官方新闻)')
md.append('  - FPSO BACALHAU → modec.com 新闻稿')
md.append('  - FPSO SEPETIBA → oedigital.com 新闻')
md.append('- Rosebank 项目 → equinor.com/energy/rosebank')
md.append('- 指向首页/列表页/搜索页/下载目录页的链接已清空标记为 待补充')
md.append('  (nstauthority field themes、epaguyana download-category、gov.br planos 列表、')
md.append('   11 个行业垂直站首页、petroleum.gov.gy 首页、供应商门户等)')
md.append('- 数据文件类链接 (ANP CSV 下载、NSTA 模板文件) 保留 — 可下载但非文章原文')
md.append('')
md.append('## 建议后续\n')
md.append('- 对 待补充 的行业垂直站项目 (hydrocarbonprocessing/lngprime/chemweek 等 11 站):')
md.append('  crawler 抓取时未保存文章 URL，需重跑对应 adapter 并保留原文链接')
md.append('- 对 nstauthority/epaguyana 数据类项目: 可在 AI 分析阶段提取具体文件直链')
md.append('  (download-category 页面内有文件列表)')
md.append('- 回滚数据: crawler/scripts/link_fix_backup.json (每次变更的 old/new URL)')

out = os.path.join(os.path.dirname(__file__), '..', '..', 'docs', 'link-quality-report.md')
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, 'w') as f:
    f.write('\n'.join(md) + '\n')

print('\n'.join(md[:14]))
print(f'\nreport written: {out}')
