from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage
from langfuse.callback import CallbackHandler
from app.agents.state import AgentState
from app.agents.supervisor import get_llm
from app.tools.prometheus_tools import query_prometheus, query_prometheus_range
from app.tools.loki_tools import query_loki, count_error_logs
from app.tools.docker_tools import get_container_stats
from app.core.logging import logger


async def run(state: AgentState) -> AgentState:
    """
    Monitor agent — investigates the incident using real telemetry.
    Queries Prometheus, Loki, Docker SDK.
    Writes findings to state.
    """
    logger.info("monitor_running", incident_id=state["incident_id"])

    service = state["service"]

    # ── Gather telemetry ──────────────────────
    cpu_data = await query_prometheus(
        f'rate(container_cpu_usage_seconds_total{{name="{service}"}}[5m]) * 100'
    )
    memory_data = await query_prometheus(
        f'container_memory_usage_bytes{{name="{service}"}}'
    )
    error_logs = await query_loki(service=service, pattern="ERROR", duration="10m")
    container_stats = await get_container_stats(service)

    # Extract values safely
    cpu_percent = 0.0
    if cpu_data.get("results"):
        cpu_percent = cpu_data["results"][0]["value"]

    memory_mb = 0.0
    if memory_data.get("results"):
        memory_mb = memory_data["results"][0]["value"] / 1024 / 1024

    error_count = error_logs.get("count", 0)
    restart_count = container_stats.get("restart_count", 0)

    # Build telemetry summary for LLM
    telemetry_summary = f"""
Service: {service}
CPU Usage: {cpu_percent:.1f}%
Memory Usage: {memory_mb:.1f} MB
Error logs (last 10m): {error_count}
Container restarts: {restart_count}
Container status: {container_stats.get('status', 'unknown')}

Recent error logs:
{chr(10).join([log['line'] for log in error_logs.get('log_lines', [])[:10]])}
"""

    # ── LLM analysis ─────────────────────────
    llm, _ = get_llm(f"monitor-{state['incident_id']}")

    messages = [
        SystemMessage(content=(
            "You are the Monitor agent of a DevOps AI Copilot. "
            "Analyse infrastructure telemetry and identify anomalies. "
            "Be precise and factual. Only report what the data shows."
        )),
        HumanMessage(content=(
            f"Analyse this telemetry for service '{service}':\n\n"
            f"{telemetry_summary}\n\n"
            f"Identify: what is abnormal, which metrics are concerning, "
            f"and what time period the anomaly started. "
            f"Format your response as:\n"
            f"ANOMALY: <yes/no>\n"
            f"AFFECTED_METRICS: <list>\n"
            f"SUMMARY: <2-3 sentences>\n"
        )),
    ]

    response = await llm.ainvoke(messages)

    monitor_findings = {
        "cpu_percent": round(cpu_percent, 2),
        "memory_mb": round(memory_mb, 2),
        "error_count": error_count,
        "restart_count": restart_count,
        "container_status": container_stats.get("status", "unknown"),
        "recent_errors": [log["line"] for log in error_logs.get("log_lines", [])[:5]],
        "llm_analysis": response.content,
        "anomaly_detected": "ANOMALY: yes" in response.content.lower(),
    }

    logger.info(
        "monitor_complete",
        incident_id=state["incident_id"],
        cpu=cpu_percent,
        errors=error_count,
        anomaly=monitor_findings["anomaly_detected"],
    )

    return {
        **state,
        "current_agent": "monitor",
        "monitor_findings": monitor_findings,
        "messages": state.get("messages", []) + [response],
    }