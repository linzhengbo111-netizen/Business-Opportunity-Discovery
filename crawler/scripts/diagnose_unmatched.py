#!/usr/bin/env python3
"""Diagnose which project names have no match in PROJECT_ALIASES."""
import os, sys
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_CRAWLER_DIR = os.path.dirname(_SCRIPT_DIR)
sys.path.insert(0, _CRAWLER_DIR)
from dotenv import load_dotenv
from supabase import create_client
from adapters.media_common import normalize_project_name, get_display_name, PROJECT_ALIASES

_PROJECT_ROOT = os.path.dirname(_CRAWLER_DIR)
if os.path.exists(os.path.join(_PROJECT_ROOT, ".env")):
    load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("VITE_SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Get all unique project names from projects table
all_names = set()
offset = 0
while True:
    resp = supabase.table("projects").select("name").range(offset, offset + 999).execute()
    batch = resp.data or []
    if not batch: break
    for row in batch:
        name = (row.get("name") or "").strip()
        if name:
            all_names.add(name)
    if len(batch) < 1000: break
    offset += 1000

print(f"Total unique project names: {len(all_names)}")

matched = 0
unmatched = []

for name in sorted(all_names):
    cid = normalize_project_name(name)
    if cid:
        matched += 1
        print(f"  ✓ {name[:70]} -> {cid}")
    else:
        unmatched.append(name)
        print(f"  ✗ {name[:70]} -> NO MATCH")

print(f"\n=== SUMMARY ===")
print(f"Matched:   {matched}")
print(f"Unmatched: {len(unmatched)}")

if unmatched:
    print(f"\n=== UNMATCHED PROJECTS ({len(unmatched)}) ===")
    # Generate suggested alias entries
    for i, name in enumerate(unmatched):
        # Create a kebab-case ID from the name
        slug = name.lower().replace(" ", "-").replace("(", "").replace(")", "").replace(",", "").replace("'", "")
        slug = "-".join(slug.split("--"))  # collapse double dashes
        # Try to guess country from name
        country = "Unknown"
        # Print as copy-paste-ready TS entries
        print(f"\n  // Entry {i+1}")
        print(f"  '{slug}': {{")
        print(f"    displayName: '{name}',")
        print(f"    country: '{country}',  // TODO: set correct country")
        print(f"    aliases: ['{name}'],")
        print(f"  }},")
