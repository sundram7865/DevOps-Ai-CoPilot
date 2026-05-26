from langchain_core.messages import SystemMessage, HumanMessage
from app.agents.state import AgentState
from app.agents.supervisor import get_llm
from app.tools.prometheus_tools import get_metric_baseline
from app.tools.loki_tools import query_loki
from app.tools.otel_tools import get_request_latency
from app.services.embedding_service import search_incident_history
from app.core.logging import logger


async def run(state: AgentState) -> AgentState:
    """
    RCA agent — finds root cause of the incident.
    Correlates metrics, logs, traces and past incidents.
    """
    logger.info("rca_running", incident_id=state["incident_id"])

    service = state["service"]
    findings = state.get("monitor_findings", {})

    # ── Gather deeper telemetry ───────────────
    # Compare current vs baseline
    cpu_baseline = await get_metric_baseline(
        f'rate(container_cpu_usage_seconds_total{{name="{service}"}}[5m]) * 100'
    )
    # Get all recent logs (not just errors)
    all_logs = await query_loki(service=service, duration="30m", limit=50)
    # Get latency data
    latency = await get_request_latency(service)
    # Search similar past incidents
    past_incidents = await search_incident_history(
        f"service:{service} cpu:{findings.get('cpu_percent', 0)}"
    )

    # Build context for LLM
    context = f"""
Current findings:
{findings.get('llm_analysis', 'No analysis available')}

CPU baseline (last 1h avg): {cpu_baseline.get('baseline', 'unknown')}
CPU current: {findings.get('cpu_percent', 0)}%
CPU max (1h): {cpu_baseline.get('max', 'unknown')}

Request latency P99: {latency.get('p99_seconds', 0):.3f}s
Request latency P95: {latency.get('p95_seconds', 0):.3f}s

Recent log patterns (last 30m):
{chr(10).join([log['line'] for log in all_logs.get('log_lines', [])[:20]])}

Similar past incidents:
{chr(10).join([f"- {inc['title']}: {inc.get('root_cause', 'unknown')}" for inc in past_incidents[:3]])}
"""

    # ── LLM root cause analysis ───────────────
    llm, _ = get_llm(f"rca-{state['incident_id']}")

    messages = [
        SystemMessage(content=(
            "You are the RCA (Root Cause Analysis) agent of a DevOps AI Copilot. "
            "Your job is to find the root cause of infrastructure incidents. "
            "Use the telemetry data provided. Be specific and precise. "
            "Give a confidence score 0-100 based on evidence quality."
        )),
        HumanMessage(content=(
            f"Perform root cause analysis for incident on service '{service}':\n\n"
            f"{context}\n\n"
            f"Respond in this exact format:\n"
            f"ROOT_CAUSE: <specific root cause>\n"
            f"CONFIDENCE: <0-100>\n"
            f"EVIDENCE: <comma separated list of key evidence points>\n"
            f"RELATED_SERVICES: <comma separated list or 'none'>\n"
            f"EXPLANATION: <2-3 sentences explaining the causal chain>\n"
        )),
    ]

    response = await llm.ainvoke(messages)

    # Parse LLM response
    content = response.content
    root_cause = _extract_field(content, "ROOT_CAUSE")
    confidence_str = _extract_field(content, "CONFIDENCE")
    evidence_str = _extract_field(content, "EVIDENCE")
    related_str = _extract_field(content, "RELATED_SERVICES")

    try:
        confidence = float(confidence_str) / 100 if confidence_str else 0.5
    except ValueError:
        confidence = 0.5

    evidence_chain = [e.strip() for e in evidence_str.split(",")] if evidence_str else []
    related_services = (
        [s.strip() for s in related_str.split(",")]
        if related_str and related_str.lower() != "none"
        else []
    )

    logger.info(
        "rca_complete",
        incident_id=state["incident_id"],
        root_cause=root_cause[:100] if root_cause else "unknown",
        confidence=confidence,
    )

    return {
        **state,
        "current_agent": "rca",
        "root_cause": root_cause,
        "confidence": confidence,
        "evidence_chain": evidence_chain,
        "related_services": related_services,
        "messages": state.get("messages", []) + [response],
    }


def _extract_field(text: str, field: str) -> str:
    """Extract a field value from structured LLM response."""
    for line in text.split("\n"):
        if line.startswith(f"{field}:"):
            return line.split(":", 1)[1].strip()
    return ""