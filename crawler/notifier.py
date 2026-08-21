#!/usr/bin/env python3
"""
Notification module — sends Feishu (Lark) push notifications to subscribers
when new projects match their subscription criteria.

Flow:
  1. Get tenant_access_token via LARK_APP_ID + LARK_APP_SECRET.
  2. Query user_subscriptions table for all subscribers.
  3. For each new/updated project, check if it matches any subscription.
  4. If match: send Feishu card message via webhook (preferred) or direct message.

Rate limit: 100 requests/minute for Feishu API. This module batches sends
with a 600ms minimum interval.
"""

import os
import time
import json
import logging
from datetime import datetime, timezone

import requests

log = logging.getLogger("fpso-notifier")

# ---- Feishu API endpoints ----

LARK_TENANT_TOKEN_URL = (
    "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
)
LARK_SEND_MESSAGE_URL = (
    "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id"
)
LARK_WEBHOOK_URL_TEMPLATE = "{webhook_url}"  # user-supplied webhook

# ---- Config ----

LARK_APP_ID = os.getenv("LARK_APP_ID", "")
LARK_APP_SECRET = os.getenv("LARK_APP_SECRET", "")

# Min interval between Feishu API calls (seconds) to respect 100/min rate limit
MIN_API_INTERVAL = 0.7

# ---- Globals ----

_tenant_token: str | None = None
_tenant_token_expiry: float = 0.0  # Unix timestamp


def _get_tenant_access_token() -> str | None:
    """Fetch or refresh tenant_access_token.

    Tokens expire after ~2 hours. We cache and reuse until < 5 min remaining.
    """
    global _tenant_token, _tenant_token_expiry

    now = time.time()
    if _tenant_token and now < _tenant_token_expiry - 300:
        return _tenant_token

    if not LARK_APP_ID or not LARK_APP_SECRET:
        log.warning("LARK_APP_ID or LARK_APP_SECRET not set — cannot get tenant_token")
        return None

    try:
        resp = requests.post(
            LARK_TENANT_TOKEN_URL,
            json={"app_id": LARK_APP_ID, "app_secret": LARK_APP_SECRET},
            timeout=15,
        )
        data = resp.json()
        if data.get("code") != 0:
            log.error("Tenant token error: %s (code=%s)", data.get("msg"), data.get("code"))
            return None

        _tenant_token = data["tenant_access_token"]
        _tenant_token_expiry = now + data.get("expire", 7200)  # default 2h
        log.info("Tenant access token refreshed (expires in %ds)", data.get("expire", 7200))
        return _tenant_token
    except Exception:
        log.error("Tenant token request failed", exc_info=True)
        return None


# Phase → procurement window estimate. Mirrors the TS engine's
# estimateProcurementWindow (src/lib/material_matcher.ts) phase rules, so card
# values stay consistent with the frontend's displayed estimates.
_PHASE_WINDOW = {
    "procurement": "0-3 个月",
    "epc award": "2-4 个月",
    "construction": "3-6 个月",
    "approval": "6-12 个月",
    "design": "12-18 个月",
    "planning": "12 个月以上",
    "concept": "12 个月以上",
    "commissioning": "时间未定",
    "delivery": "时间未定",
}

# Legacy status values (pre migration-025) tolerated by the scorer.
_LEGACY_PHASE = {
    "delivered": "Delivery",
    "completed": "Delivery",
    "under construction": "Construction",
    "planned": "Planning",
}


def _procurement_window(phase: str) -> str:
    """Estimate procurement window from project phase.

    Phase-based only (no timeline events available in notifier context).
    Returns 待补充 when phase is unknown.
    """
    raw = (phase or "").strip()
    if not raw:
        return "待补充"
    norm = _LEGACY_PHASE.get(raw.lower(), raw).lower()
    return _PHASE_WINDOW.get(norm, "待补充")


def _parse_recommendation(project: dict) -> dict:
    """Parse recommendation_json (JSONB may arrive as dict or str)."""
    rec = project.get("recommendation_json")
    if isinstance(rec, str):
        try:
            rec = json.loads(rec)
        except Exception:
            rec = None
    return rec if isinstance(rec, dict) else {}


def _recommended_grades(project: dict, rec: dict) -> list[str]:
    """Recommended stainless grades: recommendation_json.grades first,
    fall back to the legacy stainless_steel text field."""
    grades: list[str] = []
    for g in rec.get("grades") or []:
        if isinstance(g, dict):
            name = g.get("grade") or g.get("name") or ""
        else:
            name = str(g)
        name = name.strip()
        if name and name not in grades:
            grades.append(name)
    if not grades:
        for g in (project.get("stainless_steel") or "").split(","):
            g = g.strip()
            if g and g not in grades:
                grades.append(g)
    return grades


