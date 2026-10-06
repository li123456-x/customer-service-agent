from database.chat_repository import (
    find_chat_session_by_id,
    list_messages_by_session_id,
)

def get_chat_session_detail(session_id):
    session = find_chat_session_by_id(session_id)
    if not session:
        return {
            "success": False,
            "message": f"没有找到会话 {session_id}",
            "data": None,
        }
    messages = list_messages_by_session_id(session_id)
    return {
        "success": True,
        "message": "会话详情查询成功",
        "data": {
            "session": session,
            "messages": messages,
        },
    }