from fastapi import APIRouter
from app.schemas.webhook import AlertmanagerPayload
from app.services.incident_service import create_incident, add_incident_event
from app.workers.tasks import run_agent_task
from app.core.logging import logger

router = APIRouter()


@router.post("/webhook/alert", status_code=200)
async def receive_alert(
    payload: AlertmanagerPayload
):
    logger.info("webhook_received", alerts=len(payload.alerts), status=payload.status)

    incidents_created = 0

    for alert in payload.alerts:
        if alert.status != "firing":
            continue

        incident = await create_incident(
            title=f"{alert.labels.alertname} on {alert.labels.service}",
            service=alert.labels.service,
            severity=alert.labels.severity,
            alert_payload=payload.model_dump(),
        )

        await add_incident_event(
            incident_id=incident.id,
            event_type="DETECTED",
            message=f"Alert {alert.labels.alertname} fired",
            metadata={"fingerprint": alert.fingerprint},
        )

        # Trigger agent as Celery background task
        run_agent_task.delay(
            incident_id=incident.id,
            service=alert.labels.service,
            alert_payload=payload.model_dump(),
        )

        logger.info("agent_triggered", incident_id=incident.id)
        incidents_created += 1

    return {"status": "received", "incidents_created": incidents_created}