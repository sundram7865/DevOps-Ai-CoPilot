from datetime import datetime, timezone
from langchain_core.messages import SystemMessage, HumanMessage
from app.agents.state import AgentState
from app.agents.supervisor import get_llm
from app.services.notification_service import send_resolution_summary
from app.core.database import db
from app.core.logging import logger


async def run(state: AgentState) -> AgentState:
    """
    Reporting agent — generates RCA report, stores to DB,
    sends Discord summary, closes the incident.
    """
    logger.info("reporting_running", incident_id=state["incident_id"])

    # ── Generate RCA report ───────────────────
    llm, _ = get_llm(f"reporting-{state['incident_id']}")

    verification = state.get("verification_result", {})
    selected_action = state.get("selected_action", {})

    messages = [
        SystemMessage(content=(
            "You are the Reporting agent of a DevOps AI Copilot. "
            "Generate professional, concise incident reports."
        )),
        HumanMessage(content=(
            f"Generate an incident report:\n\n"
            f"Service: {state['service']}\n"
            f"Root cause: {state.get('root_cause', 'unknown')}\n"
            f"Confidence: {(state.get('confidence', 0) * 100):.0f}%\n"
            f"Severity: {state.get('severity', 'unknown')}\n"
            f"Evidence: {', '.join(state.get('evidence_chain', []))}\n"
            f"Action taken: {selected_action.get('action', 'none')} "
            f"on {selected_action.get('target', 'unknown')}\n"
            f"Recovery: {'successful' if verification.get('success') else 'failed'}\n"
            f"CPU before: {verification.get('cpu_before', 0):.1f}%\n"
            f"CPU after: {verification.get('cpu_after', 0):.1f}%\n\n"
            f"Write a brief incident report with: summary, root cause, "
            f"action taken, outcome, and recommendation."
        )),
    ]

    response = await llm.ainvoke(messages)
    rca_report = response.content

    # ── Store report to DB ────────────────────
    resolved_at = datetime.now(timezone.utc)
    detected_at = None

    incident = await db.incident.find_unique(where={"id": state["incident_id"]})
    if incident:
        detected_at = incident.detectedAt

    mttr = None
    if detected_at:
        mttr = int((resolved_at - detected_at).total_seconds())

    await db.incident.update(
        where={"id": state["incident_id"]},
        data={
            "rootCause": state.get("root_cause"),
            "confidence": state.get("confidence"),
            "resolvedAt": resolved_at,
            "mttr": mttr,
        },
    )

    # ── Store embedding for semantic search ───
    # Phase 4 basic: store text summary
    # Full pgvector embedding added in Phase 7 hardening
    await db.incidentevent.create(
        data={
            "incidentId": state["incident_id"],
            "type": "REPORT_GENERATED",
            "message": "RCA report generated",
            "metadata": {
                "report": rca_report[:1000],
                "mttr_seconds": mttr,
            },
        }
    )

    # ── Send Discord summary ──────────────────
    await send_resolution_summary(
        incident_id=state["incident_id"],
        service=state["service"],
        severity=state.get("severity", "unknown"),
        root_cause=state.get("root_cause", "unknown"),
        action_taken=selected_action.get("action", "none"),
        recovered=verification.get("success", False),
        mttr=mttr,
    )

    logger.info(
        "reporting_complete",
        incident_id=state["incident_id"],
        mttr=mttr,
    )

    return {
        **state,
        "current_agent": "reporting",
        "rca_report": rca_report,
        "incident_closed": True,
        "messages": state.get("messages", []) + [response],
    }