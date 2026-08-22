#!/usr/bin/env python3
"""
Backfill demo-project timeline events + correct tech-spec values.

Adds 3 verified, traceable accepted events per demo project (from official
press releases / operator announcements) so each demo project has >= 3
accepted timeline events for the Feishu push analysis.

Also corrects tech-spec values that contradict the public record:
  - FPSO ALMIRANTE TAMANDARE: oil_capacity_bpd 270000 -> 225000
    (SBM Offshore LoI PR 2021-02-25: 225,000 bpd / 12 MMm3/d gas)
  - FPSO SEPETIBA: oil_capacity_bpd 225100 -> 180000,
    gas_capacity_mmcmd 15000 -> 12000
    (OEDigital 2019-12-11: 180,000 bpd / 12 MMsm3/d gas treatment)
  - FPSO BACALHAU: values already match public record (220,000 bpd), no change.

Every event carries source_name, source_url, publication_date and a verbatim
evidence_quote — all facts below are from the linked public sources
(SBM Offshore, Petrobras Agencia, MODEC, Equinor, World Oil, OEDigital).

Usage:
  python scripts/backfill_demo_events.py --dry-run
  python scripts/backfill_demo_events.py --execute
"""

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

from supabase import create_client  # noqa: E402

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("VITE_SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY")