def _recommended_applications(project: dict, rec: dict) -> list[str]:
    """Recommended products/applications: recommendation_json.applications
    first, fall back to the legacy application text field."""
    apps: list[str] = []
    for a in rec.get("applications") or []:
        a = str(a).strip()
        if a and a not in apps:
            apps.append(a)
    if not apps:
        for a in (project.get("application") or "").split(","):
            a = a.strip()
            if a and a not in apps:
                apps.append(a)
    return apps


def _score_dict(project: dict) -> dict | None:
    """Parse opportunity_score (JSONB may arrive as dict or str)."""
    score = project.get("opportunity_score")
    if isinstance(score, str):
        try:
            score = json.loads(score)
        except Exception:
            score = None
    return score if isinstance(score, dict) else None


def _build_card_message(
    project: dict,
    app_url: str = "https://business-opportunity-discovery.linzhengbo111.workers.dev",
    is_update: bool = False,
) -> dict:
    """Build a Feishu card message showing the project's core profile directly.

    All values come from real project fields; missing short fields show
    待补充, missing long lists are omitted entirely.

    Args:
        project: project dict from Supabase (name, country, phase, summary,
            procurement_chain, stainless_steel, application,
            recommendation_json, opportunity_score, source_url, source_name).
        is_update: if True, prepend [Update] tag and use red-tinted header.
    """
    header_color = "red" if is_update else "blue"
    title_prefix = "[Update] " if is_update else ""

    name = (project.get("name") or "未命名项目")[:60]
    summary = (project.get("summary") or "").strip()
    country = (project.get("country") or "").strip() or "待补充"
    phase = (project.get("phase") or project.get("status") or "").strip() or "待补充"
    window = _procurement_window(phase)
    chain = (project.get("procurement_chain") or "").strip() or "待补充"
    source_url = (project.get("source_url") or "").strip()
    source_name = (project.get("source_name") or "").strip()

    rec = _parse_recommendation(project)
    grades = _recommended_grades(project, rec)
    apps = _recommended_applications(project, rec)

    score_info = _score_dict(project)
    if score_info and score_info.get("totalScore") is not None and score_info.get("grade"):
        score_text = f"{score_info['totalScore']} 分 · {score_info['grade']} 级"
    else:
        score_text = "待补充"
    action = (score_info or {}).get("recommendedAction") or ""

    elements: list[dict] = []

    if is_update:
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": (
                    "🔔 **项目更新** — 检测到新事件 "
                    f"({datetime.now(timezone.utc).strftime('%Y-%m-%d')})"
                ),
            },
        })

    if summary:
        content = summary[:240]
        if len(summary) > 240:
            content += "..."
        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": content},
        })

    # Two-column field grid: country/phase, score/window; EPC full width.
    elements.append({
        "tag": "div",
        "fields": [
            {
                "is_short": True,
                "text": {"tag": "lark_md", "content": f"**国家：** {country}"},
            },
            {
                "is_short": True,
                "text": {"tag": "lark_md", "content": f"**阶段：** {phase}"},
            },
            {
                "is_short": True,
                "text": {"tag": "lark_md", "content": f"**机会评分：** {score_text}"},
            },
            {
                "is_short": True,
                "text": {"tag": "lark_md", "content": f"**采购时间窗（预估）：** {window}"},
            },
            {
                "is_short": False,
                "text": {"tag": "lark_md", "content": f"**EPC/承包商：** {chain}"},
            },
        ],
    })

    if apps:
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"**推荐产品：** {'、'.join(apps[:12])}",
            },
        })

    if grades:
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"**推荐不锈钢牌号：** {'、'.join(grades[:12])}",
            },
        })

    if action:
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"**下一步行动：** {action}",
            },
        })

    elements.append({
        "tag": "action",
        "actions": [
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "View Details"},
                "type": "primary",
                "url": f"{app_url}/database?project={name}",
            }
        ],
    })

    if source_url or source_name:
        if source_url and source_name:
            source_text = f"来源：{source_name} · [原文链接]({source_url})"
        elif source_url:
            source_text = f"[原文链接]({source_url})"
        else:
            source_text = f"来源：{source_name}"
        elements.append({
            "tag": "note",
            "elements": [{"tag": "lark_md", "content": source_text}],
        })

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"{title_prefix}{name}",
                },
                "template": header_color,
            },
            "elements": elements,
        },
    }


def _send_via_webhook(webhook_url: str, card: dict) -> bool:
    """Send card message via Feishu webhook URL (bot/custom bot)."""
    try:
        resp = requests.post(webhook_url, json=card, timeout=15)
        data = resp.json()
        if data.get("code") != 0 and data.get("StatusCode") != 0:
            log.warning("Webhook send failed: %s", data.get("msg", resp.text[:120]))
            return False
        return True
    except Exception:
        log.error("Webhook send error", exc_info=True)
        return False


