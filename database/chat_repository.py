from config.database import get_connection

def create_chat_session_if_not_exists(session_id, customer_name=None, phone=None):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO chat_sessions (
                    session_id,
                    customer_name,
                    phone
                )
                VALUES (%s, %s, %s)
                ON CONFLICT (session_id) DO UPDATE
                SET
                    customer_name = COALESCE(EXCLUDED.customer_name, chat_sessions.customer_name),
                    phone = COALESCE(EXCLUDED.phone, chat_sessions.phone),
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id
                """,
                (
                    session_id,
                    customer_name,
                    phone,
                ),
            )
            row = cursor.fetchone()
            return row["id"]

def save_chat_message(session_id, role, content):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO chat_messages (
                    session_id,
                    role,
                    content
                )
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (
                    session_id,
                    role,
                    content,
                ),
            )
            row = cursor.fetchone()
            return row["id"]

def list_recent_messages(session_id, limit=6):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    role,
                    content,
                    created_at
                FROM chat_messages
                WHERE session_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (
                    session_id,
                    limit,
                ),
            )
            rows = cursor.fetchall()
            return list(reversed(rows))

def find_chat_session_by_id(session_id):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    session_id,
                    customer_name,
                    phone,
                    status,
                    service_mode,
                    assigned_agent,
                    handoff_version,
                    waiting_since,
                    claimed_at,
                    created_at,
                    updated_at
                FROM chat_sessions
                WHERE session_id = %s
                """,
                (session_id,),
            )
            return cursor.fetchone()

def list_messages_by_session_id(session_id):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    session_id,
                    role,
                    content,
                    sender_name,
                    created_at
                FROM chat_messages
                WHERE session_id = %s
                ORDER BY id ASC
                """,
                (session_id,),
            )
            return cursor.fetchall()
