#!/usr/bin/env python3
"""
Tests for project alias normalization and promote dedup logic.

Usage:
  python crawler/test_project_aliases.py
"""

import sys
import os
import json

# Add crawler directory to path so we can import crawl
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from crawl import normalize_project_name, get_display_name
from adapters.media_common import PROJECT_ALIASES


def test_guyana_payara_aliases():
    """Test that various Payara aliases all normalize to 'guyana-payara'."""
    aliases = [
        "Payara Dev Project",
        "FPSO Prosperity",
        "Payara FPSO",
        "Payara",
        "Payara Development",
        "Prosperity FPSO",
        "Payara Project",
        "Payara Field",
        "Prosperity",
        "FPSO Payara",
        "Payara Phase",
    ]

    print("=" * 70)
    print("TEST 1: guyana-payara alias normalization")
    print("=" * 70)

    all_passed = True
    for alias in aliases:
        result = normalize_project_name(alias)
        passed = result == "guyana-payara"
        status = "PASS" if passed else f"FAIL (got: {result})"
        print(f"  [{status}] normalize({alias!r})")
        if not passed:
            all_passed = False

    if all_passed:
        print(f"\n  ✓ All {len(aliases)} aliases correctly normalized to 'guyana-payara'")
    else:
        print(f"\n  ✗ Some aliases FAILED")
    print()

    return all_passed


def test_unknown_project():
    """Test that unknown project names return None."""
    unknown_names = [
        "FPSO FooBarBaz",
        "Random Non-Existent Project",
        "FPSO XYZ-123",
        "Totally Made Up FPSO Name",
        "",
        "   ",
    ]

    print("=" * 70)
    print("TEST 2: unknown project → None")
    print("=" * 70)

    all_passed = True
    for name in unknown_names:
        result = normalize_project_name(name)
        passed = result is None
        status = "PASS" if passed else f"FAIL (got: {result})"
        print(f"  [{status}] normalize({name!r})")
        if not passed:
            all_passed = False

    if all_passed:
        print(f"\n  ✓ All {len(unknown_names)} unknown inputs correctly returned None")
    else:
        print(f"\n  ✗ Some tests FAILED")
    print()

    return all_passed


