from typing import TypedDict, Optional, Any
from prisma.enums import Severity, IncidentStatus


class AgentState(TypedDict):
    # ── Incident info ─────────────────────────
    incident_id: str
    service: str
    alert_payload: dict

    # ── Monitor agent output ──────────────────
    monitor_findings: Optional[dict]
    # Example:
    # {
    #   "cpu_percent": 94.2,
    #   "memory_percent": 87.1,
    #   "error_count": 847,
    #   "anomaly_detected": True,
    #   "affected_metrics": ["cpu", "memory"],
    #   "time_window": "last 10 minutes"
    # }

    # ── RCA agent output ──────────────────────
    root_cause: Optional[str]
    confidence: Optional[float]
    evidence_chain: Optional[list[str]]
    related_services: Optional[list[str]]

    # ── Severity agent output ─────────────────
    severity: Optional[str]          # LOW / MEDIUM / HIGH / CRITICAL
    requires_approval: Optional[bool]

    # ── Remediation agent output ──────────────
    proposed_actions: Optional[list[dict]]
    # Example:
    # [
    #   {"action": "restart_container", "target": "sample-app", "reason": "..."},
    #   {"action": "scale_service", "target": "worker", "replicas": 3}
    # ]
    selected_action: Optional[dict]

    # ── Approval gate ─────────────────────────
    approval_status: Optional[str]   # PENDING / APPROVED / REJECTED
    approved_by: Optional[str]

    # ── Verification agent output ─────────────
    verification_result: Optional[dict]
    # Example:
    # {
    #   "success": True,
    #   "metrics_normalized": True,
    #   "service_healthy": True,
    #   "message": "CPU back to 12%, service healthy"
    # }

    # ── Reporting agent output ────────────────
    rca_report: Optional[str]
    incident_closed: Optional[bool]

    # ── Graph control ─────────────────────────
    current_agent: Optional[str]
    error: Optional[str]
    messages: list[Any]              # LangChain message history