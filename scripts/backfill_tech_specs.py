#!/usr/bin/env python3
"""
Backfill script: populate projects table with ANP CSV technical specs
and run stainless steel material matching.

Usage:
  python scripts/backfill_tech_specs.py              # Full run (dry-run preview first)
  python scripts/backfill_tech_specs.py --dry-run    # Preview only, no writes
  python scripts/backfill_tech_specs.py --execute    # Actually write to Supabase
  python scripts/backfill_tech_specs.py --match-only # Only run material matching on existing specs
"""

import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

# ---- Paths & Config --------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent  # repo root
sys.path.insert(0, str(BASE_DIR / "crawler" / "adapters"))

load_dotenv(BASE_DIR / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("VITE_SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY")

ANP_CSV_SNAPSHOT = BASE_DIR / "crawler" / "data" / "anp"

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")
NOW_ISO = datetime.now(timezone.utc).isoformat()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("backfill-tech-specs")


# ============================================================================
# 1. Material Matching Engine (Python — mirrors src/lib/material_matcher.ts)
# ============================================================================

def match_materials(specs: dict) -> dict:
    """Run stainless steel material matching rules.
    Returns { grades: [str], applications: [str], confidence: str, reasoning: str }
    """
    rules = []

    wd = specs.get("water_depth_m")
    oil = specs.get("oil_capacity_bpd")
    gas = specs.get("gas_capacity_mmcmd")
    hull = (specs.get("hull_type") or "").lower()
    basin = (specs.get("basin") or "").lower()
    operator = (specs.get("operator_name") or "").lower()

    # Water depth rules
    if wd and wd > 2000:
        rules.append({
            "grades": ["Super Duplex 2507", "6Mo (UNS S31254)"],
            "applications": ["Deepwater Risers", "Subsea Manifolds", "Seawater Lift Pump (deep)"],
            "reason": f"Water depth {wd}m >2000m: extreme deepwater requires Super Duplex 2507 or 6Mo."
        })
    elif wd and wd > 1500:
        rules.append({
            "grades": ["Super Duplex 2507"],
            "applications": ["Seawater Lift Pump (deep)", "Subsea Manifolds"],
            "reason": f"Water depth {wd}m >1500m: deepwater conditions recommend Super Duplex 2507."
        })
    elif wd and wd <= 500:
        rules.append({
            "grades": ["Duplex 2205", "316L"],
            "applications": ["Process Piping", "Seawater Lift Pump"],
            "reason": f"Water depth {wd}m ≤500m: Duplex 2205 sufficient for moderate-depth service."
        })

    # Oil capacity rules
    if oil and oil > 150000:
        rules.append({
            "grades": ["Duplex 2205", "Super Duplex 2507"],
            "applications": ["Cargo Oil Tanks", "Process Piping", "Heat Exchangers", "Produced Water Treatment"],
            "reason": f"Oil capacity {oil:,} bpd >150,000: large-scale topsides. Duplex/Super Duplex combo."
        })
    elif oil and oil > 50000:
        rules.append({
            "grades": ["Duplex 2205", "316L"],
            "applications": ["Process Piping", "Cargo Oil Tanks"],
            "reason": f"Oil capacity {oil:,} bpd 50k-150k: mid-scale production. Duplex 2205 for critical piping."
        })

    # Gas capacity rules
    if gas and gas > 5:
        rules.append({
            "grades": ["Super Duplex 2507", "6Mo (UNS S31254)", "Inconel 625"],
            "applications": ["Gas Compression", "Gas Processing Piping", "Heat Exchangers", "Flare Systems"],
            "reason": f"Gas capacity {gas} MMcmd >5: high-volume gas processing. Corrosion-resistant alloys needed."
        })
    elif gas and gas > 1:
        rules.append({
            "grades": ["Duplex 2205", "Super Duplex 2507"],
            "applications": ["Gas Compression", "Process Piping"],
            "reason": f"Gas capacity {gas} MMcmd 1-5: moderate gas processing. Duplex/Super Duplex for compression."
        })

    # Hull type rules
    if "turret" in hull:
        rules.append({
            "grades": ["Super Duplex 2507", "Duplex 2205"],
            "applications": ["Mooring Systems", "Turret Bearing Components", "Swivel Stack"],
            "reason": "Turret mooring: high-stress rotating components require Duplex/Super Duplex."
        })
    if "spread" in hull:
        rules.append({
            "grades": ["Duplex 2205"],
            "applications": ["Mooring Components", "Fairleads", "Chain Stoppers"],
            "reason": "Spread moored: Duplex 2205 sufficient for mooring components."
        })
    if "flng" in hull or "lng" in hull or "conversion" in hull:
        rules.append({
            "grades": ["Super Duplex 2507", "6Mo (UNS S31254)", "Inconel 625"],
            "applications": ["LNG Process Piping", "Cryogenic Heat Exchangers", "Gas Compression", "LNG Storage Tanks (lining)"],
            "reason": "FLNG/LNG conversion: cryogenic and gas processing demand high-alloy stainless/nickel alloys."
        })

    # Basin rules
    if any(b in basin for b in ["santos", "campos", "espirito"]):
        rules.append({
            "grades": ["Super Duplex 2507", "6Mo (UNS S31254)", "Inconel 625"],
            "applications": ["Subsea Manifolds", "Deepwater Risers", "Gas Compression", "Production Separators"],
            "reason": "Brazilian pre-salt basin: high CO2, deepwater, high-pressure. Premium corrosion-resistant alloys."
        })

    # Operator rules
    if "petrobras" in operator:
        rules.append({
            "grades": ["Super Duplex 2507", "6Mo (UNS S31254)", "Duplex 2205"],
            "applications": ["Subsea Manifolds", "Deepwater Risers", "Process Piping", "Gas Compression", "Produced Water Treatment"],
            "reason": "Petrobras operator: known pre-salt requirements. High CO2, deepwater, strict material specs."
        })

    # Default if no rules fired
    if not rules:
        return {
            "grades": ["316L", "Duplex 2205"],
            "applications": ["Process Piping", "Cargo Oil Tanks"],
            "confidence": "low",
            "reasoning": "Insufficient technical data for rule-based matching. Defaulting to 316L and Duplex 2205."
        }

    # Aggregate
    grade_counts = {}
    app_counts = {}
    reasons = []
    for r in rules:
        for g in r["grades"]:
            grade_counts[g] = grade_counts.get(g, 0) + 1
        for a in r["applications"]:
            app_counts[a] = app_counts.get(a, 0) + 1
        reasons.append(r["reason"])

    sorted_grades = sorted(grade_counts, key=lambda g: (-grade_counts[g], g))
    sorted_apps = sorted(app_counts, key=lambda a: (-app_counts[a], a))

    # Confidence
    data_points = sum(1 for v in [
        specs.get("water_depth_m"), specs.get("oil_capacity_bpd"),
        specs.get("gas_capacity_mmcmd"), specs.get("hull_type"),
        specs.get("field_name"), specs.get("operator_name"), specs.get("basin")
    ] if v)
    if len(rules) >= 3 and data_points >= 3:
        confidence = "high"
    elif len(rules) >= 2:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "grades": sorted_grades,
        "applications": sorted_apps,
        "confidence": confidence,
        "reasoning": " ".join(reasons)
    }


