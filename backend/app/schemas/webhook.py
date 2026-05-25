from pydantic import BaseModel
from typing import Any


class AlertLabel(BaseModel):
    alertname: str
    severity: str = "low"
    service: str = "unknown"


class Alert(BaseModel):
    status: str
    labels: AlertLabel
    annotations: dict[str, Any] = {}
    startsAt: str
    endsAt: str = ""
    fingerprint: str = ""


class AlertmanagerPayload(BaseModel):
    version: str = "4"
    groupKey: str = ""
    status: str
    receiver: str
    alerts: list[Alert]