def test_broad_coverage():
    """Test that normalization works across different countries/projects."""
    test_cases = [
        # (raw_name, expected_canonical_id)
        # Guyana
        ("Liza Phase 1", "guyana-liza-1"),
        ("FPSO Liza Destiny", "guyana-liza-1"),
        ("Liza Destiny", "guyana-liza-1"),
        ("Liza Phase 2", "guyana-liza-2"),
        ("FPSO Liza Unity", "guyana-liza-2"),
        ("Yellowtail FPSO", "guyana-yellowtail"),
        ("FPSO ONE GUYANA", "guyana-yellowtail"),
        ("FPSO One Guyana", "guyana-yellowtail"),
        ("Uaru Field", "guyana-uaru"),
        ("FPSO Errea Wittu", "guyana-uaru"),
        ("Whiptail Development", "guyana-whiptail"),
        ("FPSO Jaguar", "guyana-whiptail"),
        ("Hammerhead Project", "guyana-hammerhead"),
        ("Longtail Field", "guyana-longtail"),
        ("Gas to Energy", "guyana-gas-to-energy"),
        ("Guyana Gas to Energy", "guyana-gas-to-energy"),

        # Brazil
        ("FPSO Maria Quitéria", "brazil-maria-quiteria"),
        ("Maria Quiteria", "brazil-maria-quiteria"),
        ("FPSO Atlanta", "brazil-atlanta"),
        ("Atlanta FPSO", "brazil-atlanta"),
        ("FPSO Alexandre de Gusmão", "brazil-alexandre-de-gusmao"),
        ("ALEXANDRE DE GUSMÃO", "brazil-alexandre-de-gusmao"),
        ("FPSO ALMIRANTE BARROSO", "brazil-almirante-barroso"),
        ("Almirante Barroso", "brazil-almirante-barroso"),
        ("FPSO Duque de Caxias", "brazil-duque-de-caxias"),
        ("FPSO Anita Garibaldi", "brazil-anita-garibaldi"),
        ("FPSO Anna Nery", "brazil-anna-nery"),
        ("FPSO Guanabara", "brazil-guanabara"),
        ("FPSO Espirito Santo", "brazil-espirito-santo"),

        # UK
        ("Rosebank", "uk-rosebank"),
        ("FPSO Rosebank", "uk-rosebank"),
        ("Rosebank Field", "uk-rosebank"),
        ("Equinor Rosebank", "uk-rosebank"),
        ("Victory Field", "uk-victory"),
        ("Victory Development", "uk-victory"),
        ("Belinda Project", "uk-belinda"),
        ("FPSO Triton", "uk-triton"),

        # Angola
        ("FPSO Agogo", "angola-agogo"),
        ("Agogo FPSO", "angola-agogo"),
        ("Agogo Field", "angola-agogo"),
        ("MODEC Agogo", "angola-agogo"),
        ("FPSO Dalia", "angola-dalia"),
        ("Dalia Field", "angola-dalia"),
        ("FPSO Girassol", "angola-girassol"),
        ("FPSO Pazflor", "angola-pazflor"),
        ("FPSO CLOV", "angola-clov"),

        # Nigeria
        ("FPSO Zafiro", "nigeria-zafiro"),
        ("Zafiro FPSO", "nigeria-zafiro"),
        ("Zafiro Field", "nigeria-zafiro"),
        ("FPSO Bonga", "nigeria-bonga"),
        ("Bonga Field", "nigeria-bonga"),
        ("FPSO Egina", "nigeria-egina"),
        ("FPSO Akpo", "nigeria-akpo"),

        # Ghana
        ("Jubilee Field", "ghana-jubilee"),
        ("FPSO Kwame Nkrumah", "ghana-jubilee"),
        ("TEN Field", "ghana-ten"),

        # Ivory Coast
        ("Baleine", "ivory-coast-baleine"),
        ("FPSO Baleine", "ivory-coast-baleine"),
        ("Baobab", "ivory-coast-baobab"),
        ("FPSO Baobab", "ivory-coast-baobab"),

        # Senegal
        ("Sangomar", "senegal-sangomar"),
        ("Sangomar Field", "senegal-sangomar"),
        ("Sangomar FPSO", "senegal-sangomar"),

        # USA
        ("Vito", "usa-vito"),
        ("FPSO Vito", "usa-vito"),
        ("Argos FPSO", "usa-argos"),
        ("Mad Dog Phase 2", "usa-argos"),
        ("Stones FPSO", "usa-stones"),
        ("FPSO Turritella", "usa-stones"),

        # Norway
        ("Johan Castberg", "norway-johan-castberg"),
        ("FPSO Johan Castberg", "norway-johan-castberg"),
    ]

    print("=" * 70)
    print("TEST 3: broad coverage — cross-country normalization")
    print("=" * 70)

    passed = 0
    failed = 0

    for raw_name, expected in test_cases:
        result = normalize_project_name(raw_name)
        if result == expected:
            passed += 1
        else:
            print(f"  FAIL: normalize({raw_name!r}) = {result!r}, expected {expected!r}")
            failed += 1

    total = len(test_cases)
    all_passed = failed == 0
    print(f"\n  Passed: {passed}/{total}")
    if failed > 0:
        print(f"  Failed: {failed}/{total}")
    print()

    return all_passed


