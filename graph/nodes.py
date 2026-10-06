import re
from uuid import uuid4
from config.model import get_model
from database.chat_repository import (
    create_chat_session_if_not_exists,
    list_recent_messages,
    save_chat_message,
)
from database.human_review_repository import create_human_review
from database.trace_repository import find_latest_order_no_by_session_id, save_agent_trace
from tools.logistics_tool import search_logistics
from tools.order_tool import search_order
from tools.refund_tool import search_refund
from tools.knowledge_tool import search_policy_knowledge

def add_trace_step(state, step):
    trace_steps = state.get("trace_steps", [])
    return trace_steps + [step]

def extract_order_no(text):
    match = re.search(r"DD\d+", text, re.IGNORECASE)
    if match:
        return match.group().upper()
    return None

def extract_order_no_from_history(history_messages):
    for message in reversed(history_messages):
        order_no = extract_order_no(message["content"])
        if order_no:
            return order_no
    return None

def recognize_intent(message):
    if any(keyword in message for keyword in ["发票", "开票", "抬头", "税号"]):
        return "knowledge_query", 0.85
    if any(keyword in message for keyword in ["政策", "规则", "流程", "条件", "多久到账", "怎么申请"]):
        return "knowledge_query", 0.8
    if any(keyword in message for keyword in ["退款", "退钱", "退货", "换货", "售后", "坏了", "没声音", "质量问题"]):
        return "after_sale_refund", 0.9
    if any(keyword in message for keyword in ["物流", "快递", "到哪", "送到", "签收", "运单"]):
        return "logistics_query", 0.9
    if any(keyword in message for keyword in ["订单", "商品", "买了", "下单", "支付", "多少钱", "金额"]):
        return "order_query", 0.85
    return "unknown", 0.4

def start_node(state):
    session_id = state.get("session_id") or f"session-{uuid4()}"
    user_message = state["user_message"]
    create_chat_session_if_not_exists(session_id)
    save_chat_message(session_id, "user", user_message)
    history_messages = list_recent_messages(session_id)
    return {
        **state,
        "session_id": session_id,
        "history_messages": history_messages,
        "tools_called": [],
        "trace_steps": add_trace_step(
            state,
            {
                "node": "start",
                "session_id": session_id,
                "message_saved": True,
            },
        ),
    }

def parse_message_node(state):
    user_message = state["user_message"]
    history_messages = state["history_messages"]
    order_no = extract_order_no(user_message)
    if not order_no and any(keyword in user_message for keyword in ["这个订单", "这个", "它", "刚才", "上面", "多少钱", "退款", "物流", "售后"]):
        order_no = extract_order_no_from_history(history_messages)
    if not order_no:
        order_no = find_latest_order_no_by_session_id(state["session_id"])
    intent, confidence = recognize_intent(user_message)
    return {
        **state,
        "order_no": order_no,
        "intent": intent,
        "confidence": confidence,
        "trace_steps": add_trace_step(
            state,
            {
                "node": "parse_message",
                "order_no": order_no,
                "intent": intent,
                "confidence": confidence,
            },
        ),
    }

def ask_order_no_node(state):
    final_reply = "我还不知道您想查询哪个订单，请提供订单号，例如：DD10001。"
    return {
        **state,
        "final_reply": final_reply,
        "final_action": "ask_order_no",
        "trace_steps": add_trace_step(
            state,
            {
                "node": "ask_order_no",
                "final_action": "ask_order_no",
            },
        ),
    }

def knowledge_only_context_node(state):
    return {
        **state,
        "order_result": {
            "success": False,
            "message": "当前问题未提供订单号，未查询订单",
            "data": None,
        },
        "logistics_result": {
            "success": False,
            "message": "当前问题未提供订单号，未查询物流",
            "data": None,
        },
        "refund_result": {
            "success": False,
            "message": "当前问题未提供订单号，未查询退款/售后记录",
            "data": None,
        },
        "context": {
            "order": {
                "success": False,
                "message": "当前问题未提供订单号，未查询订单",
                "data": None,
            },
            "logistics": {
                "success": False,
                "message": "当前问题未提供订单号，未查询物流",
                "data": None,
            },
            "refund": {
                "success": False,
                "message": "当前问题未提供订单号，未查询退款/售后记录",
                "data": None,
            },
            "knowledge": state.get("knowledge_result"),
        },
        "trace_steps": add_trace_step(
            state,
            {
                "node": "knowledge_only_context",
                "reason": "纯知识库问题，无需订单号",
            },
        ),
    }

