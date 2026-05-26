from fastapi import APIRouter, HTTPException
from app.services.incident_service import (
    get_incidents,
    get_incident,
    update_incident_status,
    add_incident_event,
)
from app.schemas.incident import IncidentResponse, ApproveRequest
from prisma.enums import IncidentStatus

router = APIRouter()


@router.get("/incidents", response_model=list[IncidentResponse])
async def list_incidents(skip: int = 0, limit: int = 20):
    return await get_incidents(skip=skip, limit=limit)


@router.get("/incidents/{incident_id}", response_model=IncidentResponse)
async def get_one_incident(incident_id: str):
    incident = await get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident


@router.post("/incidents/{incident_id}/approve")
async def approve_incident(incident_id: str, body: ApproveRequest):
    incident = await get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    await update_incident_status(incident_id, IncidentStatus.APPROVED)
    await add_incident_event(
        incident_id=incident_id,
        event_type="APPROVED",
        message=f"Approved by {body.approvedBy}",
    )

    # Resume LangGraph from Redis checkpoint
    from app.workers.tasks import resume_agent_task
    resume_agent_task.delay(
        incident_id=incident_id,
        approved_by=body.approvedBy,
    )

    return {"status": "approved", "incident_id": incident_id}


@router.post("/incidents/{incident_id}/reject")
async def reject_incident(incident_id: str):
    incident = await get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    await update_incident_status(incident_id, IncidentStatus.FAILED)
    await add_incident_event(
        incident_id=incident_id,
        event_type="REJECTED",
        message="Rejected by operator",
    )

    return {"status": "rejected", "incident_id": incident_id}