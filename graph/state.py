from typing import Any, TypedDict


class CustomerServiceState(TypedDict, total=False):
    session_id: str
    user_message: str
    history_messages: list[dict[str, Any]]
    order_no: str | None
    intent: str
    confidence: float
    order_result: dict[str, Any]
    logistics_result: dict[str, Any]
    refund_result: dict[str, Any]
    knowledge_result: dict[str, Any]
    tools_called: list[str]
    context: dict[str, Any]
    trace_steps: list[dict[str, Any]]
    need_human_review: bool
    review_reason: str | None
    final_action: str
    final_reply: str