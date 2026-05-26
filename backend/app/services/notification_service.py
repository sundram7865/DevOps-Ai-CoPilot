import httpx
from app.core.config import settings
from app.core.logging import logger


async def send_approval_request(
    incident_id: str,
    service: str,
    severity: str,
    root_cause: str,
    proposed_actions: list[dict],
) -> None:
    """
    Send Discord message requesting human approval.
    """
    if not settings.DISCORD_WEBHOOK_URL:
        logger.warning("discord_not_configured")
        return

    actions_text = "\n".join([
        f"• {a['action']} on {a['target']}: {a.get('reason', '')}"
        for a in proposed_actions
    ])

    severity_emoji = {
        "LOW": "🟡", "MEDIUM": "🟠", "HIGH": "🔴", "CRITICAL": "🚨"
    }.get(severity, "⚠️")

    message = {
        "embeds": [{
            "title": f"{severity_emoji} Incident #{incident_id[:8]} — Approval Required",
            "color": 15158332,  # red
            "fields": [
                {"name": "Service", "value": service, "inline": True},
                {"name": "Severity", "value": severity, "inline": True},
                {"name": "Root Cause", "value": root_cause[:500]},
                {"name": "Proposed Actions", "value": actions_text},
                {
                    "name": "Approve",
                    "value": f"POST http://backend:8000/incidents/{incident_id}/approve"
                },
            ],
        }]
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(settings.DISCORD_WEBHOOK_URL, json=message)
        logger.info("discord_approval_sent", incident_id=incident_id)
    except Exception as e:
        logger.error("discord_send_error", error=str(e))


async def send_resolution_summary(
    incident_id: str,
    service: str,
    severity: str,
    root_cause: str,
    action_taken: str,
    recovered: bool,
    mttr: int | None,
) -> None:
    """
    Send Discord message with incident resolution summary.
    """
    if not settings.DISCORD_WEBHOOK_URL:
        return

    status_emoji = "✅" if recovered else "❌"
    mttr_text = f"{mttr}s" if mttr else "unknown"

    message = {
        "embeds": [{
            "title": f"{status_emoji} Incident #{incident_id[:8]} — {'Resolved' if recovered else 'Failed'}",
            "color": 3066993 if recovered else 15158332,
            "fields": [
                {"name": "Service", "value": service, "inline": True},
                {"name": "Severity", "value": severity, "inline": True},
                {"name": "MTTR", "value": mttr_text, "inline": True},
                {"name": "Root Cause", "value": root_cause[:300]},
                {"name": "Action Taken", "value": action_taken},
            ],
        }]
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(settings.DISCORD_WEBHOOK_URL, json=message)
        logger.info("discord_resolution_sent", incident_id=incident_id)
    except Exception as e:
        logger.error("discord_resolution_error", error=str(e))