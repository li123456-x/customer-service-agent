import json
from config.database import get_connection

def save_agent_trace(
    session_id,
    user_message,
    intent,
    order_no,
    tools_called,
    confidence,
    final_action,
    final_reply,
    trace_steps=None,
):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO agent_traces (
                    session_id,
                    user_message,
                    intent,
                    order_no,
                    tools_called,
                    confidence,
                    final_action,
                    final_reply,
                    trace_steps
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                RETURNING id
                """,
                (
                    session_id,
                    user_message,
                    intent,
                    order_no,
                    tools_called,
                    confidence,
                    final_action,
                    final_reply,
                    json.dumps(trace_steps or [], ensure_ascii=False),
                ),
            )
            row = cursor.fetchone()
            return row["id"]
def list_recent_agent_traces(limit=20):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    session_id,
                    user_message,
                    intent,
                    order_no,
                    tools_called,
                    confidence,
                    final_action,
                    final_reply,
                    trace_steps,
                    created_at
                FROM agent_traces
                ORDER BY id DESC
                LIMIT %s
                """,
                (limit,),
            )
            return cursor.fetchall()

def find_agent_trace_by_id(trace_id):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    session_id,
                    user_message,
                    intent,
                    order_no,
                    tools_called,
                    confidence,
                    final_action,
                    final_reply,
                    trace_steps,
                    created_at
                FROM agent_traces
                WHERE id = %s
                """,
                (trace_id,),
            )
            return cursor.fetchone()

def list_agent_traces_by_session_id(session_id, limit=20):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    session_id,
                    user_message,
                    intent,
                    order_no,
                    tools_called,
                    confidence,
                    final_action,
                    final_reply,
                    trace_steps,
                    created_at
                FROM agent_traces
                WHERE session_id = %s
                ORDER BY id DESC
                LIMIT %s
                """,
                (
                    session_id,
                    limit,
                ),
            )
            return cursor.fetchall()

def find_latest_order_no_by_session_id(session_id):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT order_no
                FROM agent_traces
                WHERE session_id = %s
                  AND order_no IS NOT NULL
                ORDER BY id DESC
                LIMIT 1
                """,
                (session_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return row["order_no"]
