#!/usr/bin/env python3
"""Verify source_registry table data integrity after migration 002."""
import os
import sys
from supabase import create_client

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("VITE_SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: SUPABASE_URL and SUPABASE_ANON_KEY must be set in .env")
    sys.exit(1)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Fetch all rows
resp = supabase.table("source_registry").select("*").execute()
rows = resp.data

print(f"Total rows: {len(rows)}")
assert len(rows) >= 16, f"Expected >=16 rows, got {len(rows)}"

# Aggregate checks
by_country = {}
by_tier = {}
by_priority = {}
by_type = {}
by_frequency = {}
active_count = 0

for r in rows:
    by_country[r["country_focus"]] = by_country.get(r["country_focus"], 0) + 1
    by_tier[r["tier"]] = by_tier.get(r["tier"], 0) + 1
    by_priority[r["priority"]] = by_priority.get(r["priority"], 0) + 1
    by_type[r["source_type"]] = by_type.get(r["source_type"], 0) + 1
    by_frequency[r["crawl_frequency"]] = by_frequency.get(r["crawl_frequency"], 0) + 1
    if r["is_active"]:
        active_count += 1

print(f"\nBy country: {by_country}")
print(f"By tier:    {by_tier}")
print(f"By priority: {by_priority}")
print(f"By type:    {by_type}")
print(f"By frequency: {by_frequency}")
print(f"Active:     {active_count} / {len(rows)}")

# Assert expected distributions
assert by_country.get("Brazil", 0) == 4, f"Brazil expected 4, got {by_country.get('Brazil', 0)}"
assert by_country.get("Guyana", 0) == 4, f"Guyana expected 4, got {by_country.get('Guyana', 0)}"
assert by_country.get("UK", 0) == 4, f"UK expected 4, got {by_country.get('UK', 0)}"
assert by_country.get("Global", 0) == 4, f"Global expected 4, got {by_country.get('Global', 0)}"
assert by_tier.get(1, 0) == 4, f"Tier 1 expected 4, got {by_tier.get(1, 0)}"
assert by_tier.get(2, 0) == 7, f"Tier 2 expected 7, got {by_tier.get(2, 0)}"
assert by_tier.get(3, 0) == 5, f"Tier 3 expected 5, got {by_tier.get(3, 0)}"

# Verify specific P0 sources exist
p0_names = {r["source_name"] for r in rows if r["priority"] == "P0"}
expected_p0 = {"ANP FPSO CSV", "ANP 开发计划", "Guyana EPA", "NSTA 开发计划",
               "Equinor Rosebank 公告", "Offshore Energy", "World Oil"}
missing_p0 = expected_p0 - p0_names
assert not missing_p0, f"Missing P0 sources: {missing_p0}"

# Print full table
print("\n--- Full table ---")
for r in sorted(rows, key=lambda r: (r["country_focus"], r["priority"], r["source_name"])):
    print(f"  [{r['priority']}] [{r['country_focus']:<8}] T{r['tier']} {r['source_name']:<30} "
          f"type={r['source_type']:<16} access={r['access_method']:<5} freq={r['crawl_frequency']} "
          f"active={r['is_active']}")

print("\nAll checks passed.")
