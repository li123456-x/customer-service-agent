from database.trace_repository import (
    find_agent_trace_by_id,
    list_agent_traces_by_session_id,
    list_recent_agent_traces,
)

def get_recent_traces(limit=20):
    traces = list_recent_agent_traces(limit)
    return {
        "success": True,
        "message": "Agent执行轨迹列表查询成功",
        "data": traces,
    }

def get_trace_detail(trace_id):
    trace = find_agent_trace_by_id(trace_id)
    if not trace:
        return {
            "success": False,
            "message": f"没有找到执行轨迹 {trace_id}",
            "data": None,
        }
    return {
        "success": True,
        "message": "Agent执行轨迹详情查询成功",
        "data": trace,
    }

def get_session_traces(session_id, limit=20):
    traces = list_agent_traces_by_session_id(session_id, limit)
    return {
        "success": True,
        "message": "会话执行轨迹查询成功",
        "data": traces,
    }