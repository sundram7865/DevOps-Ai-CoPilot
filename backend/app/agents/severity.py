from langchain_core.messages import SystemMessage, HumanMessage
from app.agents.state import AgentState
from app.agents.supervisor import get_llm
from app.tools.policy_engine import check_policy
from app.core.logging import logger


async def run(state: AgentState) -> AgentState:
    """
    Severity agent — classifies incident severity.
    Determines if human approval is needed.
    """
    logger.info("severity_running", incident_id=state["incident_id"])

    findings = state.get("monitor_findings", {})
    root_cause = state.get("root_cause", "unknown")
    confidence = state.get("confidence", 0.5)

    # Build classification context
    context = f"""
Service: {state['service']}
CPU: {findings.get('cpu_percent', 0)}%
Memory: {findings.get('memory_mb', 0)} MB
Error count (10m): {findings.get('error_count', 0)}
Restart count: {findings.get('restart_count', 0)}
Container status: {findings.get('container_status', 'unknown')}
Root cause: {root_cause}
RCA confidence: {confidence * 100:.0f}%
"""

    llm, _ = get_llm(f"severity-{state['incident_id']}")

    messages = [
        SystemMessage(content=(
            "You are the Severity Classification agent of a DevOps AI Copilot. "
            "Classify incident severity based on impact and urgency.\n\n"
            "Severity levels:\n"
            "LOW: minor issue, auto-recoverable, no user impact\n"
            "MEDIUM: moderate issue, some user impact, auto-fix safe\n"
            "HIGH: significant issue, clear user impact, needs approval\n"
            "CRITICAL: severe outage, major user impact, urgent approval needed\n"
        )),
        HumanMessage(content=(
            f"Classify the severity of this incident:\n\n"
            f"{context}\n\n"
            f"Respond in this exact format:\n"
            f"SEVERITY: <LOW/MEDIUM/HIGH/CRITICAL>\n"
            f"REASON: <one sentence>\n"
        )),
    ]

    response = await llm.ainvoke(messages)
    content = response.content

    # Parse severity
    severity = "MEDIUM"  # default
    for line in content.split("\n"):
        if line.startswith("SEVERITY:"):
            raw = line.split(":", 1)[1].strip().upper()
            if raw in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]:
                severity = raw
            break

    # Check policy — does this severity require approval?
    policy = check_policy(
        action="restart_container",
        target=state["service"],
        severity=severity,
    )
    requires_approval = policy["requires_approval"]

    logger.info(
        "severity_classified",
        incident_id=state["incident_id"],
        severity=severity,
        requires_approval=requires_approval,
    )

    return {
        **state,
        "current_agent": "severity",
        "severity": severity,
        "requires_approval": requires_approval,
        "messages": state.get("messages", []) + [response],
    }