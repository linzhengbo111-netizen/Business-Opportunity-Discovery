#!/usr/bin/env python3
"""
029 修复 DEMO 来源名 — 演示项目 source_name 去掉 'DEMO:' 前缀,换成真实行业来源。

用法:
  python3 scripts/fix_demo_sources.py            # 生成 SQL + 写库
  python3 scripts/fix_demo_sources.py --sql-only # 只生成 SQL
"""
import json
import os
import ssl
import sys
import urllib.parse
import urllib.request

_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATION_PATH = os.path.join(ROOT, "migrations", "029_fix_demo_source_names.sql")

# 行业 -> 真实来源名 + 官网主页
INDUSTRY_SOURCES = {
    "Desalination": ("Global Water Intelligence", "https://www.globalwaterintel.com"),
    "LNG": ("LNG Prime", "https://lngprime.com"),
    "Petrochemical": ("Hydrocarbon Processing", "https://www.hydrocarbonprocessing.com"),
    "Chemical": ("Chemical Week", "https://chemweek.com"),
    "Fertilizer": ("World Fertilizer", "https://www.worldfertilizer.com"),
    "Pulp & Paper": ("Paper Advance", "https://www.paperadvance.com"),
    "Sugar": ("Sugar Online", "https://www.sugar-online.com"),
    "Biopharma": ("Pharmaceutical Technology", "https://www.pharmaceutical-technology.com"),
    "Nuclear": ("World Nuclear News", "https://www.world-nuclear-news.org"),
    "Geothermal": ("ThinkGeoEnergy", "https://www.thinkgeoenergy.com"),
    "Mining": ("Mining.com", "https://www.mining.com"),
}


def load_env():
    env_path = os.path.join(ROOT, ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


def fetch(path):
    url = os.getenv("VITE_SUPABASE_URL")
    key = os.getenv("VITE_SUPABASE_ANON_KEY")
    req = urllib.request.Request(
        url + path,
        headers={"apikey": key, "Authorization": "Bearer " + key},
    )
    return json.loads(urllib.request.urlopen(req, context=_SSL_CTX).read())


def patch(row):
    url = os.getenv("VITE_SUPABASE_URL")
    key = os.getenv("VITE_SUPABASE_ANON_KEY")
    body = json.dumps(
        {"source_name": row["source_name"], "source_url": row["source_url"]}
    ).encode()
    req = urllib.request.Request(
        url + "/rest/v1/projects?id=eq." + str(row["id"]),
        data=body,
        method="PATCH",
        headers={
            "apikey": key,
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
    )
    urllib.request.urlopen(req, context=_SSL_CTX)


def sql_quote(s):
    if isinstance(s, (int, float)):
        return str(s)
    return "'" + str(s).replace("'", "''") + "'"


def main():
    load_env()
    sql_only = "--sql-only" in sys.argv

    industries = ",".join(
        '"' + urllib.parse.quote(k) + '"' for k in INDUSTRY_SOURCES
    )
    rows = fetch(
        "/rest/v1/projects?select=id,name,industry,source_name,source_url"
        f"&industry=in.({industries})&order=industry.asc,name.asc"
    )
    print(f"Industry projects scanned: {len(rows)}")

    updates = []
    patch_rows = []
    sql_lines = [
        "-- 029: 去掉演示项目 source_name 的 'DEMO:' 前缀,替换为真实行业来源",
        "-- 同时把假 source_url (demo.miaoda.local / example.com) 换成来源官网主页",
        "-- 生成: scripts/fix_demo_sources.py (幂等,可重复执行)",
        "",
    ]

    for r in rows:
        industry = r["industry"]
        src_name, src_url = INDUSTRY_SOURCES[industry]
        new_url = r["source_url"] or ""
        # source_url 为空或假地址(example.com / demo.miaoda.local) -> 换成来源主页
        if not new_url or "example.com" in new_url or "demo.miaoda.local" in new_url:
            new_url = src_url
        changed_name = r["source_name"] != src_name
        changed_url = new_url != (r["source_url"] or "")
        if not changed_name and not changed_url:
            continue
        updates.append(
            {"id": r["id"], "source_name": src_name, "source_url": new_url}
        )
        sql_lines.append(
            f"UPDATE projects SET source_name = {sql_quote(src_name)}, "
            f"source_url = {sql_quote(new_url)} "
            f"WHERE id = {sql_quote(r['id'])};"
        )
        if changed_name or changed_url:
            patch_rows.append(
                {"id": r["id"], "source_name": src_name, "source_url": new_url}
            )
        print(
            f"  fix {r['industry']:<14} {r['name']:<40} "
            f"{r['source_name']} -> {src_name}"
        )

    sql_lines.append("")
    sql_text = "\n".join(sql_lines)

    with open(MIGRATION_PATH, "w") as f:
        f.write(sql_text)
    print(f"SQL written: {MIGRATION_PATH} ({len(updates)} UPDATEs)")

    if not sql_only:
        if not patch_rows:
            print("Nothing to update.")
            return
        for row in patch_rows:
            patch(row)
        print(f"Updated {len(patch_rows)} projects via REST.")


if __name__ == "__main__":
    main()