EVENTS = [
    # ---- FPSO ALMIRANTE TAMANDARE (Buzios, Petrobras, SBM Offshore) ----
    {
        "canonical_project_id": "brazil-almirante-tamandare",
        "project_name_raw": "FPSO ALMIRANTE TAMANDARE",
        "country": "Brazil",
        "event_type": "FPSO_CONTRACT_AWARDED",
        "publication_date": "2021-02-25",
        "source_name": "SBM Offshore",
        "source_url": "https://www.sbmoffshore.com/sites/sbm-offshore/files/sbm-offshore/investors/investor-download-center/press-release/2021/SBM-Offshore-awarded-Letter-of-Intent-for-FPSO-Almirante-Tamandare-lease-and-operate-contract-by-Petrobras.pdf",
        "summary": "SBM Offshore signed a Letter of Intent with Petrobras for a 26.25-year lease and operate contract for the FPSO Almirante Tamandare, to be deployed at the Buzios field, Santos Basin. Unit designed for 225,000 bpd oil and 12 million m3/d gas, using the Fast4Ward MPF hull.",
        "evidence_quote": "SBM Offshore is pleased to announce that it has signed a Letter of Intent (LOI) together with Petroleo Brasileiro S.A. (Petrobras) for a 26.25 years lease and operate contract for the FPSO Almirante Tamandare.",
    },
    {
        "canonical_project_id": "brazil-almirante-tamandare",
        "project_name_raw": "FPSO ALMIRANTE TAMANDARE",
        "country": "Brazil",
        "event_type": "PRODUCTION_START",
        "publication_date": "2025-02-15",
        "source_name": "Petrobras Agencia",
        "source_url": "https://agencia.petrobras.com.br/en/w/negocio/fpso-almirante-tamandare-inicia-producao-no-pre-sal",
        "summary": "FPSO Almirante Tamandare started production on 02/15/2025 at the Buzios field, pre-salt Santos Basin. Capacity up to 225,000 bpd and 12 million m3 gas daily; sixth production system at Buzios, leased from SBM Offshore.",
        "evidence_quote": "The FPSO Almirante Tamandare started production today, 02/15, in the Buzios field, located in the pre-salt layer of the Santos Basin... the unit can produce up to 225,000 barrels of oil per day (bpd) and process 12 million cubic meters of gas daily.",
    },
    {
        "canonical_project_id": "brazil-almirante-tamandare",
        "project_name_raw": "FPSO ALMIRANTE TAMANDARE",
        "country": "Brazil",
        "event_type": "DELIVERED",
        "publication_date": "2025-02-16",
        "source_name": "SBM Offshore",
        "source_url": "https://www.marketscreener.com/quote/stock/SBM-OFFSHORE-N-V-6284/news/FPSO-Almirante-Tamandare-producing-and-on-hire-49103198/",
        "summary": "SBM Offshore announced the FPSO Almirante Tamandare is formally on hire as of February 16, 2025, after first oil and a 72-hour continuous production test leading to Final Acceptance.",
        "evidence_quote": "SBM Offshore announces that FPSO Almirante Tamandare is formally on hire as of February 16, 2025 after achieving first oil and completing a 72-hour continuous production test leading to Final Acceptance.",
    },
    # ---- FPSO BACALHAU (Equinor, MODEC) ----
    {
        "canonical_project_id": "brazil-bacalhau",
        "project_name_raw": "FPSO BACALHAU",
        "country": "Brazil",
        "event_type": "FPSO_CONTRACT_AWARDED",
        "publication_date": "2020-01-30",
        "source_name": "MODEC",
        "source_url": "https://post.tokyoipo.com/tdnet/20200130/202001301530/20200130453621/140120200130453621.pdf",
        "summary": "MODEC signed a Sales and Purchase Agreement with Equinor Brasil Energia Ltda for the Bacalhau FPSO, covering Front End Engineering Design (FEED) and pre-investment; EPCI execution as an option subject to Equinor FID.",
        "evidence_quote": "MODEC has been awarded a contract by Equinor Brasil Energia Ltda, a subsidiary of Equinor ASA, to supply an FPSO vessel for the Bacalhau field.",
    },
    {
        "canonical_project_id": "brazil-bacalhau",
        "project_name_raw": "FPSO BACALHAU",
        "country": "Brazil",
        "event_type": "FPSO_CONTRACT_AWARDED",
        "publication_date": "2021-06-03",
        "source_name": "MODEC",
        "source_url": "https://www.modec.com/news/assets/pdf/20210603_pr_Bacalhau_epci_en.pdf",
        "summary": "MODEC's Bacalhau FPSO project proceeds to EPCI (Engineering, Procurement, Construction and Installation) phase following Final Investment Decision by Equinor. First application of MODEC M350 hull.",
        "evidence_quote": "MODEC's Bacalhau FPSO Project for offshore Brazil proceeds to EPCI Phase with FID by Equinor.",
    },
    {
        "canonical_project_id": "brazil-bacalhau",
        "project_name_raw": "FPSO BACALHAU",
        "country": "Brazil",
        "event_type": "FIRST_OIL",
        "publication_date": "2025-10-16",
        "source_name": "MODEC",
        "source_url": "https://www.modec.com/news/2025/20251016_pr_Bacalhau.html",
        "summary": "FPSO Bacalhau achieved first oil on October 15, 2025 (announced 2025-10-16), Equinor's first pre-salt project in Brazil. Designed for 220,000 bpd, ~2050 m water depth, M350 hull.",
        "evidence_quote": "MODEC announced that the FPSO Bacalhau achieved first oil production on October 15, 2025, marking successful delivery for Equinor Brasil Energia Ltda.",
    },
    # ---- FPSO SEPETIBA (Mero, Petrobras, SBM Offshore) ----
    {
        "canonical_project_id": "brazil-sepetiba",
        "project_name_raw": "FPSO SEPETIBA",
        "country": "Brazil",
        "event_type": "FPSO_CONTRACT_AWARDED",
        "publication_date": "2019-06-12",
        "source_name": "World Oil",
        "source_url": "https://www.worldoil.com/news/2019/6/12/sbm-offshore-awarded-loi-operate-contracts-for-fpso-mero-2-lease",
        "summary": "Libra Consortium took final investment decision on Mero-2; SBM Offshore signed a binding Letter of Intent with Petrobras for a 22.5-year lease and operate contract for FPSO Mero-2 (later named Sepetiba).",
        "evidence_quote": "SBM Offshore awarded LOI, operate contracts for FPSO Mero 2 lease.",
    },
    {
        "canonical_project_id": "brazil-sepetiba",
        "project_name_raw": "FPSO SEPETIBA",
        "country": "Brazil",
        "event_type": "FPSO_CONTRACT_AWARDED",
        "publication_date": "2019-12-11",
        "source_name": "OEDigital",
        "source_url": "https://www.oedigital.com/news/473742-sbm-offshore-inks-fpso-sepetiba-contracts",
        "summary": "SBM Offshore firmed up contracts with Petrobras for the 22.5-year lease and operation of FPSO Sepetiba at Mero field, Santos Basin. Capacity 180,000 bpd, gas treatment 12 million m3/d, Fast4Ward program.",
        "evidence_quote": "SBM Offshore firmed up contracts with Brazil's Petroleo Brasileiro S.A. (Petrobras) for the 22.5-years lease and operation of the FPSO Sepetiba... capacity to process up to 180,000 barrels of oil per day (bpd).",
    },
    {
        "canonical_project_id": "brazil-sepetiba",
        "project_name_raw": "FPSO SEPETIBA",
        "country": "Brazil",
        "event_type": "FIRST_OIL",
        "publication_date": "2024-01-05",
        "source_name": "SBM Offshore",
        "source_url": "https://www.oilfieldtechnology.com/offshore-and-subsea/08012024/sbm-offshore-announces-formal-hire-of-fpso-sepetiba/",
        "summary": "FPSO Sepetiba formally on hire as of January 2, 2024, after first oil and 72-hour continuous production test leading to Final Acceptance. Mero unitized field, Santos Basin, ~2000 m water depth.",
        "evidence_quote": "SBM Offshore announced that the FPSO Sepetiba was formally on hire as of January 2, 2024, following the achievement of first oil and the successful completion of a 72-hour continuous production test.",
    },
]

