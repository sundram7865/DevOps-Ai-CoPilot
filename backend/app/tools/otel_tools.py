import httpx
import time
from app.core.logging import logger


async def query_otel_traces(
    service: str,
    duration: str = "1h",
) -> dict:
    """
    Query OTEL collector for traces from a service.
    NOTE: OTEL collector in this setup exports to debug/console.
    This queries Tempo if available, otherwise returns empty.
    For MVP we use this as a stub — traces visible in collector logs.
    """
    logger.info("otel_traces_queried", service=service, duration=duration)

    # In MVP setup, OTEL collector logs traces to console (debug exporter)
    # Full Tempo integration is a future enhancement
    # For now return structured stub so agents can handle it gracefully
    return {
        "service": service,
        "duration": duration,
        "traces": [],
        "note": "OTEL traces available in collector logs. Tempo integration pending.",
    }


async def get_request_latency(service: str) -> dict:
    """
    Get P50, P95, P99 latency for a service from Prometheus
    (populated by OTEL instrumentation via prom-client).
    """
    from app.tools.prometheus_tools import query_prometheus

    p99 = await query_prometheus(
        f'histogram_quantile(0.99, rate(http_request_duration_seconds_bucket{{job="{service}"}}[5m]))'
    )
    p95 = await query_prometheus(
        f'histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{{job="{service}"}}[5m]))'
    )
    p50 = await query_prometheus(
        f'histogram_quantile(0.50, rate(http_request_duration_seconds_bucket{{job="{service}"}}[5m]))'
    )

    def extract_value(result: dict) -> float:
        if "error" in result or not result["results"]:
            return 0.0
        return result["results"][0]["value"]

    return {
        "service": service,
        "p50_seconds": extract_value(p50),
        "p95_seconds": extract_value(p95),
        "p99_seconds": extract_value(p99),
    }