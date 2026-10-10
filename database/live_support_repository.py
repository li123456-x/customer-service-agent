from contextlib import contextmanager

from config.database import get_connection


class SupportConflict(ValueError):
    pass


@contextmanager
def session_guard(session_id):
    # The same PostgreSQL lock serializes AI turns and handoff actions across workers.
    with get_connection() as conn:
        conn.autocommit = True
        with conn.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_lock(hashtextextended(%s, 0))", (session_id,))
            try:
                yield
            finally:
                cursor.execute("SELECT pg_advisory_unlock(hashtextextended(%s, 0))", (session_id,))


def _message(cursor, session_id, role, content, sender_name=None, request_id=None):
    cursor.execute("""
        INSERT INTO chat_messages (session_id, role, content, sender_name, client_message_id)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (session_id, client_message_id) DO NOTHING
        RETURNING *
    """, (session_id, role, content, sender_name, request_id))
    message = cursor.fetchone()
    if message is None:
        cursor.execute("""
            SELECT * FROM chat_messages WHERE session_id = %s AND client_message_id = %s
        """, (session_id, request_id))
        message = cursor.fetchone()
        if message["content"] != content or message["sender_name"] != sender_name:
            raise SupportConflict("同一消息标识不能用于不同内容")
    return message


def request_handoff(session_id, announce=True):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM chat_sessions WHERE session_id = %s FOR UPDATE", (session_id,))
            session = cursor.fetchone()
            if not session:
                raise LookupError("会话不存在")
            if session["service_mode"] in ("waiting_human", "human"):
                return session
            cursor.execute("""
                UPDATE chat_sessions SET service_mode = 'waiting_human', assigned_agent = NULL,
                    waiting_since = CURRENT_TIMESTAMP, claimed_at = NULL,
                    handoff_version = handoff_version + 1, updated_at = CURRENT_TIMESTAMP
                WHERE session_id = %s RETURNING *
            """, (session_id,))
            session = cursor.fetchone()
            if announce:
                _message(cursor, session_id, "system", "已进入人工接待队列，正在等待客服接入。您可以继续补充问题。")
            return session


def list_support_sessions(limit=100):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT s.*, m.content AS last_message FROM chat_sessions s
                LEFT JOIN LATERAL (
                    SELECT content FROM chat_messages WHERE session_id = s.session_id
                    ORDER BY id DESC LIMIT 1
                ) m ON TRUE
                WHERE s.service_mode IN ('waiting_human', 'human')
                ORDER BY s.waiting_since ASC, s.id ASC LIMIT %s
            """, (limit,))
            return cursor.fetchall()


def claim_session(session_id, agent_name):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM chat_sessions WHERE session_id = %s FOR UPDATE", (session_id,))
            session = cursor.fetchone()
            if not session:
                raise LookupError("会话不存在")
            if session["service_mode"] == "human" and session["assigned_agent"] == agent_name:
                return session
            if session["service_mode"] != "waiting_human":
                raise SupportConflict("会话已被其他客服接待，或已退出等待队列")
            cursor.execute("""
                UPDATE chat_sessions SET service_mode = 'human', assigned_agent = %s,
                    claimed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE session_id = %s RETURNING *
            """, (agent_name, session_id))
            session = cursor.fetchone()
            _message(cursor, session_id, "system", f"人工客服 {agent_name} 已接入。")
            return session


def check_owner(session, agent_name, handoff_version):
    if not session:
        raise LookupError("会话不存在")
    if (session["service_mode"] != "human" or session["assigned_agent"] != agent_name
            or session["handoff_version"] != handoff_version):
        raise SupportConflict("您不是当前接待客服，或本轮人工接待已经结束，请刷新会话")


def reply_to_session(session_id, agent_name, handoff_version, content, request_id):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM chat_sessions WHERE session_id = %s FOR UPDATE", (session_id,))
            check_owner(cursor.fetchone(), agent_name, handoff_version)
            message = _message(cursor, session_id, "human", content, agent_name, request_id)
            cursor.execute("UPDATE chat_sessions SET updated_at = CURRENT_TIMESTAMP WHERE session_id = %s", (session_id,))
            return message


def release_session(session_id, agent_name, handoff_version):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM chat_sessions WHERE session_id = %s FOR UPDATE", (session_id,))
            check_owner(cursor.fetchone(), agent_name, handoff_version)
            cursor.execute("""
                UPDATE chat_sessions SET service_mode = 'ai', assigned_agent = NULL,
                    waiting_since = NULL, claimed_at = NULL, updated_at = CURRENT_TIMESTAMP
                WHERE session_id = %s RETURNING *
            """, (session_id,))
            session = cursor.fetchone()
            _message(cursor, session_id, "system", f"人工客服 {agent_name} 已结束接待，后续问题由 AI 客服处理。")
            return session
