#!/usr/bin/env python3
"""Targeted phase recalibration — evidence-based corrections for rows the
AI backfill mislabeled.

The phase backfill misjudged rows whose only evidence is the ANP FPSO CSV
register: 'Start: YYYY' there is the year the unit BEGAN PRODUCTION
(投产年份, ANP "ANO DE INÍCIO DE OPERAÇÃO"), but the LLM read it as a future
schedule date and labeled producing units Construction/Procurement.

Corrections (verified against the ANP register + public first-oil reports):
    PETROBRAS 78              Construction -> Delivery   (first oil 2025-12-31)
    PETROBRAS 79              Procurement -> Delivery   (first oil 2026-05-01)
    FPSO Alexandre de Gusmão  Construction -> Delivery   (first oil 2025-05-24)

Safety: dry run by default (--write to persist), local JSON backup before
writing (mirrors backfill_phases.py).
"""
import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_SCRIPT_DIR)
sys.path.insert(0, _SCRIPT_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(_ROOT_DIR, ".env"))
from supabase import create_client

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("phase-recalibration")

# name -> (target_phase, evidence)
CORRECTIONS = [
    ("PETROBRAS 78", "Delivery",
     "ANP open data Start: 2025 (投产年份) | first oil 2025-12-31 "
     "(Petrobras/Seatrium, Jan 2026)"),
    ("PETROBRAS 79", "Delivery",
     "ANP open data Start: 2026 (投产年份) | first oil 2026-05-01, first "
     "offloading 2026-05-30 (Búzios 8, Hanwha Ocean EPC)"),
    ("FPSO Alexandre de Gusmão", "Delivery",
     "ANP open data Start: 2025 (投产年份) | first oil 2025-05-24 "
     "(Mero-4, S&P Global / TotalEnergies)"),
]


def main():
    ap = argparse.ArgumentParser(description="Evidence-based phase corrections")
    ap.add_argument("--write", action="store_true",
                    help="persist updates (default: dry run)")
    args = ap.parse_args()

    sb = create_client(os.environ["VITE_SUPABASE_URL"],
                       os.environ["VITE_SUPABASE_ANON_KEY"])
    table = sb.table("projects")

    before = []
    for name, _, _ in CORRECTIONS:
        resp = table.select("id, name, phase").eq("name", name).execute()
        for row in resp.data or []:
            before.append(row)
    log.info("Rows found: %d (write=%s)", len(before), args.write)

    if args.write and before:
        data_dir = os.path.join(_SCRIPT_DIR, "data")
        os.makedirs(data_dir, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = os.path.join(data_dir, f"phase_recalibration_backup_{stamp}.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(before, fh, ensure_ascii=False, indent=2)
        log.info("Backup written: %s", path)

    for row in before:
        match = next((c for c in CORRECTIONS if c[0] == row["name"]), None)
        if not match:
            continue
        target, evidence = match[1], match[2]
        log.info("  %-28s %s -> %s", row["name"][:28], row["phase"], target)
        log.info("    evidence: %s", evidence)
        if args.write:
            table.update({"phase": target}).eq("id", row["id"]).execute()

    if not args.write:
        log.info("DRY RUN — pass --write to persist.")


if __name__ == "__main__":
    main()
