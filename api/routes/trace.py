from fastapi import APIRouter
from api.response import serialize_value
from tools.trace_tool import (
    get_recent_traces,
    get_session_traces,
    get_trace_detail,
)

router = APIRouter(prefix="/traces", tags=["traces"])

def normalize_tool_result(result):
    return {
        "success": result["success"],
        "message": result["message"],
        "data": serialize_value(result["data"]),
    }

@router.get("/recent")
def recent_traces(limit: int = 20):
    return normalize_tool_result(get_recent_traces(limit=limit))

@router.get("/session/{session_id}")
def session_traces(session_id: str, limit: int = 20):
    return normalize_tool_result(
        get_session_traces(
            session_id=session_id,
            limit=limit,
        )
    )

@router.get("/{trace_id}")
def trace_detail(trace_id: int):
    return normalize_tool_result(get_trace_detail(trace_id))
