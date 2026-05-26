import asyncio
from langchain_core.messages import SystemMessage, HumanMessage
from app.agents.state import AgentState
from app.agents.supervisor import get_llm
from app.tools.prometheus_tools import query_prometheus
from app.tools.docker_tools import verify_service_health
from app.services.incident_service import update_incident_status, add_incident_event
from prisma.enums import IncidentStatus
from app.core.logging import logger


async def run(state: AgentState) -> AgentState:
    """
    Verification agent — confirms the fix worked.
    Waits 30 seconds then re-checks metrics.
    """
    logger.info("verification_running", incident_id=state["incident_id"])

    service = state["service"]

    await update_incident_status(state["incident_id"], IncidentStatus.VERIFYING)

    # Wait for service to stabilize
    logger.info("verification_waiting", seconds=30)
    await asyncio.sleep(30)

    # Re-check metrics
    cpu_data = await query_prometheus(
        f'rate(container_cpu_usage_seconds_total{{name="{service}"}}[2m]) * 100'
    )
    health = await verify_service_health(service)

    cpu_now = 0.0
    if cpu_data.get("results"):
        cpu_now = cpu_data["results"][0]["value"]

    cpu_before = state.get("monitor_findings", {}).get("cpu_percent", 100)
    cpu_improved = cpu_now < cpu_before * 0.7  # 30% improvement

    # ── LLM verification assessment ───────────
    llm, _ = get_llm(f"verification-{state['incident_id']}")

    messages = [
        SystemMessage(content=(
            "You are the Verification agent of a DevOps AI Copilot. "
            "Assess whether a remediation action successfully resolved an incident."
        )),
        HumanMessage(content=(
            f"Verify recovery for service '{service}':\n\n"
            f"Before fix — CPU: {cpu_before:.1f}%\n"
            f"After fix — CPU: {cpu_now:.1f}%\n"
            f"Service running: {health.get('is_running', False)}\n"
            f"Health check: {health.get('is_healthy', False)}\n"
            f"Restart count: {health.get('restart_count', 0)}\n\n"
            f"Respond:\n"
            f"RECOVERED: <yes/no>\n"
            f"SUMMARY: <one sentence>\n"
        )),
    ]

    response = await llm.ainvoke(messages)
    recovered = "RECOVERED: yes" in response.content.lower()

    verification_result = {
        "success": recovered,
        "cpu_before": cpu_before,
        "cpu_after": round(cpu_now, 2),
        "cpu_improved": cpu_improved,
        "service_healthy": health.get("is_healthy", False),
        "is_running": health.get("is_running", False),
        "llm_assessment": response.content,
    }

    # Update DB
    new_status = IncidentStatus.RESOLVED if recovered else IncidentStatus.FAILED
    await update_incident_status(state["incident_id"], new_status)
    await add_incident_event(
        incident_id=state["incident_id"],
        event_type="VERIFIED",
        message=f"Recovery {'successful' if recovered else 'failed'}",
        metadata=verification_result,
    )

    logger.info(
        "verification_complete",
        incident_id=state["incident_id"],
        recovered=recovered,
        cpu_after=cpu_now,
    )

    return {
        **state,
        "current_agent": "verification",
        "verification_result": verification_result,
        "messages": state.get("messages", []) + [response],
    }