# ============================================================================
# 2. ANP CSV Data Loading
# ============================================================================

def load_anp_records() -> list[dict]:
    """Load ANP FPSO records from the most recent local snapshot JSON."""
    snapshots = sorted(ANP_CSV_SNAPSHOT.glob("*_snapshot.json"), reverse=True)
    if not snapshots:
        log.error("No ANP snapshot found in %s. Run ANP CSV adapter first.", ANP_CSV_SNAPSHOT)
        return []

    latest = snapshots[0]
    log.info("Loading ANP records from %s", latest)
    data = json.loads(latest.read_text(encoding="utf-8"))
    records = data.get("records", {})
    return list(records.values())


def load_anp_from_csv_directly() -> list[dict]:
    """If no snapshot exists, try downloading and parsing the CSV directly."""
    try:
        from anp_fpso_csv import download_csv, parse_csv
        raw, sha256 = download_csv()
        records, headers = parse_csv(raw)
        log.info("Downloaded and parsed %d FPSO records from ANP CSV", len(records))
        return records
    except ImportError:
        log.error("Cannot import anp_fpso_csv adapter. Ensure crawler/ is on PYTHONPATH.")
        return []
    except Exception as e:
        log.error("Failed to download ANP CSV: %s", e)
        return []


def _parse_int(val) -> Optional[int]:
    if val is None or (isinstance(val, str) and not val.strip()):
        return None
    try:
        s = str(val).strip().replace(".", "").replace(",", "")
        n = int(float(s))
        return n if n > 0 else None
    except (ValueError, TypeError):
        return None


