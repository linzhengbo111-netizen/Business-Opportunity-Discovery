#!/usr/bin/env python3
"""
Backfill PDF text extraction for ANP Development Plans.

Batch processes all PDFs in crawler/data/anp_plans/, extracts text via
pdfplumber, parses technical specs (materials, media, parameters), and
updates candidate_events and projects tables in Supabase.

Usage:
  python crawler/scripts/backfill_pdf_parse.py              # full backfill
  python crawler/scripts/backfill_pdf_parse.py --dry-run     # parse only, no DB writes
  python crawler/scripts/backfill_pdf_parse.py --show N      # show N examples
  python crawler/scripts/backfill_pdf_parse.py --limit N     # process only N PDFs
"""

import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Ensure crawler/ is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from adapters.anp_development_plan import (
    extract_pdf_text,
    parse_technical_specs,
    KNOWN_BRAZILIAN_FIELDS,
    extract_field_name,
    extract_operator,
    extract_water_depth_from_text,
    extract_oil_capacity_from_text,
    extract_gas_capacity_from_text,
    extract_hull_type_from_text,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("backfill-pdf-parse")

BASE_DIR = Path(__file__).resolve().parent.parent  # crawler/
DATA_DIR = BASE_DIR / "data" / "anp_plans"

load_dotenv(BASE_DIR.parent / ".env")
SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("VITE_SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY")


def get_supabase():
    from supabase import create_client
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL and SUPABASE_ANON_KEY must be set in .env")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ---- Field name normalization for matching ---------------------------------

def field_name_from_filename(pdf_path: Path) -> str:
    """Extract a likely field name from a PDF filename.

    Examples:
        albacora.pdf          -> Albacora
        albacora_leste.pdf    -> Albacora Leste
        agua-grande.pdf       -> Agua Grande
        alto_do_rodrigues.pdf -> Alto do Rodrigues
    """
    stem = pdf_path.stem  # filename without .pdf
    # Replace underscores and hyphens with spaces
    name = stem.replace("_", " ").replace("-", " ")
    # Title case (but preserve known acronyms)
    name = name.title()
    return name


def match_projects_by_field(field_name: str, supabase) -> list[dict]:
    """Find projects matching a field name via case-insensitive containment search."""
    if not supabase:
        return []

    # Strategy 1: Direct ILIKE on field_name column
    try:
        r = supabase.table("projects") \
            .select("id,name,field_name,country,stainless_steel,application,water_depth_m,oil_capacity_bpd") \
            .ilike("field_name", f"%{field_name}%") \
            .execute()
        if r.data:
            return r.data
    except Exception:
        pass

    # Strategy 2: Case-insensitive containment on name column
    try:
        r = supabase.table("projects") \
            .select("id,name,field_name,country,stainless_steel,application,water_depth_m,oil_capacity_bpd") \
            .ilike("name", f"%{field_name}%") \
            .execute()
        if r.data:
            return r.data
    except Exception:
        pass

    # Strategy 3: Broad match — search by first word in field_name
    first_word = field_name.split()[0] if field_name.split() else field_name
    if len(first_word) > 3:
        try:
            r = supabase.table("projects") \
                .select("id,name,field_name,country,stainless_steel,application,water_depth_m,oil_capacity_bpd") \
                .ilike("field_name", f"%{first_word}%") \
                .execute()
            if r.data:
                return r.data
        except Exception:
            pass

    # Strategy 4: Broad match by first word in project name
    if len(first_word) > 3:
        try:
            r = supabase.table("projects") \
                .select("id,name,field_name,country,stainless_steel,application,water_depth_m,oil_capacity_bpd") \
                .ilike("name", f"%{first_word}%") \
                .execute()
            if r.data:
                return r.data
        except Exception:
            pass

    return []


def update_project_fields(project_id: int, specs: dict, water_depth, oil_cap,
                          gas_cap, hull_type, supabase) -> bool:
    """Update a single project row with parsed technical specs.

    Only writes fields that are currently null/empty in the target row,
    preserving existing data.
    """
    updates = {}

    stainless = specs.get("stainless_steel", "")
    application = specs.get("application", "")
    evidence = specs.get("evidence_quote", "")
    tech_params = specs.get("tech_params", {}) or {}

    if stainless:
        updates["stainless_steel"] = stainless
    if application:
        updates["application"] = application
    if water_depth:
        updates["water_depth_m"] = water_depth
    if oil_cap:
        updates["oil_capacity_bpd"] = oil_cap
    if gas_cap:
        updates["gas_capacity_mmcmd"] = gas_cap
    if hull_type:
        updates["hull_type"] = hull_type

    # Write extracted specs into recommendation_json
    rec_parts = []
    if stainless:
        rec_parts.append(f"materials: {stainless}")
    if specs.get("media"):
        rec_parts.append(f"media: {specs['media']}")
    if tech_params:
        for k, v in tech_params.items():
            rec_parts.append(f"{k}: {v}")
    if evidence:
        rec_parts.append(f"evidence: {evidence[:200]}")

    if rec_parts:
        updates["recommendation_json"] = json.dumps(
            {"source": "ANP development plan PDF extraction", "findings": rec_parts},
            ensure_ascii=False,
        )

    if not updates:
        return False

    try:
        supabase.table("projects").update(updates).eq("id", project_id).execute()
        return True
    except Exception as e:
        log.warning("  Update project %d failed: %s", project_id, str(e)[:100])
        return False


def run_backfill(dry_run: bool = False, limit: Optional[int] = None, show: int = 0):
    """Main backfill routine."""
    log.info("=" * 60)
    log.info("ANP PDF Backfill — Parse existing PDFs for material keywords")
    log.info("=" * 60)

    if not DATA_DIR.exists():
        log.error("Data directory not found: %s", DATA_DIR)
        sys.exit(1)

    pdf_files = sorted(DATA_DIR.glob("*.pdf"))
    log.info("Found %d PDF files in %s", len(pdf_files), DATA_DIR)

    if limit:
        pdf_files = pdf_files[:limit]
        log.info("Limited to %d PDFs", limit)

    supabase = None
    if not dry_run:
        supabase = get_supabase()

    # Statistics
    stats = {
        "total_pdfs": len(pdf_files),
        "parsed_ok": 0,
        "parsed_failed": 0,
        "material_found": 0,
        "projects_matched": 0,
        "projects_updated": 0,
        "examples": [],
    }

    for i, pdf_path in enumerate(pdf_files):
        log.info("[%d/%d] Processing: %s", i + 1, len(pdf_files), pdf_path.name)

        # Step 1: Extract text
        pdf_text = extract_pdf_text(str(pdf_path))
        if not pdf_text:
            stats["parsed_failed"] += 1
            continue
        stats["parsed_ok"] += 1

        # Step 2: Parse technical specs
        specs = parse_technical_specs(pdf_text)
        has_material = specs.get("has_material", False)
        if has_material:
            stats["material_found"] += 1

        # Also extract standard tech specs from PDF text
        water_depth = extract_water_depth_from_text(pdf_text)
        oil_cap = extract_oil_capacity_from_text(pdf_text)
        gas_cap = extract_gas_capacity_from_text(pdf_text)
        hull_type = extract_hull_type_from_text(pdf_text)
        operator = extract_operator(pdf_text)
        field_from_text = extract_field_name(pdf_text)

        # Step 3: Build example record (prefer PDFs with extracted data)
        if len(stats["examples"]) < 5 or (has_material and len(stats["examples"]) < 8):
            field_name_fn = field_name_from_filename(pdf_path)
            stats["examples"].append({
                "filename": pdf_path.name,
                "field_name_from_filename": field_name_fn,
                "field_name_from_text": field_from_text,
                "operator": operator,
                "materials": specs.get("stainless_steel", ""),
                "media": specs.get("media", ""),
                "application": specs.get("application", ""),
                "evidence_quote": specs.get("evidence_quote", "")[:300],
                "tech_params": specs.get("tech_params", {}),
                "water_depth_m": water_depth,
                "oil_capacity_bpd": oil_cap,
                "gas_capacity_mmcmd": gas_cap,
                "hull_type": hull_type,
                "has_material": has_material,
            })

        # Step 4: Find matching projects
        if not dry_run and supabase:
            field_name_fn = field_name_from_filename(pdf_path)
            # Try field_from_text first (from KNOWN_BRAZILIAN_FIELDS), then filename
            match_field = field_from_text or field_name_fn

            matched_projects = match_projects_by_field(match_field, supabase)
            if not matched_projects and field_from_text:
                # Retry with filename-derived name
                matched_projects = match_projects_by_field(field_name_fn, supabase)

            if matched_projects:
                stats["projects_matched"] += len(matched_projects)
                for proj in matched_projects:
                    # Update if project doesn't already have technical specs filled
                    existing_wd = proj.get("water_depth_m")
                    existing_oc = proj.get("oil_capacity_bpd")
                    existing_ss = proj.get("stainless_steel", "")
                    # Write if any new data available (water depth, oil cap, or materials)
                    has_new_data = (water_depth and not existing_wd) or \
                                   (oil_cap and not existing_oc) or \
                                   (has_material and not existing_ss)
                    if has_new_data:
                        if update_project_fields(proj["id"], specs, water_depth,
                                                 oil_cap, gas_cap, hull_type, supabase):
                            stats["projects_updated"] += 1
                            log.info("  Updated project #%d: %s (wd=%s, oil=%s, ss=%s)",
                                     proj["id"], proj.get("name", "?"),
                                     water_depth, oil_cap,
                                     specs.get("stainless_steel", "-")[:40])
                    else:
                        log.info("  Project #%d already has specs, skipping", proj["id"])

        log.info("  materials=%s, media=%s, app=%s",
                 specs.get("stainless_steel", "-")[:80],
                 specs.get("media", "-")[:60],
                 specs.get("application", "-")[:40])

    # ---- Report ----
    log.info("=" * 60)
    log.info("BACKFILL COMPLETE")
    log.info("=" * 60)
    log.info("  Total PDFs scanned:     %d", stats["total_pdfs"])
    log.info("  Successfully parsed:    %d", stats["parsed_ok"])
    log.info("  Failed to parse:        %d", stats["parsed_failed"])
    log.info("  Material keywords found: %d", stats["material_found"])
    log.info("  Projects matched:       %d", stats["projects_matched"])
    log.info("  Projects updated:       %d", stats["projects_updated"])

    # Show examples
    if stats["examples"]:
        log.info("")
        log.info("--- Example Extraction Results ---")
        for idx, ex in enumerate(stats["examples"]):
            log.info("")
            log.info("Example %d: %s", idx + 1, ex["filename"])
            log.info("  Field (filename):  %s", ex["field_name_from_filename"])
            log.info("  Field (from text): %s", ex["field_name_from_text"])
            log.info("  Operator:          %s", ex["operator"])
            log.info("  Materials:         %s", ex["materials"] or "(none found)")
            log.info("  Media:             %s", ex["media"] or "(none found)")
            log.info("  Application:       %s", ex["application"] or "(none found)")
            log.info("  Water depth:       %s m", ex["water_depth_m"])
            log.info("  Oil capacity:      %s bpd", ex["oil_capacity_bpd"])
            log.info("  Gas capacity:      %s MMcmd", ex["gas_capacity_mmcmd"])
            log.info("  Hull type:         %s", ex["hull_type"])
            log.info("  Evidence quote:    %s", ex["evidence_quote"][:200])

    return stats


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Backfill ANP PDF text extraction into candidate_events and projects tables"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse PDFs only, do not write to database")
    parser.add_argument("--show", type=int, default=0,
                        help="Show N example extractions and exit (no DB writes)")
    parser.add_argument("--limit", type=int, default=0,
                        help="Process only N PDFs")
    args = parser.parse_args()

    try:
        stats = run_backfill(
            dry_run=args.dry_run,
            limit=args.limit if args.limit > 0 else None,
            show=args.show,
        )

        # Print summary JSON
        print("\n" + json.dumps({
            "total_pdfs": stats["total_pdfs"],
            "parsed_ok": stats["parsed_ok"],
            "parsed_failed": stats["parsed_failed"],
            "material_found": stats["material_found"],
            "projects_matched": stats["projects_matched"],
            "projects_updated": stats["projects_updated"],
        }, indent=2))
    except Exception as e:
        log.error("Backfill failed: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
