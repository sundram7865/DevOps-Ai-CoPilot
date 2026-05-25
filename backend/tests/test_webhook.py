import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch
from app.main import app


@pytest.mark.asyncio
async def test_webhook_receives_alert():
    payload = {
        "version": "4",
        "status": "firing",
        "receiver": "fastapi-webhook",
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "HighCPU",
                    "severity": "high",
                    "service": "sample-app",
                },
                "annotations": {},
                "startsAt": "2024-01-01T00:00:00Z",
                "endsAt": "",
                "fingerprint": "abc123",
            }
        ],
    }

    with patch("app.routers.webhook.create_incident", new_callable=AsyncMock) as mock_create, \
         patch("app.routers.webhook.add_incident_event", new_callable=AsyncMock):

        mock_create.return_value = type("obj", (object,), {"id": "test-id-123"})()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/webhook/alert", json=payload)

        assert response.status_code == 200
        assert response.json()["incidents_created"] == 1
        mock_create.assert_called_once()


@pytest.mark.asyncio
async def test_webhook_ignores_resolved_alerts():
    payload = {
        "version": "4",
        "status": "resolved",
        "receiver": "fastapi-webhook",
        "alerts": [
            {
                "status": "resolved",
                "labels": {
                    "alertname": "HighCPU",
                    "severity": "high",
                    "service": "sample-app",
                },
                "annotations": {},
                "startsAt": "2024-01-01T00:00:00Z",
                "endsAt": "2024-01-01T01:00:00Z",
                "fingerprint": "abc123",
            }
        ],
    }

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/webhook/alert", json=payload)

    assert response.status_code == 200
    assert response.json()["incidents_created"] == 0