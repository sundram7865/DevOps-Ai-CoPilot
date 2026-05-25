from prisma.enums import Severity, IncidentStatus
from app.core.database import db
from app.core.logging import logger


async def create_incident(
    title: str,
    service: str,
    severity: str,
    alert_payload: dict,
) -> object:
    severity_map = {
        "low": Severity.LOW,
        "medium": Severity.MEDIUM,
        "high": Severity.HIGH,
        "critical": Severity.CRITICAL,
    }
    incident = await db.incident.create(
        data={
            "title": title,
            "service": service,
            "severity": severity_map.get(severity.lower(), Severity.LOW),
            "status": IncidentStatus.DETECTING,
            "alertPayload": alert_payload,
        }
    )
    logger.info("incident_created", incident_id=incident.id, service=service)
    return incident


async def get_incidents(skip: int = 0, limit: int = 20) -> list:
    return await db.incident.find_many(
        skip=skip,
        take=limit,
        order={"detectedAt": "desc"},
    )


async def get_incident(incident_id: str) -> object:
    return await db.incident.find_unique(
        where={"id": incident_id},
        include={"events": True, "actions": True},
    )


async def update_incident_status(
    incident_id: str,
    status: IncidentStatus,
) -> object:
    return await db.incident.update(
        where={"id": incident_id},
        data={"status": status},
    )


async def add_incident_event(
    incident_id: str,
    event_type: str,
    message: str,
    metadata: dict = None,
) -> object:
    return await db.incidentevent.create(
        data={
            "incidentId": incident_id,
            "type": event_type,
            "message": message,
            "metadata": metadata,
        }
    )