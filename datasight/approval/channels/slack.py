"""DataSight Slack notification channel."""

from __future__ import annotations

import logging
from datasight.config.settings import get_settings

logger = logging.getLogger("datasight.approval.slack")


def send_slack_notification(incident) -> None:
    """Send a Slack notification for an incident requiring approval."""
    settings = get_settings()
    if not settings.slack_webhook_url:
        logger.warning("Slack webhook URL not configured")
        return

    try:
        import requests

        severity_emoji = {"low": "🟡", "medium": "🟠", "high": "🔴", "critical": "🚨"}
        emoji = severity_emoji.get(incident.severity, "⚪")

        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"{emoji} DataSight Alert: Pipeline Failure"}
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*DAG:* `{incident.dag_id}`"},
                    {"type": "mrkdwn", "text": f"*Task:* `{incident.task_id}`"},
                    {"type": "mrkdwn", "text": f"*Severity:* {incident.severity.upper()}"},
                    {"type": "mrkdwn", "text": f"*Confidence:* {incident.confidence:.0%}"},
                ]
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Root Cause:* {incident.root_cause}"}
            },
        ]

        if incident.patches:
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Proposed Fix:* {incident.patches[0].description}"}
            })
            blocks.append({
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "✅ Approve Fix"},
                        "style": "primary",
                        "value": incident.id,
                        "action_id": "datasight_approve",
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "❌ Reject"},
                        "style": "danger",
                        "value": incident.id,
                        "action_id": "datasight_reject",
                    },
                ]
            })

        requests.post(
            settings.slack_webhook_url,
            json={"channel": settings.slack_channel, "blocks": blocks},
            timeout=10,
        )
        logger.info("Slack notification sent for incident %s", incident.id)

    except Exception as e:
        logger.error("Failed to send Slack notification: %s", e)
