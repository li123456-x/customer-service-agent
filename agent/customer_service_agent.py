from graph.workflow import customer_service_workflow


def customer_service_reply(message, session_id=None):
    result = customer_service_workflow.invoke(
        {
            "user_message": message,
            "session_id": session_id,
        }
    )
    return result["final_reply"]