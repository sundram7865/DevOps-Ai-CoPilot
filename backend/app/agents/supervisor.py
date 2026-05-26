from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage
from langfuse.callback import CallbackHandler
from app.agents.state import AgentState
from app.core.config import settings
from app.core.logging import logger


def get_llm(trace_name: str):
    langfuse_handler = CallbackHandler(
        secret_key=settings.LANGFUSE_SECRET_KEY,
        public_key=settings.LANGFUSE_PUBLIC_KEY,
        host=settings.LANGFUSE_HOST,
        trace_name=trace_name,
    )
    llm = ChatGroq(
        api_key=settings.GROQ_API_KEY,
        model=settings.GROQ_MODEL,
        temperature=0,
        callbacks=[langfuse_handler],
    )
    return llm, langfuse_handler


async def run(state: AgentState) -> AgentState:
    """
    Supervisor agent — entry point.
    Validates the incoming incident and prepares state for Monitor agent.
    """
    logger.info(
        "supervisor_running",
        incident_id=state["incident_id"],
        service=state["service"],
    )

    llm, _ = get_llm(f"supervisor-{state['incident_id']}")

    messages = [
        SystemMessage(content=(
            "You are the Supervisor of a DevOps AI Copilot system. "
            "Your job is to validate incoming infrastructure alerts and "
            "prepare them for investigation. Be concise and structured."
        )),
        HumanMessage(content=(
            f"New incident received:\n"
            f"Service: {state['service']}\n"
            f"Alert payload: {state['alert_payload']}\n\n"
            f"Confirm this is a valid infrastructure incident worth investigating. "
            f"Reply with: VALID or INVALID and one sentence reason."
        )),
    ]

    response = await llm.ainvoke(messages)

    logger.info("supervisor_decision", decision=response.content[:100])

    return {
        **state,
        "current_agent": "supervisor",
        "messages": state.get("messages", []) + [response],
    }