def anp_record_to_specs(record: dict) -> dict:
    """Convert an ANP CSV record to technical spec fields for projects table."""
    return {
        "water_depth_m": _parse_int(record.get("water_depth_m", "")),
        "oil_capacity_bpd": _parse_int(record.get("oil_capacity_bbl_d", "")),
        "gas_capacity_mmcmd": _parse_int(record.get("gas_capacity_m3_d", "")),
        "hull_type": (record.get("platform_type") or "").strip() or None,
        "field_name": (record.get("field") or "").strip() or None,
        "operator_name": (record.get("operator") or "").strip() or None,
        "basin": (record.get("basin") or "").strip() or None,
    }


# ============================================================================
# 3. Supabase Operations
# ============================================================================

def get_supabase():
    from supabase import create_client
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL and SUPABASE_ANON_KEY must be set in .env")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def fetch_all_projects(supabase) -> list[dict]:
    """Fetch all projects from Supabase."""
    all_rows = []
    offset = 0
    limit = 1000
    while True:
        result = supabase.table("projects").select("*").range(offset, offset + limit - 1).execute()
        rows = result.data or []
        if not rows:
            break
        all_rows.extend(rows)
        if len(rows) < limit:
            break
        offset += limit
    return all_rows


def find_project_match(anp_record: dict, projects: list[dict]) -> Optional[dict]:
    """Find a matching project in the projects table for an ANP FPSO record.
    Matches by facility name (case-insensitive, with normalization).
    """
    facility_name = (anp_record.get("facility_name") or "").strip().lower()
    facility_code = (anp_record.get("facility_code") or "").strip().lower()

    if not facility_name:
        return None

    def norm(s: str) -> str:
        return re.sub(r"[^a-z0-9]", "", s.lower())

    norm_name = norm(facility_name)
    norm_code = norm(facility_code) if facility_code else ""

    # Exact match on normalized name
    for p in projects:
        p_name = norm(p.get("name", ""))
        if p_name == norm_name:
            return p

    # Code match (ANP sigla → project name containing the code)
    if norm_code and len(norm_code) >= 2:
        for p in projects:
            p_name = norm(p.get("name", ""))
            if norm_code in p_name or p_name in norm_code:
                return p

    # Substring match (facility name within project name or vice versa)
    for p in projects:
        p_name = norm(p.get("name", ""))
        if len(norm_name) >= 8 and len(p_name) >= 8:
            if norm_name in p_name or p_name in norm_name:
                return p

    return None


def update_project(supabase, project_id: int, specs: dict,
                   recommendation: dict, dry_run: bool = True) -> bool:
    """Update a project row with technical specs and material recommendation."""

    update_data = {}
    for key in ["water_depth_m", "oil_capacity_bpd", "gas_capacity_mmcmd",
                 "hull_type", "field_name", "operator_name", "basin"]:
        val = specs.get(key)
        if val is not None:
            update_data[key] = val

    # If recommendation exists, populate legacy fields + new JSON column
    if recommendation:
        grades = recommendation.get("grades", [])
        apps = recommendation.get("applications", [])
        update_data["stainless_steel"] = ", ".join(grades[:4])  # top 4 grades
        update_data["application"] = ", ".join(apps[:5])         # top 5 applications
        update_data["recommendation_json"] = json.dumps(recommendation, ensure_ascii=False)

    if not update_data:
        return False

    if dry_run:
        name = specs.get("field_name") or specs.get("operator_name") or f"id={project_id}"
        log.info("  [DRY RUN] Would update project id=%d (%s): %s",
                 project_id, name, json.dumps(update_data, ensure_ascii=False, default=str))
        return True

    try:
        supabase.table("projects").update(update_data).eq("id", project_id).execute()
        return True
    except Exception as e:
        log.error("  Update failed for project id=%d: %s", project_id, e)
        return False


# ============================================================================
# 4. Main Flow
# ============================================================================

