from fastapi import APIRouter
from api.response import serialize_value
from tools.chat_tool import get_chat_session_detail

router = APIRouter(prefix="/sessions", tags=["sessions"])

def normalize_tool_result(result):
    return {
        "success": result["success"],
        "message": result["message"],
        "data": serialize_value(result["data"]),
    }

@router.get("/{session_id}")
def session_detail(session_id: str):
    return normalize_tool_result(get_chat_session_detail(session_id))