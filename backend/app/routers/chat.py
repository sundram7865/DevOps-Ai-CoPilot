from fastapi import APIRouter
from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest):
    # Phase 4: wire LangGraph agent here
    return ChatResponse(
        answer=f"Agent not yet connected. You asked: {body.message}",
        sources=[],
    )