from config.database import get_connection


def migrate_live_support():
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                ALTER TABLE chat_sessions
                    ADD COLUMN IF NOT EXISTS service_mode VARCHAR(30) NOT NULL DEFAULT 'ai',
                    ADD COLUMN IF NOT EXISTS assigned_agent VARCHAR(100),
                    ADD COLUMN IF NOT EXISTS waiting_since TIMESTAMP,
                    ADD COLUMN IF NOT EXISTS claimed_at TIMESTAMP,
                    ADD COLUMN IF NOT EXISTS handoff_version INTEGER NOT NULL DEFAULT 0;
                ALTER TABLE chat_messages
                    ADD COLUMN IF NOT EXISTS sender_name VARCHAR(100),
                    ADD COLUMN IF NOT EXISTS client_message_id UUID;
                CREATE UNIQUE INDEX IF NOT EXISTS chat_messages_client_message_idx
                    ON chat_messages (session_id, client_message_id);
                CREATE INDEX IF NOT EXISTS chat_messages_session_order_idx
                    ON chat_messages (session_id, id);
                CREATE INDEX IF NOT EXISTS chat_sessions_support_queue_idx
                    ON chat_sessions (service_mode, waiting_since);
            """)


if __name__ == "__main__":
    migrate_live_support()
    print("人工接待数据库迁移完成，原有业务数据保留")
