import httpx
from app.core.config import settings
from app.core.logging import logger


async def query_prometheus(metric: str, duration: str = "10m") -> dict:
    """
    Query Prometheus instant query API.
    Returns structured result with metric name, labels, and values.
    """
    url = f"{settings.PROMETHEUS_URL}/api/v1/query"
    params = {"query": metric}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

        if data["status"] != "success":
            logger.error("prometheus_query_failed", metric=metric, response=data)
            return {"error": "query failed", "metric": metric}

        results = []
        for result in data["data"]["result"]:
            results.append({
                "labels": result["metric"],
                "value": float(result["value"][1]),
                "timestamp": result["value"][0],
            })

        logger.info("prometheus_queried", metric=metric, results=len(results))
        return {"metric": metric, "results": results, "count": len(results)}

    except httpx.RequestError as e:
        logger.error("prometheus_connection_error", error=str(e))
        return {"error": str(e), "metric": metric}


async def query_prometheus_range(
    metric: str,
    duration: str = "10m",
    step: str = "30s",
) -> dict:
    """
    Query Prometheus range query API.
    Returns time-series data over a time range.
    """
    import time
    end = int(time.time())
    # Convert duration string to seconds
    duration_map = {"5m": 300, "10m": 600, "30m": 1800, "1h": 3600}
    seconds = duration_map.get(duration, 600)
    start = end - seconds

    url = f"{settings.PROMETHEUS_URL}/api/v1/query_range"
    params = {
        "query": metric,
        "start": start,
        "end": end,
        "step": step,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

        if data["status"] != "success":
            return {"error": "query failed", "metric": metric}

        results = []
        for result in data["data"]["result"]:
            results.append({
                "labels": result["metric"],
                "values": [
                    {"timestamp": v[0], "value": float(v[1])}
                    for v in result["values"]
                ],
            })

        logger.info("prometheus_range_queried", metric=metric, duration=duration)
        return {"metric": metric, "duration": duration, "results": results}

    except httpx.RequestError as e:
        logger.error("prometheus_range_error", error=str(e))
        return {"error": str(e), "metric": metric}


async def get_metric_baseline(metric: str) -> dict:
    """
    Get average value of a metric over last 1 hour.
    Used by RCA agent to compare current vs baseline.
    """
    result = await query_prometheus_range(metric, duration="1h", step="1m")
    if "error" in result:
        return result

    all_values = []
    for r in result["results"]:
        for v in r["values"]:
            all_values.append(v["value"])

    if not all_values:
        return {"metric": metric, "baseline": None}

    avg = sum(all_values) / len(all_values)
    maximum = max(all_values)
    minimum = min(all_values)

    return {
        "metric": metric,
        "baseline": avg,
        "max": maximum,
        "min": minimum,
        "samples": len(all_values),
    }