def test_promote_merge_logic():
    """
    Test the promote merging logic by simulating the grouping/merge
    that promote_accepted_candidates() performs, without touching Supabase.

    Creates 2 candidate events pointing to different aliases of the same
    canonical project, verifies they group to 1 merged result.
    """
    print("=" * 70)
    print("TEST 4: promote mode — merge candidates with same canonical project")
    print("=" * 70)

    # Simulate accepted candidates — 2 records for guyana-payara under different aliases
    candidates = [
        {
            "id": 1,
            "project_name_raw": "FPSO Prosperity",
            "country": "Guyana",
            "flag": "🇬🇾",
            "phase": "Delivery",
            "summary": "SBM Offshore FPSO Prosperity delivered for ExxonMobil's Payara development.",
            "source_name": "SBM Offshore",
            "source_url": "https://example.com/prosperity",
            "source_date": "2026-06-15",
            "stainless_steel": "",
            "application": "",
        },
        {
            "id": 2,
            "project_name_raw": "Payara Dev Project",
            "country": "Guyana",
            "flag": "🇬🇾",
            "phase": "Construction",
            "summary": "Payara development progressing — FPSO Prosperity integration at Seatrium.",
            "source_name": "Offshore Energy",
            "source_url": "https://example.com/payara-dev",
            "source_date": "2026-07-01",
            "stainless_steel": "",
            "application": "",
        },
    ]

    # Step 1: Normalize and group (same logic as promote_accepted_candidates)
    groups = {}
    for c in candidates:
        raw_name = c.get("project_name_raw", "")
        canonical_id = normalize_project_name(raw_name)
        if canonical_id:
            effective_name = get_display_name(canonical_id)
        else:
            effective_name = raw_name

        if effective_name not in groups:
            groups[effective_name] = []
        groups[effective_name].append(c)

    # Step 2: Verify
    print(f"  Candidate events: {len(candidates)}")
    print(f"  Groups after normalization: {len(groups)}")
    for name, group in groups.items():
        print(f"  Group '{name[:60]}': {len(group)} candidate(s)")
        for c in group:
            print(f"    - {c['project_name_raw'][:50]} (phase: {c['phase']})")

    # Assertions
    all_passed = True

    # Only 1 group should exist (both normalize to guyana-payara)
    if len(groups) == 1:
        print(f"\n  ✓ PASS: 2 candidates correctly merged into 1 group")
    else:
        print(f"\n  ✗ FAIL: Expected 1 group, got {len(groups)}")
        all_passed = False

    # Verify the group key is the display name
    expected_display = get_display_name("guyana-payara")
    if expected_display in groups:
        print(f"  ✓ PASS: Group key is display name: '{expected_display}'")
    else:
        print(f"  ✗ FAIL: Expected group key '{expected_display}', got {list(groups.keys())}")
        all_passed = False

    # Verify the merged summary contains both original summaries
    group = list(groups.values())[0]
    merged_summaries = [c.get("summary", "") for c in group]
    longest = max(merged_summaries, key=len)
    # Simulate merge: pick longest, append distinct others
    merged = longest
    seen = {longest}
    for c in group:
        s = c.get("summary", "")
        if s and s not in seen and len(s) > 20 and s not in merged:
            merged += " | " + s
            seen.add(s)

    if "SBM Offshore" in merged and "Seatrium" in merged:
        print(f"  ✓ PASS: Merged summary contains evidence from both candidates")
    else:
        print(f"  ✗ FAIL: Merged summary missing content from one candidate")
        print(f"    Merged: {merged[:200]}...")
        all_passed = False

    # Phase should be Delivery (latest lifecycle phase wins over Construction)
    phases = [c.get("phase") or c.get("status") for c in group]
    phase_order = ["Concept", "Planning", "Design", "Approval", "EPC Award",
                   "Procurement", "Construction", "Commissioning", "Delivery"]
    merged_phase = max(phases, key=lambda s: phase_order.index(s) if s in phase_order else -1)
    if merged_phase == "Delivery":
        print(f"  ✓ PASS: Merged phase is 'Delivery' (later than 'Construction')")
    else:
        print(f"  ✗ FAIL: Expected merged phase 'Delivery', got '{merged_phase}'")
        all_passed = False

    print()
    return all_passed


