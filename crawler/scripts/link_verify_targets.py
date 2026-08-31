#!/usr/bin/env python3
"""Verify candidate URLs for the 10 target projects: HTTP status + title/keyword relevance."""
import re
import sys
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/pdf,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

TARGETS = {
    'Belinda': ('https://www.offshore-mag.com/subsea/article/55020788/serica-energy-serica-commits-to-north-sea-belinda-triton-tieback', ['belinda', 'serica']),
    'Payara': ('https://www.offshore-mag.com/production/article/14301518/exxon-mobil-starts-production-through-payara-fpso-offshore-guyana', ['payara', 'guyana']),
    'Victory': ('https://www.ogj.com/drilling-production/production-operations/news/55320515/shell-begins-gas-production-from-north-sea-victory-field', ['victory', 'shell']),
    'Tartaruga Verde': ('https://www.modec.com/news/2018/20180626.html', ['tartaruga', 'first oil']),
    'Hammerhead': ('https://www.oedigital.com/news/530296-exxonmobil-makes-fid-on-hammerhead', ['hammerhead', 'guyana']),
    'Uaru': ('https://www.oedigital.com/news/542313-fifth-fpso-for-exxon-arrives-in-guyana', ['uaru', 'guyana']),
    'Whiptail': ('https://www.offshore-mag.com/regional-reports/latin-america/article/55018103/exxonmobil-issues-fid-for-whiptail-project', ['whiptail', 'guyana']),
    'Yellowtail': ('https://www.rigzone.com/news/exxonmobil_partners_start_producing_oil_at_yellowtail-11-aug-2025-181424-article/', ['yellowtail', 'guyana']),
    'Liza Phase 1': ('https://www.offshore-energy.biz/exxonmobil-makes-history-in-guyana-as-liza-destiny-fpso-produces-first-oil/', ['liza', 'destiny']),
    'Liza Phase 2': ('https://www.spglobal.com/energy/en/news-research/latest-news/crude-oil/021122-first-oil-flows-from-liza-phase-2-development-at-offshore-guyanas-stabroek-block', ['liza', 'guyana']),
}

FALLBACKS = {
    'Yellowtail': 'https://theenergyyear.com/news/exxonmobil-starts-production-at-guyanas-yellowtail/',
    'Liza Phase 2': 'https://flng.worldenergyreports.com/news/detail/liza-unity-exxons-second-fpso-in-guyana-produces-first-oil-209266',
    'Uaru': 'https://www.offshore-mag.com/regional-reports/latin-america/article/55050991/modec-receives-fpso-errea-wittu-arrives-offshore-guyana',
}

def check(url, kws):
    try:
        r = requests.get(url, headers=HEADERS, timeout=25, stream=True)
        ctype = r.headers.get('content-type', '')
        body = ''
        if 'text/html' in ctype or 'application/pdf' in ctype:
            body = r.raw.read(120000, decode_content=True).decode('utf-8', errors='ignore')
        r.close()
        low = body.lower()
        title = re.search(r'<title[^>]*>(.*?)</title>', body, re.S | re.I)
        title = re.sub(r'\s+', ' ', title.group(1)).strip()[:100] if title else '(no title)'
        hits = {kw: kw in low for kw in kws}
        return r.status_code, title, hits, ctype.split(';')[0][:40]
    except Exception as e:
        return 'ERR', str(e)[:80], {}, ''

for name, (url, kws) in TARGETS.items():
    st, title, hits, ct = check(url, kws)
    ok = st == 200 and all(hits.values())
    print(f'{"OK " if ok else "BAD"} {st} {name:16s} kw={hits}')
    print(f'    {title}')
    if not ok:
        print(f'    URL: {url}')
        fb = FALLBACKS.get(name)
        if fb:
            st2, t2, h2, ct2 = check(fb, kws)
            ok2 = st2 == 200 and all(h2.values())
            print(f'    FALLBACK {"OK " if ok2 else "BAD"} {st2} {fb} kw={h2}')
            print(f'    {t2}')
