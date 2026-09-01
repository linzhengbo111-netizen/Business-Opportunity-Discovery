#!/usr/bin/env python3
"""
Normalize material grade names in stored project data.

Fixes LLM-generated grade names that drifted from the factory catalog
(e.g. "6Mo (UNS N08367)" → "6Mo (UNS S31254)", "Duplex 2285" → dropped).

Fields touched:
  - projects.stainless_steel      (comma-separated grade list)
  - projects.recommendation_json  (grades: string[] or {grade}[])

Mirrors normalize_material_grade() in crawler/ai_push_analyst.py and
normalizeMaterialGrade() in src/lib/material_matcher.ts. Keep the alias
map in sync with those files.

Usage:
  python3 scripts/normalize_material_grades.py              # dry-run, report only
  python3 scripts/normalize_material_grades.py --write      # apply updates
  python3 scripts/normalize_material_grades.py --name "FPSO BACALHAU"
"""

import argparse
import json
import os
import re
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_SCRIPT_DIR)
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(_ROOT_DIR, ".env"))

from supabase import create_client  # noqa: E402

from ai_push_analyst import normalize_material_grade  # noqa: E402


# ---- Helpers -------------------------------------------------------------

def normalize_steel_field(value: str | None):
    """Normalize a comma-separated stainless_steel value.

    Returns (new_value_or_None, dropped_names).
    """
    if not value:
        return None, []
    kept: list[str] = []
    dropped: list[str] = []
    for part in re.split(r"[,\n;、]", value):
        name = part.strip()
        if not name:
            continue
        canon = normalize_material_grade(name)
        if canon is None:
            dropped.append(name)
        elif canon not in kept:
            kept.append(canon)
    new_value = ", ".join(kept) if kept else None
    old_value = value.strip() or None
    if new_value == old_value:
        return None, dropped
    return new_value, dropped


def normalize_recommendation(value: str | None):
    """Normalize recommendation_json.grades.

    Returns (new_json_or_None, dropped_names).
    """
    if not value:
        return None, []
    try:
        parsed = json.loads(value)
    except Exception:
        return None, []
    if not isinstance(parsed, dict) or not isinstance(parsed.get("grades"), list):
        return None, []

    kept: list[object] = []
    dropped: list[str] = []
    seen: set[str] = set()
    for g in parsed["grades"]:
        if isinstance(g, str):
            raw_name, extra = g, None
        elif isinstance(g, dict):
            raw_name = g.get("grade") or g.get("name") or ""
            extra = g
        else:
            dropped.append(str(g))
            continue
        name = str(raw_name).strip()
        if not name:
            continue
        canon = normalize_material_grade(name)
        if canon is None:
            dropped.append(name)
            continue
        if canon in seen:
            continue
        seen.add(canon)
        if isinstance(g, str):
            kept.append(canon)
        else:
            new_item = dict(extra or {})
            new_item["grade"] = canon
            new_item["in_factory_scope"] = True
            kept.append(new_item)

    parsed["grades"] = kept
    new_value = json.dumps(parsed, ensure_ascii=False)
    if new_value == value:
        return None, dropped
    return new_value, dropped


# ---- Main -----------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Normalize material grade names in projects table.")
    ap.add_argument("--write", action="store_true",
                    help="apply updates (default: dry-run, report only)")
    ap.add_argument("--name", default=None,
                    help="only process rows whose name matches")
    args = ap.parse_args()

    sb = create_client(os.environ["VITE_SUPABASE_URL"],
                       os.environ["VITE_SUPABASE_ANON_KEY"])

    # Paginated fetch — Supabase caps a single query at 1000 rows.
    rows: list[dict] = []
    page = 0
    while True:
        query = (sb.table("projects")
                 .select("id,name,stainless_steel,recommendation_json")
                 .order("id")
                 .range(page * 1000, page * 1000 + 999))
        if args.name:
            query = query.ilike("name", f"%{args.name}%")
        resp = query.execute()
        page_rows = resp.data or []
        rows.extend(page_rows)
        if len(page_rows) < 1000:
            break
        page += 1
    print(f"rows: {len(rows)}")

    n_update = 0
    n_drop = 0
    fabricated: dict[str, set[str]] = {}
    updates: list[dict] = []

    for row in rows:
        changed: dict[str, object] = {}
        dropped_names: list[str] = []

        new_steel, d1 = normalize_steel_field(row.get("stainless_steel"))
        if new_steel is not None:
            changed["stainless_steel"] = new_steel
        dropped_names += d1

        new_rec, d2 = normalize_recommendation(row.get("recommendation_json"))
        if new_rec is not None:
            changed["recommendation_json"] = new_rec
        dropped_names += d2

        for name in dropped_names:
            fabricated.setdefault(name, set()).add(row.get("name") or "?")

        if not changed and not dropped_names:
            continue

        n_drop += len(dropped_names)
        if changed:
            n_update += 1
            updates.append({"id": row["id"], **changed})
            print(f"[update] {row.get('name')}")
            for k, v in changed.items():
                print(f"    {k}: {v}")
        for name in dropped_names:
            print(f"[drop]   {row.get('name')}: {name}")

    print()
    print(f"projects needing update: {n_update}, dropped grade tokens: {n_drop}")
    if fabricated:
        print("fabricated/unknown grade names found:")
        for name, projects in sorted(fabricated.items()):
            proj_list = ", ".join(sorted(projects)[:5])
            if len(projects) > 5:
                proj_list += f", ... (+{len(projects) - 5})"
            print(f"  - {name}  [{proj_list}]")

    if args.write and updates:
        print()
        print(f"applying {len(updates)} updates...")
        for upd in updates:
            sb.table("projects").update(upd).eq("id", upd["id"]).execute()
        print("done.")
    elif updates:
        print()
        print("dry-run: no writes. Pass --write to apply.")


if __name__ == "__main__":
    main()
