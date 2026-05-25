from fastapi import APIRouter, HTTPException
from app.services.incident_service import (
    get_incidents,
    get_incident,
    update_incident_status,
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
    updated = await update_incident_status(incident_id, IncidentStatus.APPROVED)
    # Phase 4: resume LangGraph here
    return {"status": "approved", "incident_id": incident_id}


@router.post("/incidents/{incident_id}/reject")
async def reject_incident(incident_id: str):
    incident = await get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    updated = await update_incident_status(incident_id, IncidentStatus.FAILED)
    return {"status": "rejected", "incident_id": incident_id}