def run_backfill(dry_run: bool = True, match_only: bool = False):
    """Main backfill logic."""
    log.info("=" * 60)
    log.info("FPSO Technical Specs Backfill — %s", "DRY RUN" if dry_run else "EXECUTE")
    log.info("=" * 60)

    supabase = get_supabase()

    # Fetch all projects
    log.info("Fetching projects from Supabase...")
    projects = fetch_all_projects(supabase)
    log.info("  Found %d projects", len(projects))

    if match_only:
        # Only run material matching on projects that already have tech specs
        log.info("Match-only mode: running matching on projects with existing tech specs...")
        updated = 0
        matched = 0
        for p in projects:
            specs = {
                "water_depth_m": p.get("water_depth_m"),
                "oil_capacity_bpd": p.get("oil_capacity_bpd"),
                "gas_capacity_mmcmd": p.get("gas_capacity_mmcmd"),
                "hull_type": p.get("hull_type"),
                "field_name": p.get("field_name"),
                "operator_name": p.get("operator_name"),
                "basin": p.get("basin"),
            }
            has_any = any(v is not None and v != "" for v in specs.values())
            if not has_any:
                continue

            # Only update if recommendation_json is missing
            if p.get("recommendation_json") or p.get("stainless_steel"):
                continue

            recommendation = match_materials(specs)
            pid = p.get("id")
            if update_project(supabase, pid, specs, recommendation, dry_run=dry_run):
                updated += 1
                matched += 1
                log.info("  Matched: %s → %s (confidence: %s)",
                         p.get("name", "?"),
                         ", ".join(recommendation["grades"][:3]),
                         recommendation["confidence"])

        log.info("Match-only complete: %d projects matched", matched)
        return {"matched_only": matched, "total_projects": len(projects)}

    # Full backfill: load ANP data, match to projects, update
    log.info("Loading ANP FPSO records...")
    anp_records = load_anp_records()
    if not anp_records:
        log.info("No local snapshot. Trying direct CSV download...")
        anp_records = load_anp_from_csv_directly()
    if not anp_records:
        log.error("No ANP records available. Run ANP CSV adapter first or use --match-only.")
        return {"error": "No ANP records"}

    log.info("  Loaded %d ANP FPSO records", len(anp_records))

    updated = 0
    matched = 0
    skipped = 0
    examples = []

    for record in anp_records:
        specs = anp_record_to_specs(record)
        has_any = any(v is not None for v in specs.values() if not isinstance(v, str))
        has_any = has_any or any(v for v in [specs.get("hull_type"), specs.get("field_name"),
                                               specs.get("operator_name"), specs.get("basin")] if v)

        if not has_any:
            skipped += 1
            continue

        # Find matching project
        match = find_project_match(record, projects)
        if not match:
            skipped += 1
            continue

        # Run material matching
        recommendation = match_materials(specs)

        pid = match.get("id")
        if update_project(supabase, pid, specs, recommendation, dry_run=dry_run):
            updated += 1
            matched += 1
            facility = record.get("facility_name", "?")
            log.info("  %s project id=%d (%s) → %s (confidence: %s)",
                     "Would update" if dry_run else "Updated",
                     pid, facility,
                     ", ".join(recommendation["grades"][:3]),
                     recommendation["confidence"])

            if len(examples) < 5:
                examples.append({
                    "facility_name": facility,
                    "specs": {k: v for k, v in specs.items() if v},
                    "recommendation": recommendation,
                })

    log.info("=" * 60)
    log.info("Backfill complete:")
    log.info("  Total ANP records: %d", len(anp_records))
    log.info("  Projects updated:  %d", updated)
    log.info("  Skipped (no match or no data): %d", skipped)

    # Print examples
    if examples:
        log.info("--- Examples ---")
        for ex in examples:
            log.info("  %s", ex["facility_name"])
            log.info("    Specs: %s", json.dumps(ex["specs"], ensure_ascii=False))
            log.info("    Grades: %s", ex["recommendation"]["grades"])
            log.info("    Applications: %s", ex["recommendation"]["applications"])
            log.info("    Confidence: %s", ex["recommendation"]["confidence"])

    return {
        "total_anp_records": len(anp_records),
        "projects_updated": updated,
        "skipped": skipped,
        "examples": examples,
    }


# ============================================================================
# 5. CLI
# ============================================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Backfill FPSO technical specs and stainless steel matching"
    )
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Preview only, no writes (default)")
    parser.add_argument("--execute", action="store_true",
                        help="Actually write to Supabase")
    parser.add_argument("--match-only", action="store_true",
                        help="Only run material matching on projects with existing tech specs")
    args = parser.parse_args()

    dry_run = not args.execute

    try:
        result = run_backfill(dry_run=dry_run, match_only=args.match_only)
    except RuntimeError as e:
        log.error("%s", e)
        sys.exit(1)
    except Exception as e:
        log.error("Backfill failed: %s", e, exc_info=True)
        sys.exit(1)

    print("\n" + json.dumps(result, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
