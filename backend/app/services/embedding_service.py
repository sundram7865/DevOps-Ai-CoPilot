from app.core.database import db
from app.core.logging import logger


async def search_incident_history(query: str, limit: int = 5) -> list:
    """
    Search for similar past incidents using pgvector.
    Phase 4 will add real embedding generation.
    For now returns recent incidents as fallback.
    """
    try:
        # Phase 4: replace with real pgvector similarity search
        # For now return most recent resolved incidents
        incidents = await db.incident.find_many(
            where={"status": "RESOLVED"},
            take=limit,
            order={"detectedAt": "desc"},
        )

        results = []
        for inc in incidents:
            results.append({
                "id": inc.id,
                "title": inc.title,
                "service": inc.service,
                "root_cause": inc.rootCause,
                "resolved_at": str(inc.resolvedAt) if inc.resolvedAt else None,
            })

        logger.info("incident_history_searched", query=query, results=len(results))
        return results

    except Exception as e:
        logger.error("incident_history_search_error", error=str(e))
        return []