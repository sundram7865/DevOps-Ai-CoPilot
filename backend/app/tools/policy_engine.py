from app.core.logging import logger


# ── Policy configuration ──────────────────────
# AUTO: agent executes without human approval (LOW/MEDIUM severity)
# MANUAL: requires human approval (HIGH/CRITICAL severity)

POLICY = {
    "auto": [
        "restart_container",    # safe — container just restarts
        "verify_service_health", # read-only
        "get_container_stats",  # read-only
        "scale_service",        # only scale UP workers
        "stop_container",       # only for non-critical services
    ],
    "manual": [
        "rollback_deploy",      # high risk — changes running image
        "restart_database",     # very high risk
        "delete_data",          # destructive
        "scale_service_down",   # could cause downtime
    ],
}

# Services that always require manual approval regardless of action
CRITICAL_SERVICES = ["postgres", "redis"]


def check_policy(action: str, target: str, severity: str) -> dict:
    """
    Validate if an action can be auto-executed or needs human approval.

    Returns:
        {
            "allowed": bool,
            "requires_approval": bool,
            "reason": str
        }
    """
    # Critical services always need approval
    if target in CRITICAL_SERVICES:
        logger.info(
            "policy_manual_required",
            action=action,
            target=target,
            reason="critical_service",
        )
        return {
            "allowed": True,
            "requires_approval": True,
            "reason": f"{target} is a critical service — manual approval required",
        }

    # HIGH and CRITICAL severity always need approval
    if severity.upper() in ["HIGH", "CRITICAL"]:
        logger.info(
            "policy_manual_required",
            action=action,
            target=target,
            reason="high_severity",
        )
        return {
            "allowed": True,
            "requires_approval": True,
            "reason": f"Severity {severity} requires manual approval",
        }

    # Check action allowlist
    if action in POLICY["manual"]:
        return {
            "allowed": True,
            "requires_approval": True,
            "reason": f"Action {action} always requires manual approval",
        }

    if action in POLICY["auto"]:
        logger.info("policy_auto_approved", action=action, target=target)
        return {
            "allowed": True,
            "requires_approval": False,
            "reason": f"Action {action} is auto-approved for severity {severity}",
        }

    # Unknown action — block by default
    logger.warning("policy_unknown_action", action=action, target=target)
    return {
        "allowed": False,
        "requires_approval": True,
        "reason": f"Unknown action {action} — blocked by default",
    }


def is_auto_approved(action: str, target: str, severity: str) -> bool:
    result = check_policy(action, target, severity)
    return result["allowed"] and not result["requires_approval"]