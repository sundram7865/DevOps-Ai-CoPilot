import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── Prometheus tests ──────────────────────────

@pytest.mark.asyncio
async def test_query_prometheus_success():
    mock_response = {
        "status": "success",
        "data": {
            "result": [
                {
                    "metric": {"job": "sample-app"},
                    "value": [1234567890, "0.42"],
                }
            ]
        },
    }

    with patch("httpx.AsyncClient") as mock_client:
        mock_response_obj = MagicMock()
        mock_response_obj.json.return_value = mock_response
        mock_response_obj.raise_for_status = MagicMock()

        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=mock_response_obj
        )

        from app.tools.prometheus_tools import query_prometheus
        result = await query_prometheus("http_requests_total")

    assert result["count"] == 1
    assert result["results"][0]["value"] == 0.42


@pytest.mark.asyncio
async def test_query_prometheus_connection_error():
    import httpx

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            side_effect=httpx.RequestError("connection refused")
        )

        from app.tools.prometheus_tools import query_prometheus
        result = await query_prometheus("http_requests_total")

    assert "error" in result


# ── Loki tests ────────────────────────────────

@pytest.mark.asyncio
async def test_query_loki_success():
    mock_response = {
        "data": {
            "result": [
                {
                    "stream": {"service": "sample-app"},
                    "values": [
                        ["1234567890000000000", "[ERROR] connection pool exhausted"],
                        ["1234567891000000000", "[INFO] request received"],
                    ],
                }
            ]
        }
    }

    with patch("httpx.AsyncClient") as mock_client:
        mock_response_obj = MagicMock()
        mock_response_obj.json.return_value = mock_response
        mock_response_obj.raise_for_status = MagicMock()

        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=mock_response_obj
        )

        from app.tools.loki_tools import query_loki
        result = await query_loki("sample-app", duration="1h")

    assert result["count"] == 2
    assert result["service"] == "sample-app"


@pytest.mark.asyncio
async def test_query_loki_with_pattern():
    mock_response = {"data": {"result": []}}

    with patch("httpx.AsyncClient") as mock_client:
        mock_response_obj = MagicMock()
        mock_response_obj.json.return_value = mock_response
        mock_response_obj.raise_for_status = MagicMock()

        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=mock_response_obj
        )

        from app.tools.loki_tools import query_loki
        result = await query_loki(
            "sample-app",
            pattern="ERROR",
            duration="30m",
        )

    assert result["pattern"] == "ERROR"
    assert result["count"] == 0


# ── Docker tools tests ────────────────────────

@pytest.mark.asyncio
async def test_restart_container_success():
    mock_container = MagicMock()
    mock_container.status = "running"
    mock_container.restart = MagicMock()
    mock_container.reload = MagicMock()

    with patch("app.tools.docker_tools.get_docker_client") as mock_client:
        mock_client.return_value.containers.get.return_value = mock_container

        from app.tools.docker_tools import restart_container
        result = await restart_container("sample-app")

    assert result["success"] is True
    assert result["name"] == "sample-app"
    mock_container.restart.assert_called_once()


@pytest.mark.asyncio
async def test_restart_container_not_found():
    import docker

    with patch("app.tools.docker_tools.get_docker_client") as mock_client:
        mock_client.return_value.containers.get.side_effect = (
            docker.errors.NotFound("not found")
        )

        from app.tools.docker_tools import restart_container
        result = await restart_container("nonexistent")

    assert result["success"] is False
    assert "not found" in result["error"].lower()


@pytest.mark.asyncio
async def test_get_container_stats_success():
    mock_container = MagicMock()
    mock_container.status = "running"
    mock_container.attrs = {"RestartCount": 0}
    mock_container.image.tags = ["sample-app:latest"]

    mock_container.stats.return_value = {
        "cpu_stats": {
            "cpu_usage": {"total_usage": 2000000},
            "system_cpu_usage": 100000000,
            "online_cpus": 4,
        },
        "precpu_stats": {
            "cpu_usage": {"total_usage": 1000000},
            "system_cpu_usage": 90000000,
        },
        "memory_stats": {
            "usage": 52428800,
            "limit": 1073741824,
        },
    }

    with patch("app.tools.docker_tools.get_docker_client") as mock_client:
        mock_client.return_value.containers.get.return_value = mock_container

        from app.tools.docker_tools import get_container_stats
        result = await get_container_stats("sample-app")

    assert result["name"] == "sample-app"
    assert result["status"] == "running"
    assert result["restart_count"] == 0
    assert "cpu_percent" in result
    assert "memory_percent" in result


# ── Policy engine tests ───────────────────────

def test_policy_auto_approved_low_severity():
    from app.tools.policy_engine import check_policy

    result = check_policy("restart_container", "sample-app", "low")

    assert result["allowed"] is True
    assert result["requires_approval"] is False


def test_policy_manual_required_high_severity():
    from app.tools.policy_engine import check_policy

    result = check_policy("restart_container", "sample-app", "high")

    assert result["allowed"] is True
    assert result["requires_approval"] is True


def test_policy_critical_service_always_manual():
    from app.tools.policy_engine import check_policy

    result = check_policy("restart_container", "postgres", "low")

    assert result["requires_approval"] is True


def test_policy_unknown_action_blocked():
    from app.tools.policy_engine import check_policy

    result = check_policy("delete_everything", "sample-app", "low")

    assert result["allowed"] is False


def test_policy_manual_action_always_manual():
    from app.tools.policy_engine import check_policy

    result = check_policy("rollback_deploy", "sample-app", "low")

    assert result["requires_approval"] is True
