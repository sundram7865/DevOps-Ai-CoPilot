import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch
from app.main import app
from prisma.enums import Severity, IncidentStatus
from datetime import datetime


def mock_incident(id="inc-1", status=IncidentStatus.DETECTING):
    obj = type("Incident", (), {
        "id": id,
        "title": "HighCPU on sample-app",
        "service": "sample-app",
        "severity": Severity.HIGH,
        "status": status,
        "rootCause": None,
        "confidence": None,
        "detectedAt": datetime.utcnow(),
        "resolvedAt": None,
        "mttr": None,
    })()
    return obj


@pytest.mark.asyncio
async def test_list_incidents():
    with patch("app.routers.incidents.get_incidents", new_callable=AsyncMock) as mock_list:
        mock_list.return_value = [mock_incident()]

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/incidents")

        assert response.status_code == 200
        assert len(response.json()) == 1
        assert response.json()[0]["service"] == "sample-app"


@pytest.mark.asyncio
async def test_get_incident_not_found():
    with patch("app.routers.incidents.get_incident", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = None

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/incidents/nonexistent-id")

        assert response.status_code == 404


@pytest.mark.asyncio
async def test_approve_incident():
    with patch("app.routers.incidents.get_incident", new_callable=AsyncMock) as mock_get, \
         patch("app.routers.incidents.update_incident_status", new_callable=AsyncMock) as mock_update:

        mock_get.return_value = mock_incident()
        mock_update.return_value = mock_incident(status=IncidentStatus.APPROVED)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/incidents/inc-1/approve",
                json={"approvedBy": "operator"}
            )

        assert response.status_code == 200
        assert response.json()["status"] == "approved"