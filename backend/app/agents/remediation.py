from langchain_core.messages import SystemMessage, HumanMessage
from app.agents.state import AgentState
from app.agents.supervisor import get_llm
from app.tools.policy_engine import check_policy
from app.tools.docker_tools import restart_container, scale_service
from app.services.incident_service import update_incident_status, add_incident_event
from app.services.notification_service import send_approval_request
from prisma.enums import IncidentStatus
from app.core.logging import logger


async def run(state: AgentState) -> AgentState:
    """
    Remediation agent — proposes and executes fixes.
    For HIGH/CRITICAL: pauses and requests human approval.
    For LOW/MEDIUM: auto-executes.
    """
    logger.info(
        "remediation_running",
        incident_id=state["incident_id"],
        severity=state.get("severity"),
    )

    service = state["service"]
    severity = state.get("severity", "MEDIUM")
    root_cause = state.get("root_cause", "unknown")
    findings = state.get("monitor_findings", {})

    # ── LLM proposes actions ──────────────────
    llm, _ = get_llm(f"remediation-{state['incident_id']}")

    messages = [
        SystemMessage(content=(
            "You are the Remediation agent of a DevOps AI Copilot. "
            "Propose specific remediation actions for infrastructure incidents. "
            "Only propose actions from this list: "
            "restart_container, scale_service, rollback_deploy, stop_container. "
            "Rank by safety — safest first."
        )),
        HumanMessage(content=(
            f"Propose remediation for:\n"
            f"Service: {service}\n"
            f"Severity: {severity}\n"
            f"Root cause: {root_cause}\n"
            f"CPU: {findings.get('cpu_percent', 0)}%\n"
            f"Errors: {findings.get('error_count', 0)}\n\n"
            f"Respond in this exact format (list 1-3 actions):\n"
            f"ACTION_1: <action_name> | <target> | <reason>\n"
            f"ACTION_2: <action_name> | <target> | <reason>\n"
        )),
    ]

    response = await llm.ainvoke(messages)

    # Parse proposed actions
    proposed_actions = []
    for line in response.content.split("\n"):
        if line.startswith("ACTION_"):
            parts = line.split(":", 1)[1].strip().split("|")
            if len(parts) >= 2:
                proposed_actions.append({
                    "action": parts[0].strip(),
                    "target": parts[1].strip() if len(parts) > 1 else service,
                    "reason": parts[2].strip() if len(parts) > 2 else "",
                })

    if not proposed_actions:
        proposed_actions = [{
            "action": "restart_container",
            "target": service,
            "reason": "Default: restart to recover from anomaly",
        }]

    selected_action = proposed_actions[0]

    # ── Check policy ──────────────────────────
    policy = check_policy(
        action=selected_action["action"],
        target=selected_action["target"],
        severity=severity,
    )

    if policy["requires_approval"]:
        # HIGH/CRITICAL — pause and request approval
        await update_incident_status(state["incident_id"], IncidentStatus.AWAITING_APPROVAL)
        await add_incident_event(
            incident_id=state["incident_id"],
            event_type="AWAITING_APPROVAL",
            message=f"Proposed: {selected_action['action']} on {selected_action['target']}",
            metadata={
                "proposed_actions": proposed_actions,
                "root_cause": root_cause,
                "severity": severity,
            },
        )

        # Send Discord notification
        await send_approval_request(
            incident_id=state["incident_id"],
            service=service,
            severity=severity,
            root_cause=root_cause,
            proposed_actions=proposed_actions,
        )

        logger.info(
            "approval_requested",
            incident_id=state["incident_id"],
            action=selected_action["action"],
        )

        return {
            **state,
            "current_agent": "remediation",
            "proposed_actions": proposed_actions,
            "selected_action": selected_action,
            "approval_status": "PENDING",
            "messages": state.get("messages", []) + [response],
        }

    else:
        # LOW/MEDIUM — auto execute
        await update_incident_status(state["incident_id"], IncidentStatus.EXECUTING)
        await add_incident_event(
            incident_id=state["incident_id"],
            event_type="AUTO_EXECUTING",
            message=f"Auto-executing: {selected_action['action']} on {selected_action['target']}",
        )

        # Execute the action
        if selected_action["action"] == "restart_container":
            exec_result = await restart_container(selected_action["target"])
        elif selected_action["action"] == "scale_service":
            exec_result = await scale_service(selected_action["target"], 2)
        else:
            exec_result = {"success": False, "error": "Unknown action"}

        logger.info(
            "auto_executed",
            incident_id=state["incident_id"],
            action=selected_action["action"],
            success=exec_result.get("success"),
        )

        return {
            **state,
            "current_agent": "remediation",
            "proposed_actions": proposed_actions,
            "selected_action": selected_action,
            "approval_status": "APPROVED",
            "messages": state.get("messages", []) + [response],
        }