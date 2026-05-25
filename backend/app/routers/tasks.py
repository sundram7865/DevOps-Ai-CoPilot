from app.workers.celery_app import celery_app


@celery_app.task(name="run_agent")
def run_agent_task(incident_id: str) -> dict:
    # Phase 4: LangGraph agent triggered here
    return {"status": "queued", "incident_id": incident_id}