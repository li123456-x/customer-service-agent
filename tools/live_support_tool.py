import re
from uuid import uuid4

from database.chat_repository import (
    create_chat_session_if_not_exists,
    find_chat_session_by_id,
    save_chat_message,
)
from database.live_support_repository import request_handoff, session_guard


def is_handoff_request(message):
    if any(word in message for word in ("不转人工", "不要人工", "不用人工")):
        return False
    return bool(re.search(r"转人工|人工客服|真人客服|联系人工|人工服务", message))


def request_live_support(session_id=None):
    session_id = session_id or f"session-{uuid4()}"
    with session_guard(session_id):
        create_chat_session_if_not_exists(session_id)
        return request_handoff(session_id)


def dispatch_customer_message(message, session_id, ai_reply):
    session_id = session_id or f"session-{uuid4()}"
    with session_guard(session_id):
        create_chat_session_if_not_exists(session_id)
        session = find_chat_session_by_id(session_id)
        if session["service_mode"] in ("waiting_human", "human"):
            save_chat_message(session_id, "user", message)
            return {"session_id": session_id, "reply": None,
                    "delivery": session["service_mode"], "session": session}
        if is_handoff_request(message):
            save_chat_message(session_id, "user", message)
            session = request_handoff(session_id)
            return {"session_id": session_id, "reply": None,
                    "delivery": "waiting_human", "session": session}
        reply = ai_reply(message, session_id)
        session = find_chat_session_by_id(session_id)
        return {"session_id": session_id, "reply": reply,
                "delivery": session["service_mode"], "session": session}
