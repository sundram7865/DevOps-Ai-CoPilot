import asyncio
from app.workers.celery_app import celery_app
from app.core.logging import logger


@celery_app.task(name="run_agent", bind=True, max_retries=3)
def run_agent_task(self, incident_id: str, service: str, alert_payload: dict) -> dict:
    try:
        logger.info("agent_task_started", incident_id=incident_id)
        result = asyncio.run(_run_graph(incident_id, service, alert_payload))
        logger.info("agent_task_complete", incident_id=incident_id)
        return result
    except Exception as e:
        logger.error("agent_task_error", incident_id=incident_id, error=str(e))
        raise self.retry(exc=e, countdown=60)


@celery_app.task(name="resume_agent", bind=True, max_retries=3)
def resume_agent_task(self, incident_id: str, approved_by: str) -> dict:
    try:
        logger.info("resume_task_started", incident_id=incident_id)
        result = asyncio.run(_resume_graph(incident_id, approved_by))
        logger.info("resume_task_complete", incident_id=incident_id)
        return result
    except Exception as e:
        logger.error("resume_task_error", incident_id=incident_id, error=str(e))
        raise self.retry(exc=e, countdown=30)


async def _run_graph(incident_id: str, service: str, alert_payload: dict) -> dict:
    from app.agents.graph import agent_graph
    from prisma import Prisma

    db = Prisma()
    await db.connect()

    try:
        initial_state = {
            "incident_id": incident_id,
            "service": service,
            "alert_payload": alert_payload,
            "monitor_findings": None,
            "root_cause": None,
            "confidence": None,
            "evidence_chain": None,
            "related_services": None,
            "severity": None,
            "requires_approval": None,
            "proposed_actions": None,
            "selected_action": None,
            "approval_status": None,
            "approved_by": None,
            "verification_result": None,
            "rca_report": None,
            "incident_closed": None,
            "current_agent": None,
            "error": None,
            "messages": [],
        }

        config = {"configurable": {"thread_id": incident_id}}
        await agent_graph.ainvoke(initial_state, config=config)
        return {"status": "complete", "incident_id": incident_id}

    finally:
        await db.disconnect()


async def _resume_graph(incident_id: str, approved_by: str) -> dict:
    from app.agents.graph import agent_graph
    from prisma import Prisma

    db = Prisma()
    await db.connect()

    try:
        config = {"configurable": {"thread_id": incident_id}}

        await agent_graph.aupdate_state(
            config,
            {"approval_status": "APPROVED", "approved_by": approved_by},
        )

        await agent_graph.ainvoke(None, config=config)
        return {"status": "resumed", "incident_id": incident_id}

    finally:
        await db.disconnect()