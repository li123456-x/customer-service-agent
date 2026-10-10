from uuid import uuid4
from fastapi import APIRouter
from agent.customer_service_agent import customer_service_response
from api.response import success_response
from api.schemas import ChatRequest

router = APIRouter()

@router.post("/chat")
def chat(request: ChatRequest):
    session_id = request.session_id or f"session-{uuid4()}"
    response = customer_service_response(
        message=request.message,
        session_id=session_id,
    )
    return success_response(
        message="消息处理成功",
        data=response,
    )
