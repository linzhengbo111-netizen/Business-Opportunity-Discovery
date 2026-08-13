#!/usr/bin/env python3
"""
Backfill script: complete demo project fields for the final pitch.

For the 3 selected demo projects (see docs/demo_projects.md):
  1. Backfill projects.procurement_chain from known facts. candidate_events
     carries no procurement chain for these rows (all REGULATORY_DATA), so
     values come from verified public facts:
       - FPSO ALMIRANTE TAMANDARE: SBM Offshore (FPSO construction + lease)
       - FPSO BACALHAU: MODEC (FPSO supply + operation)
       - FPSO SEPETIBA: SBM Offshore (FPSO construction + lease)
  2. Run the S5 opportunity scoring engine (crawler/opportunity_scorer.py,
     mirror of src/lib/opportunity_scorer.ts) and write the result to
     projects.opportunity_score (JSONB, includes totalScore and grade).
  3. Verify all demo-critical fields and print a summary table.

Usage:
  python scripts/backfill_demo_projects.py --dry-run   # Preview only, no writes
  python scripts/backfill_demo_projects.py --execute   # Write to Supabase
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# ---- Paths & Config --------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent  # repo root
sys.path.insert(0, str(BASE_DIR / "crawler"))

load_dotenv(BASE_DIR / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("VITE_SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("backfill-demo-projects")

# 3 demo projects from docs/demo_projects.md (2026-08-13 selection).
# procurement_chain facts per team instructions — do not invent further.
DEMO_PROJECTS = [
    {
        "name": "FPSO ALMIRANTE TAMANDARE",
        "procurement_chain": "SBM Offshore",
        "fact": "SBM Offshore 负责 FPSO 建造和租赁",
    },
    {
        "name": "FPSO BACALHAU",
        "procurement_chain": "MODEC",
        "fact": "MODEC 负责 FPSO 供应和运营",
    },
    {
        "name": "FPSO SEPETIBA",
        "procurement_chain": "SBM Offshore",
        "fact": "SBM Offshore 负责 FPSO 建造和租赁",
    },
]

VERIFY_FIELDS = [
    "name", "country", "status", "water_depth_m", "oil_capacity_bpd",
    "gas_capacity_mmcmd", "stainless_steel", "application",
    "procurement_chain", "opportunity_score", "industry", "source_url",
]


# ============================================================================
# Supabase Operations
# ============================================================================

def get_supabase():
    from supabase import create_client
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL and SUPABASE_ANON_KEY must be set in .env")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def fetch_project_by_name(supabase, name: str) -> dict | None:
    result = supabase.table("projects").select("*").eq("name", name).execute()
    rows = result.data or []
    if not rows:
        log.warning("project not found: %s", name)
        return None
    if len(rows) > 1:
        log.warning("multiple rows for %s, using first", name)
    return rows[0]


def update_project(supabase, project_id: int, fields: dict) -> None:
    supabase.table("projects").update(fields).eq("id", project_id).execute()


# ============================================================================
# Scoring
# ============================================================================

def score_project(row: dict, procurement_chain: str) -> dict:
    """Run the S5 scorer on a project row (with the new chain applied)."""
    from opportunity_scorer import score_opportunity

    project_data = dict(row)
    project_data["procurement_chain"] = procurement_chain
    return score_opportunity(project_data)


# ============================================================================
# Main
# ============================================================================

def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill demo project fields.")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no writes")
    parser.add_argument("--execute", action="store_true", help="Write to Supabase")
    args = parser.parse_args()

    if args.dry_run and args.execute:
        parser.error("--dry-run and --execute are mutually exclusive")

    supabase = get_supabase()
    results = []

    for spec in DEMO_PROJECTS:
        name = spec["name"]
        chain = spec["procurement_chain"]
        log.info("=== %s ===", name)

        row = fetch_project_by_name(supabase, name)
        if row is None:
            results.append((name, None))
            continue

        old_chain = row.get("procurement_chain")
        old_score = row.get("opportunity_score")

        # 1. Backfill procurement_chain (idempotent)
        if old_chain != chain:
            log.info("procurement_chain: %r -> %r (%s)", old_chain, chain, spec["fact"])
        else:
            log.info("procurement_chain already set: %r", chain)

        # 2. Compute opportunity score with the new chain applied
        score = score_project(row, chain)
        log.info(
            "opportunity_score: %s (was %s)",
            json.dumps({"totalScore": score["totalScore"], "grade": score["grade"]}, ensure_ascii=False),
            "NULL" if not old_score else "set",
        )

        if args.execute:
            update_project(supabase, row["id"], {
                "procurement_chain": chain,
                "opportunity_score": score,
            })
            log.info("written to projects id=%s", row["id"])

        results.append((name, {"row": row, "score": score, "chain": chain}))

    # 3. Verification table
    print()
    print("=== VERIFICATION ===")
    header = ["name", "status", "water_depth_m", "oil_capacity_bpd",
              "stainless_steel", "application", "procurement_chain",
              "opportunity_score", "industry", "source_url"]
    for name, entry in results:
        if entry is None:
            print(f"{name}: NOT FOUND")
            continue
        row = entry["row"]
        score = entry["score"]
        print(f"--- {name} ---")
        for field in header:
            if field == "opportunity_score":
                value = f"{score['totalScore']} / {score['grade']}"
            elif field == "procurement_chain":
                value = entry["chain"]
            elif field == "stainless_steel" or field == "application":
                value = row.get(field) or "NULL"
                if isinstance(value, str) and len(value) > 60:
                    value = value[:57] + "..."
            elif field == "source_url":
                value = row.get(field) or "NULL"
                if isinstance(value, str) and len(value) > 70:
                    value = value[:67] + "..."
            else:
                value = row.get(field)
            print(f"  {field}: {value}")

    missing = []
    for name, entry in results:
        if entry is None:
            missing.append(f"{name} (row not found)")
            continue
        row = entry["row"]
        for field in ["water_depth_m", "oil_capacity_bpd", "stainless_steel",
                      "application", "procurement_chain", "opportunity_score",
                      "industry", "source_url"]:
            if field == "industry":
                # Column may not exist yet (migrations/008 pending).
                if "industry" not in row:
                    missing.append(f"{name}: industry column missing from schema")
                    continue
            if field == "opportunity_score":
                value = entry["score"]
            elif field == "procurement_chain":
                value = entry["chain"]
            else:
                value = row.get(field)
            if value is None or value == "":
                missing.append(f"{name}: {field} empty")
    if missing:
        print()
        print("INCOMPLETE FIELDS:")
        for m in missing:
            print(f"  - {m}")
    else:
        print()
        print("All demo fields complete.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
