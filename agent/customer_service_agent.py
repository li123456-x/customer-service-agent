from graph.workflow import customer_service_workflow
from tools.live_support_tool import dispatch_customer_message


def _generate_ai_reply(message, session_id):
    result = customer_service_workflow.invoke(
        {
            "user_message": message,
            "session_id": session_id,
        }
    )
    return result["final_reply"]


def customer_service_response(message, session_id=None):
    return dispatch_customer_message(message, session_id, _generate_ai_reply)


def customer_service_reply(message, session_id=None):
    response = customer_service_response(message, session_id)
    return response["reply"] or "消息已发送给人工客服，请等待回复。"