def query_order_node(state):
    order_no = state["order_no"]
    tools_called = state.get("tools_called", [])
    order_result = search_order(order_no)
    return {
        **state,
        "order_result": order_result,
        "tools_called": tools_called + ["order_tool"],
        "trace_steps": add_trace_step(
            state,
            {
                "node": "query_order",
                "tool": "order_tool",
                "success": order_result["success"],
                "message": order_result["message"],
            },
        ),
    }

def query_logistics_node(state):
    order_no = state["order_no"]
    tools_called = state.get("tools_called", [])
    logistics_result = search_logistics(order_no)
    return {
        **state,
        "logistics_result": logistics_result,
        "tools_called": tools_called + ["logistics_tool"],
        "trace_steps": add_trace_step(
            state,
            {
                "node": "query_logistics",
                "tool": "logistics_tool",
                "success": logistics_result["success"],
                "message": logistics_result["message"],
            },
        ),
    }

def query_refund_node(state):
    order_no = state["order_no"]
    tools_called = state.get("tools_called", [])
    refund_result = search_refund(order_no)
    return {
        **state,
        "refund_result": refund_result,
        "tools_called": tools_called + ["refund_tool"],
        "trace_steps": add_trace_step(
            state,
            {
                "node": "query_refund",
                "tool": "refund_tool",
                "success": refund_result["success"],
                "message": refund_result["message"],
            },
        ),
    }

def query_knowledge_node(state):
    user_message = state["user_message"]
    tools_called = state.get("tools_called", [])
    knowledge_result = search_policy_knowledge(user_message)
    sources = []
    if knowledge_result["success"]:
        sources = [
            item.get("source")
            for item in knowledge_result["data"]
            if item.get("source")
        ]
    return {
        **state,
        "knowledge_result": knowledge_result,
        "tools_called": tools_called + ["knowledge_tool"],
        "trace_steps": add_trace_step(
            state,
            {
                "node": "query_knowledge",
                "tool": "knowledge_tool",
                "success": knowledge_result["success"],
                "message": knowledge_result["message"],
                "sources": sources,
            },
        ),
    }

def build_context_node(state):
    return {
        **state,
        "context": {
            "order": state.get("order_result"),
            "logistics": state.get("logistics_result"),
            "refund": state.get("refund_result"),
            "knowledge": state.get("knowledge_result"),
        },
        "trace_steps": add_trace_step(
            state,
            {
                "node": "build_context",
                "has_order": bool(state.get("order_result", {}).get("success")),
                "has_logistics": bool(state.get("logistics_result", {}).get("success")),
                "has_refund": bool(state.get("refund_result", {}).get("success")),
                "has_knowledge": bool(state.get("knowledge_result", {}).get("success")),
            },
        ),
    }


def human_review_check_node(state):
    intent = state["intent"]
    confidence = state["confidence"]
    refund_result = state.get("refund_result", {"success": False, "data": None})
    message = state["user_message"]
    if intent in ["logistics_query", "order_query", "knowledge_query"]:
        return {
            **state,
            "need_human_review": False,
            "review_reason": None,
            "trace_steps": add_trace_step(
                state,
                {
                    "node": "human_review_check",
                    "need_human_review": False,
                    "review_reason": "普通查询类问题，自动回复",
                },
            ),
        }
    if intent == "unknown" and confidence < 0.6:
        return {
            **state,
            "need_human_review": True,
            "review_reason": "用户意图置信度较低，需要人工确认",
            "trace_steps": add_trace_step(
                state,
                {
                    "node": "human_review_check",
                    "need_human_review": True,
                    "review_reason": "用户意图置信度较低，需要人工确认",
                },
            ),
        }
    if intent == "after_sale_refund":
        refund_data = refund_result["data"] if refund_result.get("success") else None

        if refund_data and refund_data["requires_human_review"]:
            return {
                **state,
                "need_human_review": True,
                "review_reason": "退款/售后记录标记为需要人工审核",
                "trace_steps": add_trace_step(
                    state,
                    {
                        "node": "human_review_check",
                        "need_human_review": True,
                        "review_reason": "退款/售后记录标记为需要人工审核",
                    },
                ),
            }
        if any(keyword in message for keyword in ["坏了", "没声音", "质量问题", "投诉", "赔偿"]):
            return {
                **state,
                "need_human_review": True,
                "review_reason": "用户问题涉及质量争议或投诉，需要人工审核",
                "trace_steps": add_trace_step(
                    state,
                    {
                        "node": "human_review_check",
                        "need_human_review": True,
                        "review_reason": "用户问题涉及质量争议或投诉，需要人工审核",
                    },
                ),
            }
    return {
        **state,
        "need_human_review": False,
        "review_reason": None,
        "trace_steps": add_trace_step(
            state,
            {
                "node": "human_review_check",
                "need_human_review": False,
                "review_reason": "未命中人工审核条件",
            },
        ),
    }

