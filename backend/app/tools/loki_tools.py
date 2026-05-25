import httpx
import time
from app.core.config import settings
from app.core.logging import logger


async def query_loki(
    service: str,
    pattern: str = "",
    duration: str = "1h",
    limit: int = 100,
) -> dict:
    """
    Query Loki for logs from a specific service.
    Optionally filter by a log pattern/keyword.
    """
    duration_map = {"5m": 300, "10m": 600, "30m": 1800, "1h": 3600, "3h": 10800}
    seconds = duration_map.get(duration, 3600)

    end_ns = int(time.time() * 1e9)
    start_ns = end_ns - int(seconds * 1e9)

    # Build LogQL query
    if pattern:
        logql = f'{{service="{service}"}} |= "{pattern}"'
    else:
        logql = f'{{service="{service}"}}'

    url = f"{settings.LOKI_URL}/loki/api/v1/query_range"
    params = {
        "query": logql,
        "start": start_ns,
        "end": end_ns,
        "limit": limit,
        "direction": "backward",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

        log_lines = []
        for stream in data.get("data", {}).get("result", []):
            for entry in stream.get("values", []):
                log_lines.append({
                    "timestamp": entry[0],
                    "line": entry[1],
                    "labels": stream.get("stream", {}),
                })

        # Sort by timestamp descending
        log_lines.sort(key=lambda x: x["timestamp"], reverse=True)

        logger.info("loki_queried", service=service, pattern=pattern, lines=len(log_lines))
        return {
            "service": service,
            "pattern": pattern,
            "duration": duration,
            "log_lines": log_lines,
            "count": len(log_lines),
        }

    except httpx.RequestError as e:
        logger.error("loki_connection_error", error=str(e))
        return {"error": str(e), "service": service}


async def query_loki_errors(service: str, duration: str = "1h") -> dict:
    """
    Shortcut — query only ERROR level logs from a service.
    Used by Monitor and RCA agents.
    """
    return await query_loki(service=service, pattern="ERROR", duration=duration)


async def count_error_logs(service: str, duration: str = "10m") -> int:
    """
    Count number of error logs in a time window.
    Used by Severity agent.
    """
    result = await query_loki_errors(service=service, duration=duration)
    if "error" in result:
        return 0
    return result["count"]