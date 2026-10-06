from uuid import uuid4
from fastapi import APIRouter
from agent.customer_service_agent import customer_service_reply
from api.response import success_response
from api.schemas import ChatRequest

router = APIRouter()

@router.post("/chat")
def chat(request: ChatRequest):
    session_id = request.session_id or f"session-{uuid4()}"
    reply = customer_service_reply(
        message=request.message,
        session_id=session_id,
    )
    return success_response(
        message="回复生成成功",
        data={
            "session_id": session_id,
            "reply": reply,
        },
    )