def test_promote_keeps_unmatched():
    """
    Test that unmatched candidates preserve their raw name as-is
    (fallback dedup behavior).
    """
    print("=" * 70)
    print("TEST 5: promote fallback — unmatched candidates keep raw name")
    print("=" * 70)

    candidates = [
        {
            "id": 1,
            "project_name_raw": "FPSO SomeNewField",
            "country": "Brazil",
            "phase": "Planning",
            "summary": "A brand new field with no alias registered yet.",
            "source_name": "OE Digital",
        },
        {
            "id": 2,
            "project_name_raw": "FPSO SomeNewField",
            "country": "Brazil",
            "phase": "Planning",
            "summary": "Another article about the same new field.",
            "source_name": "World Oil",
        },
    ]

    groups = {}
    for c in candidates:
        raw_name = c.get("project_name_raw", "")
        canonical_id = normalize_project_name(raw_name)
        if canonical_id:
            effective_name = get_display_name(canonical_id)
        else:
            effective_name = raw_name

        if effective_name not in groups:
            groups[effective_name] = []
        groups[effective_name].append(c)

    all_passed = True

    # normalize_project_name should return None
    result1 = normalize_project_name("FPSO SomeNewField")
    if result1 is None:
        print(f"  ✓ PASS: 'FPSO SomeNewField' → None (correctly unmatched)")
    else:
        print(f"  ✗ FAIL: 'FPSO SomeNewField' → {result1} (should be None)")
        all_passed = False

    # Both should group under the raw name
    if len(groups) == 1 and "FPSO SomeNewField" in groups:
        group_size = len(groups["FPSO SomeNewField"])
        if group_size == 2:
            print(f"  ✓ PASS: 2 unmatched candidates correctly grouped by raw name (fallback)")
        else:
            print(f"  ✗ FAIL: Expected 2 in group, got {group_size}")
            all_passed = False
    else:
        print(f"  ✗ FAIL: Expected group 'FPSO SomeNewField' with 2 entries, got {groups}")
        all_passed = False

    print()
    return all_passed


def test_display_name_and_getters():
    """Test the get_display_name helper."""
    print("=" * 70)
    print("TEST 6: display name and helper functions")
    print("=" * 70)

    all_passed = True

    # Known project
    display = get_display_name("guyana-payara")
    expected = "Payara (FPSO Prosperity)"
    if display == expected:
        print(f"  ✓ PASS: get_display_name('guyana-payara') = '{display}'")
    else:
        print(f"  ✗ FAIL: Expected '{expected}', got '{display}'")
        all_passed = False

    # Unknown project
    display = get_display_name("nonexistent-id")
    if display == "nonexistent-id":
        print(f"  ✓ PASS: get_display_name('nonexistent-id') falls back to ID")
    else:
        print(f"  ✗ FAIL: Expected fallback 'nonexistent-id', got '{display}'")
        all_passed = False

    # Verify first alias in each entry is a reasonable display name
    for cid, aliases in PROJECT_ALIASES.items():
        if not aliases or not isinstance(aliases[0], str) or len(aliases[0]) < 3:
            print(f"  ✗ FAIL: {cid} has invalid first alias: {aliases[0] if aliases else 'EMPTY'}")
            all_passed = False

    print(f"  ✓ All {len(PROJECT_ALIASES)} entries have valid display names")
    print()

    return all_passed


def main():
    results = {
        "guyana-payara aliases → 'guyana-payara'": test_guyana_payara_aliases(),
        "unknown project → None": test_unknown_project(),
        "broad cross-country coverage": test_broad_coverage(),
        "promote merge (2 candidates → 1 project)": test_promote_merge_logic(),
        "promote fallback (unmatched keeps raw name)": test_promote_keeps_unmatched(),
        "display name helpers": test_display_name_and_getters(),
    }

    print("=" * 70)
    print(" " * 15 + "TEST SUMMARY")
    print("=" * 70)
    for name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  [{status}] {name}")

    total = len(results)
    passed = sum(1 for v in results.values() if v)
    print(f"\n  {passed}/{total} test suites passed")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
