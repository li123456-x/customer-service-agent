from uuid import uuid4
from config.database import get_connection

def create_human_review(
    session_id,
    order_no,
    user_message,
    agent_summary,
    review_reason,
):
    review_no = f"HR{uuid4().hex[:12].upper()}"
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO human_reviews (
                    review_no,
                    session_id,
                    order_no,
                    user_message,
                    agent_summary,
                    review_reason,
                    review_status
                )
                VALUES (%s, %s, %s, %s, %s, %s, 'pending')
                RETURNING
                    id,
                    review_no,
                    review_status
                """,
                (
                    review_no,
                    session_id,
                    order_no,
                    user_message,
                    agent_summary,
                    review_reason,
                ),
            )
            return cursor.fetchone()

def list_pending_human_reviews(limit=20):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    review_no,
                    session_id,
                    order_no,
                    user_message,
                    agent_summary,
                    review_reason,
                    review_status,
                    reviewer_name,
                    reviewer_reply,
                    created_at,
                    updated_at
                FROM human_reviews
                WHERE review_status = 'pending'
                ORDER BY created_at ASC
                LIMIT %s
                """,
                (limit,),
            )
            return cursor.fetchall()

def find_human_review_by_no(review_no):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    review_no,
                    session_id,
                    order_no,
                    user_message,
                    agent_summary,
                    review_reason,
                    review_status,
                    reviewer_name,
                    reviewer_reply,
                    created_at,
                    updated_at
                FROM human_reviews
                WHERE review_no = %s
                """,
                (review_no,),
            )
            return cursor.fetchone()

def complete_human_review(review_no, reviewer_name, reviewer_reply):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE human_reviews
                SET
                    review_status = 'completed',
                    reviewer_name = %s,
                    reviewer_reply = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE review_no = %s
                RETURNING
                    id,
                    review_no,
                    review_status,
                    reviewer_name,
                    reviewer_reply
                """,
                (
                    reviewer_name,
                    reviewer_reply,
                    review_no,
                ),
            )
            return cursor.fetchone()

def reject_human_review(review_no, reviewer_name, reviewer_reply):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE human_reviews
                SET
                    review_status = 'rejected',
                    reviewer_name = %s,
                    reviewer_reply = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE review_no = %s
                RETURNING
                    id,
                    review_no,
                    review_status,
                    reviewer_name,
                    reviewer_reply
                """,
                (
                    reviewer_name,
                    reviewer_reply,
                    review_no,
                ),
            )
            return cursor.fetchone()