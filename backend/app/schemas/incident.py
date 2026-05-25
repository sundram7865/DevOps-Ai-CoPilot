from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from prisma.enums import Severity, IncidentStatus


class IncidentResponse(BaseModel):
    id: str
    title: str
    service: str
    severity: Severity
    status: IncidentStatus
    rootCause: Optional[str]
    confidence: Optional[float]
    detectedAt: datetime
    resolvedAt: Optional[datetime]
    mttr: Optional[int]

    model_config = {"from_attributes": True}


class ApproveRequest(BaseModel):
    approvedBy: str = "operator"