# Corrected tech-spec values, traceable to the sources above.
PROJECT_CORRECTIONS = [
    {
        "name": "FPSO ALMIRANTE TAMANDARE",
        "update": {"oil_capacity_bpd": 225000},
        "reason": "SBM LoI PR 2021-02-25 + Petrobras 2025-02-15: 225,000 bpd (DB had 270,000)",
    },
    {
        "name": "FPSO SEPETIBA",
        "update": {"oil_capacity_bpd": 180000, "gas_capacity_mmcmd": 12000},
        "reason": "OEDigital 2019-12-11: 180,000 bpd, 12 MMsm3/d (DB had 225,100 / 15,000)",
    },
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.dry_run and not args.execute:
        parser.error("pass --dry-run or --execute")

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    events_table = supabase.table("candidate_events")
    projects_table = supabase.table("projects")

    # Skip events that already exist (idempotent by source_url).
    for ev in EVENTS:
        existing = events_table.select("id").eq("source_url", ev["source_url"]).execute()
        if existing.data:
            print(f"SKIP (exists): {ev['event_type']} {ev['publication_date']} {ev['project_name_raw']}")
            continue
        row = dict(ev)
        row["review_status"] = "accepted"
        row["confidence"] = "high"
        from datetime import datetime, timezone
        row["fetched_at"] = datetime.now(timezone.utc).isoformat()
        if args.execute:
            events_table.insert(row).execute()
        print(f"{'INSERT' if args.execute else 'WOULD-INSERT'}: {ev['event_type']} {ev['publication_date']} {ev['project_name_raw']}")

    for corr in PROJECT_CORRECTIONS:
        if args.execute:
            projects_table.update(corr["update"]).eq("name", corr["name"]).execute()
        print(f"{'UPDATE' if args.execute else 'WOULD-UPDATE'}: {corr['name']} {json.dumps(corr['update'])} — {corr['reason']}")


if __name__ == "__main__":
    main()
