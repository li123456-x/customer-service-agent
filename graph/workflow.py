from langgraph.graph import END, StateGraph
from graph.nodes import (
    ask_order_no_node,
    build_context_node,
    create_human_review_node,
    finish_node,
    generate_reply_node,
    human_review_check_node,
    knowledge_only_context_node,
    parse_message_node,
    query_knowledge_node,
    query_logistics_node,
    query_order_node,
    query_refund_node,
    start_node,
    smalltalk_reply_node,
)
from graph.state import CustomerServiceState

def route_after_parse(state):
    if state.get("intent") == "smalltalk":
        return "smalltalk_reply"
    if not state.get("order_no") and state.get("intent") == "knowledge_query":
        return "query_knowledge"
    if not state.get("order_no"):
        return "ask_order_no"
    return "query_order"

def route_after_human_review_check(state):
    if state.get("need_human_review"):
        return "create_human_review"
    return "generate_reply"

def build_customer_service_workflow():
    workflow = StateGraph(CustomerServiceState)
    workflow.add_node("start", start_node)
    workflow.add_node("parse_message", parse_message_node)
    workflow.add_node("smalltalk_reply", smalltalk_reply_node)
    workflow.add_node("ask_order_no", ask_order_no_node)
    workflow.add_node("query_order", query_order_node)
    workflow.add_node("query_logistics", query_logistics_node)
    workflow.add_node("query_refund", query_refund_node)
    workflow.add_node("query_knowledge", query_knowledge_node)
    workflow.add_node("knowledge_only_context", knowledge_only_context_node)
    workflow.add_node("build_context", build_context_node)
    workflow.add_node("human_review_check", human_review_check_node)
    workflow.add_node("create_human_review", create_human_review_node)
    workflow.add_node("generate_reply", generate_reply_node)
    workflow.add_node("finish", finish_node)
    workflow.set_entry_point("start")
    workflow.add_edge("start", "parse_message")
    workflow.add_conditional_edges(
        "parse_message",
        route_after_parse,
        {
            "smalltalk_reply": "smalltalk_reply",
            "ask_order_no": "ask_order_no",
            "query_order": "query_order",
            "query_knowledge": "query_knowledge",
        },
    )
    workflow.add_edge("ask_order_no", "finish")
    workflow.add_edge("smalltalk_reply", "finish")
    workflow.add_edge("query_order", "query_logistics")
    workflow.add_edge("query_logistics", "query_refund")
    workflow.add_edge("query_refund", "query_knowledge")
    workflow.add_conditional_edges(
        "query_knowledge",
        lambda state: "knowledge_only_context" if not state.get("order_no") else "build_context",
        {
            "knowledge_only_context": "knowledge_only_context",
            "build_context": "build_context",
        },
    )
    workflow.add_edge("knowledge_only_context", "generate_reply")
    workflow.add_edge("build_context", "human_review_check")
    workflow.add_conditional_edges(
        "human_review_check",
        route_after_human_review_check,
        {
            "create_human_review": "create_human_review",
            "generate_reply": "generate_reply",
        },
    )
    workflow.add_edge("create_human_review", "finish")
    workflow.add_edge("generate_reply", "finish")
    workflow.add_edge("finish", END)

    return workflow.compile()
customer_service_workflow = build_customer_service_workflow()
