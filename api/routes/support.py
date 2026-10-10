from fastapi import APIRouter, HTTPException, Query

from api.response import success_response
from api.schemas import HandoffRequest, SupportActionRequest, SupportClaimRequest, SupportMessageRequest
from database.live_support_repository import (
    SupportConflict, claim_session, list_support_sessions, release_session,
    reply_to_session, session_guard,
)
from tools.live_support_tool import request_live_support

router = APIRouter(prefix="/handoffs", tags=["live-support"])


def support_action(session_id, action):
    try:
        with session_guard(session_id):
            return success_response(data=action())
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except SupportConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("")
def support_queue(limit: int = Query(default=100, ge=1, le=200)):
    return success_response(data=list_support_sessions(limit))


@router.post("/request")
def request_support(request: HandoffRequest):
    return success_response(data=request_live_support(request.session_id))


@router.post("/{session_id}/claim")
def claim_support(session_id: str, request: SupportClaimRequest):
    return support_action(session_id, lambda: claim_session(session_id, request.agent_name))


@router.post("/{session_id}/messages")
def send_support_message(session_id: str, request: SupportMessageRequest):
    return support_action(session_id, lambda: reply_to_session(
        session_id, request.agent_name, request.handoff_version,
        request.message, request.request_id,
    ))


@router.post("/{session_id}/release")
def release_support(session_id: str, request: SupportActionRequest):
    return support_action(session_id, lambda: release_session(
        session_id, request.agent_name, request.handoff_version,
    ))
