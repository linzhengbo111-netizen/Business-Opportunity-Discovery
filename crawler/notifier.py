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


def _build_card_message(
    project_name: str,
    country: str,
    industry: str,
    status: str,
    summary: str,
    project_id: str,
    app_url: str = "https://business-opportunity-discovery.pages.dev",
    is_update: bool = False,
) -> dict:
    """Build a Feishu card message for a project.

    Args:
        is_update: if True, prepend [Update] tag and use red-tinted header.
    """
    tag = "Update" if is_update else "New"
    header_color = "red" if is_update else "blue"
    title_prefix = "[Update] " if is_update else ""

    card = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"{title_prefix}{project_name}",
                },
                "template": header_color,
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": (
                            f"**Country:** {country or 'N/A'}\n"
                            f"**Industry:** {industry or 'N/A'}\n"
                            f"**Status:** {status or 'N/A'}\n\n"
                            f"{summary[:300]}{'...' if len(summary or '') > 300 else ''}"
                        ),
                    },
                },
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "View Details"},
                            "type": "primary",
                            "url": f"{app_url}/database?project={project_name}",
                        }
                    ],
                },
            ],
        },
    }

    # Add update tag as a note at top
    if is_update:
        card["card"]["elements"].insert(
            0,
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"🔔 **Project Update** — new event detected ({datetime.now(timezone.utc).strftime('%Y-%m-%d')})",
                },
            },
        )

    return card


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

            card = _build_card_message(
                project_name=project.get("name", ""),
                country=project.get("country", ""),
                industry=project.get("industry", ""),
                status=project.get("phase") or project.get("status", ""),
                summary=project.get("summary", ""),
                project_id=project.get("name", ""),
                is_update=is_update,
            )

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
