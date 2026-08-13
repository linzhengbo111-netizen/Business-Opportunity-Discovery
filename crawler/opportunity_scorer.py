"""
Opportunity Scoring Engine (S5) — Python mirror
================================================

5-dimension quantitative scoring, same logic as src/lib/opportunity_scorer.ts.
Receives a project_data dict (snake_case, as assembled in auto_ingest_to_projects)
and returns a scoring result dict.

Dimensions (each 0-20, total 0-100):
  1. Procurement Probability
  2. Factory Match
  3. Reachability
  4. Project Value
  5. Information Confidence

Grade thresholds: A >= 80, B >= 60, C >= 40, D < 40
"""

import json
import re
import math
from datetime import datetime

# ---------------------------------------------------------------------------
# EPC contractor keywords (same as TypeScript)
# ---------------------------------------------------------------------------

EPC_KEYWORDS = [
    "SBM Offshore", "MODEC", "TechnipFMC", "Saipem", "BW Offshore",
    "Yinson", "Bumi Armada", "Teekay", "Altera", "Bluewater",
    "COSCO", "Sembcorp", "Keppel", "Hyundai Heavy", "Samsung Heavy",
    "Daewoo", "DSME", "McDermott", "Subsea 7", "Wood Group",
    "Worley", "Aker Solutions", "Petrofac", "Fluor",
]

FEED_FID_KEYWORDS = ["FEED", "FID", "front-end engineering", "final investment decision"]
EARLY_STAGE_KEYWORDS = ["concept", "pre-feasibility", "feasibility", "pre-FEED", "pre-FID"]