def _send_via_api(open_id: str, card: dict) -> bool:
    """Send card message via Feishu IM API (direct message to user)."""
    token = _get_tenant_access_token()
    if not token:
        return False

    payload = {
        "receive_id": open_id,
        "msg_type": "interactive",
        "content": json.dumps(card["card"]),
    }

    try:
        resp = requests.post(
            LARK_SEND_MESSAGE_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=15,
        )
        data = resp.json()
        if data.get("code") != 0:
            log.warning("API send to %s failed: %s", open_id, data.get("msg"))
            return False
        return True
    except Exception:
        log.error("API send error for %s", open_id, exc_info=True)
        return False


def _project_matches_subscription(
    project: dict,
    sub_industries: list[str],
    sub_countries: list[str],
    followed_ids: list[str],
) -> tuple[bool, bool]:
    """Check if project matches a user's subscription criteria.

    Returns:
        (is_match, is_update): is_match = matches subscription.
        is_update = the project is in the user's followed_project_ids list
                    (indicating this is an update to an existing followed project,
                     not a brand-new project match).
    """
    if not sub_industries and not sub_countries and not followed_ids:
        return False, False

    project_industry = (project.get("industry") or "").lower()
    project_country = (project.get("country") or "").lower()
    project_name = (project.get("name") or "")

    # Check followed projects (exact name match on canonical name)
    is_update = False
    if followed_ids and project_name:
        # followed_project_ids stores canonical project names
        for fid in followed_ids:
            if fid.lower() == project_name.lower():
                is_update = True
                return True, True

    # Check industry match
    industry_match = False
    if sub_industries:
        for ind in sub_industries:
            if ind.lower() in project_industry:
                industry_match = True
                break

    # Check country match
    country_match = False
    if sub_countries:
        for cty in sub_countries:
            if cty.lower() in project_country or project_country in cty.lower():
                country_match = True
                break

    # Match logic: if both industry AND country are specified, both must match.
    # If only one is specified, that one must match.
    if sub_industries and sub_countries:
        is_match = industry_match and country_match
    elif sub_industries:
        is_match = industry_match
    elif sub_countries:
        is_match = country_match
    else:
        is_match = False

    return is_match, False


def notify_subscribers(supabase, new_projects: list[dict]) -> dict:
    """Notify subscribers about new/updated projects.

    Args:
        supabase: Supabase client instance.
        new_projects: list of project dicts that were newly created or updated.
            Each dict must have: name, country, industry, status, summary.

    Returns:
        dict: { "notified": int, "skipped": int, "errors": int }
    """
    if not LARK_APP_ID or not LARK_APP_SECRET:
        log.info("LARK_APP_ID/LARK_APP_SECRET not set — skipping notifications")
        return {"notified": 0, "skipped": 0, "errors": 0}

    if not new_projects:
        log.info("No new projects to notify about")
        return {"notified": 0, "skipped": 0, "errors": 0}

    log.info("=" * 54)
    log.info("NOTIFIER: checking subscriptions for %d project(s)", len(new_projects))

    # Fetch all subscriptions
    subs_table = supabase.table("user_subscriptions")
    all_subs = []
    offset = 0
    while True:
        resp = subs_table.select("*").range(offset, offset + 999).execute()
        batch = resp.data or []
        if not batch:
            break
        all_subs.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000

    if not all_subs:
        log.info("No subscriptions found — nothing to notify")
        return {"notified": 0, "skipped": 0, "errors": 0}

    log.info("Found %d subscription(s)", len(all_subs))

    prewarm_token = _get_tenant_access_token()
    if not prewarm_token:
        log.warning("Cannot get tenant_access_token — webhook sends will still work, API sends will fail")

    notified = 0
    skipped = 0
    errors = 0

    for sub in all_subs:
        user_open_id = sub.get("user_open_id", "")
        sub_industries = sub.get("subscribed_industries") or []
        sub_countries = sub.get("subscribed_countries") or []
        followed_ids = sub.get("followed_project_ids") or []
        webhook_url = (sub.get("webhook_url") or "").strip()

        if not user_open_id:
            continue

        for project in new_projects:
            is_match, is_update = _project_matches_subscription(
                project, sub_industries, sub_countries, followed_ids
            )

            if not is_match:
                skipped += 1
                continue

            project_name = project.get("name", "")[:60]
            log.info(
                "  MATCH: user=%s project=%s (update=%s)",
                user_open_id, project_name, is_update,
            )

            card = _build_card_message(project, is_update=is_update)

            # Send: prefer webhook, fallback to direct message API
            sent = False
            if webhook_url:
                sent = _send_via_webhook(webhook_url, card)
            else:
                sent = _send_via_api(user_open_id, card)

            if sent:
                notified += 1
            else:
                errors += 1

            # Rate limit: respect 100/min
            time.sleep(MIN_API_INTERVAL)

    log.info(
        "Notifier complete: %d sent, %d skipped (no match), %d errors",
        notified, skipped, errors,
    )
    return {"notified": notified, "skipped": skipped, "errors": errors}