def create_human_review_node(state):
    review = create_human_review(
        session_id=state["session_id"],
        order_no=state["order_no"],
        user_message=state["user_message"],
        agent_summary=str(state.get("context")),
        review_reason=state["review_reason"],
    )
    final_reply = (
        "您的问题已为您转入人工审核，"
        f"审核单号：{review['review_no']}。"
        "客服专员会根据订单和售后信息进一步处理。"
    )
    return {
        **state,
        "final_reply": final_reply,
        "final_action": "human_review",
        "trace_steps": add_trace_step(
            state,
            {
                "node": "create_human_review",
                "review_no": review["review_no"],
                "review_status": review["review_status"],
            },
        ),
    }

def build_fallback_reply(state):
    order_result = state["order_result"]
    logistics_result = state.get("logistics_result", {"success": False, "data": None})
    refund_result = state.get("refund_result", {"success": False, "data": None})
    intent = state["intent"]
    if not order_result["success"]:
        return order_result["message"]
    order = order_result["data"]
    logistics = logistics_result["data"] if logistics_result.get("success") else None
    refund = refund_result["data"] if refund_result.get("success") else None
    if intent == "logistics_query" and logistics:
        return (
            f"您的订单 {order['order_no']} 当前物流状态为：{logistics['logistics_status']}，"
            f"当前位置：{logistics['latest_location']}，"
            f"预计送达时间：{logistics['estimated_delivery_time']}。"
        )
    if intent == "after_sale_refund" and refund:
        review_text = "需要人工审核" if refund["requires_human_review"] else "暂不需要人工审核"
        return (
            f"您的订单 {order['order_no']} 当前退款/售后状态为：{refund['refund_status']}，"
            f"退款类型：{refund['refund_type']}，{review_text}。"
        )
    return (
        f"查询到您的订单 {order['order_no']}："
        f"商品为 {order['product_name']}，"
        f"订单状态为 {order['order_status']}，"
        f"支付金额 {order['paid_amount']} 元。"
    )

def generate_reply_node(state):
    order_result = state.get("order_result", {"success": False})
    knowledge_result = state.get("knowledge_result", {"success": False})
    if state.get("intent") == "knowledge_query" and knowledge_result.get("success"):
        pass
    elif not order_result["success"]:
        return {
            **state,
            "final_reply": order_result["message"],
            "final_action": "order_not_found",
        }
    model = get_model()

    system_prompt = """
你是一个企业级电商智能客服 Agent，名字叫“小想”。
你需要根据后端工具返回的数据、企业知识库检索结果和历史对话回复用户。
要求：
1. 回复礼貌、自然、简洁。
2. 只能基于工具返回的数据回答，不要编造订单、物流、退款、售后信息。
3. 如果用户问物流，重点说明物流状态、当前位置、预计送达时间。
4. 如果用户问退款或售后，重点说明退款/售后状态，以及是否需要人工审核。
5. 如果工具没有查到数据，要明确说明未查询到。
6. 历史对话只用于理解上下文，不能替代后端工具数据。
7. 如果知识库中有相关政策，回复时要结合政策说明处理依据。
""".strip()
    user_prompt = f"""
历史对话：{state.get("history_messages")}
用户问题：{state["user_message"]}
识别到的意图：{state["intent"]}
工具查询结果：{state.get("context")}
请生成最终客服回复。
""".strip()
    try:
        response = model.invoke(
            [
                ("system", system_prompt),
                ("human", user_prompt),
            ]
        )
        final_reply = response.content
        final_action = "auto_reply"
    except Exception as error:
        print(f"AI 调用失败：{error}")
        final_reply = build_fallback_reply(state)
        final_action = "fallback_reply"
    return {
        **state,
        "final_reply": final_reply,
        "final_action": final_action,
        "trace_steps": add_trace_step(
            state,
            {
                "node": "generate_reply",
                "final_action": final_action,
            },
        ),
    }

def finish_node(state):
    save_agent_trace(
        session_id=state["session_id"],
        user_message=state["user_message"],
        intent=state.get("intent"),
        order_no=state.get("order_no"),
        tools_called=",".join(state.get("tools_called", [])),
        confidence=state.get("confidence", 0),
        final_action=state.get("final_action"),
        final_reply=state.get("final_reply"),
        trace_steps=state.get("trace_steps", []),
    )
    save_chat_message(state["session_id"], "assistant", state["final_reply"])
    return state