# Factory-producible grades (mirrors PRODUCIBLE_GRADE_SET in
# src/data/factory_capabilities.ts). Substring match, same as
# TypeScript isGradeProducible().
PRODUCIBLE_GRADES = [
    "304", "304L", "304H", "316", "316L", "316H", "316Ti", "317L",
    "321", "321H", "347", "347H", "904L", "309S", "310S",
    "Duplex 2205", "Super Duplex 2507", "Lean Duplex 2304",
    "Lean Duplex 2101", "Zeron 100", "S32760",
    "Inconel 625", "Inconel 825", "Incoloy 800", "Incoloy 800H",
    "Incoloy 800HT", "Incoloy 825", "Hastelloy C276", "Hastelloy C22",
    "Monel 400", "Monel K500", "6Mo (UNS S31254)", "Alloy 20",
    "254SMO", "UNS N08926",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_grade_producible(grade_name: str) -> bool:
    """Mirror TypeScript isGradeProducible(): exact or substring match."""
    normalized = (grade_name or "").strip()
    if not normalized:
        return False
    return any(g in normalized for g in PRODUCIBLE_GRADES)


def _has_epc_contractor(procurement_chain: str | None) -> bool:
    if not procurement_chain:
        return False
    lower = procurement_chain.lower()
    return any(kw.lower() in lower for kw in EPC_KEYWORDS)


def _score_in_bracket(bracket: tuple[int, int], factor: float) -> int:
    """Convert a 0-1 factor into an integer score within [bracket_min, bracket_max]."""
    lo, hi = bracket
    span = hi - lo
    clamped = max(0.0, min(1.0, factor))
    return round(lo + span * clamped)


def _score_to_grade(score: int) -> str:
    if score >= 80:
        return "A"
    if score >= 60:
        return "B"
    if score >= 40:
        return "C"
    return "D"


def _parse_recommendation(json_str: str | None) -> dict | None:
    """Parse recommendation_json and return the parsed object, or None."""
    if not json_str:
        return None
    try:
        parsed = json.loads(json_str)
        if isinstance(parsed, dict) and "grades" in parsed:
            return parsed
        return None
    except (json.JSONDecodeError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Dimension 1: Procurement Probability (0-20)
# ---------------------------------------------------------------------------

def _score_procurement(project: dict) -> tuple[int, str]:
    status = (project.get("status") or "").strip().lower()

    if status == "delivered":
        return 0, "项目已投产交付，无采购机会"

    procurement_chain = project.get("procurement_chain") or ""

    if status == "under construction":
        # Try to estimate procurement window from procurement_chain text
        # Look for date patterns like 2026-Q3, 2026H2, 2026/2027, etc.
        chain_upper = procurement_chain.upper()

        # Simple date extraction: look for year mentions near procurement window hints
        import re
        year_match = re.search(r'(\d{4})', procurement_chain)
        if year_match:
            est_year = int(year_match.group(1))
            now = datetime.now()
            now_months = now.year * 12 + now.month
            # Assume mid-year if only year found
            est_months = est_year * 12 + 6
            months_ahead = est_months - now_months

            if months_ahead <= 6:
                factor = max(0, 1 - (months_ahead - 0) / 6)
                score = _score_in_bracket((18, 20), factor)
                return score, f"在建项目，预计采购时间约{max(0, months_ahead)}个月内，紧迫度高"

            if months_ahead <= 12:
                factor = max(0, 1 - (months_ahead - 6) / 6)
                score = _score_in_bracket((14, 17), factor)
                return score, f"在建项目，预计采购时间约{months_ahead}个月内，有一定准备时间"

            # > 12 months out
            score = _score_in_bracket((10, 13), 0.3)
            return score, f"在建项目，预计采购时间窗较远（约{months_ahead}个月），建议持续监控"

        # No year in chain: mirror TS estimateProcurementWindow —
        # Under Construction implies procurement within 3-6 months.
        factor = 1 - 3 / 6
        score = _score_in_bracket((18, 20), factor)
        return score, "在建项目，预计采购时间窗为 3-6 个月，紧迫度高"

    if status == "planned":
        chain_upper = procurement_chain.upper()
        is_feed_fid = any(kw.upper() in chain_upper for kw in FEED_FID_KEYWORDS)
        is_early = any(kw.upper() in chain_upper for kw in EARLY_STAGE_KEYWORDS)

        if is_feed_fid:
            score = _score_in_bracket((10, 13), 0.7)
            return score, "规划中项目，处于FEED/FID阶段，采购临近"

        if is_early:
            score = _score_in_bracket((5, 9), 0.4)
            return score, "规划中项目，处于早期概念/可研阶段，采购较远"

        return _score_in_bracket((5, 9), 0.6), "规划中项目，阶段信息不明确"

    # Unknown status
    return 5, f"项目状态未知（{status or '无数据'}），按最低紧迫度赋分"


# ---------------------------------------------------------------------------
# Dimension 2: Factory Match (0-20)
# ---------------------------------------------------------------------------

def _score_factory_match(project: dict) -> tuple[int, str]:
    rec_json = project.get("recommendation_json")
    rec = _parse_recommendation(rec_json)

    if rec:
        grades = rec.get("grades", [])
        # Normalize legacy string grades (mirrors parseRecommendation in
        # material_matcher.ts): strings get in_factory_scope from
        # isGradeProducible().
        producible_count = 0
        for g in grades:
            if isinstance(g, dict):
                grade_name = g.get("grade") or g.get("name") or ""
                in_scope = g.get("in_factory_scope")
            else:
                grade_name = str(g)
                in_scope = None
            if in_scope is None:
                in_scope = _is_grade_producible(grade_name)
            if in_scope:
                producible_count += 1

        if producible_count >= 3:
            factor = min(1.0, (producible_count - 3) / 3)
            score = _score_in_bracket((18, 20), factor)
            return score, f"{producible_count} 种推荐材质在工厂生产能力范围内，匹配度优秀"

        if producible_count >= 1:
            factor = (producible_count - 1) / 2
            score = _score_in_bracket((12, 17), factor)
            return score, f"{producible_count} 种推荐材质可生产，部分匹配"

        return _score_in_bracket((0, 3), 0), "推荐材质均不在工厂生产能力范围内"

    # No recommendation_json
    return 5, "无推荐材质数据，无法评估工厂匹配度"


# ---------------------------------------------------------------------------
# Dimension 3: Reachability (0-20)
# ---------------------------------------------------------------------------

def _score_reachability(project: dict) -> tuple[int, str]:
    procurement_chain = project.get("procurement_chain") or ""
    operator_name = project.get("operator_name") or ""

    has_epc = _has_epc_contractor(procurement_chain)
    has_operator = bool(operator_name and operator_name.strip())
    has_chain = bool(procurement_chain and procurement_chain.strip())

    if has_epc:
        # Extract EPC names
        entities = [e.strip() for e in procurement_chain.split(",")]
        epc_names = [
            e for e in entities
            if any(kw.lower() in e.lower() for kw in EPC_KEYWORDS)
        ]
        epc_list = ", ".join(epc_names) if epc_names else "已知EPC承包商"
        score = _score_in_bracket((15, 20), 0.8)
        return score, f"已识别EPC承包商：{epc_list}，采购链清晰，可触达性高"

    if has_operator or has_chain:
        detail = f"已知业主/运营商：{operator_name}" if has_operator else "有采购链信息但未识别EPC承包商"
        factor = 0.7 if has_operator else 0.4
        score = _score_in_bracket((8, 14), factor)
        return score, f"{detail}，需进一步确认采购控制方"

    return _score_in_bracket((0, 7), 0.2), "无采购链实体信息，可触达性低"


# ---------------------------------------------------------------------------
# Dimension 4: Project Value (0-20)
# ---------------------------------------------------------------------------

def _score_value(project: dict) -> tuple[int, str]:
    oil = project.get("oil_capacity_bpd")
    gas = project.get("gas_capacity_mmcmd")

    # Convert to float if not None
    try:
        oil = float(oil) if oil is not None and oil != "" else None
    except (ValueError, TypeError):
        oil = None
    try:
        gas = float(gas) if gas is not None and gas != "" else None
    except (ValueError, TypeError):
        gas = None

    # Large: oil > 150k or gas > 10k
    if oil is not None and oil > 150000:
        factor = min(1.0, (oil - 150000) / 150000)
        score = _score_in_bracket((16, 20), factor)
        return score, f"大型项目，原油产能 {int(oil):,} bpd，材料需求量大"

    if gas is not None and gas > 10000:
        factor = min(1.0, (gas - 10000) / 10000)
        score = _score_in_bracket((16, 20), factor)
        return score, f"大型项目，天然气产能 {int(gas):,} MMcmd，材料需求量大"

    # Medium: oil 80k-150k
    if oil is not None and oil >= 80000:
        factor = (oil - 80000) / 70000
        score = _score_in_bracket((10, 15), factor)
        return score, f"中型项目，原油产能 {int(oil):,} bpd"

    # Small
    if oil is not None and oil > 0:
        factor = oil / 80000
        score = _score_in_bracket((0, 9), factor)
        return score, f"原油产能 {int(oil):,} bpd，规模较小"

    if gas is not None and gas > 0:
        factor = min(1.0, gas / 10000)
        score = _score_in_bracket((0, 9), factor)
        return score, f"天然气产能 {int(gas):,} MMcmd，规模一般"

    return 5, "无产能数据，按中等偏低规模评估"


# ---------------------------------------------------------------------------
# Dimension 5: Information Confidence (0-20)
# ---------------------------------------------------------------------------

def _score_confidence(project: dict) -> tuple[int, str]:
    conf = (project.get("confidence") or "").strip().lower()

    if conf == "high":
        score = _score_in_bracket((18, 20), 0.8)
        return score, "信息来源可信度高（官方/一手来源），决策依据充分"

    if conf == "medium":
        score = _score_in_bracket((10, 17), 0.6)
        return score, "信息来源可信度中等，建议结合其他渠道交叉验证"

    if conf == "low":
        score = _score_in_bracket((0, 9), 0.3)
        return score, "信息来源可信度低，需要进一步确认"

    return 5, "无可信度评估数据"


# ---------------------------------------------------------------------------
# Summary & action
# ---------------------------------------------------------------------------

def _generate_summary(total: int, grade: str) -> str:
    if grade == "A":
        return f"高分商机（{total}分）：采购紧迫、工厂匹配度高、可触达性强，建议优先跟进"
    if grade == "B":
        return f"良好商机（{total}分）：具备跟进价值，部分维度有提升空间"
    if grade == "C":
        return f"一般商机（{total}分）：信息缺口较多，建议补充情报后重新评估"
    return f"低分项目（{total}分）：当前不适合投入销售资源，等待条件变化"


def _action_for_grade(grade: str) -> str:
    if grade == "A":
        return "立即联系EPC承包商与业主，争取进入询价清单"
    if grade == "B":
        return "监控项目进展，准备技术方案与客户案例"
    if grade == "C":
        return "持续关注项目动态，补充信息缺口"
    return "低优先级，等待更多信息或项目阶段变化"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_opportunity(project_data: dict) -> dict:
    """
    Score a project's sales opportunity across 5 dimensions.

    Args:
        project_data: Dict with snake_case project fields (name, status, confidence,
                      procurement_chain, oil_capacity_bpd, gas_capacity_mmcmd,
                      operator_name, recommendation_json, etc.)

    Returns:
        Dict with totalScore, grade, dimensions (each with score + reasoning),
        summary, and recommendedAction.
    """
    procurement = _score_procurement(project_data)
    factory_match = _score_factory_match(project_data)
    reachability = _score_reachability(project_data)
    value = _score_value(project_data)
    confidence = _score_confidence(project_data)

    total = procurement[0] + factory_match[0] + reachability[0] + value[0] + confidence[0]
    grade = _score_to_grade(total)

    return {
        "totalScore": total,
        "grade": grade,
        "dimensions": {
            "procurement": {"score": procurement[0], "reasoning": procurement[1]},
            "factoryMatch": {"score": factory_match[0], "reasoning": factory_match[1]},
            "reachability": {"score": reachability[0], "reasoning": reachability[1]},
            "value": {"score": value[0], "reasoning": value[1]},
            "confidence": {"score": confidence[0], "reasoning": confidence[1]},
        },
        "summary": _generate_summary(total, grade),
        "recommendedAction": _action_for_grade(grade),
    }
